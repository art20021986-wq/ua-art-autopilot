#!/usr/bin/env python3
"""Safely mirror Claude GitHub outputs from cloud/ to a PythonAnywhere inbox.

This uploader deliberately DOES NOT execute files, reload the web app, touch CRM,
or write into production paths. It only uploads UTF-8/text/code deliverables to:

    /home/<username>/autopilot_inbox/cloud/...

Authentication is provided through PYTHONANYWHERE_API_TOKEN in GitHub Actions.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLOUD = ROOT / "cloud"

USERNAME = (os.environ.get("PYTHONANYWHERE_USERNAME") or "Carix").strip()
HOST = (os.environ.get("PYTHONANYWHERE_HOST") or "www.pythonanywhere.com").strip()
TOKEN = (os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
REMOTE_ROOT = (
    os.environ.get("PYTHONANYWHERE_REMOTE_ROOT")
    or f"/home/{USERNAME}/autopilot_inbox"
).rstrip("/")

MAX_FILE_BYTES = 5 * 1024 * 1024
ALLOWED_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".html", ".htm",
    ".css", ".js", ".csv", ".toml", ".ini", ".cfg", ".sh", ".sql",
}
SECRET_PATTERNS = [
    re.compile(rb"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"ghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def fail(message: str) -> "NoReturn":
    raise SystemExit(message)


def ensure_configuration() -> None:
    if not USERNAME:
        fail("PYTHONANYWHERE_USERNAME_MISSING")
    if not TOKEN:
        fail(
            "PYTHONANYWHERE_API_TOKEN_MISSING: add it in GitHub -> Settings -> "
            "Secrets and variables -> Actions -> New repository secret"
        )
    if HOST not in {"www.pythonanywhere.com", "eu.pythonanywhere.com"}:
        fail("PYTHONANYWHERE_HOST_INVALID")
    expected_prefix = f"/home/{USERNAME}/autopilot_inbox"
    if REMOTE_ROOT != expected_prefix and not REMOTE_ROOT.startswith(expected_prefix + "/"):
        fail("PYTHONANYWHERE_REMOTE_ROOT_UNSAFE")


def list_cloud_files() -> list[pathlib.Path]:
    if not CLOUD.is_dir():
        fail("CLOUD_DIRECTORY_MISSING")
    result: list[pathlib.Path] = []
    for path in sorted(CLOUD.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            print(f"SKIP unsupported extension: {path.relative_to(ROOT)}")
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            fail(f"FILE_TOO_LARGE:{path.relative_to(ROOT)}:{size}")
        result.append(path)
    if not result:
        fail("NO_SYNCABLE_CLOUD_FILES")
    return result


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject_embedded_secret(rel: str, data: bytes) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(data):
            fail(f"SECRET_LIKE_CONTENT_BLOCKED:{rel}")


def make_multipart(filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----uaart-" + uuid.uuid4().hex
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
    )
    body.extend(data)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def api_url(remote_path: str) -> str:
    encoded = urllib.parse.quote(remote_path, safe="/")
    return f"https://{HOST}/api/v0/user/{urllib.parse.quote(USERNAME)}/files/path{encoded}"


def upload(remote_path: str, filename: str, data: bytes) -> int:
    body, multipart_type = make_multipart(filename, data)
    request = urllib.request.Request(
        api_url(remote_path),
        data=body,
        headers={
            "Authorization": f"Token {TOKEN}",
            "Content-Type": multipart_type,
            "User-Agent": "ua-art-autopilot-pythonanywhere-sync/1",
        },
        method="POST",
    )

    last_error = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = response.status
                response.read(4096)
            if status not in (200, 201):
                fail(f"UPLOAD_UNEXPECTED_STATUS:{remote_path}:{status}")
            return status
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                detail = exc.read(500).decode("utf-8", "replace")
                fail(f"UPLOAD_FAILED:{remote_path}:{exc.code}:{detail[:300]}")
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as exc:
            last_error = type(exc).__name__
            if attempt == 3:
                fail(f"UPLOAD_NETWORK_FAILED:{remote_path}:{last_error}")
        time.sleep(2 ** attempt)
    fail(f"UPLOAD_FAILED:{remote_path}:{last_error or 'unknown'}")


def append_summary(manifest: dict) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = [
        "## PythonAnywhere inbox sync",
        "",
        f"Status: **PASS**",
        f"Files uploaded: **{manifest['files_uploaded']}**",
        f"Remote root: `{manifest['remote_root']}`",
        "",
        "No files were executed, no web app was reloaded, and production was not touched.",
    ]
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> None:
    ensure_configuration()
    files = list_cloud_files()
    entries = []

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        reject_embedded_secret(rel, data)
        remote = REMOTE_ROOT + "/" + rel
        status = upload(remote, path.name, data)
        digest = sha256(data)
        entries.append(
            {
                "source": rel,
                "remote": remote,
                "bytes": len(data),
                "sha256": digest,
                "http_status": status,
            }
        )
        print(f"SYNCED {rel} -> {remote} sha256={digest} status={status}")

    manifest = {
        "status": "PASS",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "repository": os.environ.get("GITHUB_REPOSITORY", "art20021986-wq/ua-art-autopilot"),
        "commit": os.environ.get("GITHUB_SHA", "UNKNOWN"),
        "remote_root": REMOTE_ROOT,
        "files_uploaded": len(entries),
        "files": entries,
        "production_touched": False,
        "executed_remote_code": False,
        "webapp_reloaded": False,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    upload(REMOTE_ROOT + "/_sync_manifest.json", "_sync_manifest.json", manifest_bytes)
    append_summary(manifest)
    print(json.dumps({"status": "PASS", "files_uploaded": len(entries), "remote_root": REMOTE_ROOT}))


if __name__ == "__main__":
    main()
