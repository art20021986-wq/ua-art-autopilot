#!/usr/bin/env python3
"""Upload, execute, restart, verify and auto-rollback TASK 085."""
from __future__ import annotations

import datetime as dt
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


HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
# Reuse the proven existing task083 staging directory.  PythonAnywhere's
# temporary always-on bootstrap lane can be delayed indefinitely; unique
# task085 filenames keep this package isolated without creating a second writer.
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_083_catalog_dedup"
FILES = {
    REMOTE + "/task085_remote_installer.py": HERE / "remote_installer.py",
    REMOTE + "/task085_stage_payload_guard.py": HERE / "stage_payload_guard.py",
}
RECEIPTS = {
    mode: REMOTE + "/task085_%s_receipt.json" % mode
    for mode in ("shadow", "apply", "postcheck", "rollback")
}
COMMANDS = {
    mode: "cd %s && python3.10 task085_remote_installer.py %s" % (REMOTE, mode)
    for mode in RECEIPTS
}
DIR_MARKER = REMOTE + "/task085_directory.ready"
CONTRACT_ID = "UA-0011-STAGE-PAYLOAD-RESET-005-V1.0"
TARGET_CODE = "UA-0011"
PROTECTED_CODE = "UA-0009"
EXPECTED_STATUS = "kr_bought"
EXPECTED_VIN = "KMHE341DBKA544289"
OLD_CONTAINER = "ONEYSELGF1046602"
OLD_ETA_VALUES = (
    "2026-12-12", "12.12.2026", "12 декабря 2026", "12 грудня 2026",
)
EVIDENCE = HERE / "evidence/production.json"
REPORT = HERE / "TASK_085_REPORT.md"
MAX_BYTES = 20_000_000


class ControllerError(RuntimeError):
    pass


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class API:
    def __init__(self) -> None:
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,), timeout=90):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task085-controller/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(
            url, data=data, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status, body = int(response.status), response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d:%s" % (status, urllib.parse.urlsplit(url).path))
        return status, body

    def file_url(self, path: str) -> str:
        allowed = set(FILES) | set(RECEIPTS.values()) | {DIR_MARKER}
        if path not in allowed:
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False):
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING")
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task085-" + uuid.uuid4().hex
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
    def _objects(body: bytes) -> list:
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    @staticmethod
    def _trigger_id(body: bytes):
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, command: str, description: str):
        """Use the scheduled lane; a second always-on process is quota-blocked."""
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)
        form = urllib.parse.urlencode({
            "command": command,
            "description": description + " scheduled executor",
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
        identifier = self._trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_SCHEDULED_EXECUTOR")
        return "schedule", identifier

    def delete_trigger(self, trigger) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", BASE + "%s/%d/" % (endpoint, identifier),
            allowed=(200, 202, 204, 404),
        )

    def ensure_directory(self) -> None:
        """Verify the existing staging lane without a delayed bootstrap trigger."""
        marker = b"TASK085_READY"
        self.upload(DIR_MARKER, marker)
        if self.read(DIR_MARKER) != marker:
            raise ControllerError("REMOTE_STAGING_READBACK")

    def run_remote(self, mode: str, timeout: int = 360) -> dict[str, Any]:
        receipt = RECEIPTS[mode]
        last_error = None
        for run_attempt in (1, 2):
            self.delete_file(receipt)
            trigger = self.create_trigger(
                COMMANDS[mode], "task085 %s attempt %d" % (mode, run_attempt)
            )
            try:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    raw = self.read(receipt, missing=True)
                    if raw:
                        return json.loads(raw.decode("utf-8"))
                    time.sleep(5)
                last_error = "REMOTE_RECEIPT_TIMEOUT:%s:%d" % (mode, run_attempt)
            finally:
                self.delete_trigger(trigger)
            # The remote file lock makes this retry serial and idempotent.
            time.sleep(5)
        raise ControllerError(last_error or "REMOTE_EXECUTION_FAILED:" + mode)

    def restart_bot(self) -> dict[str, Any]:
        _, body = self.request("GET", BASE + "always_on/")
        matches = [
            item for item in self._objects(body)
            if isinstance(item, dict) and item.get("enabled") is not False
            and str(item.get("command", "")).strip()
            == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matches) != 1:
            raise ControllerError("ACTIVE_LAUNCHER_COUNT:%d" % len(matches))
        identifier = int(matches[0]["id"])
        self.request(
            "POST", BASE + "always_on/%d/restart/" % identifier,
            b"", allowed=(200, 201, 202, 204),
        )
        return {
            "command": "python3.10 /home/Carix/start_safe.py",
            "task_id": identifier, "restart_accepted": True,
        }


def require_pass(value: dict, label: str) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError(
            "%s_FAIL:%s" % (label, ";".join(value.get("errors") or []))
        )
    if value.get("runtime_llm_tokens") != 0:
        raise ControllerError(label + "_LLM_TOKENS")


def validate_shadow(value: dict) -> None:
    require_pass(value, "SHADOW")
    if value.get("production_write") or value.get("crm_write") or value.get("media_write"):
        raise ControllerError("SHADOW_WRITE_SCOPE")
    target = (value.get("database") or {}).get("target") or {}
    projected = value.get("projected_target") or {}
    if (
        target.get("auto_number") != TARGET_CODE
        or str(target.get("vin") or "").strip().upper() != EXPECTED_VIN
        or projected.get("status") != EXPECTED_STATUS
    ):
        raise ControllerError("SHADOW_TARGET")
    for field in ("sea_container", "sea_date_out", "days_to_kyiv", "eta_manual"):
        if projected.get(field) not in (None, ""):
            raise ControllerError("SHADOW_PROJECTED_STALE_FIELD:" + field)
    if ((value.get("database") or {}).get("protected_ua0009") or {}).get(
        "auto_number"
    ) != PROTECTED_CODE:
        raise ControllerError("SHADOW_UA0009")
    if len(value.get("candidate_sources") or {}) != 6:
        raise ControllerError("SHADOW_SOURCE_COVERAGE")


def validate_apply(value: dict) -> None:
    require_pass(value, "APPLY")
    if value.get("production_write") is not True or value.get("media_write") is not False:
        raise ControllerError("APPLY_SCOPE")
    if value.get("rollback") is not None:
        raise ControllerError("APPLY_UNEXPECTED_ROLLBACK")
    after = value.get("after") or {}
    if after.get("status") != EXPECTED_STATUS:
        raise ControllerError("APPLY_STATUS")
    for field in ("sea_container", "sea_date_out", "days_to_kyiv", "eta_manual"):
        if after.get(field) not in (None, ""):
            raise ControllerError("APPLY_STALE_FIELD:" + field)
    if not value.get("backup_root"):
        raise ControllerError("APPLY_BACKUP_MISSING")


def validate_postcheck(value: dict) -> None:
    require_pass(value, "POSTCHECK")
    if value.get("production_write") or value.get("crm_write") or value.get("media_write"):
        raise ControllerError("POSTCHECK_WRITE_SCOPE")
    database = value.get("database") or {}
    if database.get("quick_check") != "ok":
        raise ControllerError("POSTCHECK_DB")
    target = database.get("target") or {}
    for field in ("sea_container", "sea_date_out", "days_to_kyiv", "eta_manual"):
        if target.get(field) not in (None, ""):
            raise ControllerError("POSTCHECK_STALE_FIELD:" + field)
    if value.get("markers") != {
        "db.py": 1, "cars_ui.py": 1, "stranica.py": 1,
        "master_card.py": 1, "cars_schema.py": 1,
    }:
        raise ControllerError("POSTCHECK_MARKERS")


def fetch_public(path: str, nonce: str) -> str:
    separator = "&" if "?" in path else "?"
    request = urllib.request.Request(
        "https://www.uaart.com.ua" + path + separator + "task085=" + nonce,
        headers={"User-Agent": "ua-art-task085-public/2", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(5_000_001)
        final = urllib.parse.urlsplit(response.geturl())
        expected_path = urllib.parse.urlsplit(path).path
        canonical = (
            final.scheme == "https"
            and final.hostname in {"www.uaart.com.ua", "uaart.com.ua"}
            and final.path == expected_path
        )
        if response.status != 200 or len(data) > 5_000_000 or not canonical:
            raise ControllerError(
                "PUBLIC_HTTP:%s:%s:%s" % (path, response.status, response.geturl())
            )
    return data.decode("utf-8", "replace")


def public_round(label: str) -> dict:
    """Verify the one public /video route; /site remains a local mirror gate."""
    nonce = "%s-%d" % (label, time.time_ns())
    result = {}
    for surface in ("video",):
        detail = fetch_public("/%s/%s.html" % (surface, TARGET_CODE), nonce)
        visible = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", detail))
        countdown = bool(re.search(
            r"\b\d{1,3}\s*(?:дн|дней|дня|дні|днів).*?(?:Киев|Київ|выдач|прибыт)",
            visible, re.I,
        ))
        detail_checks = {
            "korea": bool(re.search(r"Коре[яеиї]|Korea", visible, re.I)),
            "photo": bool(re.search(r"<img\b[^>]*src=", detail, re.I)),
            "vin": "4289" in detail,
            "container_absent": OLD_CONTAINER not in detail,
            "eta_absent": not countdown and not any(value in detail for value in OLD_ETA_VALUES),
            "tracker_absent": "Отследить контейнер онлайн" not in visible,
        }
        if not all(detail_checks.values()):
            raise ControllerError("PUBLIC_DETAIL:%s:%s" % (
                surface, ",".join(key for key, ok in detail_checks.items() if not ok)
            ))

        catalog = fetch_public("/%s/katalog.html" % surface, nonce)
        block_pattern = re.compile(
            r"<a\b(?=[^>]*href=[\"'][^\"']*(UA-[0-9]{4,})\.html(?:\?[^\"']*)?[\"'])"
            r"[^>]*>.*?</a\s*>", re.I | re.S,
        )
        blocks = list(block_pattern.finditer(catalog))
        ids = [match.group(1).upper() for match in blocks]
        if len(ids) != len(set(ids)):
            raise ControllerError("PUBLIC_CATALOG_DUPLICATE_IDS:" + surface)
        target_blocks = [match.group(0) for match in blocks if match.group(1).upper() == TARGET_CODE]
        if len(target_blocks) != 1:
            raise ControllerError("PUBLIC_CATALOG_COUNT:%s:%d" % (
                surface, len(target_blocks)
            ))
        opening = re.match(r"<a\b[^>]*>", target_blocks[0], re.I | re.S).group(0)
        if not any(token in opening for token in (
            'data-ua-card-stage="korea"', "data-ua-card-stage='korea'",
            'data-stage="korea"', "data-stage='korea'",
            'data-etap="korea"', "data-etap='korea'",
            'data-ua-stage="1"', "data-ua-stage='1'",
        )):
            raise ControllerError("PUBLIC_CATALOG_STAGE:" + surface)
        stage_counts = {"korea": 0, "more": 0, "gruzia": 0, "kiev": 0}
        for match in blocks:
            card_opening = re.match(r"<a\b[^>]*>", match.group(0), re.I | re.S).group(0)
            stage = re.search(
                r"data-(?:ua-card-stage|stage|etap)=[\"'](korea|more|gruzia|kiev)[\"']",
                card_opening, re.I,
            )
            if stage:
                stage_counts[stage.group(1).lower()] += 1
        chip_counts = {}
        for key in ("all", "korea", "more", "gruzia", "kiev"):
            chip = re.findall(
                r"<a\b(?=[^>]*class=[\"'][^\"']*\bchip\b)(?=[^>]*data-f=[\"']"
                + re.escape(key)
                + r"[\"'])[^>]*>.*?<b[^>]*>\s*(\d+)\s*</b>.*?</a\s*>",
                catalog, re.I | re.S,
            )
            if len(chip) != 1:
                raise ControllerError("PUBLIC_CHIP_COUNT:%s:%s:%d" % (
                    surface, key, len(chip)
                ))
            chip_counts[key] = int(chip[0])
        expected_counts = {"all": len(ids), **stage_counts}
        if chip_counts != expected_counts:
            raise ControllerError(
                "PUBLIC_VISIBLE_COUNTS:%s:%s:%s"
                % (surface, json.dumps(chip_counts, sort_keys=True),
                   json.dumps(expected_counts, sort_keys=True))
            )
        result[surface] = {
            "detail": detail_checks,
            "catalog_count": 1,
            "catalog_stage": "korea",
            "visible_counts": chip_counts,
            "unique_cards": len(ids),
        }
    return result


def report_text(result: dict) -> str:
    final = result.get("postcheck_delayed") or result.get("postcheck") or {}
    target = ((final.get("database") or {}).get("target") or {})
    return "\n".join([
        "# UA-0011-STAGE-PAYLOAD-RESET-005 v1.0", "",
        "STATUS: **%s**" % result.get("status", "FAIL"), "",
        "- UA-0011 status: `%s`" % target.get("status", "—"),
        "- Container removed: %s" % ("PASS" if target.get("sea_container") in (None, "") else "FAIL"),
        "- ETA/days removed: %s" % (
            "PASS" if target.get("eta_manual") in (None, "") and target.get("days_to_kyiv") in (None, "") else "FAIL"
        ),
        "- Permanent stage payload guard: %s" % (
            "PASS" if result.get("status") == "PASS" else "NOT VERIFIED"
        ),
        "- Immediate + delayed public checks: %s" % (
            "PASS" if result.get("status") == "PASS" else "NOT VERIFIED"
        ),
        "- Bot restart: %s" % ("PASS" if result.get("bot_restarted") else "NOT CONFIRMED"),
        "- Runtime LLM tokens: 0",
        "- Rollback: %s" % ("not needed" if result.get("status") == "PASS" else json.dumps(result.get("rollback"), ensure_ascii=False)),
        "- Errors: %s" % ("none" if not result.get("errors") else "; ".join(result["errors"])),
        "",
    ])


def main() -> int:
    result: dict[str, Any] = {
        "contract_id": CONTRACT_ID, "status": "FAIL", "started_at_utc": now_utc(),
        "errors": [], "runtime_llm_tokens": 0, "rollback": None,
        "bot_restarted": False, "automatic_remote_retry": True,
    }
    api = None
    apply_attempted = False
    applied = False
    restart_done = False
    try:
        api = API()
        api.ensure_directory()
        for remote, local in FILES.items():
            data = local.read_bytes()
            compile(data.decode("utf-8"), str(local), "exec")
            api.upload(remote, data)
            if api.read(remote) != data:
                raise ControllerError("UPLOAD_READBACK:" + local.name)
        shadow = api.run_remote("shadow")
        result["shadow"] = shadow
        validate_shadow(shadow)
        apply_attempted = True
        apply_value = api.run_remote("apply", timeout=1200)
        result["apply"] = apply_value
        validate_apply(apply_value)
        applied = True
        result["restart"] = api.restart_bot()
        result["bot_restarted"] = True
        restart_done = True
        time.sleep(12)
        immediate = api.run_remote("postcheck")
        result["postcheck"] = immediate
        validate_postcheck(immediate)
        result["public_immediate"] = public_round("immediate")
        time.sleep(35)
        delayed = api.run_remote("postcheck")
        result["postcheck_delayed"] = delayed
        validate_postcheck(delayed)
        result["public_delayed"] = public_round("delayed")
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
        apply_value = result.get("apply") or {}
        remote_already_rolled = apply_value.get("status") == "ROLLED_BACK"
        if api is not None and applied:
            try:
                rolled = api.run_remote("rollback")
                result["rollback"] = rolled
                require_pass(rolled, "ROLLBACK")
                result["rollback_restart"] = api.restart_bot()
                result["bot_restarted"] = True
                restart_done = True
                result["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
                result["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                result["status"] = "BLOCKED"
        elif remote_already_rolled:
            result["rollback"] = apply_value.get("rollback")
            result["status"] = "ROLLED_BACK"
        if api is not None and apply_attempted and not restart_done:
            try:
                result["recovery_restart"] = api.restart_bot()
                result["bot_restarted"] = True
            except Exception as restart_exc:
                result["errors"].append("RECOVERY_RESTART:" + str(restart_exc))
    result["finished_at_utc"] = now_utc()
    atomic_text(EVIDENCE, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, report_text(result))
    print(json.dumps({"status": result["status"], "errors": result["errors"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

