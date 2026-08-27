"""Restricted no-argument Gate A launcher for TASK 021.

The only runtime entrypoint is `python3 -m ua_cards_unified.launcher`.
It uses fixed roots, builds and reloads a cryptographically bound manifest,
executes once under an exclusive lock, and atomically exposes only a complete
report/preview run. It has no production, CRM-write, reload, or process-control
mode.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import fcntl
import json
import os
import stat
import sys
from pathlib import Path

from . import common
from . import manifest_builder
from . import runner


class LauncherError(Exception):
    pass


BASE_ROOT = Path("/home/Carix")
REPORT_ROOT = BASE_ROOT / common.REPORT_SUBDIR
PACKAGE_DIR = Path(__file__).resolve().parent
LOCK_FILENAME = ".ua_cards_unified_gate_a.lock"


def load_manifest(manifest_path: Path) -> dict:
    common.require_regular_non_symlink(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    if not isinstance(manifest, dict):
        raise LauncherError("Manifest is not an object")
    if not manifest_builder.verify_manifest_integrity(manifest):
        raise LauncherError("Manifest integrity check failed")
    return manifest


def verify_code_hashes(manifest: dict, package_dir: Path) -> None:
    expected = manifest.get("code_hashes")
    required = set(manifest_builder.SELF_MODULE_NAMES)
    if not isinstance(expected, dict) or set(expected) != required:
        raise LauncherError("Manifest code-hash set is incomplete or unexpected")
    for name in sorted(required):
        expected_hash = expected.get(name)
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise LauncherError(f"Invalid expected code hash for {name}")
        p = package_dir / name
        common.require_within_roots(p, [package_dir])
        common.require_regular_non_symlink(p)
        actual_hash = common.sha256_file(p)
        if actual_hash != expected_hash:
            raise LauncherError(f"Code hash mismatch for {name}")


def verify_input_hashes(manifest: dict, base_root: Path = BASE_ROOT) -> None:
    discovered = manifest.get("discovered_inputs")
    expected_hashes = manifest.get("protected_paths_before")
    if not isinstance(discovered, dict) or not isinstance(expected_hashes, dict):
        raise LauncherError("Manifest input maps are invalid")
    if set(discovered) != set(expected_hashes):
        raise LauncherError("Manifest input path/hash sets differ")
    for name, path_str in discovered.items():
        if not isinstance(path_str, str):
            raise LauncherError(f"Invalid input path for {name}")
        p = Path(path_str)
        common.require_within_roots(p, [base_root])
        common.require_regular_non_symlink(p)
        expected = expected_hashes[name]
        if not isinstance(expected, str) or len(expected) != 64:
            raise LauncherError(f"Invalid input hash for {name}")
        if common.sha256_file(p) != expected:
            raise LauncherError(f"Input hash mismatch for {name}")


def _ensure_fixed_roots() -> None:
    if BASE_ROOT.is_symlink() or not BASE_ROOT.is_dir():
        raise LauncherError("Fixed base root is missing, non-directory, or a symlink")
    base = common.canonical_resolve(BASE_ROOT)
    report = common.canonical_resolve(REPORT_ROOT)
    try:
        report.relative_to(base)
    except ValueError as exc:
        raise LauncherError("Fixed report root escapes the fixed base root") from exc
    if REPORT_ROOT.is_symlink():
        raise LauncherError("Fixed report root is a symlink")
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    if common.canonical_resolve(REPORT_ROOT) != report:
        raise LauncherError("Fixed report root changed while being created")


def _acquire_lock():
    lock_path = REPORT_ROOT / LOCK_FILENAME
    if lock_path.is_symlink():
        raise LauncherError("Execution lock is a symlink")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lock_path, flags, 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise LauncherError("Execution lock is not a single-link regular file")
        handle = os.fdopen(fd, "r+")
        fd = -1
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise LauncherError("Another Gate A execution is already running") from exc
        return handle
    finally:
        if fd >= 0:
            os.close(fd)


def _bounded_discovery() -> dict[str, str]:
    discovered: dict[str, str] = {}
    for code in common.ALL_CODES:
        path = runner.discover_card_source(BASE_ROOT, code)
        if path is not None:
            discovered[code] = str(common.canonical_resolve(path))
    discovered.update(runner.discover_generators(BASE_ROOT))
    crm_path = runner.discover_crm(BASE_ROOT)
    if crm_path is not None:
        discovered[common.CRM_CANDIDATE_NAME] = str(common.canonical_resolve(crm_path))
    return dict(sorted(discovered.items()))


def _fingerprint_inputs(discovered: dict[str, str]) -> dict[str, str]:
    return {
        name: common.sha256_file(Path(path))
        for name, path in sorted(discovered.items())
    }


def _new_execution_id() -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{os.getpid()}"


def _planned_outputs() -> list[str]:
    outputs = ["gate_a_manifest.json", "gate_a_result.json", "gate_a_receipt.json"]
    for code in common.REAL_CODES:
        outputs.extend(
            [
                f"preview/{code}.html",
                f"preview/{code}-diag.html",
                f"preview/{code}-track.html",
            ]
        )
    return sorted(outputs)


def _verify_manifest_contract(
    manifest: dict,
    execution_id: str,
    staging_root: Path,
    final_root: Path,
    planned_outputs: list[str],
) -> None:
    exact = {
        "task_id": "task_021",
        "source_provenance": "cloud/ua_cards_unified",
        "target_mode": "GATE_A_REPORT_PREVIEW_ONLY",
        "gate_a": True,
        "gate_b": False,
        "execution_id": execution_id,
        "final_output_root": str(final_root),
    }
    for field, expected in exact.items():
        if manifest.get(field) != expected:
            raise LauncherError(f"Manifest contract mismatch for {field}")
    if manifest.get("write_roots_allowlist") != [str(staging_root)]:
        raise LauncherError("Manifest write-root allowlist mismatch")
    if manifest.get("planned_outputs") != planned_outputs:
        raise LauncherError("Manifest planned-output set mismatch")


def _rewrite_result_paths(result: runner.GateAResult, staging: Path, final: Path) -> None:
    staging_resolved = common.canonical_resolve(staging)
    for card in result.cards.values():
        output = card.get("output_path")
        if not output:
            continue
        output_path = common.canonical_resolve(Path(output))
        try:
            rel = output_path.relative_to(staging_resolved)
        except ValueError as exc:
            raise LauncherError("Runner reported an output outside staging") from exc
        card["output_path"] = str(final / rel)


def _validate_pass_outputs(result: runner.GateAResult, preview_root: Path) -> None:
    for code, card in result.cards.items():
        if card.get("status") != "PASS":
            continue
        if code not in common.REAL_CODES:
            raise LauncherError(f"Unexpected PASS card: {code}")
        expected = {
            "output_path": preview_root / f"{code}.html",
            "diag_href": f"{code}-diag.html",
            "track_href": f"{code}-track.html",
        }
        if common.canonical_resolve(Path(card.get("output_path", ""))) != common.canonical_resolve(expected["output_path"]):
            raise LauncherError(f"Unexpected preview output path for {code}")
        if card.get("diag_href") != expected["diag_href"] or card.get("track_href") != expected["track_href"]:
            raise LauncherError(f"Unexpected companion href for {code}")
        for path in (
            expected["output_path"],
            preview_root / expected["diag_href"],
            preview_root / expected["track_href"],
        ):
            common.require_regular_non_symlink(path)


def run() -> dict:
    if len(sys.argv) != 1:
        raise LauncherError("This launcher accepts no command-line arguments")

    _ensure_fixed_roots()
    lock_file = _acquire_lock()
    try:
        execution_id = _new_execution_id()
        staging_root = REPORT_ROOT / f".staging-{execution_id}"
        final_root = REPORT_ROOT / "runs" / execution_id
        common.require_within_roots(staging_root, [REPORT_ROOT])
        common.require_within_roots(final_root, [REPORT_ROOT])
        if staging_root.exists() or final_root.exists():
            raise LauncherError("Execution output path already exists")

        discovered = _bounded_discovery()
        protected_before = _fingerprint_inputs(discovered)
        planned_outputs = _planned_outputs()
        manifest = manifest_builder.build_manifest(
            task_id="task_021",
            source_provenance="cloud/ua_cards_unified",
            discovered_inputs=discovered,
            protected_paths_before=protected_before,
            write_roots=[str(staging_root)],
            planned_outputs=planned_outputs,
            package_dir=PACKAGE_DIR,
            execution_id=execution_id,
            final_output_root=str(final_root),
        )

        writer = common.AtomicWriter([staging_root])
        manifest_path = staging_root / "gate_a_manifest.json"
        writer.write_text(manifest_path, manifest_builder.serialize_manifest(manifest))
        loaded = load_manifest(manifest_path)
        _verify_manifest_contract(
            loaded, execution_id, staging_root, final_root, planned_outputs
        )
        verify_code_hashes(loaded, PACKAGE_DIR)
        verify_input_hashes(loaded, BASE_ROOT)

        checkpoints: list[dict] = []

        def checkpoint(percent: int, message: str) -> None:
            checkpoints.append({"percent": percent, "message": message})

        preview_root = staging_root / "preview"
        result = runner.run_gate_a(
            BASE_ROOT,
            REPORT_ROOT,
            PACKAGE_DIR,
            checkpoint_cb=checkpoint,
            output_root=preview_root,
        )
        result.checkpoints = checkpoints
        if result.discovered_inputs != discovered:
            raise LauncherError("Runtime discovery differs from manifest binding")
        if result.production_write != "NO":
            raise LauncherError("Runner reported a production write")
        _validate_pass_outputs(result, preview_root)

        _rewrite_result_paths(result, preview_root, final_root / "preview")
        result_path = staging_root / "gate_a_result.json"
        writer.write_text(
            result_path,
            json.dumps(dataclasses.asdict(result), sort_keys=True, indent=2) + "\n",
        )

        output_hashes: dict[str, str] = {}
        for rel in planned_outputs:
            if rel == "gate_a_receipt.json":
                continue
            path = staging_root / rel
            if path.exists():
                common.require_regular_non_symlink(path)
                output_hashes[rel] = common.sha256_file(path)

        verify_input_hashes(loaded, BASE_ROOT)
        receipt = {
            "execution_id": execution_id,
            "manifest_sha256": loaded["manifest_sha256"],
            "code_hashes": loaded["code_hashes"],
            "output_hashes": output_hashes,
            "protected_before": result.protected_before,
            "protected_after": result.protected_after,
            "unexpected_protected_changes": result.unexpected_protected_changes,
            "overall_status": result.overall_status,
            "production_write": result.production_write,
            "final_output_root": str(final_root),
        }
        writer.write_text(
            staging_root / "gate_a_receipt.json",
            json.dumps(receipt, sort_keys=True, indent=2) + "\n",
        )

        final_root.parent.mkdir(parents=True, exist_ok=True)
        common.require_within_roots(final_root.parent, [REPORT_ROOT])
        if final_root.exists():
            raise LauncherError("Final output root appeared during execution")
        os.rename(staging_root, final_root)
        return receipt
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def main() -> int:
    if len(sys.argv) != 1:
        print("This launcher accepts no arguments.", file=sys.stderr)
        return 2
    try:
        receipt = run()
    except (LauncherError, common.GateAError, OSError, ValueError) as exc:
        print(f"GATE_A_LAUNCHER_BLOCKED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
