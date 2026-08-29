#!/usr/bin/env python3
"""GitHub Actions controller for the owner-directed TASK 083 deployment."""
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

import installer as installer_mod


CONTRACT = "CATALOG-CARD-DEDUP-GUARD-083-V1.0"
APPROVAL = "CATALOG-CARD-DEDUP-GUARD-083-V1.0-OWNER-DIRECTIVE"
HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_083_catalog_dedup"
INSTALLER = HERE / "installer.py"
REMOTE_INSTALLER = REMOTE + "/installer.py"
RECEIPTS = {name: REMOTE + "/" + name + "_receipt.json" for name in ("shadow", "install", "rollback")}
EVIDENCE = HERE / "evidence/controller.json"
REPORT = HERE / "TASK_083_REPORT.md"
MAX_BYTES = 24_000_000
PRODUCTION_WORKFLOWS = {
    "task068-ferry-vin-v1-1-deploy",
    "SEO Rehab Guard 068 production",
    "TASK073_GATE_B_V5",
    "task074-catalog-card-unify-v1",
    "task082-catalog-stage-production",
    "task084-crm-hang-root-cause-production",
    "task083-catalog-dedup-v1",
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
        "User-Agent": "ua-art-task083-conflict-guard/1",
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


def wait_for_github_quiet(timeout: int = 1200) -> list[dict]:
    deadline = time.monotonic() + timeout
    last: list[dict] = []
    while time.monotonic() < deadline:
        last = github_conflicts()
        if not last:
            return []
        time.sleep(15)
    raise Blocked("PARALLEL_PRODUCTION_GATE_TIMEOUT:" + json.dumps(last))


class API:
    def __init__(self) -> None:
        self.token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not self.token:
            raise Blocked("PYTHONANYWHERE_TOKEN_MISSING")

    def request(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None,
                allowed=(200,), timeout=120) -> tuple[int, bytes]:
        request_headers = {"Authorization": "Token " + self.token, "User-Agent": "ua-art-task083/1"}
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
        boundary = "----uaart-task083-" + uuid.uuid4().hex
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
            "task083 " + mode,
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
    # /video/katalog.html is the client-facing catalog.  The parallel
    # /site/katalog.html file is still protected and validated byte-for-byte
    # by the remote installer, but production routing does not expose it as a
    # catalog endpoint, so it must not be used as a public HTTP gate.
    for root in ("video",):
        url = "https://www.uaart.com.ua/%s/katalog.html?task083=%d" % (root, int(time.time()))
        request = urllib.request.Request(url, headers={"User-Agent": "ua-art-task083-public/1", "Cache-Control": "no-cache"})
        # Production canonically redirects www.uaart.com.ua to uaart.com.ua.
        # Follow it, but accept only HTTPS, the two owned hosts and the exact
        # requested catalog path; a foreign host/path remains a hard failure.
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            source = response.read(MAX_BYTES + 1).decode("utf-8")
            final_url = response.geturl()
        final = urllib.parse.urlsplit(final_url)
        safe_canonical_url = (
            final.scheme == "https"
            and final.hostname in {"www.uaart.com.ua", "uaart.com.ua"}
            and final.path == "/%s/katalog.html" % root
        )
        analysis = installer_mod.validate_catalog(source, require_dedup=True)
        style_marker = (
            installer_mod.STYLE_MARKER
            if analysis["mode"] == "legacy_v1"
            else installer_mod.STAGE_STYLE_MARKER
        )
        checks = {
            "http_200": status == 200,
            "safe_canonical_url": safe_canonical_url,
            "style_once": source.count(style_marker) == 1,
            "ua0009": "UA-0009" in analysis["identifiers"],
            "ua0011": "UA-0011" in analysis["identifiers"],
            "at_least_eleven_blocks": analysis["card_count"] >= 11,
            "no_semantic_duplicates": not analysis["duplicate_issues"],
            "status_preserved": installer_mod.ferry_status_present(source),
        }
        if not all(checks.values()):
            raise Blocked("PUBLIC_CATALOG_FAIL:%s:%s" % (root, json.dumps(checks, sort_keys=True)))
        result[root] = {
            "url": final_url,
            "bytes": len(source.encode()),
            "checks": checks,
            "mode": analysis["mode"],
            "card_count": analysis["card_count"],
            "identifiers": analysis["identifiers"],
        }
    return result


def require_pass(value: dict, label: str) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise Blocked(label + "_FAILED:" + json.dumps(value.get("errors") or [])[:1000])


def already_enforced(shadow: dict) -> bool:
    if any(item.get("changed") for item in (shadow.get("candidate_sources") or {}).values()):
        return False
    core = shadow.get("candidate_core")
    if core and core.get("changed"):
        return False
    before_catalogs = (shadow.get("before") or {}).get("catalogs") or {}
    for path, item in (shadow.get("candidate_catalogs") or {}).items():
        if item.get("sha256") != (before_catalogs.get(path) or {}).get("sha256"):
            return False
    return bool(before_catalogs)


def report(value: dict) -> str:
    install = value.get("install") or {}
    return "\n".join([
        "# CATALOG-CARD-DEDUP-GUARD-083 v1.0", "",
        "STATUS: **%s**" % value.get("status", "FAIL"), "",
        "- Повторы этапа, двигателя и видео удалены: %s" % ("PASS" if value.get("status") == "PASS" else "NOT VERIFIED"),
        "- Уникальные VIN, ETA и полезные сведения сохранены: %s" % ("PASS" if value.get("status") == "PASS" else "NOT VERIFIED"),
        "- Общий генератор будущих карточек защищён: %s" % ("PASS" if value.get("status") == "PASS" else "NOT VERIFIED"),
        "- Все текущие карточки и UA-0009: %s" % ("PASS" if value.get("status") == "PASS" else "NOT VERIFIED"),
        "- CRM/медиа/отдельные страницы изменены: НЕТ",
        "- Backup: `%s`" % install.get("backup_root", ""), "",
    ])


def main() -> int:
    value = {"contract_id": CONTRACT, "status": "BLOCKED", "errors": [], "rollback": None}
    api = None
    installed = False
    try:
        if os.environ.get("TASK083_OWNER_DIRECTIVE") != APPROVAL:
            raise Blocked("OWNER_DIRECTIVE_MISSING")
        verify_only = os.environ.get("TASK083_VERIFY_ONLY") == "1"
        if not verify_only:
            wait_for_github_quiet()
        api = API()
        data = INSTALLER.read_bytes()
        compile(data.decode(), "installer.py", "exec")
        api.upload(REMOTE_INSTALLER, data)
        if api.read(REMOTE_INSTALLER) != data:
            raise Blocked("UPLOAD_READBACK")
        shadow = api.run_remote("shadow")
        value["shadow"] = shadow
        require_pass(shadow, "SHADOW")
        if not verify_only:
            wait_for_github_quiet(timeout=600)
        if verify_only and not already_enforced(shadow):
            raise Blocked("VERIFY_ONLY_GUARD_NOT_INSTALLED")
        if already_enforced(shadow):
            install = {
                "contract_id": CONTRACT,
                "status": "PASS",
                "mode": "ALREADY_INSTALLED",
                "production_write": False,
                "crm_db_write": False,
                "backup_root": None,
                "changed_paths": [],
                "before": shadow["before"],
                "after": shadow["before"],
            }
        else:
            install = api.run_remote("install")
        value["install"] = install
        require_pass(install, "INSTALL")
        installed = install.get("mode") == "INSTALL"
        if install.get("before", {}).get("database") != install.get("after", {}).get("database"):
            raise Blocked("INSTALL_DATABASE_CHANGED")
        if install.get("before", {}).get("protected_pages") != install.get("after", {}).get("protected_pages"):
            raise Blocked("INSTALL_CARD_PAGES_CHANGED")
        if installed:
            value["restart"] = api.restart_bot()
            time.sleep(18)
        else:
            value["restart"] = {"status": "SKIPPED_ALREADY_INSTALLED"}
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
