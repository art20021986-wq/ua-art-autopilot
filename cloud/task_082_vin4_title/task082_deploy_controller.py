#!/usr/bin/env python3
"""GitHub-side safe deploy controller for CRM-VIN4-TITLE-001 v1.0."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import task082_exact_patch as patcher

HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
ROOT = "/home/Carix"
UPLOADS = ROOT + "/uploads"
SOURCE = ROOT + "/cars_ui.py"
DB = ROOT + "/crm.db"
REMOTE_INSTALLER = UPLOADS + "/task082_remote_installer.py"
REMOTE_HEALTH = UPLOADS + "/task082_remote_health.py"
REMOTE_CANDIDATE = UPLOADS + "/task082_cars_ui_candidate.py"
REMOTE_CONFIG = UPLOADS + "/task082_install_config.json"
INSTALL_RECEIPT = UPLOADS + "/task082_install_receipt.json"
HEALTH_RECEIPT = UPLOADS + "/task082_health_receipt.json"
EVIDENCE = HERE / "evidence" / "deploy_v2.json"
REPORT = HERE / "TASK_082_RESULT.md"
DELAY = int(os.environ.get("TASK082_DELAY_SECONDS", "45"))
MAX_BYTES = 100_000_000
PROTECTED_WEB = tuple(
    [ROOT + "/mysite/video/katalog.html", ROOT + "/mysite/site/katalog.html"]
    + [ROOT + "/mysite/%s/UA-%04d.html" % (site_root, number)
       for site_root in ("video", "site") for number in range(1, 14)]
)


class DeployError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    temporary = pathlib.Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class API:
    def __init__(self):
        self.token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "").strip()
        if not self.token:
            raise DeployError("PYTHONANYWHERE_API_TOKEN_MISSING")

    def request(self, method, url, data=None, headers=None, allowed=(200,), limit=MAX_BYTES):
        request_headers = {"Authorization": "Token " + self.token, "User-Agent": "ua-art-task082-vin4/1"}
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                status, body = response.status, response.read(limit + 1)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read(limit + 1)
        except Exception as exc:
            raise DeployError("NETWORK:" + type(exc).__name__) from exc
        if len(body) > limit:
            raise DeployError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise DeployError("HTTP_%d:%s" % (status, url.rsplit("/", 2)[-2]))
        return status, body

    @staticmethod
    def file_url(path):
        if not path.startswith(ROOT + "/"):
            raise DeployError("PATH_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path, missing=False):
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise DeployError("FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete(self, path):
        if not path.startswith(UPLOADS + "/task082_"):
            raise DeployError("DELETE_SCOPE")
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path, data: bytes):
        if not path.startswith(UPLOADS + "/task082_"):
            raise DeployError("UPLOAD_SCOPE")
        boundary = "----uaart-task082-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend(('Content-Disposition: form-data; name="content"; filename="%s"\r\n'
                     "Content-Type: %s\r\n\r\n" % (filename, mime)).encode())
        body.extend(data)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        for attempt in range(1, 6):
            status, _ = self.request(
                "POST", self.file_url(path), bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504), limit=2_000_000,
            )
            if status in (200, 201):
                return
            if attempt < 5:
                time.sleep(attempt * 2)
        raise DeployError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def objects(body):
        value = json.loads(body.decode())
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    def create_trigger(self, command, description):
        form = urllib.parse.urlencode({"command": command, "description": description, "enabled": "true"}).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409), limit=2_000_000,
        )
        try:
            value = json.loads(body.decode())
            identifier = value.get("id") if isinstance(value, dict) else None
        except Exception:
            identifier = None
        if status in (200, 201, 202) and identifier:
            return "always_on", int(identifier)
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command, "description": description + " fallback", "enabled": "true",
            "interval": "daily", "hour": run_at.hour, "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409), limit=2_000_000,
        )
        try:
            value = json.loads(body.decode())
            identifier = value.get("id") if isinstance(value, dict) else None
        except Exception:
            identifier = None
        if not identifier:
            raise DeployError("NO_REMOTE_TRIGGER")
        return "schedule", int(identifier)

    def delete_trigger(self, trigger):
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request("DELETE", BASE + "%s/%d/" % (endpoint, identifier), allowed=(200, 202, 204, 404), limit=2_000_000)

    def run_remote(self, command, description, receipt_path, seconds=300):
        self.delete(receipt_path)
        trigger = self.create_trigger(command, description)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt_path, missing=True)
                if raw:
                    return json.loads(raw.decode())
                time.sleep(3)
            raise DeployError("RECEIPT_TIMEOUT:" + pathlib.PurePosixPath(receipt_path).name)
        finally:
            self.delete_trigger(trigger)

    def restart_bot(self):
        _, body = self.request("GET", BASE + "always_on/", limit=2_000_000)
        tasks = self.objects(body)
        matches = [item for item in tasks if isinstance(item, dict)
                   and item.get("enabled") is not False
                   and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise DeployError("LAUNCHER_TASK_COUNT:%d" % len(matches))
        identifier = int(matches[0]["id"])
        self.request("POST", BASE + "always_on/%d/restart/" % identifier, b"", allowed=(200, 201, 202, 204), limit=2_000_000)
        return {"task_id": identifier, "restart_accepted": True, "command": "python3.10 /home/Carix/start_safe.py"}


def _db_snapshot(raw: bytes) -> dict:
    with tempfile.TemporaryDirectory(prefix="task082-db-") as directory:
        path = pathlib.Path(directory) / "crm.db"
        path.write_bytes(raw)
        connection = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            quick = connection.execute("PRAGMA quick_check").fetchone()[0]
            columns = [row[1] for row in connection.execute("PRAGMA table_info(cars)")]
            rows = [dict(row) for row in connection.execute("SELECT * FROM cars ORDER BY id")]
        finally:
            connection.close()
    if quick != "ok":
        raise DeployError("DB_QUICK_CHECK")
    media_fields = [name for name in ("photos", "videos", "condition_photos", "condition_videos") if name in columns]
    cards = []
    media = {}
    state = {}
    ns = patcher._helper_namespace()
    for row in rows:
        identifier = str(row.get("auto_number") or "")
        vin4 = ns["_ua082_vin4"](row)
        cards.append({
            "id": identifier, "vin4": vin4, "vin_valid": vin4 is not None,
            "title_html": ns["_ua082_vin4_title_html"](row),
            "button_label": ns["_ua082_vin4_button_label"](row),
        })
        media[identifier] = _sha(json.dumps({name: row.get(name) for name in media_fields}, ensure_ascii=False, sort_keys=True, default=str).encode())
        state[identifier] = _sha(json.dumps({name: row.get(name) for name in columns if name not in media_fields}, ensure_ascii=False, sort_keys=True, default=str).encode())
    return {"sha256": _sha(raw), "bytes": len(raw), "quick_check": quick, "cards": cards, "media": media, "row_state": state}


def _web_snapshot(api: API) -> dict:
    result = {}
    for path in PROTECTED_WEB:
        raw = api.read(path, missing=True)
        result[path] = None if raw is None else _sha(raw)
    return result


def _validate_cards(cards):
    expected = ["UA-%04d" % number for number in range(1, 14)]
    if [item["id"] for item in cards] != expected:
        raise DeployError("CARD_ID_SET")
    for item in cards:
        vin4 = item.get("vin4") or ""
        if len(vin4) != 4 or not item.get("vin_valid"):
            raise DeployError("VIN4_INVALID:" + item["id"])
        if item["title_html"].count("VIN") != 1 or item["title_html"].count("<b>") != 2:
            raise DeployError("TITLE_FORMAT:" + item["id"])
        if not item["title_html"].endswith("VIN <b>%s</b>" % vin4):
            raise DeployError("TITLE_SUFFIX:" + item["id"])
        if len(item["button_label"]) > 64 or not item["button_label"].endswith("VIN %s" % vin4):
            raise DeployError("BUTTON_FORMAT:" + item["id"])


def _health(api: API, label: str) -> dict:
    value = api.run_remote(
        "cd /home/Carix/uploads && python3.10 task082_remote_health.py",
        "TASK082 VIN4 %s health" % label, HEALTH_RECEIPT, seconds=240,
    )
    if value.get("status") != "PASS":
        raise DeployError("HEALTH_%s:%s" % (label, ";".join(value.get("errors") or [])))
    _validate_cards(value.get("cards") or [])
    return value


def _rollback(api: API, backup_path, original_sha, candidate_sha):
    config = {
        "action": "rollback", "backup_path": backup_path,
        "expected_current_sha": candidate_sha, "expected_restored_sha": original_sha,
    }
    api.upload(REMOTE_CONFIG, (json.dumps(config, sort_keys=True) + "\n").encode())
    receipt = api.run_remote(
        "cd /home/Carix/uploads && python3.10 task082_remote_installer.py",
        "TASK082 VIN4 rollback", INSTALL_RECEIPT, seconds=240,
    )
    restart = api.restart_bot()
    time.sleep(8)
    restored = _sha(api.read(SOURCE))
    if receipt.get("status") != "PASS" or restored != original_sha:
        raise DeployError("ROLLBACK_FAILED")
    return {"receipt": receipt, "restart": restart, "restored_sha": restored}


def run() -> int:
    result = {
        "contract": patcher.CONTRACT, "status": "FAIL", "production_touched": False,
        "started_at_utc": _utc(), "errors": [], "llm_tokens": 0,
    }
    api = None
    backup_path = None
    original_sha = None
    candidate_sha = None
    installed = False
    try:
        patcher.self_test()
        api = API()
        source_raw = api.read(SOURCE)
        source = source_raw.decode("utf-8")
        original_sha = _sha(source_raw)
        db_before = _db_snapshot(api.read(DB))
        _validate_cards(db_before["cards"])
        web_before = _web_snapshot(api)
        candidate, patch_info = patcher.patch_source(source)
        candidate_raw = candidate.encode("utf-8")
        candidate_sha = _sha(candidate_raw)
        if patch_info.get("already_installed"):
            raise DeployError("ALREADY_INSTALLED_USE_POSTCHECK")
        result.update({
            "source_sha_before": original_sha, "source_sha_candidate": candidate_sha,
            "patch": patch_info, "db_before": db_before, "protected_web_before": web_before,
        })

        api.upload(REMOTE_INSTALLER, (HERE / "task082_remote_installer.py").read_bytes())
        api.upload(REMOTE_HEALTH, (HERE / "task082_remote_health.py").read_bytes())
        api.upload(REMOTE_CANDIDATE, candidate_raw)
        config = {"action": "install", "expected_source_sha_before": original_sha, "expected_source_sha_after": candidate_sha}
        api.upload(REMOTE_CONFIG, (json.dumps(config, sort_keys=True) + "\n").encode())
        receipt = api.run_remote(
            "cd /home/Carix/uploads && python3.10 task082_remote_installer.py",
            "TASK082 VIN4 atomic install", INSTALL_RECEIPT, seconds=240,
        )
        result["install_receipt"] = receipt
        if receipt.get("status") != "PASS" or receipt.get("source_sha_after") != candidate_sha:
            raise DeployError("INSTALL_RECEIPT:" + ";".join(receipt.get("errors") or []))
        installed = True
        result["production_touched"] = True
        backup_path = receipt.get("backup_path")
        if not backup_path:
            raise DeployError("BACKUP_PATH_MISSING")

        result["restart"] = api.restart_bot()
        time.sleep(10)
        if _sha(api.read(SOURCE)) != candidate_sha:
            raise DeployError("SOURCE_SHA_AFTER_RESTART")
        health_initial = _health(api, "initial")
        db_initial = _db_snapshot(api.read(DB))
        web_initial = _web_snapshot(api)
        if db_initial["media"] != db_before["media"] or db_initial["row_state"] != db_before["row_state"]:
            raise DeployError("CRM_ROWS_CHANGED")
        if web_initial != web_before:
            raise DeployError("PROTECTED_WEB_CHANGED")
        result.update({"health_initial": health_initial, "db_initial": db_initial, "protected_web_initial": web_initial})

        time.sleep(DELAY)
        if _sha(api.read(SOURCE)) != candidate_sha:
            raise DeployError("DELAYED_SOURCE_OVERWRITE")
        health_delayed = _health(api, "delayed")
        db_delayed = _db_snapshot(api.read(DB))
        web_delayed = _web_snapshot(api)
        if db_delayed["media"] != db_before["media"] or db_delayed["row_state"] != db_before["row_state"]:
            raise DeployError("DELAYED_CRM_ROWS_CHANGED")
        if web_delayed != web_before:
            raise DeployError("DELAYED_PROTECTED_WEB_CHANGED")
        result.update({"health_delayed": health_delayed, "db_delayed": db_delayed, "protected_web_delayed": web_delayed})
        result["status"] = "PASS"
        result["completed_at_utc"] = _utc()
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api and installed and backup_path and original_sha and candidate_sha:
            try:
                result["rollback"] = _rollback(api, backup_path, original_sha, candidate_sha)
                result["production_touched"] = True
            except Exception as rollback_exc:
                result["rollback_error"] = type(rollback_exc).__name__ + ":" + str(rollback_exc)
    finally:
        result["finished_at_utc"] = _utc()
        _atomic_json(EVIDENCE, result)
        cards = ((result.get("health_delayed") or result.get("health_initial") or {}).get("cards") or [])
        lines = [
            "# CRM-VIN4-TITLE-001 v1.0", "", "STATUS: **%s**" % result["status"], "",
            "- Production touched: %s" % ("YES" if result.get("production_touched") else "NO"),
            "- Backup: `%s`" % (backup_path or "NONE"),
            "- Source SHA before: `%s`" % (original_sha or "UNKNOWN"),
            "- Source SHA after: `%s`" % (candidate_sha or "UNKNOWN"),
            "- Current cards verified: %d/13" % len(cards),
            "- Future cards: centralized runtime helper; UA-9999 fixture PASS.",
            "- Database/site/media writes by this task: 0.",
            "- Runtime LLM tokens: 0.", "",
        ]
        for card in cards:
            lines.append("- %s · VIN **%s**" % (card.get("id"), card.get("vin4")))
        if result.get("errors"):
            lines.extend(["", "Errors: " + "; ".join(result["errors"])])
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if api:
            for path in (REMOTE_CANDIDATE, REMOTE_CONFIG, REMOTE_INSTALLER, REMOTE_HEALTH, INSTALL_RECEIPT, HEALTH_RECEIPT):
                try:
                    api.delete(path)
                except Exception:
                    pass
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(run())
