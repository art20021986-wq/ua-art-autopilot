"""Fetch the live cars_ui.py source and a READ-ONLY hash/quick_check shadow
of crm.db via the PythonAnywhere API, using the transport pattern proven in
TASK 067/068/077 (PYTHONANYWHERE_API_TOKEN only; no new credentials asked).

This module never writes to crm.db and never writes to production. It only
reads bytes to compute SHA256 / sqlite quick_check for drift detection.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import urllib.request
import urllib.error

PA_API_BASE = os.environ.get("PA_API_BASE", "https://www.pythonanywhere.com/api/v0")
PA_USERNAME = os.environ.get("PA_USERNAME", "")
PA_TOKEN = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")

SOURCE_PATH = "/home/Carix/cars_ui.py"
DB_PATH = "/home/Carix/crm.db"


class FetchError(Exception):
    pass


def _files_path_url(remote_path: str) -> str:
    return f"{PA_API_BASE}/user/{PA_USERNAME}/files/path{remote_path}"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Token {PA_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} fetching {url}: {e.read()[:500]!r}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"Network error fetching {url}: {e}") from e


def fetch_source() -> tuple[str, str]:
    """Return (source_text, sha256_hex) of the live cars_ui.py."""
    if not PA_USERNAME or not PA_TOKEN:
        raise FetchError("PA_USERNAME / PYTHONANYWHERE_API_TOKEN not set in environment.")
    raw = _get(_files_path_url(SOURCE_PATH))
    text = raw.decode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    return text, sha


def fetch_db_shadow_hashes() -> dict:
    """Download crm.db bytes to a local temp file ONLY for read-only hashing
    and sqlite `PRAGMA quick_check`. The temp file is deleted immediately
    after. No write ever happens against the live DB.
    """
    if not PA_USERNAME or not PA_TOKEN:
        raise FetchError("PA_USERNAME / PYTHONANYWHERE_API_TOKEN not set in environment.")
    raw = _get(_files_path_url(DB_PATH))
    sha = hashlib.sha256(raw).hexdigest()
    quick_check = "UNKNOWN"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
        try:
            cur = conn.execute("PRAGMA quick_check;")
            rows = cur.fetchall()
            quick_check = rows[0][0] if rows else "UNKNOWN"
        finally:
            conn.close()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return {"sha256": sha, "quick_check": quick_check, "size_bytes": len(raw)}


def upload_source(new_text: str) -> None:
    """Atomic-ish upload of a new cars_ui.py via the PythonAnywhere Files API.
    Caller (installer.py) is responsible for backup + verification before
    calling this, and for restart afterwards.
    """
    if not PA_USERNAME or not PA_TOKEN:
        raise FetchError("PA_USERNAME / PYTHONANYWHERE_API_TOKEN not set in environment.")
    url = _files_path_url(SOURCE_PATH)
    data = new_text.encode("utf-8")
    boundary = "----vin4boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="content"; filename="cars_ui.py"\r\n'
        f"Content-Type: text/x-python\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Token {PA_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        raise FetchError(f"Upload failed HTTP {e.code}: {e.read()[:500]!r}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"Upload network error: {e}") from e


def restart_launcher() -> None:
    """Restart the exact launcher `python3.10 /home/Carix/start_safe.py` via
    the PythonAnywhere always-on-task restart endpoint (same pattern as TASK
    067/068/077). The always-on task id/name is read from PA_TASK_ID env var
    supplied by the workflow; if not configured, this raises so the
    controller can fail closed instead of silently skipping restart.
    """
    task_id = os.environ.get("PA_ALWAYS_ON_TASK_ID", "")
    if not task_id:
        raise FetchError("PA_ALWAYS_ON_TASK_ID not configured; refusing silent restart skip.")
    url = f"{PA_API_BASE}/user/{PA_USERNAME}/always_on_tasks/{task_id}/restart/"
    req = urllib.request.Request(url, data=b"", method="POST",
                                  headers={"Authorization": f"Token {PA_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        raise FetchError(f"Restart failed HTTP {e.code}: {e.read()[:500]!r}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"Restart network error: {e}") from e
