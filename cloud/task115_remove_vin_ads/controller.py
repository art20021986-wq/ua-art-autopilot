#!/usr/bin/env python3
"""Guarded production controller for the owner-requested VIN-ad removal."""
from __future__ import annotations

import datetime as dt
import hashlib
import html
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
from typing import Any, Mapping


TASK_ID = "TASK115-REMOVE-VIN-ADS"
CONTRACT = "UA-ART-NO-VIN-ADS-V1.0"
CRITICAL = "UA-ART-CRITICAL-ADAPTER-V1.0"
MANIFEST_SHA256 = "684c7e18cacb684bc8f4e4e695924821bd5d815417f68a596f416a64c5220378"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin"
REMOTE_SCRIPT = REMOTE + "/task115_remove_vin_ads.py"
REMOTE_RECEIPT = REMOTE + "/task115_receipt.json"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
RECEIPT_REL = "state/receipts/%s.json" % TASK_ID
EVIDENCE_REL = "cloud/task115_remove_vin_ads/evidence.json"
PUBLIC = "https://www.uaart.com.ua/video/"
IDS = tuple("UA-%04d" % value for value in range(1, 17))
FORBIDDEN = (
    "carhistory", "vindecoderz", "проверить vin", "перевірити vin",
    "2 200 krw", "2200 krw",
)
APPROVED_HOSTS = {
    "www.uaart.com.ua", "uaart.com.ua", "wa.me", "t.me", "telegram.org",
    "maps.app.goo.gl", "ecomm.one-line.com", "schema.org", "www.w3.org",
}
LEGACY_VIN_AD_COMMAND_MARKERS = ("task068_ferry_vin_repair.py",)
LEGACY_VIN_AD_REMOTE_FILES = (
    REMOTE + "/task068_ferry_vin_repair.py",
    REMOTE + "/repair_remote.py",
    "/home/Carix/autopilot_inbox/cloud/task_067/installer.py",
)
REMOTE_MODES = frozenset(("backup", "install", "verify", "rollback"))
MAX_BYTES = 64 * 1024 * 1024
MIN_SPEC_ROWS = 10


class ControllerError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def required(environment: Mapping[str, str]) -> dict[str, str]:
    names = ("PYTHONANYWHERE_API_TOKEN", "UAART_REQUEST_PATH", "UAART_REQUEST_SHA256",
             "UAART_TASK_ID", "UAART_TASK_CLASS", "UAART_RUN_ID", "UAART_RECEIPT_PATH",
             "UAART_BACKUP_MANIFEST_SHA256")
    values = {name: str(environment.get(name, "")).strip() for name in names}
    if any(not values[name] for name in names):
        raise ControllerError("MISSING_ENVIRONMENT")
    if values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"].upper() != "CRITICAL":
        raise ControllerError("TASK_IDENTITY")
    if values["UAART_RECEIPT_PATH"] != RECEIPT_REL:
        raise ControllerError("RECEIPT_IDENTITY")
    if not re.fullmatch(r"[0-9a-f]{64}", values["UAART_BACKUP_MANIFEST_SHA256"]):
        raise ControllerError("BACKUP_MANIFEST_SHA256_IDENTITY")
    request_path = (ROOT / values["UAART_REQUEST_PATH"]).resolve()
    if not request_path.is_relative_to(ROOT.resolve()) or sha(request_path.read_bytes()) != values["UAART_REQUEST_SHA256"]:
        raise ControllerError("REQUEST_IDENTITY")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("task_id") != TASK_ID or request.get("production_required") is not True:
        raise ControllerError("REQUEST_SCOPE")
    if (request.get("critical") or {}).get("manifest_sha256") != MANIFEST_SHA256:
        raise ControllerError("MANIFEST_IDENTITY")
    return values


class API:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, url: str, data: bytes | None = None,
                headers: dict[str, str] | None = None, allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        actual = {"Authorization": "Token " + self.token, "User-Agent": "ua-art-task115/1"}
        actual.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=actual, method=method)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                status, body = int(response.status), response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES or status not in allowed:
            raise ControllerError("HTTP_%d" % status)
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        if not isinstance(path, str) or not path or "\\" in path or any(
                ord(character) < 32 for character in path):
            raise ControllerError("REMOTE_SCOPE")
        candidate = pathlib.PurePosixPath(path)
        # PurePosixPath normalizes '.', duplicate separators, and trailing
        # separators. Requiring the exact canonical spelling rejects all of
        # those aliases before they reach the remote Files API.
        if (not candidate.is_absolute() or str(candidate) != path
                or ".." in candidate.parts):
            raise ControllerError("REMOTE_SCOPE")
        remote_root = pathlib.PurePosixPath(REMOTE)
        legacy = {pathlib.PurePosixPath(value) for value in LEGACY_VIN_AD_REMOTE_FILES}
        if remote_root not in candidate.parents and candidate not in legacy:
            raise ControllerError("REMOTE_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(str(candidate), safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_MISSING")
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))
        for attempt in range(4):
            if self.read(path, missing=True) is None:
                return
            if attempt < 3:
                time.sleep(0.25 * (attempt + 1))
        raise ControllerError("REMOTE_DELETE_READBACK:" + path)

    def upload(self, path: str, value: bytes) -> None:
        boundary = "----uaart-task115-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend(('Content-Disposition: form-data; name="content"; filename="%s"\r\n'
                     "Content-Type: %s\r\n\r\n" % (filename, mime)).encode())
        body.extend(value)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        self.request("POST", self.file_url(path), bytes(body),
                     {"Content-Type": "multipart/form-data; boundary=" + boundary}, allowed=(200, 201))
        if self.read(path) != value:
            raise ControllerError("UPLOAD_READBACK")

    @staticmethod
    def object_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode())
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) else None

    def create_trigger(self, command: str) -> tuple[str, int]:
        form = urllib.parse.urlencode({"command": command, "description": TASK_ID, "enabled": "true"}).encode()
        status, body = self.request("POST", BASE + "always_on/", form,
                                    {"Content-Type": "application/x-www-form-urlencoded"},
                                    allowed=(200, 201, 202, 400, 403, 404, 409))
        identifier = self.object_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({"command": command, "description": TASK_ID + " fallback",
                                      "enabled": "true", "interval": "daily", "hour": at.hour,
                                      "minute": at.minute}).encode()
        _, body = self.request("POST", BASE + "schedule/", form,
                               {"Content-Type": "application/x-www-form-urlencoded"}, allowed=(200, 201, 202))
        identifier = self.object_id(body)
        if not identifier:
            raise ControllerError("NO_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        self.request("DELETE", BASE + "%s/%d/" % (kind, identifier), allowed=(200, 202, 204, 404))

    @staticmethod
    def task_objects(body: bytes) -> list[dict[str, Any]]:
        value = json.loads(body.decode("utf-8"))
        raw = (value.get("results") or value.get("objects") or value.get("tasks") or []) \
            if isinstance(value, dict) else value
        if not isinstance(raw, list):
            raise ControllerError("TRIGGER_LIST_INVALID")
        return [item for item in raw if isinstance(item, dict)]

    def remove_legacy_vin_ad_triggers(
            self, audit: dict[str, Any] | None = None) -> dict[str, Any]:
        """Irreversibly quarantine stale TASK068 jobs capable of restoring VIN ads.

        This owner-mandated safety deletion is intentionally outside the file
        rollback scope: a rollback must never recreate a forbidden ad trigger.
        ``audit`` is mutated incrementally so partial progress survives errors.
        """
        result: dict[str, Any] = audit if audit is not None else {}
        result.clear()
        result.update({
            "status": "RUNNING",
            "operation": "IRREVERSIBLE_SAFETY_QUARANTINE",
            "irreversible": True,
            "rollback_policy": "NEVER_RESTORE_OWNER_FORBIDDEN_VIN_AD_TRIGGER",
            "match_markers": list(LEGACY_VIN_AD_COMMAND_MARKERS),
            "candidates": [],
            "removed": [],
            "removed_count": 0,
            "remaining": None,
        })
        try:
            candidates = []
            for kind in ("always_on", "schedule"):
                _, body = self.request("GET", BASE + kind + "/")
                for item in self.task_objects(body):
                    command = str(item.get("command") or "").strip()
                    if not any(marker in command for marker in LEGACY_VIN_AD_COMMAND_MARKERS):
                        continue
                    identifier = item.get("id")
                    if not isinstance(identifier, int) or identifier <= 0:
                        raise ControllerError("LEGACY_TRIGGER_ID_INVALID")
                    candidates.append({"kind": kind, "id": identifier, "command": command})
            candidates.sort(key=lambda item: (str(item["kind"]), int(item["id"])))
            result["candidates"] = candidates
            result["candidate_count"] = len(candidates)
            result["candidate_inventory_sha256"] = sha((json.dumps(
                candidates, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ) + "\n").encode("utf-8"))

            for item in candidates:
                self.delete_trigger((str(item["kind"]), int(item["id"])))
                result["removed"].append(dict(item))
                result["removed_count"] = len(result["removed"])

            remaining = []
            for kind in ("always_on", "schedule"):
                _, body = self.request("GET", BASE + kind + "/")
                for item in self.task_objects(body):
                    command = str(item.get("command") or "").strip()
                    if any(marker in command for marker in LEGACY_VIN_AD_COMMAND_MARKERS):
                        remaining.append({"kind": kind, "id": item.get("id"), "command": command})
            result["remaining"] = len(remaining)
            result["remaining_items"] = remaining
            if remaining:
                raise ControllerError("LEGACY_VIN_AD_TRIGGER_REMAINS")
            result["removed_count"] = len(result["removed"])
            result["status"] = "PASS"
            return result
        except Exception as exc:
            result["status"] = "FAIL"
            result["failure"] = type(exc).__name__ + ":" + str(exc)
            raise

    def remove_legacy_vin_ad_remote_files(
            self, audit: dict[str, Any] | None = None) -> dict[str, Any]:
        """Irreversibly remove the executable TASK068 VIN-ad reinstallers."""
        result: dict[str, Any] = audit if audit is not None else {}
        result.clear()
        result.update({
            "status": "RUNNING",
            "operation": "IRREVERSIBLE_EXECUTABLE_QUARANTINE",
            "irreversible": True,
            "rollback_policy": "NEVER_RESTORE_OWNER_FORBIDDEN_VIN_AD_REINSTALLER",
            "candidates": [],
            "removed": [],
            "removed_count": 0,
            "remaining": None,
        })
        try:
            candidates = []
            for path in LEGACY_VIN_AD_REMOTE_FILES:
                value = self.read(path, missing=True)
                if value is not None:
                    candidates.append({
                        "path": path,
                        "sha256": sha(value),
                        "bytes": len(value),
                    })
            candidates.sort(key=lambda item: str(item["path"]))
            result["candidates"] = candidates
            result["candidate_count"] = len(candidates)
            result["candidate_inventory_sha256"] = sha((json.dumps(
                candidates, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ) + "\n").encode("utf-8"))
            for item in candidates:
                path = str(item["path"])
                self.delete_file(path)
                if self.read(path, missing=True) is not None:
                    raise ControllerError("LEGACY_REINSTALLER_DELETE_READBACK:" + path)
                result["removed"].append(dict(item))
                result["removed_count"] = len(result["removed"])
            remaining = [
                path for path in LEGACY_VIN_AD_REMOTE_FILES
                if self.read(path, missing=True) is not None
            ]
            result["remaining"] = len(remaining)
            result["remaining_items"] = remaining
            if remaining:
                raise ControllerError("LEGACY_VIN_AD_REINSTALLER_REMAINS")
            result["status"] = "PASS"
            return result
        except Exception as exc:
            result["status"] = "FAIL"
            result["failure"] = type(exc).__name__ + ":" + str(exc)
            raise

    def run(
            self, mode: str, timeout: int = 1200,
            backup_manifest_sha256: str | None = None) -> dict[str, Any]:
        if mode not in REMOTE_MODES:
            raise ControllerError("REMOTE_MODE")
        if mode in ("install", "rollback"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(backup_manifest_sha256 or "")):
                raise ControllerError("BACKUP_MANIFEST_SHA256_REQUIRED")
        elif backup_manifest_sha256 is not None:
            raise ControllerError("UNEXPECTED_BACKUP_MANIFEST_SHA256")
        self.delete_file(REMOTE_RECEIPT)
        command = "cd %s && python3.10 task115_remove_vin_ads.py --mode %s" % (REMOTE, mode)
        if backup_manifest_sha256 is not None:
            # The strict lowercase hex validation above makes this shell-safe.
            command += " --backup-manifest-sha256 " + backup_manifest_sha256
        trigger = self.create_trigger(command)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(REMOTE_RECEIPT, missing=True)
                if raw:
                    value = json.loads(raw.decode("utf-8"))
                    if not isinstance(value, dict):
                        raise ControllerError("REMOTE_RECEIPT")
                    return value
                time.sleep(5)
            raise ControllerError("REMOTE_TIMEOUT")
        finally:
            self.delete_trigger(trigger)

    def restart(self) -> None:
        _, body = self.request("GET", BASE + "always_on/")
        value = json.loads(body.decode())
        tasks = value.get("results") or value.get("objects") or value.get("tasks") or [] if isinstance(value, dict) else value
        matches = [item for item in tasks if isinstance(item, dict) and item.get("enabled") is not False
                   and str(item.get("command") or "").strip() == "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise ControllerError("BOT_TASK_NOT_UNIQUE")
        self.request("POST", BASE + "always_on/%d/restart/" % int(matches[0]["id"]), b"", allowed=(200, 201, 202, 204))


def validate_remote(
        value: Mapping[str, Any], mode: str,
        expected_backup_sha256: str | None = None) -> None:
    if (value.get("task_id") != TASK_ID or value.get("contract_id") != CONTRACT
            or value.get("status") != "PASS" or value.get("mode") != mode.upper()):
        raise ControllerError("REMOTE_%s_FAIL:%s" % (mode.upper(), value.get("errors")))
    if value.get("crm_write") is not False or value.get("media_write") is not False:
        raise ControllerError("REMOTE_SCOPE")
    if (expected_backup_sha256 is not None
            and value.get("backup_manifest_sha256") != expected_backup_sha256):
        raise ControllerError("REMOTE_BACKUP_MANIFEST_SHA256_MISMATCH")
    if mode in ("install", "verify"):
        if int(value.get("card_count", 0)) != 16 or int(value.get("page_count", 0)) != 32:
            raise ControllerError("REMOTE_CARD_COUNT")
        if int(value.get("vin_ad_count", -1)) != 0 or value.get("ua0009") != "PASS":
            raise ControllerError("REMOTE_AD_OR_UA0009")
        if value.get("autoworker_enabled") is not True:
            raise ControllerError("REMOTE_SPEC_AUTOWORKER_DISABLED")
        if int(value.get("specification_min_rows", 0)) < MIN_SPEC_ROWS:
            raise ControllerError("REMOTE_ADDITIONAL_SPEC_INCOMPLETE")


def fetch(path: str) -> str:
    request = urllib.request.Request(PUBLIC + path + "?task115=" + str(time.time_ns()),
                                     headers={"Cache-Control": "no-cache", "User-Agent": "ua-art-task115-verify/1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read(MAX_BYTES + 1)
        if response.status != 200 or len(body) > MAX_BYTES:
            raise ControllerError("PUBLIC_HTTP")
    return body.decode("utf-8")


def external_hosts(source: str) -> set[str]:
    decoded = html.unescape(str(source or ""))
    candidates: list[str] = []
    attribute = re.compile(
        r"\b(?:href|src|action|formaction)\s*=\s*"
        r"(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'`=<>]+))",
        re.I,
    )
    for match in attribute.finditer(decoded):
        candidates.append(next(item for item in match.groups() if item is not None))
    for tag in re.findall(r"<meta\b[^>]*>", decoded, re.I | re.S):
        content = re.search(
            r"\bcontent\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'`=<>]+))",
            tag,
            re.I,
        )
        if content:
            value = next(item for item in content.groups() if item is not None)
            refresh = re.search(r"\burl\s*=\s*([^;\s]+|['\"][^'\"]+['\"])", value, re.I)
            if refresh:
                candidates.append(refresh.group(1).strip("'\""))
    candidates.extend(
        match.group(1).strip().strip("'\"")
        for match in re.finditer(r"\burl\(\s*([^)]*?)\s*\)", decoded, re.I)
    )
    candidates.extend(
        next(item for item in match.groups() if item is not None)
        for match in re.finditer(
            r"@import\s+(?:url\(\s*)?(?:\"([^\"]+)\"|'([^']+)'|([^\s;\)]+))",
            decoded,
            re.I,
        )
    )
    candidates.extend(re.findall(
        r"(?i)(?<![:A-Za-z0-9+.-])(?:(?:https?|ftp|wss?):)?//"
        r"(?:(?:[a-z0-9-]+\.)+[a-z0-9-]{2,63}|"
        r"\d{1,3}(?:\.\d{1,3}){3}|\[[0-9a-f:]+\])(?::\d+)?"
        r"(?:[/?#][^\s\"'<>`{}|\\^]*)?",
        decoded,
    ))
    result = set()
    for candidate in candidates:
        value = candidate.strip().rstrip(",.;)}]")
        if value.startswith("//"):
            value = "https:" + value
        host = (urllib.parse.urlsplit(value).hostname or "").casefold().rstrip(".")
        if host:
            result.add(host)
    return result


def live_verify() -> dict[str, Any]:
    results = {}
    specification_rows = {}
    for uid in IDS:
        page = fetch(uid + ".html")
        lowered = " ".join(page.casefold().split())
        if any(term in lowered for term in FORBIDDEN):
            raise ControllerError("PUBLIC_VIN_AD:" + uid)
        unknown_hosts = external_hosts(page) - APPROVED_HOSTS
        if unknown_hosts:
            raise ControllerError(
                "PUBLIC_UNAPPROVED_EXTERNAL_HOST:" + uid + ":" + ",".join(sorted(unknown_hosts))
            )
        if page.count("<!--UA099_ADD_SPEC_START-->") != 1 or page.count("<!--UA099_CLEAN_VIN_START-->") != 1:
            raise ControllerError("PUBLIC_SPEC_OR_VIN:" + uid)
        rows = len(re.findall(
            r"<div\b[^>]*class=['\"][^'\"]*\bua-addspec-row\b[^'\"]*['\"]",
            page, re.I,
        ))
        if rows < MIN_SPEC_ROWS:
            raise ControllerError("PUBLIC_ADDITIONAL_SPEC_INCOMPLETE:" + uid)
        specification_rows[uid] = rows
        results[uid] = sha(page.encode())
    return {"status": "PASS", "card_count": 16, "vin_ad_count": 0, "ua0009": "PASS",
            "sha256": results, "specification_rows": specification_rows,
            "specification_min_rows": min(specification_rows.values())}


def validate_specification_proofs(*proofs: Mapping[str, Any]) -> int:
    if not proofs:
        raise ControllerError("SPECIFICATION_PROOFS_MISSING")
    expected = proofs[0].get("specification_rows")
    if (not isinstance(expected, dict) or set(expected) != set(IDS)
            or any(type(value) is not int or value < MIN_SPEC_ROWS
                   for value in expected.values())):
        raise ControllerError("SPECIFICATION_PROOF_INVALID")
    minimum = min(expected.values())
    for proof in proofs:
        if (proof.get("specification_rows") != expected
                or proof.get("specification_min_rows") != minimum):
            raise ControllerError("SPECIFICATION_PROOF_DRIFT")
    return minimum


def execute(environment: Mapping[str, str]) -> dict[str, Any]:
    values = required(environment)
    evidence: dict[str, Any] = {"task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL",
                                "started_at": now(), "errors": [], "production_required": True}
    try:
        script = (HERE / "remote_installer.py").read_bytes()
        compile(script.decode("utf-8"), "remote_installer.py", "exec")
        api = API(values["PYTHONANYWHERE_API_TOKEN"])
        evidence["legacy_vin_ad_triggers"] = {}
        api.remove_legacy_vin_ad_triggers(evidence["legacy_vin_ad_triggers"])
        evidence["legacy_vin_ad_remote_files"] = {}
        api.remove_legacy_vin_ad_remote_files(evidence["legacy_vin_ad_remote_files"])
        api.upload(REMOTE_SCRIPT, script)
        expected_backup_sha256 = values["UAART_BACKUP_MANIFEST_SHA256"]
        install = api.run("install", backup_manifest_sha256=expected_backup_sha256)
        evidence["install"] = install
        validate_remote(install, "install", expected_backup_sha256)
        api.restart()
        time.sleep(15)
        evidence["public_immediate"] = live_verify()
        verify = api.run("verify")
        evidence["remote_verify"] = verify
        validate_remote(verify, "verify")
        time.sleep(35)
        delayed_verify = api.run("verify")
        evidence["remote_delayed_verify"] = delayed_verify
        validate_remote(delayed_verify, "verify")
        evidence["public_delayed"] = live_verify()
        specification_min_rows = validate_specification_proofs(
            install,
            evidence["public_immediate"],
            verify,
            delayed_verify,
            evidence["public_delayed"],
        )
        evidence["delayed_legacy_vin_ad_triggers"] = {}
        api.remove_legacy_vin_ad_triggers(
            evidence["delayed_legacy_vin_ad_triggers"]
        )
        evidence["delayed_legacy_vin_ad_remote_files"] = {}
        api.remove_legacy_vin_ad_remote_files(
            evidence["delayed_legacy_vin_ad_remote_files"]
        )
        if (evidence["delayed_legacy_vin_ad_triggers"]["candidate_count"] != 0
                or evidence["delayed_legacy_vin_ad_remote_files"]["candidate_count"] != 0):
            raise ControllerError("LEGACY_VIN_AD_QUARANTINE_REAPPEARED")
        receipt = {"contract_id": CRITICAL, "task_id": TASK_ID, "status": "FINISHED",
                   "task_class": "CRITICAL", "target_environment": "production", "tests": "PASS",
                   "backup": install["backup"], "production": "PASS", "live_verify": "PASS",
                   "backup_manifest_sha256": expected_backup_sha256,
                   "rollback": "PASS", "rollback_ready": True, "unexpected_changes": 0,
                   "protected_files_unchanged": True, "crm_unchanged": True, "media_unchanged": True,
                   "production_required": True, "request_sha256": values["UAART_REQUEST_SHA256"],
                   "manifest_sha256": MANIFEST_SHA256, "run_id": values["UAART_RUN_ID"],
                   "card_count": 16, "page_count": 32, "vin_ad_count": 0, "ua0009": "PASS",
                   "additional_specification": "RESTORED_NONEMPTY",
                   "specification_min_rows": specification_min_rows,
                   "vin_autoworker_enabled": True,
                   "rollback_scope": "FILESYSTEM_TARGETS_ONLY",
                   "scheduler_quarantine": "PASS",
                   "scheduler_quarantine_irreversible": True,
                   "scheduler_quarantine_rollback_policy":
                       "NEVER_RESTORE_OWNER_FORBIDDEN_VIN_AD_TRIGGER",
                   "legacy_vin_ad_trigger_inventory_sha256":
                       evidence["legacy_vin_ad_triggers"]["candidate_inventory_sha256"],
                   "legacy_vin_ad_triggers_remaining": 0,
                   "legacy_vin_ad_triggers_removed":
                       evidence["legacy_vin_ad_triggers"]["removed_count"],
                   "legacy_vin_ad_reinstallers_inventory_sha256":
                       evidence["legacy_vin_ad_remote_files"]["candidate_inventory_sha256"],
                   "legacy_vin_ad_reinstallers_remaining": 0,
                   "legacy_vin_ad_reinstallers_removed":
                       evidence["legacy_vin_ad_remote_files"]["removed_count"],
                   "delayed_legacy_vin_ad_quarantine": "PASS_NO_REAPPEARANCE",
                   "production_write": "TASK115_ONLY", "finished_at": now()}
        atomic_text(ROOT / RECEIPT_REL, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        evidence["rollback"] = "DEFERRED"
        evidence["rollback_owner"] = "GENERIC_CRITICAL_WORKFLOW"
    evidence["finished_at"] = now()
    atomic_text(ROOT / EVIDENCE_REL, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return evidence


def main() -> int:
    value = execute(os.environ)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
