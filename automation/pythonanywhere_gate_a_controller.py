#!/usr/bin/env python3
"""Execute and relay the owner-approved TASK 020 Gate A run.

This controller runs in GitHub Actions.  It never writes production files,
never reloads a web app, and never performs Gate B.  Its remote write scope is
strictly limited to the already-approved Gate A report/receipt namespaces and
temporary PythonAnywhere task metadata needed to start the no-argument safe-
inbox launcher.

Flow:
1. Verify TASK 020 owner authorization and Claude status in the checked-out repo.
2. Verify the safe-inbox sync manifest cryptographically matches the required
   local TASK 020 package.
3. Delete only the exact stale TASK 020 receipt path, if present.
4. Start a temporary PythonAnywhere always-on task; fall back to a one-shot
   scheduled task when always-on creation is unavailable.
5. Poll the exact receipt path, validate fail-closed safety fields and hashes.
6. Download only the approved report/receipt artifacts into a GitHub relay
   directory for an auditable commit.
7. Delete the temporary task in a finally block.

Python 3.11 stdlib only.  Secrets are never printed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASK_FILE = ROOT / "tasks" / "task_020.md"
LATEST_STATUS = ROOT / "cloud" / "latest_status.md"
PACKAGE_ROOT = ROOT / "cloud" / "ua_cards_unified"
RELAY_ROOT = ROOT / "cloud" / "gate_a_receipts" / "task_020"

USERNAME = (os.environ.get("PYTHONANYWHERE_USERNAME") or "Carix").strip()
HOST = (os.environ.get("PYTHONANYWHERE_HOST") or "www.pythonanywhere.com").strip()
TOKEN = (os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
GITHUB_RUN_ID = (os.environ.get("GITHUB_RUN_ID") or "local").strip()
GITHUB_SHA = (os.environ.get("GITHUB_SHA") or "UNKNOWN").strip()

SAFE_INBOX = "/home/Carix/autopilot_inbox/cloud/ua_cards_unified"
SYNC_MANIFEST_PATH = "/home/Carix/autopilot_inbox/_sync_manifest.json"
REMOTE_COMMAND = (
    "python3.10 "
    "/home/Carix/autopilot_inbox/cloud/ua_cards_unified/"
    "gate_a_task020_launcher.py"
)

REQUIRED_LOCAL_FILES = [
    "gate_a_task020_common.py",
    "gate_a_task020_preflight.py",
    "gate_a_task020_runner.py",
    "gate_a_task020_launcher.py",
    "GATE_A_TASK020_OPERATOR.md",
    "gate_a_task020_contract.json",
    "tests/test_gate_a_task020.py",
]

REMOTE_OUTPUTS = {
    "receipt": "/home/Carix/ua_cards_unified_gate_a_receipt/task_020_gate_a_receipt.json",
    "manifest": "/home/Carix/video/reports/ua_cards_unified/task_020_manifest.json",
    "results": "/home/Carix/video/reports/ua_cards_unified/task_020_results.json",
    "protected_hashes": "/home/Carix/video/reports/ua_cards_unified/task_020_protected_hashes.json",
    "progress": "/home/Carix/video/reports/ua_cards_unified/progress.json",
    "latest_status": "/home/Carix/video/reports/ua_cards_unified/latest_status.html",
    "preview_index": "/home/Carix/video/reports/ua_cards_unified/preview/index.html",
}

PUBLIC_URLS = {
    "latest_status": "https://www.uaart.com.ua/video/reports/ua_cards_unified/latest_status.html",
    "preview_index": "https://www.uaart.com.ua/video/reports/ua_cards_unified/preview/index.html",
}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
CARD_CODES = [f"UA-{i:04d}" for i in range(1, 10)]


class ControllerError(RuntimeError):
    pass


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def api_base() -> str:
    if HOST not in {"www.pythonanywhere.com", "eu.pythonanywhere.com"}:
        raise ControllerError("PYTHONANYWHERE_HOST_INVALID")
    if USERNAME != "Carix":
        raise ControllerError("PYTHONANYWHERE_USERNAME_INVALID")
    if not TOKEN:
        raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")
    return f"https://{HOST}/api/v0/user/{urllib.parse.quote(USERNAME)}/"


def request(
    method: str,
    url: str,
    *,
    form: dict[str, Any] | None = None,
    timeout: int = 60,
    allow_status: set[int] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    data = None
    headers = {
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "ua-art-gate-a-controller/1",
    }
    if form is not None:
        data = urllib.parse.urlencode(
            {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in form.items()}
        ).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            return response.status, body, response_headers
    except urllib.error.HTTPError as exc:
        body = exc.read(2048)
        if allow_status and exc.code in allow_status:
            return exc.code, body, {k.lower(): v for k, v in exc.headers.items()}
        detail = body.decode("utf-8", "replace")[:400]
        raise ControllerError(f"HTTP_{exc.code}:{url}:{detail}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionResetError) as exc:
        raise ControllerError(f"NETWORK_ERROR:{url}:{type(exc).__name__}") from exc


def file_url(path: str) -> str:
    if not path.startswith("/home/Carix/"):
        raise ControllerError(f"REMOTE_PATH_OUTSIDE_ACCOUNT:{path}")
    encoded = urllib.parse.quote(path, safe="/")
    return api_base() + "files/path" + encoded


def remote_get(path: str, *, missing_ok: bool = False) -> bytes | None:
    allowed = {404} if missing_ok else None
    status, body, _ = request("GET", file_url(path), allow_status=allowed)
    if status == 404 and missing_ok:
        return None
    if status != 200:
        raise ControllerError(f"REMOTE_GET_UNEXPECTED:{path}:{status}")
    return body


def remote_delete(path: str) -> None:
    status, _, _ = request("DELETE", file_url(path), allow_status={404})
    if status not in {204, 404}:
        raise ControllerError(f"REMOTE_DELETE_UNEXPECTED:{path}:{status}")


def parse_json_bytes(label: str, data: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControllerError(f"INVALID_JSON:{label}") from exc
    if not isinstance(obj, dict):
        raise ControllerError(f"JSON_NOT_OBJECT:{label}")
    return obj


def verify_repo_authorization() -> None:
    if not TASK_FILE.is_file():
        raise ControllerError("TASK_020_MISSING")
    task = TASK_FILE.read_text(encoding="utf-8")
    required_task_markers = [
        "OWNER_CONFIRMATION: «Подтверждаю»",
        "MODE: GATE_A_REAL_INPUTS_READ_ONLY",
        "PRODUCTION_WRITE: FORBIDDEN",
        "GATE_B: FORBIDDEN",
    ]
    for marker in required_task_markers:
        if marker not in task:
            raise ControllerError(f"TASK_020_AUTHORIZATION_MARKER_MISSING:{marker}")

    if not LATEST_STATUS.is_file():
        raise ControllerError("LATEST_STATUS_MISSING")
    status = LATEST_STATUS.read_text(encoding="utf-8")
    if not re.search(r"(?m)^TASK_ID:\s*task_020\s*$", status):
        raise ControllerError("LATEST_STATUS_NOT_TASK_020")
    if not re.search(r"(?m)^CLAUDE_STATUS:\s*DONE\s*$", status):
        raise ControllerError("TASK_020_CLAUDE_NOT_DONE")
    if re.search(r"(?m)^PRODUCTION_TOUCHED:\s*(?!NO\s*$)", status):
        raise ControllerError("LATEST_STATUS_PRODUCTION_SAFETY_INVALID")

    for rel in REQUIRED_LOCAL_FILES:
        path = PACKAGE_ROOT / rel
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise ControllerError(f"REQUIRED_LOCAL_FILE_INVALID:{rel}")
        resolved = path.resolve()
        if not resolved.is_relative_to(PACKAGE_ROOT.resolve()):
            raise ControllerError(f"REQUIRED_LOCAL_FILE_ESCAPE:{rel}")
        if path.suffix == ".py":
            compile(path.read_text(encoding="utf-8"), str(path), "exec")


def verify_sync_manifest() -> dict[str, Any]:
    raw = remote_get(SYNC_MANIFEST_PATH)
    assert raw is not None
    manifest = parse_json_bytes("sync_manifest", raw)
    if manifest.get("status") != "PASS":
        raise ControllerError("SYNC_MANIFEST_NOT_PASS")
    if manifest.get("remote_root") != "/home/Carix/autopilot_inbox":
        raise ControllerError("SYNC_MANIFEST_REMOTE_ROOT_INVALID")
    if manifest.get("production_touched") is not False:
        raise ControllerError("SYNC_MANIFEST_PRODUCTION_FLAG_INVALID")
    if manifest.get("executed_remote_code") is not False:
        raise ControllerError("SYNC_MANIFEST_EXECUTION_FLAG_INVALID")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ControllerError("SYNC_MANIFEST_FILES_INVALID")
    by_source: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("source"), str):
            by_source[entry["source"]] = entry

    for rel in REQUIRED_LOCAL_FILES:
        source = f"cloud/ua_cards_unified/{rel}"
        entry = by_source.get(source)
        if not entry:
            raise ControllerError(f"SYNC_MANIFEST_REQUIRED_SOURCE_MISSING:{source}")
        expected_remote = f"/home/Carix/autopilot_inbox/{source}"
        if entry.get("remote") != expected_remote:
            raise ControllerError(f"SYNC_MANIFEST_REMOTE_MISMATCH:{source}")
        local_hash = sha256_file(PACKAGE_ROOT / rel)
        if entry.get("sha256") != local_hash:
            raise ControllerError(f"SYNC_MANIFEST_HASH_MISMATCH:{source}")
        remote_data = remote_get(expected_remote)
        assert remote_data is not None
        if sha256_bytes(remote_data) != local_hash:
            raise ControllerError(f"REMOTE_FILE_HASH_MISMATCH:{source}")
    return manifest


def _json_response(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def create_always_on(started_at: dt.datetime) -> tuple[str, int] | None:
    description = f"UA ART Gate A task020 GitHub run {GITHUB_RUN_ID}"
    url = api_base() + "always_on/"
    try:
        status, body, _ = request(
            "POST",
            url,
            form={"command": REMOTE_COMMAND, "description": description, "enabled": True},
            allow_status={400, 403, 404, 409},
        )
    except ControllerError:
        return None
    if status not in {200, 201, 202}:
        return None
    obj = _json_response(body)
    task_id = obj.get("id") if isinstance(obj, dict) else None
    if not isinstance(task_id, int):
        return None
    return "always_on", task_id


def create_scheduled(started_at: dt.datetime) -> tuple[str, int] | None:
    run_at = started_at + dt.timedelta(minutes=2)
    description = f"UA ART Gate A task020 GitHub run {GITHUB_RUN_ID}"
    url = api_base() + "schedule/"
    try:
        status, body, _ = request(
            "POST",
            url,
            form={
                "command": REMOTE_COMMAND,
                "enabled": True,
                "interval": "daily",
                "hour": run_at.hour,
                "minute": run_at.minute,
                "description": description,
            },
            allow_status={400, 403, 404, 409},
        )
    except ControllerError:
        return None
    if status not in {200, 201, 202}:
        return None
    obj = _json_response(body)
    task_id = obj.get("id") if isinstance(obj, dict) else None
    if not isinstance(task_id, int):
        return None
    return "schedule", task_id


def delete_trigger(trigger: tuple[str, int] | None) -> None:
    if trigger is None:
        return
    kind, task_id = trigger
    endpoint = "always_on" if kind == "always_on" else "schedule"
    url = api_base() + f"{endpoint}/{task_id}/"
    try:
        request("DELETE", url, allow_status={404})
    except ControllerError as exc:
        print(f"CLEANUP_WARNING:{type(exc).__name__}", file=sys.stderr)


def wait_for_receipt(started_at: dt.datetime, timeout_seconds: int = 1200) -> bytes:
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        data = remote_get(REMOTE_OUTPUTS["receipt"], missing_ok=True)
        if data:
            receipt = parse_json_bytes("receipt", data)
            generated = receipt.get("generated_at_utc") or receipt.get("completed_at_utc")
            if isinstance(generated, str):
                try:
                    parsed = dt.datetime.fromisoformat(generated.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=dt.timezone.utc)
                    if parsed < started_at - dt.timedelta(seconds=5):
                        remote_delete(REMOTE_OUTPUTS["receipt"])
                        time.sleep(5)
                        continue
                except ValueError:
                    pass
            return data
        if attempt % 6 == 0:
            print(f"WAITING_FOR_GATE_A_RECEIPT attempt={attempt}")
        time.sleep(10)
    raise ControllerError("GATE_A_RECEIPT_TIMEOUT")


def _require_false(receipt: dict[str, Any], key: str) -> None:
    if receipt.get(key) is not False:
        raise ControllerError(f"RECEIPT_SAFETY_FIELD_INVALID:{key}")


def _extract_per_card(receipt: dict[str, Any]) -> dict[str, Any]:
    value = receipt.get("per_card")
    if isinstance(value, dict):
        return value
    value = receipt.get("per_card_status")
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        out: dict[str, Any] = {}
        for item in value:
            if isinstance(item, dict):
                code = item.get("code") or item.get("card_id")
                if isinstance(code, str):
                    out[code] = item
        return out
    raise ControllerError("RECEIPT_PER_CARD_INVALID")


def validate_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("task_id") != "task_020":
        raise ControllerError("RECEIPT_TASK_ID_INVALID")
    if receipt.get("mode") != "GATE_A_REAL_INPUTS_READ_ONLY":
        raise ControllerError("RECEIPT_MODE_INVALID")
    if receipt.get("gate_status") not in {"BLOCKED", "AWAITING_GATE_B"}:
        raise ControllerError("RECEIPT_GATE_STATUS_INVALID")
    for key in [
        "production_write",
        "crm_write",
        "gate_b_executed",
        "wsgi_reloaded",
        "ua0009_published",
    ]:
        _require_false(receipt, key)
    if receipt.get("unexpected_protected_changes") != 0:
        raise ControllerError("RECEIPT_PROTECTED_CHANGES_NONZERO")

    for key in ["manifest_sha256", "runner_sha256"]:
        value = receipt.get(key)
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise ControllerError(f"RECEIPT_HASH_INVALID:{key}")

    for key in ["input_hashes", "output_hashes"]:
        value = receipt.get(key)
        if not isinstance(value, dict) or not value:
            raise ControllerError(f"RECEIPT_HASH_MAP_INVALID:{key}")
        for path, digest in value.items():
            if not isinstance(path, str) or not isinstance(digest, str) or not HEX64.fullmatch(digest):
                raise ControllerError(f"RECEIPT_HASH_MAP_ENTRY_INVALID:{key}")

    per_card = _extract_per_card(receipt)
    missing = [code for code in CARD_CODES if code not in per_card]
    if missing:
        raise ControllerError("RECEIPT_CARD_STATUS_MISSING:" + ",".join(missing))


def public_http_statuses() -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    cache_buster = int(time.time())
    for name, url in PUBLIC_URLS.items():
        request_url = url + ("&" if "?" in url else "?") + f"gate_a={cache_buster}"
        req = urllib.request.Request(request_url, headers={"User-Agent": "ua-art-gate-a-controller/1"})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                response.read(512)
                results[name] = {"status": response.status, "final_url": response.geturl()}
        except urllib.error.HTTPError as exc:
            results[name] = {"status": exc.code, "error": "HTTPError"}
        except Exception as exc:
            results[name] = {"status": None, "error": type(exc).__name__}
    return results


def write_relay(
    *,
    started_at: dt.datetime,
    completed_at: dt.datetime,
    trigger: tuple[str, int],
    sync_manifest: dict[str, Any],
    receipt_bytes: bytes,
) -> dict[str, Any]:
    RELAY_ROOT.mkdir(parents=True, exist_ok=True)
    receipt = parse_json_bytes("receipt", receipt_bytes)
    validate_receipt(receipt)

    downloaded: dict[str, dict[str, Any]] = {}
    filenames = {
        "receipt": "task_020_gate_a_receipt.json",
        "manifest": "task_020_manifest.json",
        "results": "task_020_results.json",
        "protected_hashes": "task_020_protected_hashes.json",
        "progress": "progress.json",
        "latest_status": "latest_status.html",
        "preview_index": "preview_index.html",
    }
    for key, remote_path in REMOTE_OUTPUTS.items():
        data = receipt_bytes if key == "receipt" else remote_get(remote_path)
        if data is None:
            raise ControllerError(f"REMOTE_OUTPUT_MISSING:{key}")
        local_path = RELAY_ROOT / filenames[key]
        local_path.write_bytes(data)
        downloaded[key] = {
            "remote_path": remote_path,
            "local_path": local_path.relative_to(ROOT).as_posix(),
            "bytes": len(data),
            "sha256": sha256_bytes(data),
        }

    public_checks = public_http_statuses()
    public_pass = all(item.get("status") == 200 for item in public_checks.values())

    report = {
        "controller_status": "PASS" if public_pass else "BLOCKED_PUBLIC_HTTP",
        "task_id": "task_020",
        "owner_confirmation": True,
        "mode": "GATE_A_REAL_INPUTS_READ_ONLY",
        "started_at_utc": iso(started_at),
        "completed_at_utc": iso(completed_at),
        "github_run_id": GITHUB_RUN_ID,
        "github_sha": GITHUB_SHA,
        "remote_trigger": {"kind": trigger[0], "id": trigger[1]},
        "sync_manifest_sha256": sha256_bytes(
            json.dumps(sync_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "remote_gate_status": receipt.get("gate_status"),
        "production_write": False,
        "crm_write": False,
        "gate_b_executed": False,
        "public_http_checks": public_checks,
        "downloaded": downloaded,
    }
    (RELAY_ROOT / "controller_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return report


def main() -> int:
    started_at = utc_now()
    trigger: tuple[str, int] | None = None
    try:
        verify_repo_authorization()
        sync_manifest = verify_sync_manifest()
        remote_delete(REMOTE_OUTPUTS["receipt"])

        trigger = create_always_on(started_at)
        if trigger is None:
            trigger = create_scheduled(started_at)
        if trigger is None:
            raise ControllerError("NO_REMOTE_EXECUTION_MECHANISM_AVAILABLE")

        receipt_bytes = wait_for_receipt(started_at)
        completed_at = utc_now()
        write_relay(
            started_at=started_at,
            completed_at=completed_at,
            trigger=trigger,
            sync_manifest=sync_manifest,
            receipt_bytes=receipt_bytes,
        )
        return 0
    except ControllerError as exc:
        RELAY_ROOT.mkdir(parents=True, exist_ok=True)
        error_report = {
            "controller_status": "ERROR",
            "task_id": "task_020",
            "mode": "GATE_A_REAL_INPUTS_READ_ONLY",
            "started_at_utc": iso(started_at),
            "failed_at_utc": iso(utc_now()),
            "error": str(exc),
            "production_write": False,
            "crm_write": False,
            "gate_b_executed": False,
        }
        (RELAY_ROOT / "controller_error.json").write_text(
            json.dumps(error_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"GATE_A_CONTROLLER_ERROR:{exc}", file=sys.stderr)
        return 1
    finally:
        delete_trigger(trigger)


if __name__ == "__main__":
    raise SystemExit(main())
