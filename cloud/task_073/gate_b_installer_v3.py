"""
TASK_073 ROUND 4 - gate_b_installer_v3.py

Owner-approved, manual-only production installer. This module performs real
writes and MUST only be invoked by gate_b_controller_v3.py after exact
approval-token verification, exclusive production window acquisition, a
successful shadow/dry-run, and full backups of every target.

Claude/Cloud does not execute this module. It is prepared for Codex to run
via the manual workflow_dispatch workflow after Gate A V3 PASS.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests


class InstallerV3Error(RuntimeError):
    pass


CODE_FILES = [
    "konteyner.py",
    "cars_ui.py",
    "stranica.py",
    "master_card.py",
    "yadro.py",
    "publikaciya.py",
]


@dataclass
class WriteSetEntry:
    remote_path: str
    new_content: str
    preimage_sha256: Optional[str] = None


@dataclass
class InstallReport:
    installed: List[str] = field(default_factory=list)
    backups: Dict[str, str] = field(default_factory=dict)
    rolled_back: bool = False
    error: Optional[str] = None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PythonAnywhereWriteClient:
    """GET+POST client restricted to the exact endpoints Gate B needs: file
    read, file write, and always_on-task restart. No other endpoint is
    exposed."""

    def __init__(self, username: str, token: str, api_host: str = "www.pythonanywhere.com"):
        self.username = username
        self.token = token
        self.api_host = api_host

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": "Token {}".format(self.token)}

    def get_file_text(self, remote_path: str) -> str:
        url = "https://{host}/api/v0/user/{user}/files/path{path}".format(
            host=self.api_host, user=self.username, path=remote_path
        )
        response = requests.get(url, headers=self._headers(), timeout=30)
        if response.status_code != 200:
            raise InstallerV3Error("GET {} returned {}".format(remote_path, response.status_code))
        return response.text

    def put_file_text(self, remote_path: str, content: str) -> None:
        url = "https://{host}/api/v0/user/{user}/files/path{path}".format(
            host=self.api_host, user=self.username, path=remote_path
        )
        response = requests.post(
            url,
            headers=self._headers(),
            files={"content": content.encode("utf-8")},
            timeout=30,
        )
        if response.status_code not in (200, 201):
            raise InstallerV3Error("PUT {} returned {}".format(remote_path, response.status_code))

    def restart_launcher(self, task_id: str) -> None:
        url = "https://{host}/api/v0/user/{user}/always_on_tasks/{task_id}/restart/".format(
            host=self.api_host, user=self.username, task_id=task_id
        )
        response = requests.post(url, headers=self._headers(), timeout=60)
        if response.status_code not in (200, 202):
            raise InstallerV3Error("restart returned {}".format(response.status_code))


def backup_all(client: PythonAnywhereWriteClient, remote_paths: Dict[str, str], local_backup_dir: str) -> Dict[str, str]:
    os.makedirs(local_backup_dir, exist_ok=True)
    backups: Dict[str, str] = {}
    for label, remote_path in remote_paths.items():
        content = client.get_file_text(remote_path)
        local_path = os.path.join(local_backup_dir, label.replace("/", "__") + ".bak")
        with open(local_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        backups[label] = local_path
    return backups


def install_write_set(
    client: PythonAnywhereWriteClient,
    write_set: Dict[str, WriteSetEntry],
    local_backup_dir: str,
) -> InstallReport:
    report = InstallReport()
    backups = backup_all(client, {label: entry.remote_path for label, entry in write_set.items()}, local_backup_dir)
    report.backups = backups

    for label, entry in write_set.items():
        with open(backups[label], "r", encoding="utf-8") as fh:
            preimage = fh.read()
        if entry.preimage_sha256 is not None and sha256_text(preimage) != entry.preimage_sha256:
            report.error = "preimage sha drift on {} before any write".format(label)
            return report

    try:
        for label, entry in write_set.items():
            client.put_file_text(entry.remote_path, entry.new_content)
            report.installed.append(label)

        for label, entry in write_set.items():
            on_disk = client.get_file_text(entry.remote_path)
            if sha256_text(on_disk) != sha256_text(entry.new_content):
                raise InstallerV3Error("read-back mismatch after install: {}".format(label))

        return report
    except Exception as exc:  # noqa: BLE001 - fail closed, always roll back
        report.error = str(exc)
        for label in report.installed:
            with open(backups[label], "r", encoding="utf-8") as fh:
                preimage = fh.read()
            client.put_file_text(write_set[label].remote_path, preimage)
        report.rolled_back = True
        return report
