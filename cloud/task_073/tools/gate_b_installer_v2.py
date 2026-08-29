"""
cloud/task_073/tools/gate_b_installer_v2.py

Bounded, atomic installer for CRM-UNIFIED-CATALOG-001 v1.0 production
writes. Only Codex, after real Gate A V2 PASS and the already-recorded
owner approval token, may execute this against production. Claude/Cloud
never runs this against live PythonAnywhere.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class InstallError(RuntimeError):
    pass


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class WriteSetEntry:
    target_path: str
    new_content: bytes
    preimage_sha: str


@dataclass
class InstallManifest:
    entries: List[Dict[str, str]] = field(default_factory=list)
    backup_dir: str = ""
    committed: bool = False


class AtomicInstaller:
    """Stages a bounded write set to a temp dir, backs up every target with
    a collision-safe name derived from the full relative path, replaces
    atomically, reads back every SHA, and rolls back the entire set on any
    failure.
    """

    def __init__(self, write_set: List[WriteSetEntry], workdir: Optional[str] = None):
        if not write_set:
            raise InstallError("empty write set is not a valid install")
        self.write_set = write_set
        self.workdir = workdir or tempfile.mkdtemp(prefix="task073_install_")
        self.backup_dir = os.path.join(self.workdir, "backup")
        os.makedirs(self.backup_dir, exist_ok=True)
        self.manifest = InstallManifest(backup_dir=self.backup_dir)

    def _backup_name(self, target_path: str) -> str:
        digest = hashlib.sha256(target_path.encode("utf-8")).hexdigest()[:16]
        safe = target_path.replace("/", "__").replace("\\", "__")
        return os.path.join(self.backup_dir, f"{digest}__{safe}.bak")

    def preflight(self) -> None:
        for entry in self.write_set:
            if not os.path.exists(entry.target_path):
                raise InstallError(f"target missing, refusing blind create: {entry.target_path}")
            current_sha = sha256_file(entry.target_path)
            if current_sha != entry.preimage_sha:
                raise InstallError(
                    f"preimage drift on {entry.target_path}: expected {entry.preimage_sha}, found {current_sha}"
                )

    def backup_all(self) -> None:
        for entry in self.write_set:
            backup_path = self._backup_name(entry.target_path)
            shutil.copy2(entry.target_path, backup_path)
            if sha256_file(backup_path) != entry.preimage_sha:
                raise InstallError(f"backup integrity check failed for {entry.target_path}")

    def stage_all(self) -> Dict[str, str]:
        staged: Dict[str, str] = {}
        for entry in self.write_set:
            staged_path = os.path.join(self.workdir, "staged__" + entry.target_path.replace("/", "__"))
            with open(staged_path, "wb") as fh:
                fh.write(entry.new_content)
                fh.flush()
                os.fsync(fh.fileno())
            staged[entry.target_path] = staged_path
        return staged

    def install(self) -> InstallManifest:
        self.preflight()
        self.backup_all()
        staged = self.stage_all()
        installed: List[str] = []
        try:
            for entry in self.write_set:
                staged_path = staged[entry.target_path]
                os.replace(staged_path, entry.target_path)
                installed.append(entry.target_path)
                new_sha = sha256_file(entry.target_path)
                expected_sha = sha256_bytes(entry.new_content)
                if new_sha != expected_sha:
                    raise InstallError(f"read-back SHA mismatch after replace: {entry.target_path}")
                self.manifest.entries.append({
                    "target_path": entry.target_path,
                    "preimage_sha": entry.preimage_sha,
                    "installed_sha": new_sha,
                })
            self.manifest.committed = True
            return self.manifest
        except Exception as exc:
            self.rollback(installed)
            raise InstallError(f"install failed, full rollback executed: {exc}") from exc

    def rollback(self, installed_targets: Optional[List[str]] = None) -> None:
        targets = installed_targets if installed_targets is not None else [e.target_path for e in self.write_set]
        for entry in self.write_set:
            if entry.target_path not in targets:
                continue
            backup_path = self._backup_name(entry.target_path)
            if not os.path.exists(backup_path):
                raise InstallError(f"cannot rollback, backup missing for {entry.target_path}")
            shutil.copy2(backup_path, entry.target_path)
            restored_sha = sha256_file(entry.target_path)
            if restored_sha != entry.preimage_sha:
                raise InstallError(f"rollback verification failed for {entry.target_path}")
        self.manifest.committed = False

    def write_manifest(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "entries": self.manifest.entries,
                "committed": self.manifest.committed,
                "generated_at": time.time(),
            }, fh, indent=2, sort_keys=True)
