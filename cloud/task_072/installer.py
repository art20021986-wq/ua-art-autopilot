"""
Local installer: dry-run / apply / rollback for the description-save patch.

SAFETY: This installer refuses to operate on any path containing '/home/Carix' — the
known live production path — under any circumstance. It only ever operates on temp
copies passed in explicitly by the caller. This is defense in depth on top of the
fact that Gate B (production) is not executed by this task.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

PRODUCTION_MARKER = "/home/Carix"


class ProductionGuardError(Exception):
    pass


def _guard_not_production(path: str) -> None:
    if PRODUCTION_MARKER in os.path.abspath(path):
        raise ProductionGuardError(
            f"Refusing to operate on {path!r}: matches production marker {PRODUCTION_MARKER!r}. "
            "This installer only runs against local temp copies (Gate A). Production "
            "changes require a separate, owner-approved Gate B run."
        )


def dry_run(target_dir: str) -> dict:
    _guard_not_production(target_dir)
    report = {"target_dir": target_dir, "mode": "dry_run", "files": []}
    for name in ("db.py", "cars_ui.py", "trace_zhurnal.py"):
        path = os.path.join(target_dir, name)
        report["files"].append({"path": path, "exists": os.path.exists(path)})
    return report


def apply(target_dir: str, backup_dir: str) -> dict:
    _guard_not_production(target_dir)
    _guard_not_production(backup_dir)
    os.makedirs(backup_dir, exist_ok=True)
    backed_up = []
    for name in ("db.py", "cars_ui.py", "trace_zhurnal.py"):
        src = os.path.join(target_dir, name)
        if os.path.exists(src):
            dst = os.path.join(backup_dir, f"{name}.{int(time.time())}.bak")
            shutil.copy2(src, dst)
            backed_up.append(dst)
    return {"mode": "apply", "backed_up": backed_up, "target_dir": target_dir}


def rollback(target_dir: str, backup_dir: str) -> dict:
    _guard_not_production(target_dir)
    _guard_not_production(backup_dir)
    restored = []
    if not os.path.isdir(backup_dir):
        return {"mode": "rollback", "restored": restored, "note": "no backup_dir found"}
    # Restore the most recent backup for each known filename.
    latest = {}
    for fname in os.listdir(backup_dir):
        for base in ("db.py", "cars_ui.py", "trace_zhurnal.py"):
            if fname.startswith(base + "."):
                latest.setdefault(base, []).append(fname)
    for base, candidates in latest.items():
        candidates.sort()
        chosen = candidates[-1]
        shutil.copy2(os.path.join(backup_dir, chosen), os.path.join(target_dir, base))
        restored.append(base)
    return {"mode": "rollback", "restored": restored, "target_dir": target_dir}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: installer.py [dry-run|apply|rollback] target_dir [backup_dir]")
        sys.exit(1)
    mode = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else "."
    backup = sys.argv[3] if len(sys.argv) > 3 else os.path.join(target, "_backup")
    try:
        if mode == "dry-run":
            print(json.dumps(dry_run(target), indent=2))
        elif mode == "apply":
            print(json.dumps(apply(target, backup), indent=2))
        elif mode == "rollback":
            print(json.dumps(rollback(target, backup), indent=2))
        else:
            print(f"unknown mode {mode!r}")
            sys.exit(1)
    except ProductionGuardError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        sys.exit(2)
