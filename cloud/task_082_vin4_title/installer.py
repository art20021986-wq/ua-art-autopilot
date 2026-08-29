"""Backup + atomic source-only install for cars_ui.py.

Only ever writes:
  - a timestamped backup copy under backups/
  - the new cars_ui.py content (atomically, via temp file + PA upload)

Never touches crm.db, media, or website files.
"""
from __future__ import annotations

import hashlib
import os
import time

import fetch_and_shadow as fas

BACKUP_DIR_LOCAL = os.path.join(os.path.dirname(__file__), "backups")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_backup(original_source_text: str) -> str:
    os.makedirs(BACKUP_DIR_LOCAL, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    sha = _sha256_text(original_source_text)[:12]
    backup_path = os.path.join(BACKUP_DIR_LOCAL, f"cars_ui.py.{ts}.{sha}.bak")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(original_source_text)
    return backup_path


def install(new_source_text: str) -> dict:
    """Upload new_source_text as cars_ui.py, then restart the exact launcher.
    Returns a dict with before/after info for the postcheck step.
    """
    fas.upload_source(new_source_text)
    fas.restart_launcher()
    return {
        "new_sha256": _sha256_text(new_source_text),
        "installed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def rollback(backup_path: str) -> dict:
    """Restore the exact backed-up source and restart. Used on any FAIL."""
    with open(backup_path, "r", encoding="utf-8") as f:
        original = f.read()
    fas.upload_source(original)
    fas.restart_launcher()
    return {
        "restored_sha256": _sha256_text(original),
        "rolled_back_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
