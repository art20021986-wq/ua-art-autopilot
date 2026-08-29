"""Atomic installer with preimage backup and rollback for TASK 073.

Used for both the keyboard-transform code install and any small,
field-level candidate change. Never performs a full-database or
full-site rollback; operates only on the explicit target set given by
the caller, with byte-for-byte preimage verification available.
"""

import hashlib
import os
import shutil
from typing import Dict, List


def sha256_file(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_preimage_manifest(paths: List[str]) -> Dict[str, str]:
    manifest = {}
    for path in paths:
        manifest[path] = sha256_file(path) if os.path.exists(path) else None
    return manifest


def atomic_install(candidate_paths: Dict[str, str], target_paths: Dict[str, str], backup_dir: str) -> Dict[str, str]:
    """candidate_paths maps target_path -> source_candidate_path.

    target_paths is reserved for future symmetric bookkeeping and is not
    otherwise used. Returns the preimage manifest so callers can verify
    or roll back later.
    """
    os.makedirs(backup_dir, exist_ok=True)
    preimage = build_preimage_manifest(list(candidate_paths.keys()))
    backups: Dict[str, str] = {}
    try:
        for target in candidate_paths:
            if os.path.exists(target):
                backup_path = os.path.join(backup_dir, os.path.basename(target) + ".bak")
                shutil.copyfile(target, backup_path)
                backups[target] = backup_path
        for target, source in candidate_paths.items():
            tmp_path = target + ".install_tmp"
            shutil.copyfile(source, tmp_path)
            os.replace(tmp_path, target)
        return preimage
    except Exception:
        rollback(preimage, backups)
        raise


def rollback(preimage: Dict[str, str], backups: Dict[str, str]) -> None:
    for target, backup_path in backups.items():
        if os.path.exists(backup_path):
            shutil.copyfile(backup_path, target)
    for target, prior_sha in preimage.items():
        if prior_sha is None and target not in backups and os.path.exists(target):
            os.remove(target)


def verify_preimage_restored(preimage: Dict[str, str]) -> bool:
    for target, prior_sha in preimage.items():
        if prior_sha is None:
            if os.path.exists(target):
                return False
        else:
            if not os.path.exists(target) or sha256_file(target) != prior_sha:
                return False
    return True
