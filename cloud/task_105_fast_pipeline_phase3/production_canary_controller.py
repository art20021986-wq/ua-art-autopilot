#!/usr/bin/env python3
"""GitHub-side controller for one bounded TASK105 FAST production canary."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

CONTRACT_ID = "UA-ART-FAST-PRODUCTION-CANARY-105-V1.0"
TASK_ID = "TASK105-FAST-PRODUCTION-CANARY"
HERE = pathlib.Path(__file__).resolve().parent
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_105_fast_pipeline_phase3"
REMOTE_SCRIPT = REMOTE + "/task105_fast_canary_remote.py"
REMOTE_PAYLOAD = REMOTE + "/task105_fast_canary_payload.txt"
REMOTE_RECEIPTS = {
    "install": REMOTE + "/task105_fast_canary_install_receipt.json",
    "rollback": REMOTE + "/task105_fast_canary_rollback_receipt.json",
}
COMMANDS = {
    mode: "cd %s && python3.10 task105_fast_canary_remote.py %s" % (REMOTE, mode)
    for mode in REMOTE_RECEIPTS
}
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
PUBLIC_MARKER = "https://www.uaart.com.ua/video/task105-fast-canary.txt"
PUBLIC_CORE = (
    "https://www.uaart.com.ua/video/index.html",
    "https://www.uaart.com.ua/video/katalog.html",
)
EVIDENCE = HERE / "production_canary_evidence.json"
REPORT = HERE / "PRODUCTION_CANARY_REPORT.md"
FINAL_RECEIPT = HERE.parents[1] / "state/receipts/TASK105-FAST-PRODUCTION-CANARY.json"
MAX_BYTES = 10 * 1024 * 1024


class ControllerError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".task105.tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def build_payload(run_id: str, commit_sha: str) -> bytes:
    safe_run = run_id if re.fullmatch(r"[0-9]{1,30}", run_id or "") else "LOCAL"
    safe_sha = commit_sha.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha or "") else "UNKNOWN"
    lines = [
        "UA_ART_FAST_PIPELINE_CANARY",
        "TASK_ID=" + TASK_ID,
        "CONTRACT_ID=" + CONTRACT_ID,
        "GITHUB_RUN_ID=" + safe_run,
        "GITHUB_SHA=" + safe_sha,
        "NO_CRM_WRITE=TRUE",
        "NO_EXISTING_SITE_FILE_WRITE=TRUE",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


class API:
    def __init__(self) -> None:
        self.token = (os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
        if not self.token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")

    def request(
        self,
        method: str,
        url: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        allowed: tuple[int, ...] = (200,),
    ) -> tuple[int, bytes]:
        all_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task105-fast-canary/1",
        }
        all_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=70) as response:
                status = int(response.status)
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError(
                "HTTP_%d:%s" % (status, urllib.parse.urlsplit(url).path)
            )
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + path)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, value: bytes) -> None:
        boundary = "----uaart-task105-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode("ascii"))
        body.extend(
            (
                'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
                "Content-Type: %s\r\n\r\n" % (filename, mime)
            ).encode("utf-8")
        )
        body.extend(value)
        body.extend(("\r\n--%s--\r\n" % boundary).encode("ascii"))
        for attempt in range(1, 6):
            status, _ = self.request(
                "POST",
                self.file_url(path),
                bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504),
            )
            if status in (200, 201):
                return
            if attempt < 5:
                time.sleep(min(3 * attempt, 12))
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def identifier(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        result = value.get("id") if isinstance(value, dict) else None
        return result if isinstance(result, int) and result > 0 else None

    def create_trigger(self, command: str, description: str) -> tuple[str, int]:
        moment = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)
        form = urllib.parse.urlencode(
            {
                "command": command,
                "description": description + " scheduled executor",
                "enabled": "true",
                "interval": "daily",
                "hour": moment.hour,
                "minute": moment.minute,
            }
        ).encode("utf-8")
        status, body = self.request(
            "POST",
            BASE + "schedule/",
            form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.identifier(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_SCHEDULED_EXECUTOR")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        self.request(
            "DELETE",
            BASE + "%s/%d/" % trigger,
            allowed=(200, 202, 204, 404),
        )

    def run_remote(self, mode: str, timeout_seconds: int = 420) -> dict[str, Any]:
        receipt = REMOTE_RECEIPTS[mode]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[mode], "task105-fast-canary-" + mode)
        try:
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    try:
                        result = json.loads(raw.decode("utf-8"))
                    except Exception as exc:
                        raise ControllerError("REMOTE_RECEIPT_INVALID:" + mode) from exc
                    if not isinstance(result, dict):
                        raise ControllerError("REMOTE_RECEIPT_NOT_OBJECT:" + mode)
                    return result
                time.sleep(5)
            raise ControllerError("REMOTE_RECEIPT_TIMEOUT:" + mode)
        finally:
            self.delete_trigger(trigger)


def _public_fetch(url: str, label: str) -> tuple[int, bytes]:
    delimiter = "&" if "?" in url else "?"
    request = urllib.request.Request(
        url
        + delimiter
        + urllib.parse.urlencode(
            {"task105_verify": uuid.uuid4().hex, "round": label}
        ),
        headers={
            "User-Agent": "UA-ART-task105-public-verify/1",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            status = int(response.status)
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read(MAX_BYTES + 1)
    except Exception as exc:
        raise ControllerError("PUBLIC_NETWORK:%s:%s" % (label, type(exc).__name__)) from exc
    if len(body) > MAX_BYTES:
        raise ControllerError("PUBLIC_TOO_LARGE:" + label)
    return status, body


def classify_public_target(
    marker_status: int,
    marker_body: bytes,
    home_status: int,
    home_body: bytes,
) -> str:
    if home_status != 200:
        raise ControllerError("PUBLIC_HOME_BASELINE_HTTP:%d" % home_status)
    if marker_status == 404:
        return "ABSENT_404"
    if marker_status == 200 and marker_body == home_body:
        return "ABSENT_HOME_FALLBACK"
    if marker_status == 200:
        return "EXISTING_FILE"
    raise ControllerError("PUBLIC_BASELINE_HTTP:%d" % marker_status)


def public_baseline() -> dict[str, Any]:
    marker_status, marker_body = _public_fetch(PUBLIC_MARKER, "baseline-marker")
    home_status, home_body = _public_fetch(PUBLIC_CORE[0], "baseline-home")
    kind = classify_public_target(marker_status, marker_body, home_status, home_body)
    return {
        "kind": kind,
        "status": marker_status,
        "sha256": sha(marker_body),
        "bytes": len(marker_body),
        "home_status": home_status,
        "home_sha256": sha(home_body),
        "home_bytes": len(home_body),
    }


def verify_marker(expected: bytes, label: str, attempts: int = 6) -> dict[str, Any]:
    last: tuple[int, bytes] | None = None
    for attempt in range(1, attempts + 1):
        last = _public_fetch(PUBLIC_MARKER, "%s-%d" % (label, attempt))
        status, body = last
        if status == 200 and body == expected:
            return {
                "status": "PASS",
                "label": label,
                "attempt": attempt,
                "http": status,
                "sha256": sha(body),
                "bytes": len(body),
                "checked_at_utc": utc_now(),
            }
        if attempt < attempts:
            time.sleep(5)
    status, body = last or (0, b"")
    raise ControllerError(
        "PUBLIC_MARKER_MISMATCH:%s:http=%d:sha=%s" % (label, status, sha(body))
    )


def verify_core(label: str) -> list[dict[str, Any]]:
    result = []
    for url in PUBLIC_CORE:
        status, body = _public_fetch(url, label + "-core")
        if status != 200 or len(body) < 500:
            raise ControllerError(
                "PUBLIC_CORE_FAIL:%s:http=%d:bytes=%d" % (url, status, len(body))
            )
        result.append(
            {
                "url_path": urllib.parse.urlsplit(url).path,
                "http": status,
                "bytes": len(body),
                "sha256": sha(body),
            }
        )
    return result


def validate_install(value: dict[str, Any], expected: bytes) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("mode") != "INSTALL" or value.get("production_write") is not True:
        raise ControllerError("INSTALL_MODE_OR_WRITE")
    if value.get("crm_write") is not False:
        raise ControllerError("INSTALL_CRM_SCOPE")
    if value.get("existing_site_file_write") is not False:
        raise ControllerError("INSTALL_EXISTING_SITE_SCOPE")
    if value.get("cloudflare_write") is not False or value.get("dns_write") is not False:
        raise ControllerError("INSTALL_EDGE_SCOPE")
    if not isinstance(value.get("before"), dict):
        raise ControllerError("INSTALL_BEFORE_MISSING")
    if value.get("changed_files") != ["/home/Carix/video/task105-fast-canary.txt"]:
        raise ControllerError("INSTALL_CHANGED_FILES")
    if value.get("expected_sha256") != sha(expected):
        raise ControllerError("INSTALL_EXPECTED_SHA")
    if not value.get("backup_root") or not value.get("backup_manifest"):
        raise ControllerError("INSTALL_BACKUP_MISSING")
    if value.get("rollback_ready") is not True:
        raise ControllerError("INSTALL_ROLLBACK_NOT_READY")
    if value.get("protected_before") != value.get("protected_after"):
        raise ControllerError("INSTALL_PROTECTED_DRIFT")
    if int(value.get("unexpected_changes", -1)) != 0:
        raise ControllerError("INSTALL_UNEXPECTED_CHANGE")


def validate_baseline_mapping(baseline: dict[str, Any], before: dict[str, Any]) -> None:
    kind = baseline.get("kind")
    if before.get("existed"):
        if kind != "EXISTING_FILE" or baseline.get("sha256") != before.get("sha256"):
            raise ControllerError("PUBLIC_LOCAL_PREIMAGE_MISMATCH")
    elif kind not in {"ABSENT_404", "ABSENT_HOME_FALLBACK"}:
        raise ControllerError("PUBLIC_LOCAL_ABSENCE_MISMATCH")


def validate_rollback(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("ROLLBACK_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("mode") != "ROLLBACK" or value.get("production_write") is not True:
        raise ControllerError("ROLLBACK_MODE_OR_WRITE")
    if value.get("crm_write") is not False:
        raise ControllerError("ROLLBACK_CRM_SCOPE")
    if value.get("protected_before") != value.get("protected_after"):
        raise ControllerError("ROLLBACK_PROTECTED_DRIFT")
    if int(value.get("unexpected_changes", -1)) != 0:
        raise ControllerError("ROLLBACK_UNEXPECTED_CHANGE")


def verify_rollback_public(before: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(1, 7):
        status, body = _public_fetch(PUBLIC_MARKER, "rollback-marker-%d" % attempt)
        home_status, home_body = _public_fetch(PUBLIC_CORE[0], "rollback-home-%d" % attempt)
        kind = classify_public_target(status, body, home_status, home_body)
        if before.get("existed"):
            ok = kind == "EXISTING_FILE" and sha(body) == before.get("sha256")
        else:
            ok = kind in {"ABSENT_404", "ABSENT_HOME_FALLBACK"}
        if ok:
            return {
                "status": "PASS",
                "attempt": attempt,
                "http": status,
                "kind": kind,
                "sha256": sha(body),
                "baseline_kind": baseline.get("kind"),
                "checked_at_utc": utc_now(),
            }
        if attempt < 6:
            time.sleep(5)
    raise ControllerError("PUBLIC_ROLLBACK_VERIFY_FAILED")


def report_text(evidence: dict[str, Any]) -> str:
    status = evidence.get("status", "FAIL")
    success = status == "PASS"
    lines = [
        "# TASK105 — Controlled FAST Production Canary",
        "",
        "STATUS: **%s**" % status,
        "",
        "- Production marker: %s" % ("LIVE VERIFIED" if success else "NOT ACCEPTED"),
        "- Existing site files changed: NO",
        "- CRM changed: NO",
        "- Cloudflare/DNS changed: NO",
        "- Backup: %s" % ((evidence.get("install") or {}).get("backup_root") or "NONE"),
        "- Rollback ready: %s" % ("YES" if success else "NOT CONFIRMED"),
        "- AI calls: 0",
        "- Errors: %s" % (
            "; ".join(evidence.get("errors") or []) if evidence.get("errors") else "NONE"
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    started = utc_now()
    payload = build_payload(
        os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_SHA", "")
    )
    evidence: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "task_id": TASK_ID,
        "status": "FAIL",
        "errors": [],
        "production_touched": False,
        "crm_write": False,
        "existing_site_file_write": False,
        "cloudflare_write": False,
        "dns_write": False,
        "ai_calls": 0,
        "started_at_utc": started,
    }
    api: API | None = None
    installed = False
    install: dict[str, Any] | None = None
    baseline: dict[str, Any] | None = None
    try:
        baseline = public_baseline()
        evidence["public_baseline"] = baseline
        api = API()
        remote_source = (HERE / "production_canary_remote.py").read_bytes()
        compile(remote_source.decode("utf-8"), "production_canary_remote.py", "exec")
        api.upload(REMOTE_SCRIPT, remote_source)
        api.upload(REMOTE_PAYLOAD, payload)
        evidence["transport"] = {
            "remote_script_sha256": sha(remote_source),
            "payload_sha256": sha(payload),
            "remote_root": REMOTE,
        }
        install = api.run_remote("install")
        evidence["install"] = install
        validate_install(install, payload)
        installed = True
        evidence["production_touched"] = True
        validate_baseline_mapping(baseline, install["before"])
        evidence["public_immediate"] = {
            "marker": verify_marker(payload, "immediate"),
            "core": verify_core("immediate"),
        }
        time.sleep(12)
        evidence["public_delayed"] = {
            "marker": verify_marker(payload, "delayed"),
            "core": verify_core("delayed"),
        }
        final_receipt = {
            "task_id": TASK_ID,
            "status": "FINISHED",
            "task_class": "FAST",
            "target_environment": "production",
            "tests": "PASS",
            "unexpected_changes": 0,
            "rollback_ready": True,
            "production_required": True,
            "backup": install["backup_root"],
            "production": "PASS",
            "live_verify": "PASS",
            "ai_calls": 0,
            "changed_files": install["changed_files"],
            "protected_files_unchanged": True,
            "started_at": started,
            "finished_at": utc_now(),
        }
        evidence["final_receipt"] = final_receipt
        evidence["status"] = "PASS"
        evidence["finished_at_utc"] = utc_now()
        atomic_json(FINAL_RECEIPT, final_receipt)
        atomic_json(EVIDENCE, evidence)
        atomic_text(REPORT, report_text(evidence))
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if installed and api is not None and install is not None:
            try:
                rollback = api.run_remote("rollback")
                validate_rollback(rollback)
                evidence["rollback"] = rollback
                evidence["rollback_public"] = verify_rollback_public(
                    install["before"], baseline or {}
                )
                evidence["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                evidence["status"] = "FAIL_ROLLBACK"
        evidence["finished_at_utc"] = utc_now()
        failed_receipt = {
            "task_id": TASK_ID,
            "status": evidence["status"],
            "task_class": "FAST",
            "target_environment": "production",
            "tests": "FAIL",
            "unexpected_changes": 0 if evidence["status"] == "ROLLED_BACK" else 1,
            "rollback_ready": evidence["status"] == "ROLLED_BACK",
            "production_required": True,
            "ai_calls": 0,
            "errors": evidence["errors"],
            "started_at": started,
            "finished_at": utc_now(),
        }
        atomic_json(FINAL_RECEIPT, failed_receipt)
        atomic_json(EVIDENCE, evidence)
        atomic_text(REPORT, report_text(evidence))
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
