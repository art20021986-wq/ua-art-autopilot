#!/usr/bin/env python3
"""
gate_b_installer.py -- fail-closed, NOT-executed-by-this-task production
installer for the audited ferry wording change (task_057).

This module is imported/executed ONLY inside tests against temporary
fixtures in this task. It must never be run against real production paths
without a separate, explicitly authorized task carrying the exact approval
phrase for the real manifest_sha256.
"""
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path

BASE_ANCHOR = "/home/Carix"

ALLOWLIST = frozenset((
    "video/index.html",
    "video/katalog.html",
    "video/info.html",
    "video/podbor.html",
    "video/UA-0001.html",
    "video/UA-0002.html",
    "video/UA-0003.html",
    "video/UA-0004.html",
    "video/UA-0005.html",
    "video/UA-0006.html",
    "video/UA-0007.html",
    "video/UA-0008.html",
    "video/UA-0009.html",
    "stranica.py",
    "yadro.py",
))

APPROVAL_PREFIX = "APPROVE_PRODUCTION TASK_057 MANIFEST_SHA256="


class GateBError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_manifest_hash(manifest: dict) -> str:
    clean = dict(manifest)
    clean.pop("manifest_sha256", None)
    blob = json.dumps(clean, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_manifest(manifest_path: Path) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    declared = manifest.get("manifest_sha256")
    if not declared or not isinstance(declared, str) or len(declared) != 64:
        raise GateBError("manifest has no valid manifest_sha256")
    recomputed = canonical_manifest_hash(manifest)
    if recomputed != declared:
        raise GateBError(
            f"MANIFEST_TAMPER_DETECTED declared={declared} recomputed={recomputed}"
        )
    return manifest


def verify_approval(approval_text: str, manifest_sha256: str) -> None:
    line = approval_text.strip()
    expected = f"{APPROVAL_PREFIX}{manifest_sha256}"
    if line != expected:
        raise GateBError("APPROVAL_PHRASE_MISMATCH")


def _validate_regular_no_symlink(path: Path) -> None:
    if path.is_symlink():
        raise GateBError(f"REJECTED_SYMLINK: {path}")
    if not path.exists():
        return
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise GateBError(f"REJECTED_NON_REGULAR_FILE: {path}")
    if st.st_nlink > 1:
        raise GateBError(f"REJECTED_HARDLINK: {path}")


def _validate_within_base(base: Path, rel: str) -> Path:
    if rel not in ALLOWLIST:
        raise GateBError(f"REJECTED_NOT_IN_ALLOWLIST: {rel}")
    if ".." in Path(rel).parts:
        raise GateBError(f"REJECTED_PATH_ESCAPE: {rel}")
    full = (base / rel)
    resolved_base = base.resolve()
    resolved_full = full.resolve() if full.exists() else (base / rel)
    try:
        resolved_full_check = Path(os.path.realpath(str(full.parent))) / full.name
    except OSError:
        resolved_full_check = full
    if os.path.commonpath([str(resolved_base), str(resolved_full_check)]) != str(resolved_base) and full.exists():
        raise GateBError(f"REJECTED_PATH_ESCAPE: {rel}")
    return full


def _atomic_replace(dest: Path, data: bytes) -> None:
    dest_dir = dest.parent
    fd, tmp_name = tempfile.mkstemp(dir=str(dest_dir), prefix=".gateb_tmp_")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, str(dest))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def run_gate_b(
    base_dir: Path,
    manifest_path: Path,
    approval_path: Path,
    candidate_root: Path,
    receipt_path: Path,
    backup_root: Path,
    fail_after_n_writes: int = None,
) -> dict:
    """Execute Gate B against base_dir (fixture root in tests; NEVER real
    production in this task). Returns the receipt dict; also writes it to
    receipt_path.

    fail_after_n_writes is a TEST-ONLY hook used to inject a mid-write
    failure and prove rollback correctness. It must never be used outside
    tests.
    """
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    receipt = {
        "task_id": "task_057",
        "gate": "GATE_B",
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "production_touched": False,
        "crm_touched": False,
        "crm_db_written": False,
        "service_reloaded": False,
        "ua0009_published": False,
        "rollback_performed": False,
        "rollback_verified": None,
        "files": [],
        "result": "NOT_STARTED",
    }

    manifest = load_manifest(manifest_path)
    approval_text = Path(approval_path).read_text(encoding="utf-8")
    verify_approval(approval_text, manifest["manifest_sha256"])

    base_dir = Path(base_dir)
    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)

    targets = manifest.get("targets", [])
    replace_targets = [t for t in targets if t["action"] == "REPLACE"]
    verify_targets = [t for t in targets if t["action"] == "VERIFY_UNCHANGED"]

    # Phase 1: validate paths, re-hash live sources, verify candidates.
    plan = []
    for t in verify_targets + replace_targets:
        rel = t["path"]
        full = _validate_within_base(base_dir, rel)
        _validate_regular_no_symlink(full)
        if not full.exists():
            raise GateBError(f"SOURCE_MISSING: {rel}")
        live_hash = sha256_file(full)
        if live_hash != t["source_sha256"]:
            raise GateBError(
                f"SOURCE_DRIFT_DETECTED: {rel} expected={t['source_sha256']} actual={live_hash}"
            )
        if t["action"] == "VERIFY_UNCHANGED":
            if t["source_sha256"] != t["candidate_sha256"]:
                raise GateBError(f"VERIFY_UNCHANGED_TARGET_HAS_DIFFERING_CANDIDATE: {rel}")
            plan.append((rel, full, None))
            continue
        cand_path = Path(candidate_root) / rel
        _validate_regular_no_symlink(cand_path)
        if not cand_path.exists():
            raise GateBError(f"CANDIDATE_MISSING: {rel}")
        cand_bytes = cand_path.read_bytes()
        cand_hash = hashlib.sha256(cand_bytes).hexdigest()
        if cand_hash != t["candidate_sha256"]:
            raise GateBError(
                f"CANDIDATE_DRIFT_DETECTED: {rel} expected={t['candidate_sha256']} actual={cand_hash}"
            )
        expected_size = t.get("expected_size_bytes")
        if expected_size is not None and len(cand_bytes) != expected_size:
            raise GateBError(f"CANDIDATE_SIZE_MISMATCH: {rel}")
        plan.append((rel, full, cand_bytes))

    # Phase 2: backup every REPLACE target before any write.
    backups = {}
    for rel, full, cand_bytes in plan:
        if cand_bytes is None:
            continue
        backup_path = backup_root / (rel.replace("/", "__") + ".bak")
        shutil.copy2(full, backup_path)
        src_hash = sha256_file(full)
        bkp_hash = sha256_file(backup_path)
        if src_hash != bkp_hash:
            raise GateBError(f"BACKUP_HASH_MISMATCH: {rel}")
        backups[rel] = (backup_path, src_hash)

    # Phase 3: atomic writes, with rollback on any failure.
    written = []
    try:
        write_count = 0
        for rel, full, cand_bytes in plan:
            if cand_bytes is None:
                receipt["files"].append({
                    "path": rel,
                    "action": "VERIFY_UNCHANGED",
                    "before_sha256": manifest_target_hash(manifest, rel),
                    "after_sha256": manifest_target_hash(manifest, rel),
                    "backup_sha256": None,
                })
                continue
            write_count += 1
            if fail_after_n_writes is not None and write_count > fail_after_n_writes:
                raise GateBError("INJECTED_TEST_FAILURE")
            before_hash = sha256_file(full)
            _atomic_replace(full, cand_bytes)
            after_hash = sha256_file(full)
            written.append(rel)
            receipt["files"].append({
                "path": rel,
                "action": "REPLACE",
                "before_sha256": before_hash,
                "after_sha256": after_hash,
                "backup_sha256": backups[rel][1],
            })
        receipt["production_touched"] = True if written else False
        receipt["result"] = "SUCCESS"
    except BaseException as exc:
        # rollback everything already written
        restored_ok = True
        for rel in written:
            backup_path, orig_hash = backups[rel]
            full = base_dir / rel
            shutil.copy2(backup_path, full)
            restored_hash = sha256_file(full)
            if restored_hash != orig_hash:
                restored_ok = False
        receipt["rollback_performed"] = bool(written)
        receipt["rollback_verified"] = restored_ok if written else None
        receipt["result"] = f"FAILED: {exc}"
        receipt["production_touched"] = False
        receipt["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        Path(receipt_path).write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        raise

    # Phase 4: final verification of all targets against manifest.
    for rel, full, cand_bytes in plan:
        expected_hash = manifest_target_hash(manifest, rel)
        actual_hash = sha256_file(full)
        if actual_hash != expected_hash:
            raise GateBError(f"POST_WRITE_VERIFICATION_FAILED: {rel}")

    receipt["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(receipt_path).write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def manifest_target_hash(manifest: dict, rel: str) -> str:
    for t in manifest.get("targets", []):
        if t["path"] == rel:
            return t["candidate_sha256"]
    raise GateBError(f"UNKNOWN_TARGET: {rel}")
