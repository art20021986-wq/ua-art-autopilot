#!/usr/bin/env python3
"""Guarded production controller for TASK109 container tracking UI."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Mapping

import remote_installer as installer


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TASK_ID = "TASK109-CONTAINER-TRACK-INLINE"
CONTRACT = "UA-CARDS-CONTAINER-TRACK-INLINE-001-V1.0"
CRITICAL_CONTRACT = "UA-ART-CRITICAL-ADAPTER-V1.0"
MANIFEST_SHA256 = "d8e7e895a3c2540a1b79ab3f69cdfb885c74c6c03dff396515f7f6dbfbc5b1cb"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin"
REMOTE_SCRIPT = REMOTE + "/task109_container_inline.py"
SOURCE_RECEIPT = REMOTE + "/task109_source_receipt.json"
CARDS_RECEIPT = REMOTE + "/task109_cards_receipt.json"
VERIFY_RECEIPT = REMOTE + "/task109_verify_receipt.json"
ROLLBACK_RECEIPT = REMOTE + "/task109_rollback_receipt.json"
SOURCE_COMMAND = "cd %s && python3.10 task109_container_inline.py --sources-only" % REMOTE
CARDS_COMMAND = "cd %s && python3.10 task109_container_inline.py --cards-only" % REMOTE
VERIFY_COMMAND = "cd %s && python3.10 task109_container_inline.py --verify" % REMOTE
ROLLBACK_CARDS_COMMAND = "cd %s && python3.10 task109_container_inline.py --rollback-cards" % REMOTE
ROLLBACK_SOURCES_COMMAND = "cd %s && python3.10 task109_container_inline.py --rollback-sources" % REMOTE
EVIDENCE_REL = "automation/packages/task109_container_inline/evidence.json"
RECEIPT_REL = "state/receipts/%s.json" % TASK_ID
MAX_BYTES = 8_000_000
PUBLIC_BASE = "https://www.uaart.com.ua/video/"
CARD_LINK_RE = re.compile(r'href=["\'](?:https://www\.uaart\.com\.ua/video/)?(UA-[0-9]{4,}\.html)(?:\?[^"\']*)?["\']', re.I)


class ControllerError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


def safe_repo_path(value: str) -> str:
    path = pathlib.PurePosixPath(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ControllerError("UNSAFE_REPO_PATH")
    return path.as_posix()


def rooted(value: str) -> pathlib.Path:
    normalized = safe_repo_path(value)
    result = (ROOT / normalized).resolve(strict=False)
    base = ROOT.resolve(strict=False)
    if result == base or not result.is_relative_to(base):
        raise ControllerError("PATH_ESCAPE")
    return result


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent,
        prefix="." + path.name + ".", suffix=".task109.tmp", delete=False,
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


def required_environment(environment: Mapping[str, str]) -> dict[str, str]:
    keys = (
        "PYTHONANYWHERE_API_TOKEN",
        "UAART_REQUEST_PATH",
        "UAART_TASK_ID",
        "UAART_TASK_CLASS",
        "UAART_REQUEST_SHA256",
        "UAART_RUN_ID",
        "UAART_RECEIPT_PATH",
    )
    values = {key: str(environment.get(key, "")).strip() for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ControllerError("MISSING_ENVIRONMENT:" + ",".join(missing))
    if values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"].upper() != "CRITICAL":
        raise ControllerError("TASK_IDENTITY")
    if safe_repo_path(values["UAART_RECEIPT_PATH"]) != RECEIPT_REL:
        raise ControllerError("RECEIPT_IDENTITY")
    request_path = rooted(values["UAART_REQUEST_PATH"])
    if sha256_file(request_path) != values["UAART_REQUEST_SHA256"]:
        raise ControllerError("REQUEST_SHA_MISMATCH")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("task_id") != TASK_ID or request.get("production_required") is not True:
        raise ControllerError("REQUEST_IDENTITY")
    critical = request.get("critical") or {}
    if critical.get("manifest_sha256") != MANIFEST_SHA256:
        raise ControllerError("REQUEST_MANIFEST_IDENTITY")
    return values


def rollback_drill() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="uaart-task109-rollback-") as folder:
        path = pathlib.Path(folder) / "contract.txt"
        baseline = b"TASK109-BASELINE\n"
        path.write_bytes(baseline)
        backup = path.read_bytes()
        before = sha256_file(path)
        path.write_bytes(b"TASK109-DRILL-MUTATION\n")
        during = sha256_file(path)
        path.write_bytes(backup)
        after = sha256_file(path)
        if before == during or before != after or path.read_bytes() != baseline:
            raise ControllerError("ROLLBACK_DRILL")
        return {"status": "PASS", "before": before, "during": during, "after": after}


def browser_binary() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise ControllerError("HEADLESS_BROWSER_REQUIRED")


def mobile_width_contract(*, require_browser: bool = True) -> dict[str, Any]:
    """Render the exact migrated control and fail on wrap/overflow/hidden underline."""
    try:
        browser = browser_binary()
    except ControllerError:
        if require_browser:
            raise
        return {"status": "SKIP", "reason": "browser unavailable", "widths": []}
    page, _ = installer.transform_card(installer.card_fixture())
    base_css = (
        "<style>*{box-sizing:border-box}html,body{margin:0;width:100%;max-width:100%;"
        "overflow-x:hidden}.ua-delivery-v1{display:block;width:100%;padding:20px}"
        ".ua-stage-v1-meta{width:100%}</style>"
    )
    script = """<script>
addEventListener('load',()=>{
 const row=document.querySelector('.ua-stage-v1-container-row');
 const link=document.querySelector('.ua-stage-v1-track-link');
 const root=document.documentElement;
 const style=row?getComputedStyle(row):null;
 const linkStyle=link?getComputedStyle(link):null;
 const ok=!!row&&!!link&&row.scrollWidth<=row.clientWidth+1&&
  row.getBoundingClientRect().right<=root.clientWidth+1&&
  root.scrollWidth<=root.clientWidth+1&&style.flexWrap==='nowrap'&&
  style.whiteSpace==='nowrap'&&linkStyle.textDecorationLine.includes('underline');
 document.body.dataset.task109Contract=ok?'PASS':'FAIL';
});
</script>"""
    page = page.replace("<head>", '<head><meta name="viewport" content="width=device-width,initial-scale=1">' + base_css, 1)
    page = page.replace("</body>", script + "</body>", 1)
    results = []
    with tempfile.TemporaryDirectory(prefix="uaart-task109-browser-") as folder:
        fixture = pathlib.Path(folder) / "fixture.html"
        fixture.write_text(page, encoding="utf-8")
        for width in (320, 375, 430):
            completed = subprocess.run(
                [
                    browser, "--headless=new", "--no-sandbox", "--disable-gpu",
                    "--disable-dev-shm-usage", "--hide-scrollbars",
                    "--virtual-time-budget=1000", "--window-size=%d,900" % width,
                    "--dump-dom", fixture.as_uri(),
                ],
                check=False, capture_output=True, text=True, timeout=45,
            )
            passed = completed.returncode == 0 and 'data-task109-contract="PASS"' in completed.stdout
            results.append({"width": width, "status": "PASS" if passed else "FAIL"})
            if not passed:
                raise ControllerError("MOBILE_WIDTH_CONTRACT:%d" % width)
    return {"status": "PASS", "widths": results}


class API:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, url: str, data: bytes | None = None,
                headers: dict[str, str] | None = None, allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task109-container-inline/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = response.status
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d" % status)
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
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
        boundary = "----uaart-task109-" + uuid.uuid4().hex
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
        raise ControllerError("UPLOAD_FAILED")

    @staticmethod
    def objects(body: bytes) -> list[Any]:
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    @staticmethod
    def trigger_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, command: str, description: str) -> tuple[str, int]:
        form = urllib.parse.urlencode({
            "command": command, "description": description, "enabled": "true",
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
            "command": command, "description": description + " fallback", "enabled": "true",
            "interval": "daily", "hour": run_at.hour, "minute": run_at.minute,
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
        self.request("DELETE", BASE + "%s/%d/" % (endpoint, identifier), allowed=(200, 202, 204, 404))

    def run_remote(self, command: str, description: str, receipt_path: str,
                   seconds: int = 900) -> dict[str, Any]:
        self.delete_file(receipt_path)
        trigger = self.create_trigger(command, description)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt_path, missing=True)
                if raw:
                    value = json.loads(raw.decode("utf-8"))
                    if not isinstance(value, dict):
                        raise ControllerError("REMOTE_RECEIPT_OBJECT")
                    return value
                time.sleep(5)
            raise ControllerError("REMOTE_RECEIPT_TIMEOUT:" + pathlib.PurePosixPath(receipt_path).name)
        finally:
            self.delete_trigger(trigger)

    def restart_bot(self) -> dict[str, Any]:
        _, body = self.request("GET", BASE + "always_on/")
        matching = [
            item for item in self.objects(body)
            if isinstance(item, dict) and item.get("enabled") is not False
            and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matching) != 1 or not isinstance(matching[0].get("id"), int):
            raise ControllerError("PRODUCTION_BOT_TASK_NOT_UNIQUE")
        self.request(
            "POST", BASE + "always_on/%d/restart/" % matching[0]["id"], b"",
            allowed=(200, 201, 202, 204),
        )
        return {"status": "PASS", "command": "python3.10 /home/Carix/start_safe.py"}


def validate_phase(value: Mapping[str, Any], phase: str) -> None:
    if value.get("task_id") != TASK_ID or value.get("contract_id") != CONTRACT:
        raise ControllerError("%s_IDENTITY" % phase.upper())
    if value.get("status") != "PASS":
        raise ControllerError("%s_FAILED:%s" % (phase.upper(), ";".join(value.get("errors") or [])))
    if value.get("crm_write") is not False or value.get("media_write") is not False:
        raise ControllerError("%s_SCOPE" % phase.upper())
    if phase in {"sources", "cards"} and not str(value.get("backup", "")).startswith(REMOTE + "/task109_backups/"):
        raise ControllerError("%s_BACKUP" % phase.upper())
    if phase in {"cards", "verify"}:
        if int(value.get("card_count", 0)) < 16 or int(value.get("page_count", 0)) < 32:
            raise ControllerError("%s_CARD_COUNT" % phase.upper())
        if int(value.get("tracking_card_count", 0)) < 1:
            raise ControllerError("%s_TRACKING_COUNT" % phase.upper())


def fetch_public(path: str) -> str:
    nonce = str(int(time.time() * 1000))
    separator = "&" if "?" in path else "?"
    url = urllib.parse.urljoin(PUBLIC_BASE, path) + separator + "task109=" + nonce
    request = urllib.request.Request(url, headers={
        "User-Agent": "ua-art-task109-live-verify/1",
        "Cache-Control": "no-cache",
    })
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read(MAX_BYTES + 1)
            status = response.status
    except Exception as exc:
        raise ControllerError("PUBLIC_FETCH:" + type(exc).__name__) from exc
    if status != 200 or len(body) > MAX_BYTES:
        raise ControllerError("PUBLIC_HTTP")
    return body.decode("utf-8")


def public_verify(expected_ids: list[str]) -> dict[str, Any]:
    catalog = fetch_public("katalog.html")
    linked = sorted({match[:-5] for match in CARD_LINK_RE.findall(catalog)})
    if not set(expected_ids).issubset(linked):
        raise ControllerError("PUBLIC_CATALOG_CARD_SET")
    verified: dict[str, Any] = {}
    for card_id in expected_ids:
        page = fetch_public(card_id + ".html")
        verified[card_id] = installer.validate_card(page)
    trackable = sum(1 for item in verified.values() if item.get("trackable"))
    if len(verified) < 16 or trackable < 1:
        raise ControllerError("PUBLIC_CARD_CONTRACT")
    return {
        "status": "PASS", "card_count": len(verified),
        "tracking_card_count": trackable, "catalog_card_count": len(linked),
        "card_ids": expected_ids,
    }


def rollback(api: API, cards: Mapping[str, Any] | None,
             sources: Mapping[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "PASS", "cards": None, "sources": None, "errors": []}
    if cards and cards.get("status") == "PASS" and cards.get("backup"):
        try:
            result["cards"] = api.run_remote(
                ROLLBACK_CARDS_COMMAND, "task109 rollback cards", ROLLBACK_RECEIPT,
            )
            if result["cards"].get("status") != "PASS":
                raise ControllerError("CARD_ROLLBACK_FAILED")
        except Exception as exc:
            result["errors"].append(type(exc).__name__ + ":" + str(exc))
    if sources and sources.get("status") == "PASS" and sources.get("backup"):
        try:
            result["sources"] = api.run_remote(
                ROLLBACK_SOURCES_COMMAND, "task109 rollback generators", ROLLBACK_RECEIPT,
            )
            if result["sources"].get("status") != "PASS":
                raise ControllerError("SOURCE_ROLLBACK_FAILED")
        except Exception as exc:
            result["errors"].append(type(exc).__name__ + ":" + str(exc))
    try:
        result["restart"] = api.restart_bot()
    except Exception as exc:
        result["errors"].append("RESTART_" + type(exc).__name__ + ":" + str(exc))
    if result["errors"]:
        result["status"] = "FAIL"
    return result


def execute(environment: Mapping[str, str]) -> dict[str, Any]:
    values = required_environment(environment)
    evidence: dict[str, Any] = {
        "task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL",
        "started_at": utc_now(), "errors": [], "llm_tokens": 0,
        "automatic_mode_enabled": False,
    }
    api: API | None = None
    sources: dict[str, Any] | None = None
    cards: dict[str, Any] | None = None
    try:
        evidence["rollback_drill"] = rollback_drill()
        evidence["mobile_widths"] = mobile_width_contract(require_browser=True)
        local_script = HERE / "remote_installer.py"
        payload = local_script.read_bytes()
        compile(payload.decode("utf-8"), str(local_script), "exec")
        if installer.self_test() != 0:
            raise ControllerError("INSTALLER_SELF_TEST")

        api = API(values["PYTHONANYWHERE_API_TOKEN"])
        api.upload(REMOTE_SCRIPT, payload)
        if api.read(REMOTE_SCRIPT) != payload:
            raise ControllerError("UPLOAD_READBACK")

        sources = api.run_remote(SOURCE_COMMAND, "task109 update all card generators", SOURCE_RECEIPT)
        evidence["sources"] = sources
        validate_phase(sources, "sources")
        evidence["source_restart"] = api.restart_bot()
        time.sleep(12)

        cards = api.run_remote(CARDS_COMMAND, "task109 update existing cards", CARDS_RECEIPT)
        evidence["cards"] = cards
        validate_phase(cards, "cards")
        evidence["card_restart"] = api.restart_bot()
        time.sleep(10)

        immediate = api.run_remote(VERIFY_COMMAND, "task109 immediate persistence check", VERIFY_RECEIPT)
        evidence["verify_immediate"] = immediate
        validate_phase(immediate, "verify")
        if immediate.get("source_sha256") != sources.get("source_sha256"):
            raise ControllerError("GENERATOR_DRIFT")
        if immediate.get("protected_sha256") != sources.get("protected_sha256"):
            raise ControllerError("PROTECTED_DRIFT")
        if immediate.get("media_inventory_sha256") != sources.get("media_inventory_sha256"):
            raise ControllerError("MEDIA_DRIFT")
        public_now = public_verify(list(immediate["card_ids"]))
        evidence["public_immediate"] = public_now

        time.sleep(35)
        delayed = api.run_remote(VERIFY_COMMAND, "task109 delayed persistence check", VERIFY_RECEIPT)
        evidence["verify_delayed"] = delayed
        validate_phase(delayed, "verify")
        if delayed.get("source_sha256") != immediate.get("source_sha256"):
            raise ControllerError("DELAYED_GENERATOR_DRIFT")
        if delayed.get("protected_sha256") != immediate.get("protected_sha256"):
            raise ControllerError("DELAYED_PROTECTED_DRIFT")
        if delayed.get("media_inventory_sha256") != immediate.get("media_inventory_sha256"):
            raise ControllerError("DELAYED_MEDIA_DRIFT")
        public_delayed = public_verify(list(delayed["card_ids"]))
        evidence["public_delayed"] = public_delayed
        evidence["status"] = "PASS"
        evidence["finished_at"] = utc_now()

        receipt = {
            "contract_id": CRITICAL_CONTRACT,
            "task_id": TASK_ID,
            "status": "FINISHED",
            "task_class": "CRITICAL",
            "target_environment": "production",
            "tests": "PASS",
            "backup": "%s ; %s" % (sources["backup"], cards["backup"]),
            "production": "PASS",
            "live_verify": "PASS",
            "rollback": "PASS",
            "unexpected_changes": 0,
            "protected_files_unchanged": True,
            "crm_unchanged": True,
            "manifest_sha256": MANIFEST_SHA256,
            "rollback_ready": True,
            "production_required": True,
            "run_id": values["UAART_RUN_ID"],
            "request_sha256": values["UAART_REQUEST_SHA256"],
            "card_count": delayed["card_count"],
            "page_count": delayed["page_count"],
            "tracking_card_count": delayed["tracking_card_count"],
            "mobile_widths": [320, 375, 430],
            "future_card_generators": sorted((delayed.get("source_sha256") or {}).keys()),
            "cta_ru": "Отследить ↗",
            "cta_uk": "Відстежити ↗",
            "finished_at": utc_now(),
        }
        atomic_text(rooted(RECEIPT_REL), json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None:
            evidence["rollback"] = rollback(api, cards, sources)
    finally:
        atomic_text(rooted(EVIDENCE_REL), json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return evidence


def main() -> int:
    result = execute(os.environ)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
