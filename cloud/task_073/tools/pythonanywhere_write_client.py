"""
cloud/task_073/tools/pythonanywhere_write_client.py

Real PythonAnywhere Files API write + webapp reload client, used only by the
manual, owner-approved Gate B run. Never imported or executed by Gate A. GET
is used for preimage verification, POST (multipart) for the bounded write
set, and the webapps reload endpoint for restart.

This is a building block. Wiring it into gate_b_controller_v2's local-
filesystem AtomicInstaller for a real remote production run must reuse the
verified live path/session handling from cloud/task_069 and cloud/task_072's
Gate B controllers/installers rather than guess production paths here.
"""
from __future__ import annotations

import urllib.error
import urllib.request

PA_API_BASE = "https://www.pythonanywhere.com/api/v0"


class PythonAnywhereWriteError(RuntimeError):
    pass


class PythonAnywhereWriteClient:
    def __init__(self, username: str, token: str, base_url: str = PA_API_BASE):
        self.username = username
        self.token = token
        self.base_url = base_url

    def _headers(self) -> dict:
        return {"Authorization": f"Token {self.token}"}

    def get_file(self, remote_path: str) -> bytes:
        url = f"{self.base_url}/user/{self.username}/files/path/{remote_path}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.getcode() != 200:
                raise PythonAnywhereWriteError(f"GET {remote_path} failed: {resp.getcode()}")
            return resp.read()

    def put_file(self, remote_path: str, content: bytes) -> None:
        url = f"{self.base_url}/user/{self.username}/files/path/{remote_path}"
        boundary = "----task073boundary"
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="content"; filename="upload.bin"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = prefix + content + suffix
        headers = dict(self._headers())
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.getcode() not in (200, 201):
                    raise PythonAnywhereWriteError(f"PUT {remote_path} failed: {resp.getcode()}")
        except urllib.error.HTTPError as exc:
            raise PythonAnywhereWriteError(f"PUT {remote_path} failed: {exc.code} {exc.reason}") from exc

    def reload_webapp(self, domain: str) -> None:
        url = f"{self.base_url}/user/{self.username}/webapps/{domain}/reload/"
        req = urllib.request.Request(url, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                if resp.getcode() != 200:
                    raise PythonAnywhereWriteError(f"reload failed: {resp.getcode()}")
        except urllib.error.HTTPError as exc:
            raise PythonAnywhereWriteError(f"reload failed: {exc.code} {exc.reason}") from exc
