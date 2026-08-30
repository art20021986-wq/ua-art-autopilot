#!/usr/bin/env python3
"""Deploy and publicly verify TASK 093 homepage counter synchronization."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
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


CONTRACT_ID = "UA-HOME-STAGE-COUNTER-SYNC-093-V1.0"
HERE = pathlib.Path(__file__).resolve().parent
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_083_catalog_dedup"
FILES = {
    "task093_remote_installer.py": HERE / "remote_installer.py",
    "task093_home_counter_guard.py": HERE / "home_counter_guard.py",
}
RECEIPTS = {
    mode: REMOTE + "/task093_%s_receipt.json" % mode
    for mode in ("install", "postcheck", "rollback")
}
COMMANDS = {
    mode: "cd %s && python3.10 task093_remote_installer.py %s" % (REMOTE, mode)
    for mode in RECEIPTS
}
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
PUBLIC_HOME = "https://www.uaart.com.ua/video/index.html"
PUBLIC_CATALOG = "https://www.uaart.com.ua/video/katalog.html"
EVIDENCE = HERE / "evidence/production.json"
REPORT = HERE / "TASK_093_REPORT.md"
EXPECTED_COUNTS = {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2}
MAX_BYTES = 10 * 1024 * 1024


class ControllerError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_guard():
    specification = importlib.util.spec_from_file_location(
        "task093_controller_guard", HERE / "home_counter_guard.py")
    if specification is None or specification.loader is None:
        raise ControllerError("GUARD_IMPORT")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class API:
    def __init__(self) -> None:
        self.token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not self.token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")

    def request(self, method: str, url: str, data: bytes | None = None,
                headers: dict[str, str] | None = None,
                allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        all_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task093-controller/1",
        }
        all_headers.update(headers or {})
        request = urllib.request.Request(
            url, data=data, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=70) as response:
                status, body = int(response.status), response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d:%s" % (
                status, urllib.parse.urlsplit(url).path))
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request(
            "GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + path)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task093-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend((
            'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
            "Content-Type: %s\r\n\r\n" % (filename, mime)).encode())
        body.extend(data)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        for attempt in range(1, 6):
            status, _ = self.request(
                "POST", self.file_url(path), bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504))
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

    def create_trigger(self, command: str, description: str):
        moment = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)
        form = urllib.parse.urlencode({
            "command": command,
            "description": description + " scheduled executor",
            "enabled": "true",
            "interval": "daily",
            "hour": moment.hour,
            "minute": moment.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409))
        identifier = self.identifier(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_SCHEDULED_EXECUTOR")
        return ("schedule", identifier)

    def delete_trigger(self, trigger) -> None:
        self.request(
            "DELETE", BASE + "%s/%d/" % trigger,
            allowed=(200, 202, 204, 404))

    def run_remote(self, mode: str, seconds: int = 420) -> dict[str, Any]:
        receipt = RECEIPTS[mode]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[mode], "task093 " + mode)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    return json.loads(raw.decode("utf-8"))
                time.sleep(5)
            raise ControllerError("REMOTE_RECEIPT_TIMEOUT:" + mode)
        finally:
            self.delete_trigger(trigger)


def fetch_public(url: str, label: str) -> str:
    query = urllib.parse.urlencode({
        "task093_verify": utc_now(),
        "round": label,
    })
    request = urllib.request.Request(
        url + "?" + query,
        headers={"User-Agent": "UA-ART-task093-public-verify/1",
                 "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            status = int(response.status)
            body = response.read(MAX_BYTES + 1)
    except Exception as exc:
        raise ControllerError(
            "PUBLIC_FETCH:%s:%s" % (label, type(exc).__name__)) from exc
    if status != 200 or len(body) > MAX_BYTES:
        raise ControllerError("PUBLIC_HTTP:%s:%d" % (label, status))
    return body.decode("utf-8", "replace")


def catalog_counts(source: str) -> tuple[dict[str, int], dict[str, str]]:
    openings = re.findall(
        r'<(?:a|article)\b(?=[^>]*\bdata-ua-card\s*=)[^>]*>',
        source, re.I | re.S)
    aliases = {"kiev": "kiev", "kyiv": "kiev", "gruzia": "georgia",
               "georgia": "georgia", "more": "sea", "sea": "sea",
               "korea": "korea"}
    cards: dict[str, str] = {}
    for opening in openings:
        identifier = re.search(
            r'\bdata-ua-card\s*=\s*["\'](UA-[0-9]{4,})["\']',
            opening, re.I)
        stage = re.search(
            r'\bdata-(?:ua-card-stage|etap|stage)\s*=\s*["\']([^"\']+)["\']',
            opening, re.I)
        if not identifier or not stage:
            continue
        code = identifier.group(1).upper()
        key = aliases.get(stage.group(1).casefold())
        if not key:
            raise ControllerError("PUBLIC_CATALOG_STAGE:" + code)
        if code in cards:
            raise ControllerError("PUBLIC_CATALOG_DUPLICATE:" + code)
        cards[code] = key
    counts = {"all": len(cards), "kiev": 0, "georgia": 0, "sea": 0, "korea": 0}
    for key in cards.values():
        counts[key] += 1
    return counts, cards


def verify_public(guard, counts: dict[str, int], label: str) -> dict[str, Any]:
    home = fetch_public(PUBLIC_HOME, "home-" + label)
    catalog = fetch_public(PUBLIC_CATALOG, "catalog-" + label)
    home_audit = guard.audit_home(home, counts)
    if home_audit.get("status") != "PASS":
        raise ControllerError(
            "PUBLIC_HOME_AUDIT:" + ",".join(home_audit.get("errors") or []))
    actual, cards = catalog_counts(catalog)
    if actual != counts:
        raise ControllerError("PUBLIC_CATALOG_COUNTS:" + json.dumps(actual))
    if cards.get("UA-0011") != "sea":
        raise ControllerError("PUBLIC_UA0011_STAGE")
    block_match = re.search(
        r'<a\b(?=[^>]*\bdata-ua-card\s*=\s*["\']UA-0011["\'])'
        r'[^>]*>.*?</a\s*>',
        catalog, re.I | re.S)
    if not block_match:
        raise ControllerError("PUBLIC_UA0011_CARD")
    block = block_match.group(0)
    required = (
        "KMHE341DBKA544289",
        "11 400 $",
        "163400 км",
        "2000 см³",
        "LPI",
        "автомат",
        "Фото: 35",
        "foto/UA-0011/m/001.jpg",
    )
    missing = [value for value in required if value not in block]
    if missing:
        raise ControllerError("PUBLIC_UA0011_INCOMPLETE:" + ",".join(missing))
    return {
        "status": "PASS",
        "label": label,
        "home_bytes": len(home.encode()),
        "catalog_bytes": len(catalog.encode()),
        "counts": actual,
        "ids": sorted(cards),
        "home": home_audit,
        "ua0011_full": True,
        "http_methods": ["GET"],
        "production_write": False,
        "checked_at_utc": utc_now(),
    }


def validate_install(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("production_write") is not True:
        raise ControllerError("INSTALL_WRITE")
    if value.get("crm_write") is not False or value.get("media_write") is not False:
        raise ControllerError("INSTALL_SCOPE")
    before = value.get("database_before") or {}
    after = value.get("database_after") or {}
    if before.get("counts") != EXPECTED_COUNTS:
        raise ControllerError("INSTALL_COUNTS")
    if before.get("file_sha256") != after.get("file_sha256"):
        raise ControllerError("INSTALL_CRM_FILE_CHANGED")
    if before.get("rows_sha256") != after.get("rows_sha256"):
        raise ControllerError("INSTALL_CRM_ROWS_CHANGED")
    if "/home/Carix/video/index.html" not in (value.get("changed_files") or []):
        raise ControllerError("VIDEO_HOME_NOT_CHANGED")
    if not value.get("backup_root"):
        raise ControllerError("BACKUP_MISSING")


def validate_postcheck(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("production_write") is not False or value.get("crm_write") is not False:
        raise ControllerError("POSTCHECK_SCOPE")
    if value.get("counts") != EXPECTED_COUNTS:
        raise ControllerError("POSTCHECK_COUNTS")


def report_text(evidence: dict[str, Any]) -> str:
    passed = evidence.get("status") == "PASS"
    return "\n".join([
        "# TASK 093 — синхронизация счётчиков главной", "",
        "STATUS: **%s**" % evidence.get("status", "FAIL"), "",
        "- Главная: %s" % ("13 / 3 / 1 / 7 / 2" if passed else "НЕ ПОДТВЕРЖДЕНО"),
        "- UA-0011: %s" % ("полная карточка, этап «На пароме»" if passed else "FAIL"),
        "- Динамический пересчёт: %s" % ("УСТАНОВЛЕН" if passed else "FAIL"),
        "- CRM/media изменены: НЕТ",
        "- Ошибки: %s" % (
            "; ".join(evidence.get("errors") or []) if evidence.get("errors") else "нет"),
        "",
    ])


def main() -> int:
    evidence: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "errors": [],
        "installed": False,
        "bot_restarted": False,
        "crm_write": False,
        "media_write": False,
        "started_at_utc": utc_now(),
    }
    api: API | None = None
    try:
        guard = load_guard()
        api = API()
        for name, path in FILES.items():
            data = path.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            remote = REMOTE + "/" + name
            api.upload(remote, data)
            if api.read(remote) != data:
                raise ControllerError("UPLOAD_READBACK:" + name)
        install = api.run_remote("install")
        evidence["install"] = install
        validate_install(install)
        evidence["installed"] = True
        counts = install["database_before"]["counts"]
        immediate_remote = api.run_remote("postcheck")
        evidence["postcheck_immediate"] = immediate_remote
        validate_postcheck(immediate_remote)
        evidence["public_immediate"] = verify_public(guard, counts, "immediate")
        time.sleep(25)
        delayed_remote = api.run_remote("postcheck")
        evidence["postcheck_delayed"] = delayed_remote
        validate_postcheck(delayed_remote)
        evidence["public_delayed"] = verify_public(guard, counts, "delayed")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and evidence.get("installed"):
            try:
                rollback = api.run_remote("rollback")
                evidence["rollback"] = rollback
                if rollback.get("status") != "PASS":
                    raise ControllerError("ROLLBACK_FAILED")
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
    evidence["finished_at_utc"] = utc_now()
    atomic_text(
        EVIDENCE,
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, report_text(evidence))
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
