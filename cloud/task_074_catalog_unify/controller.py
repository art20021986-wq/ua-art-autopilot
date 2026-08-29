#!/usr/bin/env python3
"""GitHub Actions controller for approved TASK 074 production deployment."""
from __future__ import annotations

import datetime as dt
import html as html_lib
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


CONTRACT = "CATALOG-CARD-UNIFY-002-V1.0"
APPROVAL = "CATALOG-CARD-UNIFY-002-V1.0-APPROVED"
HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_074_catalog_unify"
INSTALLER = HERE / "installer.py"
REMOTE_INSTALLER = REMOTE + "/installer.py"
RECEIPTS = {name: REMOTE + "/" + name + "_receipt.json" for name in ("shadow", "install", "rollback")}
EVIDENCE = HERE / "evidence/controller.json"
REPORT = HERE / "TASK_074_REPORT.md"
MAX_BYTES = 24_000_000
PRODUCTION_WORKFLOWS = {
    "task068-ferry-vin-v1-1-deploy",
    "SEO Rehab Guard 068 production",
    "TASK073_GATE_B_V5",
    "task074-catalog-card-unify-v1",
}


class Blocked(RuntimeError):
    pass


def atomic_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def github_conflicts() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    current = str(os.environ.get("GITHUB_RUN_ID", ""))
    if not token or not repository or not current:
        raise Blocked("GITHUB_CONFLICT_GUARD_MISSING")
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ua-art-task074-conflict-guard/1",
    }
    conflicts = []
    for status in ("queued", "in_progress", "waiting", "pending"):
        url = "https://api.github.com/repos/%s/actions/runs?status=%s&per_page=100" % (repository, status)
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            runs = json.loads(response.read(4_000_001).decode()).get("workflow_runs") or []
        for run in runs:
            if str(run.get("id")) != current and run.get("name") in PRODUCTION_WORKFLOWS:
                conflicts.append({"id": run.get("id"), "name": run.get("name"), "status": run.get("status")})
    return conflicts


class API:
    def __init__(self) -> None:
        self.token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not self.token:
            raise Blocked("PYTHONANYWHERE_TOKEN_MISSING")

    def request(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None,
                allowed=(200,), timeout=120) -> tuple[int, bytes]:
        request_headers = {"Authorization": "Token " + self.token, "User-Agent": "ua-art-task074/1"}
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status, body = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise Blocked("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise Blocked("HTTP_%d:%s" % (status, url.rsplit("/", 2)[-2]))
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise Blocked("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing=False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise Blocked("REMOTE_FILE_MISSING")
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task074-" + uuid.uuid4().hex
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
                allowed=(200, 201, 429, 500, 502, 503, 504),
            )
            if status in (200, 201):
                return
            time.sleep(attempt * 2)
        raise Blocked("UPLOAD_FAILED")

    @staticmethod
    def objects(body: bytes) -> list:
        value = json.loads(body.decode())
        return value.get("tasks") or value.get("objects") or value.get("results") or [] if isinstance(value, dict) else value

    def create_trigger(self, command: str, description: str):
        form = urllib.parse.urlencode({"command": command, "description": description, "enabled": "true"}).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        value = json.loads(body.decode()) if status in (200, 201, 202) and body else {}
        if isinstance(value, dict) and isinstance(value.get("id"), int):
            return "always_on", value["id"]
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command, "description": description + " fallback", "enabled": "true",
            "interval": "daily", "hour": run_at.hour, "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        value = json.loads(body.decode()) if status in (200, 201, 202) and body else {}
        if not isinstance(value, dict) or not isinstance(value.get("id"), int):
            raise Blocked("REMOTE_TRIGGER_MISSING")
        return "schedule", value["id"]

    def delete_trigger(self, trigger) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request("DELETE", BASE + "%s/%d/" % (endpoint, identifier), allowed=(200, 202, 204, 404))

    def run_remote(self, mode: str, timeout=900) -> dict:
        receipt = RECEIPTS[mode]
        self.delete_file(receipt)
        trigger = self.create_trigger(
            "cd %s && python3.10 installer.py %s" % (REMOTE, mode),
            "task074 " + mode,
        )
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    return json.loads(raw.decode())
                time.sleep(5)
            raise Blocked("RECEIPT_TIMEOUT:" + mode)
        finally:
            self.delete_trigger(trigger)

    def launcher(self) -> dict:
        _, body = self.request("GET", BASE + "always_on/")
        matches = [item for item in self.objects(body) if isinstance(item, dict)
                   and item.get("enabled") is not False
                   and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise Blocked("PRODUCTION_LAUNCHER_COUNT:%d" % len(matches))
        return matches[0]

    def restart_bot(self) -> dict:
        item = self.launcher()
        identifier = int(item["id"])
        self.request("POST", BASE + "always_on/%d/restart/" % identifier, b"", allowed=(200, 201, 202, 204))
        return {"status": "accepted", "launcher_id": identifier}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_catalog_check() -> dict:
    result = {}
    opener = urllib.request.build_opener(NoRedirect)
    for root in ("video", "site"):
        url = "https://www.uaart.com.ua/%s/katalog.html?task074=%d" % (root, int(time.time()))
        request = urllib.request.Request(url, headers={"User-Agent": "ua-art-task074-public/1", "Cache-Control": "no-cache"})
        with opener.open(request, timeout=60) as response:
            status = response.status
            source = response.read(MAX_BYTES + 1).decode("utf-8")
            final_url = response.geturl()
        status_nodes = re.findall(
            r'<div\b[^>]*class=["\'][^"\']*\bstatus-pill\b[^"\']*["\'][^>]*>.*?</div\s*>',
            source, flags=re.I | re.S,
        )
        status_preserved = any(
            all(term in html_lib.unescape(re.sub(r"<[^>]+>", " ", node))
                for term in ("На пароме", "Маршрут", "Корея", "Грузия"))
            for node in status_nodes
        )
        checks = {
            "http_200": status == 200,
            "no_redirect": final_url.startswith("https://www.uaart.com.ua/%s/katalog.html" % root),
            "style_once": source.count("UA-CATALOG-CARD-UNIFY-002-V1.0") == 1,
            "no_ru_duplicate": "Автомобиль на пароме: Корея → Грузия." not in source,
            "no_uk_duplicate": "Автомобіль на поромі: Корея → Грузія." not in source,
            "ua0009": "UA-0009" in source,
            "eleven_blocks": source.count("<!-- UA-ART-CATALOG-VIN-V1:START -->") == 11,
            "status_preserved": status_preserved,
        }
        if not all(checks.values()):
            raise Blocked("PUBLIC_CATALOG_FAIL:%s:%s" % (root, json.dumps(checks, sort_keys=True)))
        result[root] = {"url": final_url, "bytes": len(source.encode()), "checks": checks}
    return result


def require_pass(value: dict, label: str) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise Blocked(label + "_FAILED:" + json.dumps(value.get("errors") or [])[:1000])


def report(value: dict) -> str:
    install = value.get("install") or {}
    return "\n".join([
        "# CATALOG-CARD-UNIFY-002 v1.0", "",
        "STATUS: **%s**" % value.get("status", "FAIL"), "",
        "- Дублирующий текст этапа удалён: %s" % ("PASS" if value.get("status") == "PASS" else "NOT VERIFIED"),
        "- Основной и нижний блок объединены единым фоном: %s" % ("PASS" if value.get("status") == "PASS" else "NOT VERIFIED"),
        "- Текущие карточки: 11; UA-0009: %s" % ("PASS" if value.get("status") == "PASS" else "NOT VERIFIED"),
        "- CRM/медиа/отдельные страницы изменены: НЕТ",
        "- Backup: `%s`" % install.get("backup_root", ""), "",
    ])


def main() -> int:
    value = {"contract_id": CONTRACT, "status": "BLOCKED", "errors": [], "rollback": None}
    api = None
    installed = False
    try:
        if os.environ.get("TASK074_OWNER_APPROVAL") != APPROVAL:
            raise Blocked("OWNER_APPROVAL_MISSING")
        conflicts = github_conflicts()
        if conflicts:
            raise Blocked("PARALLEL_PRODUCTION_GATE:" + json.dumps(conflicts))
        api = API()
        data = INSTALLER.read_bytes()
        compile(data.decode(), "installer.py", "exec")
        api.upload(REMOTE_INSTALLER, data)
        if api.read(REMOTE_INSTALLER) != data:
            raise Blocked("UPLOAD_READBACK")
        shadow = api.run_remote("shadow")
        value["shadow"] = shadow
        require_pass(shadow, "SHADOW")
        conflicts = github_conflicts()
        if conflicts:
            raise Blocked("PARALLEL_PRODUCTION_GATE_BEFORE_INSTALL:" + json.dumps(conflicts))
        install = api.run_remote("install")
        value["install"] = install
        require_pass(install, "INSTALL")
        installed = True
        if install.get("before", {}).get("database") != install.get("after", {}).get("database"):
            raise Blocked("INSTALL_DATABASE_CHANGED")
        if install.get("before", {}).get("protected_pages") != install.get("after", {}).get("protected_pages"):
            raise Blocked("INSTALL_CARD_PAGES_CHANGED")
        value["restart"] = api.restart_bot()
        time.sleep(18)
        value["postcheck"] = api.run_remote("shadow")
        require_pass(value["postcheck"], "POSTCHECK")
        value["public"] = public_catalog_check()
        time.sleep(65)
        value["postcheck_delayed"] = api.run_remote("shadow")
        require_pass(value["postcheck_delayed"], "DELAYED_POSTCHECK")
        value["public_delayed"] = public_catalog_check()
        value["status"] = "PASS"
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and installed:
            try:
                rollback = api.run_remote("rollback")
                value["rollback"] = rollback
                require_pass(rollback, "ROLLBACK")
                value["rollback_restart"] = api.restart_bot()
                value["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
                value["errors"].append("ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
    atomic_text(EVIDENCE, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, report(value))
    print(json.dumps({"status": value["status"], "errors": value["errors"]}, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
