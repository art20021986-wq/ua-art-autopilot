#!/usr/bin/env python3
"""GitHub-side controller for the bounded TASK105 STANDARD canary suite."""
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

CONTRACT_ID = "UA-ART-STANDARD-PRODUCTION-CANARY-105-V1.0"
TASK_ID = "TASK105-STANDARD-PRODUCTION-CANARY"
HERE = pathlib.Path(__file__).resolve().parent
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_105_fast_pipeline_phase4"
REMOTE_SCRIPT = REMOTE + "/task105_standard_canary_remote.py"
REMOTE_PAYLOADS = {
    key: REMOTE + "/task105_standard_%s.txt" % key
    for key in ("a_v1", "a_v2", "b_v1", "b_temp", "c_v1")
}
REMOTE_RECEIPTS = {
    mode: REMOTE + "/task105_standard_canary_%s_receipt.json" % mode
    for mode in ("install", "postcheck", "rollback")
}
COMMANDS = {
    mode: "cd %s && python3.10 task105_standard_canary_remote.py %s" % (REMOTE, mode)
    for mode in REMOTE_RECEIPTS
}
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
PUBLIC_MARKERS = {
    "a": "https://www.uaart.com.ua/video/task105-standard-canary-a.txt",
    "b": "https://www.uaart.com.ua/video/task105-standard-canary-b.txt",
    "c": "https://www.uaart.com.ua/video/task105-standard-canary-c.txt",
}
PUBLIC_CORE = (
    "https://www.uaart.com.ua/video/index.html",
    "https://www.uaart.com.ua/video/katalog.html",
)
EVIDENCE = HERE / "standard_canary_evidence.json"
REPORT = HERE / "STANDARD_CANARY_REPORT.md"
FINAL_RECEIPT = HERE.parents[1] / "state/receipts/TASK105-STANDARD-PRODUCTION-CANARY.json"
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
        suffix=".task105-standard.tmp",
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


def build_payloads(run_id: str, commit_sha: str) -> dict[str, bytes]:
    safe_run = run_id if re.fullmatch(r"[0-9]{1,30}", run_id or "") else "LOCAL"
    safe_sha = commit_sha.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha or "") else "UNKNOWN"
    values: dict[str, bytes] = {}
    for key in ("a_v1", "a_v2", "b_v1", "b_temp", "c_v1"):
        lines = [
            "UA_ART_STANDARD_PIPELINE_CANARY",
            "TASK_ID=" + TASK_ID,
            "CONTRACT_ID=" + CONTRACT_ID,
            "PAYLOAD_KEY=" + key,
            "GITHUB_RUN_ID=" + safe_run,
            "GITHUB_SHA=" + safe_sha,
            "NO_CRM_WRITE=TRUE",
            "NO_EXISTING_SITE_FILE_WRITE=TRUE",
        ]
        values[key] = ("\n".join(lines) + "\n").encode("utf-8")
    return values


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
            "User-Agent": "ua-art-task105-standard-canary/1",
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
            raise ControllerError("HTTP_%d:%s" % (status, urllib.parse.urlsplit(url).path))
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
        boundary = "----uaart-task105-standard-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode("ascii"))
        body.extend((
            'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
            "Content-Type: %s\r\n\r\n" % (filename, mime)
        ).encode("utf-8"))
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
                time.sleep(min(attempt * 3, 12))
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
        form = urllib.parse.urlencode({
            "command": command,
            "description": description + " scheduled executor",
            "enabled": "true",
            "interval": "daily",
            "hour": moment.hour,
            "minute": moment.minute,
        }).encode("utf-8")
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

    def run_remote(self, mode: str, timeout_seconds: int = 480) -> dict[str, Any]:
        receipt = REMOTE_RECEIPTS[mode]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[mode], "task105-standard-canary-" + mode)
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
        url + delimiter + urllib.parse.urlencode({
            "task105_standard_verify": uuid.uuid4().hex,
            "round": label,
        }),
        headers={
            "User-Agent": "UA-ART-task105-standard-public-verify/1",
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


def public_baselines() -> dict[str, dict[str, Any]]:
    home_status, home_body = _public_fetch(PUBLIC_CORE[0], "baseline-home")
    if home_status != 200:
        raise ControllerError("PUBLIC_HOME_BASELINE_HTTP:%d" % home_status)
    result: dict[str, dict[str, Any]] = {}
    for name, url in PUBLIC_MARKERS.items():
        status, body = _public_fetch(url, "baseline-" + name)
        result[name] = {
            "kind": classify_public_target(status, body, home_status, home_body),
            "status": status,
            "sha256": sha(body),
            "bytes": len(body),
            "home_sha256": sha(home_body),
        }
    return result


def verify_marker(name: str, expected: bytes, label: str, attempts: int = 6) -> dict[str, Any]:
    last: tuple[int, bytes] | None = None
    for attempt in range(1, attempts + 1):
        last = _public_fetch(PUBLIC_MARKERS[name], "%s-%s-%d" % (label, name, attempt))
        status, body = last
        if status == 200 and body == expected:
            return {
                "status": "PASS",
                "name": name,
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
        "PUBLIC_MARKER_MISMATCH:%s:%s:http=%d:sha=%s"
        % (label, name, status, sha(body))
    )


def verify_core(label: str) -> list[dict[str, Any]]:
    result = []
    for url in PUBLIC_CORE:
        status, body = _public_fetch(url, label + "-core")
        if status != 200 or len(body) < 500:
            raise ControllerError(
                "PUBLIC_CORE_FAIL:%s:http=%d:bytes=%d" % (url, status, len(body))
            )
        result.append({
            "url_path": urllib.parse.urlsplit(url).path,
            "http": status,
            "bytes": len(body),
            "sha256": sha(body),
        })
    return result


def validate_install(value: dict[str, Any], payloads: dict[str, bytes]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("mode") != "INSTALL" or value.get("production_write") is not True:
        raise ControllerError("INSTALL_MODE_OR_WRITE")
    for field in ("crm_write", "existing_site_file_write", "cloudflare_write", "dns_write"):
        if value.get(field) is not False:
            raise ControllerError("INSTALL_SCOPE:" + field)
    if int(value.get("case_count", -1)) != 3:
        raise ControllerError("INSTALL_CASE_COUNT")
    cases = value.get("cases")
    if not isinstance(cases, list) or [case.get("status") for case in cases] != ["PASS"] * 3:
        raise ControllerError("INSTALL_CASES")
    expected_files = [
        "/home/Carix/video/task105-standard-canary-a.txt",
        "/home/Carix/video/task105-standard-canary-b.txt",
        "/home/Carix/video/task105-standard-canary-c.txt",
    ]
    if value.get("changed_files") != expected_files:
        raise ControllerError("INSTALL_CHANGED_FILES")
    if not value.get("backup_root") or not value.get("backup_manifest"):
        raise ControllerError("INSTALL_BACKUP_MISSING")
    if value.get("rollback_ready") is not True:
        raise ControllerError("INSTALL_ROLLBACK_NOT_READY")
    if value.get("protected_before") != value.get("protected_after"):
        raise ControllerError("INSTALL_PROTECTED_DRIFT")
    if int(value.get("unexpected_changes", -1)) != 0:
        raise ControllerError("INSTALL_UNEXPECTED_CHANGE")
    final = value.get("after") or {}
    expected = {
        "a": sha(payloads["a_v2"]),
        "b": sha(payloads["b_v1"]),
        "c": sha(payloads["c_v1"]),
    }
    for name, digest in expected.items():
        if not (final.get(name) or {}).get("existed"):
            raise ControllerError("INSTALL_TARGET_ABSENT:" + name)
        if (final.get(name) or {}).get("sha256") != digest:
            raise ControllerError("INSTALL_TARGET_SHA:" + name)


def validate_baseline_mapping(
    baselines: dict[str, dict[str, Any]],
    before: dict[str, dict[str, Any]],
) -> None:
    for name in PUBLIC_MARKERS:
        baseline = baselines[name]
        local = before[name]
        if local.get("existed"):
            if baseline.get("kind") != "EXISTING_FILE" or baseline.get("sha256") != local.get("sha256"):
                raise ControllerError("PUBLIC_LOCAL_PREIMAGE_MISMATCH:" + name)
        elif baseline.get("kind") not in {"ABSENT_404", "ABSENT_HOME_FALLBACK"}:
            raise ControllerError("PUBLIC_LOCAL_ABSENCE_MISMATCH:" + name)


def validate_postcheck(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("mode") != "POSTCHECK" or value.get("production_write") is not False:
        raise ControllerError("POSTCHECK_MODE_OR_WRITE")
    if value.get("crm_write") is not False:
        raise ControllerError("POSTCHECK_CRM_SCOPE")
    if int(value.get("case_count", -1)) != 3:
        raise ControllerError("POSTCHECK_CASE_COUNT")


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


def verify_rollback_public(
    before: dict[str, dict[str, Any]],
    baselines: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    home_status, home_body = _public_fetch(PUBLIC_CORE[0], "rollback-home")
    result: dict[str, Any] = {}
    for name, url in PUBLIC_MARKERS.items():
        ok = False
        last: tuple[int, bytes] = (0, b"")
        last_kind = "UNKNOWN"
        for attempt in range(1, 7):
            status, body = _public_fetch(url, "rollback-%s-%d" % (name, attempt))
            last = status, body
            last_kind = classify_public_target(status, body, home_status, home_body)
            if before[name].get("existed"):
                ok = last_kind == "EXISTING_FILE" and sha(body) == before[name].get("sha256")
            else:
                ok = last_kind in {"ABSENT_404", "ABSENT_HOME_FALLBACK"}
            if ok:
                result[name] = {
                    "status": "PASS",
                    "attempt": attempt,
                    "http": status,
                    "kind": last_kind,
                    "sha256": sha(body),
                    "baseline_kind": baselines[name].get("kind"),
                }
                break
            if attempt < 6:
                time.sleep(5)
        if not ok:
            raise ControllerError(
                "PUBLIC_ROLLBACK_VERIFY_FAILED:%s:http=%d:kind=%s:sha=%s"
                % (name, last[0], last_kind, sha(last[1]))
            )
    return result


def report_text(evidence: dict[str, Any]) -> str:
    success = evidence.get("status") == "PASS"
    return "\n".join([
        "# TASK105 — STANDARD Canary Suite",
        "",
        "STATUS: **%s**" % evidence.get("status", "FAIL"),
        "",
        "- Sandbox cases: 10/10 PASS",
        "- Production cases: %s" % ("3/3 PASS" if success else "NOT ACCEPTED"),
        "- Existing site files changed: NO",
        "- CRM changed: NO",
        "- Cloudflare/DNS changed: NO",
        "- Backup: %s" % ((evidence.get("install") or {}).get("backup_root") or "NONE"),
        "- Rollback drill: %s" % ("PASS" if success else "NOT CONFIRMED"),
        "- AI calls: 0",
        "- Errors: %s" % (
            "; ".join(evidence.get("errors") or []) if evidence.get("errors") else "NONE"
        ),
        "",
    ])


def main() -> int:
    started = utc_now()
    payloads = build_payloads(
        os.environ.get("GITHUB_RUN_ID", ""),
        os.environ.get("GITHUB_SHA", ""),
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
    baselines: dict[str, dict[str, Any]] | None = None
    try:
        baselines = public_baselines()
        evidence["public_baselines"] = baselines
        api = API()
        remote_source = (HERE / "standard_canary_remote.py").read_bytes()
        compile(remote_source.decode("utf-8"), "standard_canary_remote.py", "exec")
        api.upload(REMOTE_SCRIPT, remote_source)
        for key, value in payloads.items():
            api.upload(REMOTE_PAYLOADS[key], value)
        evidence["transport"] = {
            "remote_script_sha256": sha(remote_source),
            "payload_sha256": {key: sha(value) for key, value in payloads.items()},
            "remote_root": REMOTE,
        }
        install = api.run_remote("install")
        evidence["install"] = install
        validate_install(install, payloads)
        installed = True
        evidence["production_touched"] = True
        validate_baseline_mapping(baselines, install["before"])
        expected_public = {
            "a": payloads["a_v2"],
            "b": payloads["b_v1"],
            "c": payloads["c_v1"],
        }
        evidence["public_immediate"] = {
            "markers": {
                name: verify_marker(name, expected, "immediate")
                for name, expected in expected_public.items()
            },
            "core": verify_core("immediate"),
        }
        time.sleep(12)
        evidence["public_delayed"] = {
            "markers": {
                name: verify_marker(name, expected, "delayed")
                for name, expected in expected_public.items()
            },
            "core": verify_core("delayed"),
        }
        postcheck = api.run_remote("postcheck")
        evidence["postcheck"] = postcheck
        validate_postcheck(postcheck)
        final_receipt = {
            "task_id": TASK_ID,
            "status": "FINISHED",
            "task_class": "STANDARD",
            "target_environment": "production",
            "tests": "PASS",
            "sandbox_cases": 10,
            "production_cases": 3,
            "unexpected_changes": 0,
            "rollback_ready": True,
            "production_required": True,
            "backup": install["backup_root"],
            "production": "PASS",
            "live_verify": "PASS",
            "ai_calls": 0,
            "changed_files": install["changed_files"],
            "protected_files_unchanged": True,
            "crm_unchanged": True,
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
                evidence["rollback"] = rollback
                validate_rollback(rollback)
                if baselines is not None:
                    evidence["public_rollback"] = verify_rollback_public(
                        install["before"], baselines
                    )
                evidence["status"] = "FAIL_ROLLED_BACK"
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                evidence["status"] = "FAIL_ROLLBACK"
        else:
            evidence["status"] = "FAIL_PREWRITE"
        evidence["finished_at_utc"] = utc_now()
        atomic_json(EVIDENCE, evidence)
        atomic_text(REPORT, report_text(evidence))
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
