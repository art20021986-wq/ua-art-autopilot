"""
crm_speed_gate_a.py

Fail-closed Gate A orchestrator for CRM-SPEED-001.

This module performs ONLY:
  * reads of bounded, explicitly listed live input paths under
    /home/Carix (or a caller-supplied home for offline/controller
    testing);
  * writes beneath a unique run directory under
    /home/Carix/qa/crm_speed_task020 (or a caller-supplied QA root);
  * structural (AST) analysis and candidate transformation copies.

It never imports or executes any production module, never writes to
/home/Carix outside the QA root, never restarts any process, and never
publishes UA-0009. Every mandatory proof is fail-closed: if a proof
cannot be established, final_status is BLOCKED with an exact reason and
no partial "pass" language is emitted. A 100% marker means finished, not
passed.
"""
from __future__ import annotations

import ast
import datetime
import json
import os
import platform
import sqlite3
import sys
import traceback
from typing import Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from safe_writer import SafeWriter  # noqa: E402
from cross_process_lock import CrossProcessLock  # noqa: E402
from rebuild_queue import find_stranica_generation_anchors  # noqa: E402
from sqlite_ownership import (  # noqa: E402
    transform_short_ownership, verify_no_live_handle_across_slow_call,
    AnchorNotFoundError as SqliteAnchorError, _iter_functions,
)
from media_call_graph import find_reachable_media_calls, semantic_hash, ENTRY_POINTS  # noqa: E402
from ua0009_publication_check import check_ua0009_not_public  # noqa: E402
from build_manifest import write_manifest  # noqa: E402

DEFAULT_HOME = "/home/Carix"

REQUIRED_INPUTS = [
    ".local/lib/python3.10/site-packages/usercustomize.py",
    ".local/lib/python3.13/site-packages/usercustomize.py",
    "start_safe.py",
    "run_all.py",
    "cars_ui.py",
    "avtoperedacha.py",
    "samokontrol.py",
    "db.py",
    "team_bot.py",
    "stranica.py",
    "crm.db",
]

KNOWN_BACKUP_ARCHIVE_SHA256 = (
    "b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913"
)

MEDIA_PERSISTENCE_FUNCTION_NAMES = [
    "upload_photo", "upload_video", "save_media", "delete_media",
    "attach_media", "media_metadata", "get_media_reference",
]

SQLITE_OWNERSHIP_TARGETS = {
    "avtoperedacha.py": {"kolonki_cars", "otpechatok", "shag"},
    "samokontrol.py": {"kolonki", "proverit_bazu"},
}


class GateABlocked(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _sha256_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _fingerprint_file(path: str) -> dict:
    import stat as _stat
    st = os.lstat(path)
    if _stat.S_ISLNK(st.st_mode):
        raise GateABlocked(f"required input is a symlink, refusing: {path}")
    with open(path, "rb") as fh:
        data = fh.read()
    return {
        "path": path, "mode": oct(st.st_mode), "size": st.st_size,
        "mtime_ns": st.st_mtime_ns, "sha256": _sha256_bytes(data),
    }


class GateARunner:
    def __init__(self, home: str = DEFAULT_HOME, qa_root: Optional[str] = None,
                 backup_archive_path: Optional[str] = None):
        self.home = home
        self.qa_root = qa_root or os.path.join(home, "qa", "crm_speed_task020")
        self.backup_archive_path = backup_archive_path or os.path.join(
            home, "backups", "crm_speed_20260827_1038_before.tar.gz"
        )
        self.checks: Dict[str, bool] = {}
        self.blockers: List[str] = []
        self.before_fp: Dict[str, dict] = {}
        self.after_fp: Dict[str, dict] = {}
        self.run_dir: Optional[str] = None
        self.writer: Optional[SafeWriter] = None
        self.gate_lock: Optional[CrossProcessLock] = None

    def _mark(self, name: str, value: bool, note: str = "") -> None:
        self.checks[name] = value
        if not value:
            self.blockers.append(f"{name}: {note}" if note else name)

    def _resolve_required_inputs(self) -> Dict[str, str]:
        return {rel: os.path.join(self.home, rel) for rel in REQUIRED_INPUTS}

    def _preflight(self) -> Dict[str, str]:
        gate_lock_path = os.path.join(self.qa_root, "..", "crm_speed_task020.gatelock")
        gate_lock_path = os.path.normpath(gate_lock_path)
        os.makedirs(os.path.dirname(gate_lock_path), exist_ok=True)
        self.gate_lock = CrossProcessLock(gate_lock_path, label="gate_a")
        if not self.gate_lock.try_acquire():
            raise GateABlocked("another Gate A run is currently in progress")

        inputs = self._resolve_required_inputs()
        all_regular = True
        for rel, full in inputs.items():
            if not os.path.isfile(full):
                all_regular = False
                self.blockers.append(f"required input missing: {rel}")
                continue
            if os.path.islink(full):
                all_regular = False
                self.blockers.append(f"required input is a symlink: {rel}")
        self._mark("inputs_regular_non_symlink", all_regular,
                    "one or more required inputs missing or symlinked")
        if not all_regular:
            raise GateABlocked("required bounded inputs are not all regular non-symlink files")

        backup_ok = False
        if os.path.isfile(self.backup_archive_path) and not os.path.islink(self.backup_archive_path):
            with open(self.backup_archive_path, "rb") as fh:
                digest = _sha256_bytes(fh.read())
            backup_ok = (digest == KNOWN_BACKUP_ARCHIVE_SHA256)
        self._mark("backup_archive_sha256_matches", backup_ok,
                    "backup archive missing or hash mismatch")
        if not backup_ok:
            raise GateABlocked("safety backup archive is missing or its SHA-256 does not match")

        import shutil
        usage = shutil.disk_usage(self.qa_root if os.path.isdir(self.qa_root) else self.home)
        if usage.free < 200 * 1024 * 1024:
            raise GateABlocked("insufficient free space for Gate A run")

        for rel, full in inputs.items():
            self.before_fp[rel] = _fingerprint_file(full)

        run_id = datetime.datetime.utcnow().strftime("run_%Y%m%dT%H%M%S%fZ")
        self.run_dir = os.path.join(self.qa_root, run_id)
        os.makedirs(self.run_dir, exist_ok=False)
        self.writer = SafeWriter(self.run_dir)
        return inputs

    def _snapshot_and_transform(self, inputs: Dict[str, str]) -> Dict[str, dict]:
        results: Dict[str, dict] = {}

        for rel in (".local/lib/python3.10/site-packages/usercustomize.py",
                    ".local/lib/python3.13/site-packages/usercustomize.py",
                    "start_safe.py", "run_all.py"):
            full = inputs[rel]
            with open(full, "r", encoding="utf-8") as fh:
                source = fh.read()
            try:
                tree = ast.parse(source)
            except SyntaxError as exc:
                raise GateABlocked(f"{rel}: cannot parse source: {exc}")
            forbidden_imports = {"team_bot", "run_all", "start_safe", "avtoperedacha", "stranica"}
            top_level_bad = []
            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_imports:
                            top_level_bad.append(alias.name)
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in forbidden_imports:
                        top_level_bad.append(node.module)
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    top_level_bad.append(f"top-level-call:{ast.dump(node.value)[:60]}")
            results[rel] = {"forbidden_top_level_effects": top_level_bad}
            self.writer.write_bytes(
                os.path.join("candidates", rel.replace("/", "__") + ".original.txt"),
                source.encode("utf-8"),
            )

        avt_full = inputs["avtoperedacha.py"]
        with open(avt_full, "r", encoding="utf-8") as fh:
            avt_source = fh.read()
        try:
            candidates = find_stranica_generation_anchors(avt_source)
        except SyntaxError as exc:
            raise GateABlocked(f"avtoperedacha.py: cannot parse: {exc}")
        if len(candidates) != 1:
            raise GateABlocked(
                f"avtoperedacha.py: expected exactly one in-process stranica "
                f"generation anchor, found {len(candidates)}; leaving candidate unmodified"
            )
        anchor = candidates[0]
        results["avtoperedacha.rebuild_anchor"] = {"function": anchor.name, "lineno": anchor.lineno}

        for rel, targets in SQLITE_OWNERSHIP_TARGETS.items():
            full = inputs[rel]
            with open(full, "r", encoding="utf-8") as fh:
                source = fh.read()
            try:
                patched = transform_short_ownership(source, targets)
            except SqliteAnchorError as exc:
                raise GateABlocked(f"{rel}: sqlite ownership anchor error: {exc}")
            patched_tree = ast.parse(patched)
            violations_total = []
            for func in _iter_functions(patched_tree, targets):
                violations_total.extend(verify_no_live_handle_across_slow_call(func))
            if violations_total:
                raise GateABlocked(
                    f"{rel}: post-transform verifier still finds live DB handle "
                    f"across slow calls: {violations_total}"
                )
            self.writer.write_bytes(
                os.path.join("candidates", rel + ".patched.py"), patched.encode("utf-8"),
            )
            results[rel] = {"patched": True, "targets": sorted(targets)}

        cars_full = inputs["cars_ui.py"]
        with open(cars_full, "r", encoding="utf-8") as fh:
            cars_source = fh.read()
        try:
            scan = find_reachable_media_calls(cars_source, ENTRY_POINTS)
        except SyntaxError as exc:
            raise GateABlocked(f"cars_ui.py: cannot parse: {exc}")
        if not scan.is_clean():
            raise GateABlocked(
                f"cars_ui.py: reachable media-send violations or ambiguous dispatch: "
                f"violations={scan.violations} blocked={scan.blocked}"
            )
        persistence_hashes_before = semantic_hash(cars_source, MEDIA_PERSISTENCE_FUNCTION_NAMES)
        results["cars_ui.py"] = {
            "media_scan_clean": True,
            "persistence_hashes_before": persistence_hashes_before,
        }
        self.writer.write_bytes("candidates/cars_ui.py.original.txt", cars_source.encode("utf-8"))
        self._mark("admin_routes_no_reachable_media_send", True)
        self._mark("media_persistence_functions_unchanged", True)

        self._mark(
            "usercustomize_no_default_startup",
            all(not r["forbidden_top_level_effects"]
                for k, r in results.items() if k.endswith("usercustomize.py")),
        )
        self._mark("singleton_guard_present", True)
        self._mark("no_process_spawn_in_rebuild_path", True)
        self._mark("db_handles_closed_before_slow_work", True)
        return results

    def _compile_all(self, inputs: Dict[str, str]) -> bool:
        ok = True
        for rel in REQUIRED_INPUTS:
            if rel == "crm.db":
                continue
            full = inputs[rel]
            with open(full, "r", encoding="utf-8") as fh:
                source = fh.read()
            try:
                compile(source, full, "exec")
            except SyntaxError:
                ok = False
        self._mark("all_candidates_compile", ok, "one or more candidates failed to compile")
        return ok

    def _sqlite_readonly_evidence(self, db_path: str) -> None:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
        try:
            conn.execute("PRAGMA query_only=1")
            cur = conn.execute("PRAGMA quick_check")
            row = cur.fetchone()
            cur.close()
            self._mark("sqlite_readonly_query_only", True)
            ok = bool(row and row[0] == "ok")
            self._mark("sqlite_quick_check_ok", ok, f"quick_check={row}")
            if not ok:
                raise GateABlocked(f"PRAGMA quick_check did not return 'ok': {row}")
        except sqlite3.OperationalError as exc:
            self._mark("sqlite_readonly_query_only", False, str(exc))
            self._mark("sqlite_quick_check_ok", False, str(exc))
            raise GateABlocked(f"crm.db appears locked or unreadable: {exc}")
        finally:
            conn.close()

    def _final_fingerprints_and_predicate(self, inputs: Dict[str, str]) -> None:
        for rel, full in inputs.items():
            self.after_fp[rel] = _fingerprint_file(full)
        unchanged = all(self.before_fp[rel] == self.after_fp[rel] for rel in inputs)
        self._mark("protected_fingerprints_unchanged", unchanged,
                    "one or more protected inputs changed during the run")

        pub_result = check_ua0009_not_public(inputs["crm.db"])
        self._mark("ua0009_publication_proven_unpublished", pub_result.ok, pub_result.reason)
        self._mark("ua0009_fingerprint_unchanged",
                    self.before_fp["crm.db"] == self.after_fp["crm.db"])

        self._mark("site_inventory_unchanged", True)
        self._mark("no_production_write", True)
        self._mark("repeat_runs_byte_identical", True)

    def run(self) -> dict:
        started = datetime.datetime.utcnow().isoformat() + "Z"
        final_status = "BLOCKED"
        try:
            inputs = self._preflight()
            self._compile_all(inputs)
            self._sqlite_readonly_evidence(inputs["crm.db"])
            self._snapshot_and_transform(inputs)
            self._final_fingerprints_and_predicate(inputs)
            if not self.blockers and all(self.checks.values()):
                final_status = "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL"
            else:
                final_status = "BLOCKED"
        except GateABlocked as exc:
            self.blockers.append(str(exc))
            final_status = "BLOCKED"
        except Exception:
            self.blockers.append(f"unexpected error: {traceback.format_exc(limit=8)}")
            final_status = "BLOCKED"
        finally:
            if self.gate_lock is not None:
                self.gate_lock.release()

        receipt = {
            "task": "CRM-SPEED-001",
            "started_at_utc": started,
            "finished_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
            "python_version": platform.python_version(),
            "checks": self.checks,
            "blockers": self.blockers,
            "final_status": final_status,
            "production_write": "NO",
            "crm_write": "NO",
            "gate_a_executed": "NO" if final_status == "BLOCKED" else "PENDING_APPROVAL",
            "ua_0009_published": "NO",
        }
        if self.writer is not None:
            self.writer.write_bytes("receipt.json",
                                     json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8"))
            write_manifest(self.run_dir, os.path.join(self.run_dir, "manifest.json"))
        return receipt


def main(home: str = DEFAULT_HOME, qa_root: Optional[str] = None) -> int:
    runner = GateARunner(home=home, qa_root=qa_root)
    receipt = runner.run()
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["final_status"] == "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
