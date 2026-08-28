#!/usr/bin/env python3
"""Gated PythonAnywhere production controller for SEO-REHAB-GUARD-068."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import pathlib
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import live_verify


HERE = pathlib.Path(__file__).resolve().parent
CONTRACT = "SEO-REHAB-GUARD-068"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/seo_rehab_guard_068"
REMOTE_SCRIPT = REMOTE + "/seo_rehab_guard_068_repair.py"
LOCAL_SCRIPT = HERE / "repair_remote.py"
DRY_RECEIPT = REMOTE + "/dry_run_receipt.json"
SOURCE_RECEIPT = REMOTE + "/source_install_receipt.json"
CONTENT_RECEIPT = REMOTE + "/install_receipt.json"
CONTENT_ROLLBACK_RECEIPT = REMOTE + "/rollback_receipt.json"
SOURCE_ROLLBACK_RECEIPT = REMOTE + "/source_rollback_receipt.json"
DRY_COMMAND = "cd %s && python3.10 seo_rehab_guard_068_repair.py --dry-run" % REMOTE
SOURCE_COMMAND = "cd %s && python3.10 seo_rehab_guard_068_repair.py --sources-only" % REMOTE
CONTENT_COMMAND = "cd %s && python3.10 seo_rehab_guard_068_repair.py --content-only" % REMOTE
CONTENT_ROLLBACK_COMMAND = "cd %s && python3.10 seo_rehab_guard_068_repair.py --rollback-content" % REMOTE
SOURCE_ROLLBACK_COMMAND = "cd %s && python3.10 seo_rehab_guard_068_repair.py --rollback-sources" % REMOTE
BOT_COMMAND = "python3.10 /home/Carix/start_safe.py"
WEBAPP_DOMAIN = "www.uaart.com.ua"
EVIDENCE = HERE / "evidence" / "controller.json"
MAX_BYTES = 24 * 1024 * 1024
EXPECTED_CARDS = ["UA-%04d" % number for number in range(1, 11)]


class ControllerError(RuntimeError):
    pass


def atomic_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class API:
    def __init__(self) -> None:
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerError("PYTHONANYWHERE_TOKEN_MISSING")
        self.token = token

    def request(self, method: str, url: str, data=None, headers=None, allowed=(200,)) -> tuple[int, bytes]:
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-seo-rehab-068-controller/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
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
    def json_value(body: bytes):
        try:
            return json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise ControllerError("API_JSON_INVALID") from exc

    def file_url(self, path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, *, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, data: bytes) -> None:
        if len(data) > MAX_BYTES:
            raise ControllerError("UPLOAD_TOO_LARGE")
        boundary = "----uaart-seo068-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend((
            'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
            "Content-Type: %s\r\n\r\n" % (filename, mime)
        ).encode())
        body.extend(data)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        for attempt in range(1, 6):
            status, _ = self.request(
                "POST", self.file_url(path), bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504),
            )
            if status in (200, 201):
                return
            if attempt < 5:
                time.sleep(min(attempt * 3, 12))
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def collection(body: bytes, keys: tuple[str, ...]) -> list:
        value = API.json_value(body)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for key in keys:
                if isinstance(value.get(key), list):
                    return value[key]
            if all(isinstance(item, dict) for item in value.values()):
                result = []
                for key, item in value.items():
                    copy = dict(item)
                    copy.setdefault("domain_name", key)
                    result.append(copy)
                return result
        raise ControllerError("API_COLLECTION_INVALID")

    @staticmethod
    def trigger_id(body: bytes) -> int | None:
        value = API.json_value(body)
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, command: str, description: str) -> tuple[str, int]:
        form = urllib.parse.urlencode({
            "command": command,
            "description": description,
            "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier

        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command,
            "description": description + " fallback",
            "enabled": "true",
            "interval": "daily",
            "hour": run_at.hour,
            "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER_AVAILABLE")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", BASE + "%s/%d/" % (endpoint, identifier),
            allowed=(200, 202, 204, 404),
        )

    def run_remote(self, command: str, description: str, receipt_path: str, seconds: int = 900) -> dict:
        self.delete_file(receipt_path)
        trigger = self.create_trigger(command, description)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt_path, missing=True)
                if raw:
                    value = self.json_value(raw)
                    if not isinstance(value, dict):
                        raise ControllerError("REMOTE_RECEIPT_INVALID")
                    return value
                time.sleep(5)
            raise ControllerError("REMOTE_RECEIPT_TIMEOUT:" + pathlib.PurePosixPath(receipt_path).name)
        finally:
            self.delete_trigger(trigger)

    def bot_task(self) -> dict:
        _, body = self.request("GET", BASE + "always_on/")
        tasks = self.collection(body, ("tasks", "objects", "results"))
        matching = [
            item for item in tasks
            if isinstance(item, dict)
            and item.get("enabled") is not False
            and str(item.get("command", "")).strip() == BOT_COMMAND
        ]
        if len(matching) != 1 or not isinstance(matching[0].get("id"), int):
            raise ControllerError("PRODUCTION_BOT_TASK_NOT_UNIQUE")
        return matching[0]

    def webapp(self) -> dict:
        _, body = self.request("GET", BASE + "webapps/")
        apps = self.collection(body, ("webapps", "objects", "results"))
        matching = []
        for item in apps:
            if not isinstance(item, dict):
                continue
            names = {str(item.get(key, "")).lower() for key in ("domain_name", "domain", "hostname")}
            if WEBAPP_DOMAIN in names:
                matching.append(item)
        if len(matching) != 1:
            raise ControllerError("PRODUCTION_WEBAPP_NOT_UNIQUE")
        return matching[0]

    def service_contract(self) -> dict:
        task = self.bot_task()
        self.webapp()
        return {
            "bot_command": BOT_COMMAND,
            "bot_task_id": task["id"],
            "webapp_domain": WEBAPP_DOMAIN,
            "read_only_probe": True,
        }

    def restart_bot(self) -> dict:
        task = self.bot_task()
        self.request(
            "POST", BASE + "always_on/%d/restart/" % task["id"],
            b"", allowed=(200, 201, 202, 204),
        )
        return {"command": BOT_COMMAND, "task_id": task["id"], "restart_accepted": True}

    def reload_webapp(self) -> dict:
        self.webapp()
        endpoint = BASE + "webapps/" + urllib.parse.quote(WEBAPP_DOMAIN, safe="") + "/reload/"
        self.request("POST", endpoint, b"", allowed=(200, 201, 202, 204))
        return {"domain": WEBAPP_DOMAIN, "reload_accepted": True}


def validate_dry(value: dict) -> None:
    repeat = value.get("repeatability") or {}
    if value.get("contract") != CONTRACT or value.get("mode") != "dry-run" or value.get("status") != "PASS":
        raise ControllerError("DRY_RUN_FAILED:" + ";".join(value.get("errors", [])))
    if value.get("production_write") is not False:
        raise ControllerError("DRY_RUN_WRITE_SCOPE_INVALID")
    if value.get("card_ids") != EXPECTED_CARDS or value.get("candidate_files") != 36:
        raise ControllerError("DRY_RUN_CANDIDATE_SET_INVALID")
    if repeat.get("runs") != 10 or repeat.get("unique_sha256") != 1:
        raise ControllerError("DRY_RUN_REPEATABILITY_INVALID")
    if not re_full_sha(repeat.get("tree_sha256")):
        raise ControllerError("DRY_RUN_TREE_HASH_INVALID")


def re_full_sha(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def validate_backup(value: dict, phase: str) -> None:
    if value.get("contract") != CONTRACT or value.get("mode") != "install" or value.get("phase") != phase:
        raise ControllerError("INSTALL_RECEIPT_INVALID:" + phase)
    if value.get("status") != "PASS":
        rollback = value.get("rollback") or {}
        if value.get("changed_paths") and rollback.get("status") != "PASS":
            raise ControllerError("INSTALL_AUTOROLLBACK_INVALID:" + phase)
        raise ControllerError("INSTALL_FAILED:%s:%s" % (phase, ";".join(value.get("errors", []))))
    backup = value.get("backup_root", "")
    if not isinstance(backup, str) or not backup.startswith(REMOTE + "/backups/"):
        raise ControllerError("BACKUP_ROOT_INVALID:" + phase)
    if value.get("rollback") is not None:
        raise ControllerError("UNEXPECTED_ROLLBACK_ON_PASS:" + phase)


def validate_source(value: dict) -> None:
    validate_backup(value, "sources")
    if value.get("candidate_files") != 4 or value.get("canary") is not None or value.get("card_ids") != []:
        raise ControllerError("SOURCE_PHASE_SET_INVALID")
    allowed = {
        "stranica.py", "yadro.py", "master_card.py",
        "/var/www/www_uaart_com_ua_wsgi.py",
    }
    changed = set(value.get("changed_paths") or [])
    if not changed or not changed.issubset(allowed):
        raise ControllerError("SOURCE_CHANGED_PATH_INVALID")
    if value.get("production_write") is not True:
        raise ControllerError("SOURCE_WRITE_NOT_RECORDED")


def validate_content(value: dict) -> None:
    validate_backup(value, "content")
    if value.get("candidate_files") != 32 or value.get("card_ids") != EXPECTED_CARDS:
        raise ControllerError("CONTENT_PHASE_SET_INVALID")
    canary = value.get("canary") or {}
    public = canary.get("public") or {}
    if canary.get("id") != "UA-0010" or public.get("status") != 200:
        raise ControllerError("CANARY_INVALID")
    changed = set(value.get("changed_paths") or [])
    allowed = set()
    required = set()
    for root in ("video", "site"):
        allowed.update("%s/%s" % (root, name) for name in ("index.html", "katalog.html", "info.html", "podbor.html", "robots.txt", "sitemap.xml"))
        allowed.update("%s/%s.html" % (root, identifier) for identifier in EXPECTED_CARDS)
        required.update("%s/%s.html" % (root, identifier) for identifier in EXPECTED_CARDS)
        required.update({root + "/index.html", root + "/katalog.html"})
    if not changed.issubset(allowed) or not required.issubset(changed):
        raise ControllerError("CONTENT_CHANGED_PATH_INVALID")
    if value.get("production_write") is not True:
        raise ControllerError("CONTENT_WRITE_NOT_RECORDED")


def validate_rollback(value: dict, phase: str) -> None:
    if value.get("contract") != CONTRACT or value.get("mode") != "rollback":
        raise ControllerError("ROLLBACK_RECEIPT_INVALID:" + phase)
    if value.get("phase") != phase or value.get("status") != "PASS" or value.get("errors"):
        raise ControllerError("ROLLBACK_FAILED:" + phase)


def upload_candidate(api: API) -> dict:
    data = LOCAL_SCRIPT.read_bytes()
    compile(data.decode("utf-8"), str(LOCAL_SCRIPT), "exec")
    api.upload(REMOTE_SCRIPT, data)
    if api.read(REMOTE_SCRIPT) != data:
        raise ControllerError("UPLOAD_READBACK_MISMATCH")
    return {"path": REMOTE_SCRIPT, "bytes": len(data), "readback": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-only", action="store_true")
    args = parser.parse_args()
    evidence = {
        "contract": CONTRACT,
        "status": "FAIL",
        "mode": "dry-run-only" if args.dry_run_only else "production-release",
        "llm_tokens": 0,
        "production_write_authorized": not args.dry_run_only,
        "rollback": {"content": None, "sources": None},
        "errors": [],
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    api = None
    source = None
    content = None
    try:
        api = API()
        evidence["upload"] = upload_candidate(api)
        dry = api.run_remote(DRY_COMMAND, "seo068 ten-run production dry-run", DRY_RECEIPT)
        evidence["dry_run"] = dry
        validate_dry(dry)
        evidence["service_preflight"] = api.service_contract()
        if args.dry_run_only:
            evidence["status"] = "PASS"
        else:
            source = api.run_remote(
                SOURCE_COMMAND,
                "seo068 install generator and root-route guards",
                SOURCE_RECEIPT,
            )
            evidence["source_install"] = source
            validate_source(source)
            evidence["bot_restart"] = api.restart_bot()
            evidence["webapp_reload"] = api.reload_webapp()
            time.sleep(15)

            content = api.run_remote(
                CONTENT_COMMAND,
                "seo068 canary and atomic public content rehabilitation",
                CONTENT_RECEIPT,
            )
            evidence["content_install"] = content
            validate_content(content)

            immediate = live_verify.verify_public()
            evidence["public_immediate"] = immediate
            if immediate.get("status") != "PASS":
                raise ControllerError("PUBLIC_IMMEDIATE_FAILED:" + ";".join(immediate.get("errors", [])))
            time.sleep(60)
            delayed = live_verify.verify_public()
            evidence["public_delayed"] = delayed
            if delayed.get("status") != "PASS":
                raise ControllerError("PUBLIC_DELAYED_FAILED:" + ";".join(delayed.get("errors", [])))
            evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and content and content.get("status") == "PASS" and content.get("changed_paths"):
            try:
                rollback = api.run_remote(
                    CONTENT_ROLLBACK_COMMAND,
                    "seo068 automatic content rollback",
                    CONTENT_ROLLBACK_RECEIPT,
                )
                evidence["rollback"]["content"] = rollback
                validate_rollback(rollback, "content")
            except Exception as rollback_exc:
                evidence["errors"].append("CONTENT_ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
        if api is not None and source and source.get("status") == "PASS" and source.get("changed_paths"):
            try:
                rollback = api.run_remote(
                    SOURCE_ROLLBACK_COMMAND,
                    "seo068 automatic source and WSGI rollback",
                    SOURCE_ROLLBACK_RECEIPT,
                )
                evidence["rollback"]["sources"] = rollback
                validate_rollback(rollback, "sources")
                evidence["rollback_bot_restart"] = api.restart_bot()
                evidence["rollback_webapp_reload"] = api.reload_webapp()
                time.sleep(15)
            except Exception as rollback_exc:
                evidence["errors"].append("SOURCE_ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
        if not args.dry_run_only and api is not None:
            try:
                evidence["rollback_availability"] = live_verify.availability_after_rollback()
            except Exception as availability_exc:
                evidence["errors"].append("ROLLBACK_AVAILABILITY_" + type(availability_exc).__name__ + ":" + str(availability_exc))
    atomic_json(EVIDENCE, evidence)
    print("SEO_REHAB_068_CONTROLLER_%s mode=%s" % (evidence["status"], evidence["mode"]))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
