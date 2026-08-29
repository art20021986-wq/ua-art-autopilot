#!/usr/bin/env python3
"""Atomic backup/install/rollback helper for TASK 081.

This module is intentionally inert with respect to production in this task
round: it operates purely on paths passed by the caller. Gate B is the only
authorized caller against a real production path, and Gate B requires the
exact literal owner-approval token before it will invoke anything here.
"""
import hashlib
import os
import shutil
import time
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class AtomicInstaller:
    def __init__(self, backup_dir: Path):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._backups = {}

    def backup(self, target_path: Path) -> Path:
        target_path = Path(target_path)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup_path = self.backup_dir / f"{target_path.name}.{ts}.bak"
        if target_path.exists():
            shutil.copy2(target_path, backup_path)
        else:
            backup_path = None
        self._backups[str(target_path)] = backup_path
        return backup_path

    def atomic_write(self, target_path: Path, new_bytes: bytes):
        target_path = Path(target_path)
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp_install")
        tmp_path.write_bytes(new_bytes)
        os.replace(tmp_path, target_path)

    def verify_readback(self, target_path: Path, expected_sha256: str) -> bool:
        return sha256_file(Path(target_path)) == expected_sha256

    def rollback(self, target_path: Path) -> bool:
        target_path = Path(target_path)
        backup_path = self._backups.get(str(target_path))
        if backup_path is None:
            if target_path.exists():
                target_path.unlink()
            return True
        shutil.copy2(backup_path, target_path)
        return True


def install_bundle(installer: "AtomicInstaller", files: dict) -> dict:
    """files: {target_path: new_bytes}. Installs all-or-nothing.

    Returns {'ok': bool, 'installed': [...], 'error': str|None}.
    """
    installed = []
    try:
        for target, content in files.items():
            installer.backup(Path(target))
        for target, content in files.items():
            installer.atomic_write(Path(target), content)
            expected = hashlib.sha256(content).hexdigest()
            if not installer.verify_readback(Path(target), expected):
                raise RuntimeError(f"READBACK_MISMATCH:{target}")
            installed.append(target)
        return {"ok": True, "installed": installed, "error": None}
    except Exception as exc:  # noqa: BLE001
        for target in list(files.keys()):
            installer.rollback(Path(target))
        return {"ok": False, "installed": [], "error": str(exc)}


def restart_active_launcher_exact(launcher_name: str, allowed_launcher_name: str):
    """Only allowed to restart the exact already-active launcher, and only when
    called explicitly by a Gate B run with the approved token. This function
    performs no action here; it is a guarded stub for the real Gate B runner.
    """
    if launcher_name != allowed_launcher_name:
        raise RuntimeError(
            f"REFUSED: launcher_name {launcher_name!r} does not exactly match "
            f"the active launcher {allowed_launcher_name!r}"
        )
    return {"ok": True, "action": "restart-stub-not-executed-in-this-package"}
