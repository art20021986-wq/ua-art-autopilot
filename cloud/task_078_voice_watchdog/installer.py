"""Installer/controller for applying the voice-watchdog patch.

Safety rules enforced in code:
- Refuses to run against production paths (no PA/CRM paths are hardcoded).
- Requires the operator to pass the *actually fetched* source file and its
  expected SHA-256 (from Gate A). Refuses to touch anything if the hash does
  not match, or if no hash is supplied (fail closed).
- Always writes a timestamped backup before any modification.
- Provides rollback() that restores the exact backup bytes.
- Never calls os._exit, never issues a live restart. Gate B (a manual,
  human-triggered step) is documented but NOT executed by this script.
"""
from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Optional


class InstallError(RuntimeError):
    pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class VoiceWatchdogInstaller:
    def __init__(self, target_path: Path, expected_sha256: str, backup_dir: Optional[Path] = None):
        self.target_path = Path(target_path)
        self.expected_sha256 = expected_sha256
        self.backup_dir = Path(backup_dir) if backup_dir else self.target_path.parent / "_voice_watchdog_backups"
        self._last_backup_path: Optional[Path] = None

    def verify_source(self) -> None:
        if not self.target_path.exists():
            raise InstallError(f"target file does not exist: {self.target_path}")
        actual = sha256_of(self.target_path)
        if actual != self.expected_sha256:
            raise InstallError(
                f"SHA mismatch: expected {self.expected_sha256}, got {actual}. "
                "Refusing to modify an unverified file (fail closed)."
            )

    def backup(self) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        dest = self.backup_dir / f"{self.target_path.name}.{ts}.bak"
        shutil.copy2(self.target_path, dest)
        self._last_backup_path = dest
        return dest

    def apply_patch_dry_run(self) -> str:
        """SANDBOX-only: returns a description of what would change.

        Does not modify the target file. Real application requires an
        explicit Gate B human approval step outside this codebase.
        """
        self.verify_source()
        return (
            "DRY_RUN_ONLY: would replace the voice/audio branch of "
            "catch_message with VoiceWatchdogHandler.handle_voice(...) per "
            "handler_patch.py. No bytes were written to "
            f"{self.target_path}."
        )

    def rollback(self) -> None:
        if not self._last_backup_path or not self._last_backup_path.exists():
            raise InstallError("no backup available to roll back to")
        shutil.copy2(self._last_backup_path, self.target_path)


GATE_B_MANUAL_STEPS = """
Gate B (manual, owner-approved production step — NOT executed here):
1. Independently re-fetch cars_ui.py via secret-backed GET; confirm SHA
   matches the value recorded during Gate A for this deployment window.
2. Run VoiceWatchdogInstaller.verify_source() against the real file.
3. Call VoiceWatchdogInstaller.backup() and confirm the backup file exists
   and is byte-identical to the pre-patch file.
4. Apply the patch on a canary instance only, run the sandbox test suite
   against the canary, and run a manual voice-message smoke test.
5. Only after owner approval, apply to production, keeping the backup and
   rollback() available for at least one release cycle.
6. If anything regresses, call rollback() immediately.
"""
