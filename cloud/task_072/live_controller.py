"""
GET-only PythonAnywhere live-file controller for Gate A evidence collection.

This module performs ONLY GET (read) calls against the PythonAnywhere API to fetch:
  - db.py
  - cars_ui.py
  - trace_zhurnal.py
  - any schema helper modules named on the command line
  - crm.db (binary, read-only copy)

into a local temporary directory for offline analysis. It NEVER issues POST/PUT/DELETE
and NEVER writes back to PythonAnywhere.

Credentials must be supplied via environment variables at real run time:
  PA_API_TOKEN, PA_USERNAME, PA_HOST (default www.pythonanywhere.com)

This module is not executed in the Claude/Cloud sandbox (no network egress, no
credentials available here). It is delivered ready-to-run for an operator who has
legitimate GET-only PythonAnywhere API access.
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Iterable

ALLOWED_METHODS = {"GET"}


@dataclass
class FetchResult:
    remote_path: str
    local_path: str
    sha256: str
    size_bytes: int


class ReadOnlyGuard(Exception):
    pass


def _require_get(method: str) -> None:
    if method.upper() not in ALLOWED_METHODS:
        raise ReadOnlyGuard(
            f"Refusing non-GET method {method!r}: this controller is GET-only by contract."
        )


def _sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_file(api_base: str, token: str, remote_path: str, dest_dir: str) -> FetchResult:
    """GET a single file via the PythonAnywhere Files API into dest_dir.

    api_base example: https://www.pythonanywhere.com/api/v0/user/<username>
    remote_path example: /home/Carix/db.py
    """
    _require_get("GET")
    url = f"{api_base}/files/path{remote_path}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Token {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec - GET only, no writes
        data = resp.read()
    os.makedirs(dest_dir, exist_ok=True)
    local_name = os.path.basename(remote_path)
    local_path = os.path.join(dest_dir, local_name)
    with open(local_path, "wb") as f:
        f.write(data)
    return FetchResult(
        remote_path=remote_path,
        local_path=local_path,
        sha256=_sha256_of(local_path),
        size_bytes=len(data),
    )


def fetch_all(remote_paths: Iterable[str], dest_dir: str | None = None) -> list[FetchResult]:
    token = os.environ.get("PA_API_TOKEN")
    username = os.environ.get("PA_USERNAME")
    host = os.environ.get("PA_HOST", "www.pythonanywhere.com")
    if not token or not username:
        raise RuntimeError(
            "PA_API_TOKEN / PA_USERNAME not set. This controller refuses to run without "
            "operator-supplied GET-only credentials. No credentials are embedded in this "
            "package."
        )
    api_base = f"https://{host}/api/v0/user/{username}"
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="task072_gate_a_")
    results = []
    for remote_path in remote_paths:
        results.append(fetch_file(api_base, token, remote_path, dest_dir))
    return results


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        "/home/Carix/db.py",
        "/home/Carix/cars_ui.py",
        "/home/Carix/trace_zhurnal.py",
    ]
    try:
        fetched = fetch_all(targets)
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        sys.exit(2)
    for r in fetched:
        # redacted stdout: hash + size only, never file content
        print(f"{r.remote_path} sha256={r.sha256} bytes={r.size_bytes}")
