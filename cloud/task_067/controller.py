#!/usr/bin/env python3
"""Shadow, deploy, restart, verify and soak CRM-ONLINE-GUARD-001 v1.3."""
from __future__ import annotations

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


HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
STAGING = "/home/Carix/autopilot_inbox/cloud/task_047_ferry_discovery"
STATE = "/home/Carix/autopilot_inbox/cloud/task_067"
CONTRACT = "CRM-ONLINE-GUARD-001-V1.3"
FILES = {
    "installer.py": HERE / "installer.py",
    "crm_online_guard.py": HERE / "crm_online_guard.py",
    "postcheck.py": HERE / "postcheck.py",
    "soak.py": HERE / "soak.py",
}
RECEIPTS = {
    "shadow": STATE + "/shadow_receipt.json",
    "install": STATE + "/install_receipt.json",
    "postcheck": STATE + "/postcheck_receipt.json",
    "soak": STATE + "/soak_receipt.json",
    "rollback": STATE + "/rollback_receipt.json",
}
COMMANDS = {
    "shadow": "cd %s && python3.10 installer.py --shadow" % STAGING,
    "install": "cd %s && python3.10 installer.py" % STAGING,
    "postcheck": "cd %s && python3.10 postcheck.py" % STAGING,
    "soak": "cd %s && python3.10 soak.py" % STAGING,
    "rollback": "cd %s && python3.10 installer.py --rollback" % STAGING,
}
EVIDENCE = HERE / "evidence" / "deploy.json"
REPORT = HERE / "FINAL_REPORT.md"
MAX_BYTES = 8_000_000


class ControllerError(RuntimeError):
    pass


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, prefix="." + path.name + ".",
                                         suffix=".tmp", delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class API:
    def __init__(self):
        self.token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not self.token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")

    def request(self, method, url, data=None, headers=None, allowed=(200,), timeout=90):
        request_headers = {"Authorization": "Token " + self.token,
                           "User-Agent": "ua-art-crm-online-guard-001-v1.3"}
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status, body = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d" % status)
        return status, body

    def file_url(self, path):
        if not (path.startswith(STAGING + "/") or path.startswith(STATE + "/")):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path, missing=False):
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete_file(self, path):
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))

    def upload(self, path, data):
        boundary = "----task067-" + uuid.uuid4().hex
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
                allowed=(200, 201, 429, 500, 502, 503, 504))
            if status in (200, 201):
                return
            time.sleep(min(2 * attempt, 10))
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def objects(body):
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    @staticmethod
    def trigger_id(body):
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, command, description):
        form = urllib.parse.urlencode({"command": command, "description": description,
                                      "enabled": "true"}).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409))
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({"command": command, "description": description + " fallback",
                                      "enabled": "true", "interval": "daily",
                                      "hour": run_at.hour, "minute": run_at.minute}).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409))
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger):
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request("DELETE", BASE + "%s/%d/" % (endpoint, identifier),
                     allowed=(200, 202, 204, 404))

    def run_remote(self, key, timeout):
        receipt = RECEIPTS[key]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[key], "task067 " + key)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    return json.loads(raw.decode("utf-8"))
                time.sleep(5)
            raise ControllerError("RECEIPT_TIMEOUT:" + key)
        finally:
            self.delete_trigger(trigger)

    def restart(self):
        _, body = self.request("GET", BASE + "always_on/")
        tasks = self.objects(body)
        matches = [item for item in tasks if isinstance(item, dict)
                   and item.get("enabled") is not False
                   and str(item.get("command", "")).strip() ==
                   "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise ControllerError("PRODUCTION_LAUNCHER_COUNT:%d" % len(matches))
        identifier = int(matches[0]["id"])
        self.request("POST", BASE + "always_on/%d/restart/" % identifier,
                     b"", allowed=(200, 201, 202, 204))
        return {"status": "accepted", "launcher_id": identifier,
                "command": "python3.10 /home/Carix/start_safe.py"}


def require_pass(value, key):
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError("%s_FAIL:%s" % (key, json.dumps(value.get("errors") or value.get("p0") or [])[:500]))


def report_markdown(value):
    ok = value.get("status") == "PASS"
    post = value.get("postcheck_final") or value.get("postcheck_initial") or {}
    voice = post.get("voice_golden") or {}
    media = post.get("media") or {}
    fields = post.get("field_queue") or {}
    soak = value.get("soak") or {}
    lines = ["# CRM-ONLINE-GUARD-001 v1.3 — финальный отчёт", "",
             "Статус: **%s**" % ("PASS" if ok else "FAIL"), "",
             "- Атомарная установка и автоматический rollback: %s" % ("PASS" if value.get("install", {}).get("status") == "PASS" else "FAIL"),
             "- Оба Telegram-бота и heartbeat: %s" % ("PASS" if post.get("bots") else "FAIL"),
             "- Критические callback-маршруты ≤5 с: %s" % ("PASS" if post.get("callbacks") else "FAIL"),
             "- RU/UA/EN golden: %s/%s" % (voice.get("cases", 0) - voice.get("failures", 0), voice.get("cases", 0)),
             "- Медиа: %s принято, %s сохранено, очередь %s" % (media.get("accepted", 0), media.get("saved", 0), media.get("queue", "?")),
             "- SQLite ≤2 с + durable field queue: %s (очередь %s)" % (
                 fields.get("status", "—"), fields.get("queue", "?")),
             "- 60-минутный soak: %s (%s с)" % (soak.get("status", "—"), soak.get("duration_actual_seconds", 0)),
             "- LLM-токены guard/детерминированных тестов: 0", "",
             "Существующие карточки, сайт и медиа установщиком не изменялись.", ""]
    if value.get("errors"):
        lines.extend(["Ошибки:", "", "```", "\n".join(value["errors"]), "```", ""])
    return "\n".join(lines)


def main():
    result = {"task_id": "task_067", "contract_id": CONTRACT,
              "status": "FAIL", "mode": "ATOMIC_DEPLOY_AND_60M_SOAK",
              "llm_tokens": 0, "errors": [], "started_at_utc": utc_now()}
    api = None
    installed = False
    try:
        api = API()
        for remote_name, local_path in FILES.items():
            api.upload(STAGING + "/" + remote_name, local_path.read_bytes())
        result["uploaded"] = sorted(FILES)
        shadow = api.run_remote("shadow", 900)
        result["shadow"] = shadow
        require_pass(shadow, "SHADOW")
        install = api.run_remote("install", 900)
        result["install"] = install
        require_pass(install, "INSTALL")
        installed = True
        result["restart"] = api.restart()
        initial = api.run_remote("postcheck", 900)
        result["postcheck_initial"] = initial
        require_pass(initial, "POSTCHECK_INITIAL")
        soak = api.run_remote("soak", 3900)
        result["soak"] = soak
        require_pass(soak, "SOAK")
        final = api.run_remote("postcheck", 900)
        result["postcheck_final"] = final
        require_pass(final, "POSTCHECK_FINAL")
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
        if installed and api is not None:
            try:
                rollback = api.run_remote("rollback", 900)
                result["rollback"] = rollback
                if rollback.get("status") == "PASS":
                    result["rollback_restart"] = api.restart()
                else:
                    result["errors"].append("ROLLBACK_STATUS_FAIL")
            except Exception as rollback_exc:
                result["errors"].append("ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
    result["finished_at_utc"] = utc_now()
    atomic_text(EVIDENCE, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, report_markdown(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
