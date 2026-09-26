"""Create the flat exact Python package required by execution_contract.py.

Copies public reviewed repository code only; never includes captured server
source, CRM rows/DB, authorizations, nonces, launch markers or a claimed PASS.
Existing differing files fail unless --refresh-reviewed-code is explicit; this
flag affects only the generated local release directory, never production.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sources():
    sync = ROOT / "cloud/task088_price_sync"
    renderer = ROOT / "cloud/task088_stage3_renderer"
    policy = ROOT / "cloud/task088_autopilot_owner_policy"
    result = {name: HERE / name for name in ("controller.py", "backup_controller.py", "rollback_controller.py", "remote_adapter.py", "test_adapter.py", "test_operation_recovery.py")}
    result.update({"install_package.py": sync / "install_package.py",
        "source_successor.py": sync / "source_successor.py",
        "test_install_package.py": sync / "test_install_package.py",
        "uaart_price_sync_outbox.py": sync / "outbox.py", "outbox.py": sync / "outbox.py",
        "uaart_market_prices.py": renderer / "uaart_market_prices.py"})
    for name in ("uaart_price_sync_runtime.py", "uaart_price_sync_binding.py", "uaart_price_sync_confirmation.py",
                 "uaart_price_control_reader.py"):
        result[name] = sync / name
    for name in ("owner_policy.py", "price_publication.py"):
        result[name] = policy / name
    for name in ("publication_fence.py", "mutation_recovery.py", "visibility_lifecycle.py"):
        result[name] = ROOT / "cloud/task088_v5_writer_fence" / name
    return result


def build(*, refresh=False):
    destination = HERE / "release"
    if destination.is_symlink():
        raise ValueError("LOCAL_GENERATED_PACKAGE_SYMLINK_REFUSED")
    destination.mkdir(mode=0o700, exist_ok=True)
    mapping = sources()
    present = {path.name for path in destination.glob("*.py")}
    if present - set(mapping):
        raise ValueError("UNREVIEWED_PYTHON_IN_GENERATED_PACKAGE")
    provenance = {}
    for name, path in sorted(mapping.items()):
        raw = path.read_bytes()
        compile(raw, name, "exec")
        target = destination / name
        if target.is_symlink():
            raise ValueError("GENERATED_FILE_SYMLINK_REFUSED")
        if target.exists() and target.read_bytes() != raw and not refresh:
            raise ValueError("REVIEWED_SOURCE_CHANGED_REBUILD_REQUIRED:" + name)
        if not target.exists() or target.read_bytes() != raw:
            fd, temporary = tempfile.mkstemp(prefix=".build-", dir=destination)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw); handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        if target.read_bytes() != raw:
            raise ValueError("GENERATED_CODE_READBACK_FAILED")
        provenance[name] = {"source_path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}
    receipt = {"contract": "TASK088-V5-REVIEWED-RELEASE-SOURCE-MAP-1", "sources": provenance,
        "production_written": False, "canonical_gate_created": False,
        "controller_path": (destination / "controller.py").relative_to(ROOT).as_posix(),
        "test_paths": [(destination / name).relative_to(ROOT).as_posix() for name in ("test_install_package.py", "test_adapter.py", "test_operation_recovery.py")]}
    (destination / "release_sources.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": "LOCAL_RELEASE_CODE_BUILT", "directory": str(destination), "python_files": len(mapping), "production_written": False}))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-reviewed-code", action="store_true")
    build(refresh=parser.parse_args().refresh_reviewed_code)
