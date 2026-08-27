#!/usr/bin/env python3
"""Filter and mirror the latest Claude-authored cloud deliverables to PythonAnywhere quarantine.

Safety properties:
- uploads only to /home/<user>/autopilot_inbox;
- never executes remote code, reloads the web app, or touches production/CRM;
- fail-closed filtering for path, symlink, size, extension, Python syntax and secret-like content;
- by default uploads only files named by Claude in cloud/latest_status.md, not the entire cloud history;
- handles PythonAnywhere throttling with bounded server-aware retry/backoff.
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
STATUS = CLOUD / "latest_status.md"

USERNAME = (os.environ.get("PYTHONANYWHERE_USERNAME") or "Carix").strip()
HOST = (os.environ.get("PYTHONANYWHERE_HOST") or "www.pythonanywhere.com").strip()
TOKEN = (os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
REMOTE_ROOT = (os.environ.get("PYTHONANYWHERE_REMOTE_ROOT") or f"/home/{USERNAME}/autopilot_inbox").rstrip("/")
SYNC_MODE = (os.environ.get("PYTHONANYWHERE_SYNC_MODE") or "claude_latest").strip().lower()

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_ATTEMPTS = 8
MIN_UPLOAD_INTERVAL_SECONDS = 1.5
ALLOWED_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".html", ".htm",
    ".css", ".js", ".csv", ".jsonl", ".toml", ".ini", ".cfg", ".sh", ".sql", ".proposed",
}
ALLOWED_BASENAMES = {".gitkeep"}
SECRET_PATTERNS = [
    ("anthropic_key", re.compile(rb"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("github_pat", re.compile(rb"github_pat_[A-Za-z0-9_]{20,}")),
    ("github_classic_pat", re.compile(rb"ghp_[A-Za-z0-9]{20,}")),
    ("private_key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]


def fail(message: str) -> "NoReturn":
    raise SystemExit(message)


def ensure_configuration() -> None:
    if not USERNAME:
        fail("PYTHONANYWHERE_USERNAME_MISSING")
    if not TOKEN:
        fail("PYTHONANYWHERE_API_TOKEN_MISSING")
    if HOST not in {"www.pythonanywhere.com", "eu.pythonanywhere.com"}:
        fail("PYTHONANYWHERE_HOST_INVALID")
    expected = f"/home/{USERNAME}/autopilot_inbox"
    if REMOTE_ROOT != expected and not REMOTE_ROOT.startswith(expected + "/"):
        fail("PYTHONANYWHERE_REMOTE_ROOT_UNSAFE")
    if SYNC_MODE not in {"claude_latest", "all"}:
        fail("PYTHONANYWHERE_SYNC_MODE_INVALID")


def _safe_cloud_path(rel: str) -> pathlib.Path:
    pure = pathlib.PurePosixPath(rel.strip())
    if pure.is_absolute() or not pure.parts or pure.parts[0] != "cloud" or ".." in pure.parts:
        fail(f"UNSAFE_CLOUD_PATH:{rel}")
    path = (ROOT / pathlib.Path(*pure.parts)).resolve(strict=False)
    cloud_root = CLOUD.resolve()
    if path == cloud_root or not path.is_relative_to(cloud_root):
        fail(f"UNSAFE_CLOUD_PATH:{rel}")
    return path


def _claude_latest_paths() -> list[pathlib.Path]:
    if not STATUS.is_file() or STATUS.is_symlink():
        fail("CLAUDE_STATUS_MISSING_OR_UNSAFE")
    text = STATUS.read_text(encoding="utf-8")
    match = re.search(r"(?m)^FILES_CREATED:\s*(.+?)\s*$", text)
    if not match:
        fail("CLAUDE_FILES_CREATED_MISSING")
    raw = [item.strip() for item in match.group(1).split(",") if item.strip()]
    if not raw or raw == ["NONE"]:
        fail("CLAUDE_FILES_CREATED_EMPTY")
    raw.extend(["cloud/latest_status.md", "cloud/owner_reply.md"])
    seen: set[str] = set()
    result: list[pathlib.Path] = []
    for rel in raw:
        if rel in seen:
            continue
        seen.add(rel)
        path = _safe_cloud_path(rel)
        if not path.exists():
            fail(f"CLAUDE_LISTED_FILE_MISSING:{rel}")
        result.append(path)
    return result


def _all_cloud_paths() -> list[pathlib.Path]:
    if not CLOUD.is_dir():
        fail("CLOUD_DIRECTORY_MISSING")
    return [p for p in sorted(CLOUD.rglob("*")) if p.is_file() and not p.is_symlink()]


def candidate_paths() -> list[pathlib.Path]:
    return _claude_latest_paths() if SYNC_MODE == "claude_latest" else _all_cloud_paths()


def filter_file(path: pathlib.Path) -> tuple[str, bytes, str]:
    if path.is_symlink() or not path.is_file():
        fail(f"UNSAFE_FILE_TYPE:{path}")
    resolved = path.resolve()
    if not resolved.is_relative_to(CLOUD.resolve()):
        fail(f"PATH_ESCAPE:{path}")
    rel = resolved.relative_to(ROOT.resolve()).as_posix()
    suffix = resolved.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES and resolved.name not in ALLOWED_BASENAMES:
        fail(f"UNSUPPORTED_EXTENSION:{rel}:{suffix or 'NONE'}")
    size = resolved.stat().st_size
    if size > MAX_FILE_BYTES:
        fail(f"FILE_TOO_LARGE:{rel}:{size}")
    data = resolved.read_bytes()
    for category, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            fail(f"SECRET_LIKE_CONTENT_BLOCKED:{rel}:{category}")
    if suffix == ".py":
        try:
            compile(data.decode("utf-8"), rel, "exec")
        except (UnicodeDecodeError, SyntaxError) as exc:
            fail(f"PYTHON_STATIC_CHECK_FAIL:{rel}:{type(exc).__name__}")
    digest = hashlib.sha256(data).hexdigest()
    return rel, data, digest


def make_multipart(filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----uaart-" + uuid.uuid4().hex
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend((
        f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode())
    body.extend(data)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def api_url(remote_path: str) -> str:
    encoded = urllib.parse.quote(remote_path, safe="/")
    return f"https://{HOST}/api/v0/user/{urllib.parse.quote(USERNAME)}/files/path{encoded}"


def _retry_delay(exc: urllib.error.HTTPError, detail: str, attempt: int) -> int:
    header = (exc.headers.get("Retry-After") or "").strip()
    if header.isdigit():
        return min(max(int(header) + 2, 5), 120)
    match = re.search(r"available in\s+(\d+)\s+seconds", detail, re.I)
    if match:
        return min(max(int(match.group(1)) + 2, 5), 120)
    return min(2 ** attempt, 30)


def upload(remote_path: str, filename: str, data: bytes) -> int:
    last_error = "unknown"
    for attempt in range(1, MAX_UPLOAD_ATTEMPTS + 1):
        body, multipart_type = make_multipart(filename, data)
        request = urllib.request.Request(
            api_url(remote_path),
            data=body,
            headers={
                "Authorization": f"Token {TOKEN}",
                "Content-Type": multipart_type,
                "User-Agent": "ua-art-autopilot-pythonanywhere-sync/2",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = response.status
                response.read(4096)
            if status not in (200, 201):
                fail(f"UPLOAD_UNEXPECTED_STATUS:{remote_path}:{status}")
            return status
        except urllib.error.HTTPError as exc:
            detail = exc.read(500).decode("utf-8", "replace")
            last_error = f"HTTP_{exc.code}"
            retryable = exc.code in {429, 500, 502, 503, 504}
            if not retryable or attempt >= MAX_UPLOAD_ATTEMPTS:
                fail(f"UPLOAD_FAILED:{remote_path}:{exc.code}:{detail[:300]}")
            delay = _retry_delay(exc, detail, attempt)
            print(f"UPLOAD_RETRY path={remote_path} attempt={attempt}/{MAX_UPLOAD_ATTEMPTS} wait={delay}s reason={last_error}")
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as exc:
            last_error = type(exc).__name__
            if attempt >= MAX_UPLOAD_ATTEMPTS:
                fail(f"UPLOAD_NETWORK_FAILED:{remote_path}:{last_error}")
            delay = min(2 ** attempt, 30)
            print(f"UPLOAD_RETRY path={remote_path} attempt={attempt}/{MAX_UPLOAD_ATTEMPTS} wait={delay}s reason={last_error}")
            time.sleep(delay)
    fail(f"UPLOAD_FAILED:{remote_path}:{last_error}")


def append_summary(manifest: dict) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write(
            "## PythonAnywhere filtered inbox sync\n\n"
            f"Status: **PASS**\n\n"
            f"Claude-filtered files uploaded: **{manifest['files_uploaded']}**\n\n"
            f"Remote root: `{manifest['remote_root']}`\n\n"
            "No files were executed, no web app was reloaded, and production/CRM were not touched.\n"
        )


def main() -> None:
    ensure_configuration()
    selected = candidate_paths()
    filtered = [filter_file(path) for path in selected]
    entries = []
    last_upload_at = 0.0
    for rel, data, digest in filtered:
        elapsed = time.monotonic() - last_upload_at
        if last_upload_at and elapsed < MIN_UPLOAD_INTERVAL_SECONDS:
            time.sleep(MIN_UPLOAD_INTERVAL_SECONDS - elapsed)
        remote = REMOTE_ROOT + "/" + rel
        status = upload(remote, pathlib.PurePosixPath(rel).name, data)
        last_upload_at = time.monotonic()
        entries.append({
            "source": rel,
            "remote": remote,
            "bytes": len(data),
            "sha256": digest,
            "http_status": status,
        })
        print(f"SYNCED {rel} -> {remote} sha256={digest} status={status}")

    manifest = {
        "status": "PASS",
        "filter": "claude_latest_status+static_safety" if SYNC_MODE == "claude_latest" else "all_cloud+static_safety",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "repository": os.environ.get("GITHUB_REPOSITORY", "art20021986-wq/ua-art-autopilot"),
        "commit": os.environ.get("GITHUB_SHA", "UNKNOWN"),
        "remote_root": REMOTE_ROOT,
        "files_uploaded": len(entries),
        "files": entries,
        "production_touched": False,
        "crm_touched": False,
        "executed_remote_code": False,
        "webapp_reloaded": False,
    }
    payload = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    upload(REMOTE_ROOT + "/_sync_manifest.json", "_sync_manifest.json", payload)
    append_summary(manifest)
    print(json.dumps({"status": "PASS", "files_uploaded": len(entries), "remote_root": REMOTE_ROOT}))


if __name__ == "__main__":
    main()
