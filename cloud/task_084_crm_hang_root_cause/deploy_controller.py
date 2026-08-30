#!/usr/bin/env python3
"""Build, install, restart and prove CRM-HANG-ROOT-CAUSE-084."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import importlib.util
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
REPO = HERE.parents[1]
AUDIT = HERE / "evidence/live_audit.json"
EVIDENCE = HERE / "evidence/deploy.json"
REPORT = HERE / "TASK_084_REPORT.md"
PATCHER = HERE.parent / "task_078_voice_watchdog/handler_patcher.py"
VOICE = HERE.parent / "task_078_voice_watchdog/voice_watchdog.py"
INSTALLER = HERE / "remote_installer.py"

BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
ROOT = "/home/Carix"
REMOTE = ROOT + "/autopilot_inbox/cloud/task_083_catalog_dedup"
CONTRACT = "CRM-HANG-ROOT-CAUSE-084-V1.0"
LAUNCHER = "python3.10 /home/Carix/start_safe.py"
TARGET_PATHS = {
    "cars_ui.py": ROOT + "/cars_ui.py",
    "team_bot.py": ROOT + "/team_bot.py",
    "start_safe.py": ROOT + "/start_safe.py",
    "crm_voice_watchdog.py": ROOT + "/crm_voice_watchdog.py",
}
RECEIPTS = {
    mode: REMOTE + "/task084_%s_receipt.json" % mode
    for mode in ("install", "postcheck", "rollback")
}
COMMANDS = {
    mode: "cd %s && python3.10 task084_remote_installer.py %s" % (REMOTE, mode)
    for mode in RECEIPTS
}
MAX_BYTES = 10_000_000

RUN_AI_SHA = "56e11511e4a47e8314f50e9f6bfa25bb57690657d47c9de006726e0b7f004822"
SHOW_MENU_SHA = "02ccb935c473fa811bda9bfb567b6b74519a6d2b0062cc9fc256964ff31c7906"
VVODNYE_SHA = "81e87f7e3b6fa3d20acd80a47053da1befe1f8191c10a871fdabf0c768611e4d"
START_MAIN_SHA = "9b69b8d16ee7d43f5df7e4bddbda1f134144e54fe7753a2fdd921be7d8e0f2ee"


class ControllerError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_text(value: str) -> str:
    return sha_bytes(value.encode("utf-8"))


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
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


def function_span(source: str, name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(nodes) != 1:
        raise ControllerError("FUNCTION_COUNT:%s:%d" % (name, len(nodes)))
    node = nodes[0]
    start, end = offsets[node.lineno - 1], offsets[node.end_lineno]
    return start, end, source[start:end]


def replace_function(
    source: str, name: str, expected_sha: str, transform, *, require_known: bool = True
) -> str:
    start, end, function = function_span(source, name)
    if require_known and sha_text(function) != expected_sha:
        raise ControllerError("FUNCTION_SHA_MISMATCH:" + name)
    replacement = transform(function)
    if replacement == function:
        raise ControllerError("FUNCTION_NOT_CHANGED:" + name)
    candidate = source[:start] + replacement + source[end:]
    compile(candidate, name + ".candidate.py", "exec")
    return candidate


DRAFT_OLD = """            remaining = max(0.1, hard_deadline - time.monotonic())
            text = await asyncio.wait_for(
                asyncio.to_thread(ai.transcribe, audio), timeout=remaining
            )
"""

DRAFT_NEW = """            # UA-TASK084-KILLABLE-DRAFT-VOICE
            import crm_voice_watchdog as _v178_voice
            _v184_voice = msg.voice or msg.audio or msg.video_note
            _v184_filename = (
                "voice.ogg" if msg.voice else
                "audio.mp3" if msg.audio else "video_note.mp4"
            )
            _v184_result = await _v178_voice.transcribe_with_restart(
                audio,
                _v184_filename,
                getattr(_v184_voice, "duration", 0),
            )
            text = _v184_result.text if _v184_result.ok else ""
            if not _v184_result.ok:
                logging.warning(
                    "AI voice worker failed inbox=%s attempts=%s restarts=%s error=%s",
                    inbox_id, _v184_result.attempts,
                    _v184_result.restarted_workers, _v184_result.error,
                )
"""


def patch_draft(function: str) -> str:
    if function.count(DRAFT_OLD) != 1:
        raise ControllerError("DRAFT_VOICE_ANCHOR")
    value = function.replace(DRAFT_OLD, DRAFT_NEW, 1)
    value = value.replace(
        'thinking = await msg.reply_text("🎤 ИИ распознаёт, до 15 секунд...")',
        'thinking = await msg.reply_text("🎤 ИИ распознаёт голосовое...")',
        1,
    )
    return value


def patch_menu(function: str) -> str:
    marker = "    # UA-TASK084-MENU-DEBOUNCE\n"
    if marker in function:
        raise ControllerError("MENU_ALREADY_PATCHED")
    newline = function.find("\n")
    if newline < 0:
        raise ControllerError("MENU_SIGNATURE")
    block = """    # UA-TASK084-MENU-DEBOUNCE
    import time as _v184_time
    _v184_now = _v184_time.monotonic()
    _v184_last = float(context.chat_data.get("_ua_menu_last_sent", 0.0) or 0.0)
    if _v184_now - _v184_last < 4.0:
        return
    context.chat_data["_ua_menu_last_sent"] = _v184_now
"""
    return function[: newline + 1] + block + function[newline + 1 :]


VVODNYE_NEW = '''async def vvodnye_job(context: ContextTypes.DEFAULT_TYPE):
    """После запуска бот сам присылает владельцу текущие вводные."""
    # UA-TASK084-STARTUP-NOTICE-DEBOUNCE
    import fcntl as _v184_fcntl
    import os as _v184_os
    import time as _v184_time

    _v184_state = "/home/Carix/.team_bot_start_notice"
    _v184_lock = "/home/Carix/.team_bot_start_notice.lock"
    try:
        with open(_v184_lock, "a+", encoding="utf-8") as _v184_guard:
            _v184_fcntl.flock(_v184_guard.fileno(), _v184_fcntl.LOCK_EX)
            try:
                with open(_v184_state, "r", encoding="utf-8") as _v184_handle:
                    _v184_last = int((_v184_handle.read() or "0").strip())
            except (FileNotFoundError, ValueError):
                _v184_last = 0
            _v184_now = int(_v184_time.time())
            if _v184_now - _v184_last < 600:
                logging.info("Повторное стартовое уведомление подавлено.")
                return
            _v184_temp = "%s.tmp.%d" % (_v184_state, _v184_os.getpid())
            with open(_v184_temp, "w", encoding="utf-8") as _v184_handle:
                _v184_handle.write(str(_v184_now))
                _v184_handle.flush()
                _v184_os.fsync(_v184_handle.fileno())
            _v184_os.replace(_v184_temp, _v184_state)
    except Exception as e:
        logging.warning("Стартовое уведомление подавлено: защитный шлюз недоступен: %s", e)
        return

    try:
        ids = db.staff_ids_by_role(db.ROLE_OWNER)
    except Exception as e:
        logging.warning("владелец не найден: %s", e)
        return
    for uid in ids or []:
        try:
            await context.bot.send_message(
                uid, "🟢 <b>Бот запущен и готов к работе.</b>\\n\\n" + vvodnye_text(),
                parse_mode="HTML")
        except Exception as e:
            logging.warning("вводные не отправились %s: %s", uid, e)
'''


def patch_team(source: str, *, require_known: bool = True) -> str:
    value = replace_function(
        source, "run_ai_draft", RUN_AI_SHA, patch_draft, require_known=require_known
    )
    value = replace_function(
        value, "show_menu", SHOW_MENU_SHA, patch_menu, require_known=require_known
    )
    value = replace_function(
        value, "vvodnye_job", VVODNYE_SHA, lambda _old: VVODNYE_NEW,
        require_known=require_known,
    )
    if "asyncio.to_thread(ai.transcribe, audio)" in value:
        raise ControllerError("TEAM_NONKILLABLE_STT_REMAINS")
    for marker in (
        "# UA-TASK084-KILLABLE-DRAFT-VOICE",
        "# UA-TASK084-MENU-DEBOUNCE",
        "# UA-TASK084-STARTUP-NOTICE-DEBOUNCE",
    ):
        if marker not in value:
            raise ControllerError("TEAM_MARKER_MISSING:" + marker)
    compile(value, "team_bot.py", "exec")
    return value


def patch_start_main(function: str) -> str:
    newline = function.find("\n")
    if newline < 0:
        raise ControllerError("START_SIGNATURE")
    block = '''    # UA-TASK084-START-SINGLETON
    import fcntl as _v184_fcntl
    _v184_singleton = open(
        os.path.join(BASE, ".start_safe.singleton.lock"), "a+", encoding="utf-8")
    try:
        _v184_fcntl.flock(
            _v184_singleton.fileno(), _v184_fcntl.LOCK_EX | _v184_fcntl.LOCK_NB)
    except BlockingIOError:
        log.warning("start_safe.py уже запущен; второй экземпляр остановлен")
        return
'''
    return function[: newline + 1] + block + function[newline + 1 :]


def patch_start(source: str, *, require_known: bool = True) -> str:
    value = replace_function(
        source, "main", START_MAIN_SHA, patch_start_main, require_known=require_known
    )
    if "# UA-TASK084-START-SINGLETON" not in value:
        raise ControllerError("START_MARKER_MISSING")
    compile(value, "start_safe.py", "exec")
    return value


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ControllerError("MODULE_LOAD:" + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class API:
    def __init__(self) -> None:
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerError("PYTHONANYWHERE_TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task084-controller/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=70) as response:
                status, body = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d:%s" % (status, url.rsplit("/", 2)[-2]))
        return status, body

    def file_url(self, path: str) -> str:
        allowed = path.startswith(REMOTE + "/") or path in set(TARGET_PATHS.values())
        if not allowed:
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED:" + path)
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, *, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete_file(self, path: str) -> None:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("DELETE_SCOPE")
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, data: bytes) -> None:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("UPLOAD_SCOPE")
        boundary = "----uaart-task084-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend((
            'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
            'Content-Type: %s\r\n\r\n' % (filename, mime)
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
    def objects(body: bytes) -> list:
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    @staticmethod
    def trigger_id(body: bytes):
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, command: str, description: str):
        """Use PythonAnywhere's scheduled lane; the always-on quota is occupied."""
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
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
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

    def wait_for_file(self, path: str, seconds: int) -> bytes:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            raw = self.read(path, missing=True)
            if raw:
                return raw
            time.sleep(5)
        raise ControllerError("REMOTE_FILE_TIMEOUT:" + pathlib.PurePosixPath(path).name)

    def ensure_remote_dir(self) -> None:
        receipt = REMOTE + "/task084_directory.ready"
        try:
            self.delete_file(receipt)
        except ControllerError as exc:
            if "HTTP_404" not in str(exc):
                raise
        marker = b"TASK084_READY"
        self.upload(receipt, marker)
        if self.read(receipt) != marker:
            raise ControllerError("REMOTE_STAGING_READBACK")

    def run_remote(self, mode: str, seconds: int = 420) -> dict:
        receipt = RECEIPTS[mode]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[mode], "task084 " + mode)
        try:
            raw = self.wait_for_file(receipt, seconds)
            return json.loads(raw.decode("utf-8"))
        finally:
            self.delete_trigger(trigger)

    def rescue_bot(self) -> dict:
        """Start the exact launcher once when PythonAnywhere control plane is stuck."""
        receipt = REMOTE + "/task084_rescue_started"
        self.delete_file(receipt)
        log_path = ROOT + "/task084_start_safe.log"
        command = (
            "cd " + ROOT
            + " && (nohup python3.10 start_safe.py >> " + log_path
            + " 2>&1 </dev/null &) && printf TASK084_RESCUE > " + receipt
        )
        trigger = self.create_trigger(command, "task084 one-shot launcher rescue")
        try:
            raw = self.wait_for_file(receipt, 240)
            if raw != b"TASK084_RESCUE":
                raise ControllerError("RESCUE_RECEIPT_INVALID")
        finally:
            self.delete_trigger(trigger)
        return {"scheduled": True, "command": LAUNCHER, "receipt": receipt}

    def active_launcher(self) -> dict:
        _, body = self.request("GET", BASE + "always_on/")
        matches = [
            item for item in self.objects(body)
            if isinstance(item, dict) and item.get("enabled") is not False
            and str(item.get("command", "")).strip() == LAUNCHER
        ]
        if len(matches) != 1:
            raise ControllerError("ACTIVE_LAUNCHER_NOT_UNIQUE:%d" % len(matches))
        return matches[0]

    def restart_bot(self) -> dict:
        launcher = self.active_launcher()
        identifier = int(launcher["id"])
        self.request(
            "POST", BASE + "always_on/%d/restart/" % identifier,
            b"", allowed=(200, 201, 202, 204),
        )
        return {"id": identifier, "command": LAUNCHER, "restart_accepted": True}

    def wait_launcher_running(self, seconds: int = 150) -> dict:
        deadline = time.monotonic() + seconds
        started = time.monotonic()
        last = None
        while time.monotonic() < deadline:
            last = self.active_launcher()
            state = str(last.get("state", "")).lower()
            if state == "running" or (state == "starting" and time.monotonic() - started >= 30):
                return {
                    "id": last.get("id"), "state": last.get("state"),
                    "enabled": last.get("enabled"), "command": last.get("command"),
                    "control_plane_lag": state == "starting",
                }
            time.sleep(5)
        raise ControllerError("LAUNCHER_NOT_RUNNING:" + str((last or {}).get("state")))


def audit_function(audit: dict, filename: str, name: str) -> str:
    source = audit["sources"][filename]
    matches = [item for item in source.get("functions", []) if item.get("name") == name]
    if not matches:
        matches = [item for item in source.get("marker_functions", []) if item.get("name") == name]
    if len(matches) != 1 or not matches[0].get("source"):
        raise ControllerError("AUDIT_FUNCTION_MISSING:%s:%s" % (filename, name))
    return matches[0]["source"]


def validate_audit(audit: dict) -> None:
    root = audit.get("root_cause") or {}
    if audit.get("status") != "PASS_ROOT_CAUSE_CONFIRMED":
        raise ControllerError("AUDIT_NOT_PASS")
    if audit.get("production_touched") is not False or audit.get("http_methods") != ["GET"]:
        raise ControllerError("AUDIT_NOT_READ_ONLY")
    required = {
        "fixed_deadline_4_65": True,
        "non_killable_to_thread": True,
        "wait_for_only_cancels_await": True,
        "killable_child_present": False,
        "start_safe_singleton_present": False,
    }
    for key, expected in required.items():
        if root.get(key) is not expected:
            raise ControllerError("AUDIT_ROOT_CAUSE:" + key)
    if root.get("launcher_count") != 1:
        raise ControllerError("AUDIT_LAUNCHER_COUNT")


def build_candidates(api: API) -> tuple[dict[str, bytes], dict, dict]:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    validate_audit(audit)
    live: dict[str, bytes | None] = {}
    for name, path in TARGET_PATHS.items():
        live[name] = api.read(path, missing=(name == "crm_voice_watchdog.py"))
    for name in ("cars_ui.py", "team_bot.py", "start_safe.py"):
        raw = live[name]
        if raw is None:
            raise ControllerError("LIVE_SOURCE_MISSING:" + name)
        expected = audit["sources"][name]["sha256"]
        if sha_bytes(raw) != expected:
            raise ControllerError("FRESH_AUDIT_DRIFT:" + name)

    patcher = load_module(PATCHER, "task084_handler_patcher")
    cars_source = live["cars_ui.py"].decode("utf-8")
    cars_candidate = patcher.build_candidate(cars_source, require_full_sha=False)
    if "hard_deadline = started + 4.65" in cars_candidate:
        raise ControllerError("CARS_FIXED_DEADLINE_REMAINS")
    if "asyncio.to_thread(ai.transcribe" in cars_candidate:
        raise ControllerError("CARS_NONKILLABLE_STT_REMAINS")

    team_source = live["team_bot.py"].decode("utf-8")
    team_candidate = patch_team(team_source)
    start_source = live["start_safe.py"].decode("utf-8")
    start_candidate = patch_start(start_source)
    voice_candidate = VOICE.read_bytes()
    compile(voice_candidate.decode("utf-8"), "crm_voice_watchdog.py", "exec")
    if live["crm_voice_watchdog.py"] not in (None, voice_candidate):
        raise ControllerError("UNEXPECTED_EXISTING_VOICE_WATCHDOG")

    candidates = {
        "cars_ui.py": cars_candidate.encode("utf-8"),
        "team_bot.py": team_candidate.encode("utf-8"),
        "start_safe.py": start_candidate.encode("utf-8"),
        "crm_voice_watchdog.py": voice_candidate,
    }
    for name, value in candidates.items():
        compile(value.decode("utf-8"), name, "exec")
    manifest = {
        "contract_id": CONTRACT,
        "built_at_utc": utc_now(),
        "audit_started_at_utc": audit.get("started_at_utc"),
        "targets": {
            name: {
                "path": TARGET_PATHS[name],
                "before_sha256": sha_bytes(live[name]) if live[name] is not None else None,
                "after_sha256": sha_bytes(value),
            }
            for name, value in candidates.items()
        },
    }
    meta = {
        "audit_status": audit["status"],
        "audit_started_at_utc": audit.get("started_at_utc"),
        "root_cause": audit["root_cause"],
        "candidate_sha256": {name: sha_bytes(value) for name, value in candidates.items()},
    }
    return candidates, manifest, meta


def validate_install(value: dict, manifest: dict) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("production_write") is not True:
        raise ControllerError("INSTALL_WRITE_RECEIPT")
    if value.get("crm_db_write") is not False or value.get("media_write") is not False:
        raise ControllerError("INSTALL_SCOPE")
    if set(value.get("changed_files") or []) != set(TARGET_PATHS):
        raise ControllerError("INSTALL_TARGET_SET")
    expected = {name: item["after_sha256"] for name, item in manifest["targets"].items()}
    if value.get("after_sha256") != expected:
        raise ControllerError("INSTALL_AFTER_SHA")
    if not value.get("backup_dir"):
        raise ControllerError("INSTALL_BACKUP_MISSING")
    if not all((value.get("checks") or {}).values()):
        raise ControllerError("INSTALL_CHECKS")


def validate_postcheck(value: dict) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerError("POSTCHECK_SCOPE")
    if not all((value.get("checks") or {}).values()):
        raise ControllerError("POSTCHECK_MARKERS")
    if not all((value.get("bots") or {}).get(name) for name in ("client", "crm")):
        raise ControllerError("POSTCHECK_TELEGRAM")
    if value.get("start_singleton_held") is not True:
        raise ControllerError("POSTCHECK_SINGLETON")
    if value.get("startup_notice_gate_active") is not True:
        raise ControllerError("POSTCHECK_NOTICE_GATE")


def run_self_test() -> int:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    validate_audit(audit)
    patcher = load_module(PATCHER, "task084_handler_patcher_test")
    cars = audit_function(audit, "cars_ui.py", "catch_message")
    patched_cars = patcher.build_candidate(cars, require_full_sha=False)
    assert "hard_deadline = started + 4.65" not in patched_cars
    assert "asyncio.to_thread(ai.transcribe" not in patched_cars
    team = "\n\n".join([
        audit_function(audit, "team_bot.py", "run_ai_draft"),
        audit_function(audit, "team_bot.py", "show_menu"),
        audit_function(audit, "team_bot.py", "vvodnye_job"),
    ]) + "\n"
    patched_team = patch_team(team)
    assert "# UA-TASK084-KILLABLE-DRAFT-VOICE" in patched_team
    assert "# UA-TASK084-MENU-DEBOUNCE" in patched_team
    assert "# UA-TASK084-STARTUP-NOTICE-DEBOUNCE" in patched_team
    start = audit_function(audit, "start_safe.py", "main") + "\n"
    patched_start = patch_start(start)
    assert "LOCK_EX | _v184_fcntl.LOCK_NB" in patched_start
    voice = VOICE.read_text(encoding="utf-8")
    assert "start_new_session=True" in voice
    assert "signal.SIGTERM" in voice and "signal.SIGKILL" in voice
    assert "MAX_CONCURRENT_WORKERS = 2" in voice
    compile(patched_cars, "cars_ui.py", "exec")
    compile(patched_team, "team_bot.py", "exec")
    compile(patched_start, "start_safe.py", "exec")
    print("TASK084_SELF_TEST_PASS")
    return 0


def write_report(evidence: dict) -> None:
    install = evidence.get("install") or {}
    lines = [
        "# CRM-HANG-ROOT-CAUSE-084 v1.0", "",
        "STATUS: **%s**" % evidence.get("status", "FAIL"), "",
        "- First bad source: task067 fixed 4.65-second deadline with a non-killable thread",
        "- Killable process-group STT for both CRM voice paths: %s" % (
            "PASS" if evidence.get("status") == "PASS" else "NOT VERIFIED"),
        "- Menu replay debounce: %s" % (
            "PASS" if evidence.get("status") == "PASS" else "NOT VERIFIED"),
        "- Startup singleton and notice debounce: %s" % (
            "PASS" if evidence.get("status") == "PASS" else "NOT VERIFIED"),
        "- CRM DB/media writes: NO",
        "- One controlled restart: %s" % ("YES" if evidence.get("bot_restarted") else "NO"),
        "- Backup: `%s`" % install.get("backup_dir", ""),
        "- Immediate and delayed live checks: %s" % (
            "PASS" if evidence.get("status") == "PASS" else "FAIL"),
        "- Errors: %s" % (
            "; ".join(evidence.get("errors") or []) if evidence.get("errors") else "none"),
        "",
    ]
    atomic_text(REPORT, "\n".join(lines))


def run_deploy() -> int:
    evidence = {
        "contract_id": CONTRACT,
        "status": "FAIL",
        "started_at_utc": utc_now(),
        "errors": [],
        "bot_restarted": False,
        "rollback": None,
        "crm_db_write": False,
        "media_write": False,
    }
    api = None
    install = None
    manifest = None
    try:
        api = API()
        current_audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        current_root = current_audit.get("root_cause") or {}
        already_installed = (
            current_audit.get("status")
            in ("PASS_STATE_CHANGED", "PASS_REMEDIATION_CONFIRMED")
            and current_root.get("fixed_deadline_4_65") is False
            and current_root.get("non_killable_to_thread") is False
            and current_root.get("killable_child_present") is True
            and current_root.get("start_safe_singleton_present") is True
        )
        if already_installed:
            evidence["existing_patch_verified"] = True
            evidence["build"] = {
                "audit_status": current_audit.get("status"),
                "audit_started_at_utc": current_audit.get("started_at_utc"),
                "root_cause": current_root,
            }
            evidence["launcher_immediate"] = api.wait_launcher_running()
            immediate = api.run_remote("postcheck")
            evidence["postcheck_immediate"] = immediate
            immediate_errors = " ".join(
                str(item) for item in (immediate.get("errors") or [])
            )
            if immediate.get("status") != "PASS" and any(
                marker in immediate_errors
                for marker in ("START_SINGLETON_NOT_HELD", "TELEGRAM_HEALTH")
            ):
                # The code fix is already installed, but a failed neighboring
                # publication can leave PythonAnywhere's control plane saying
                # "Running" while no start_safe process owns the lock.  Start
                # exactly one guarded launcher and re-check; the singleton in
                # start_safe makes this bounded and idempotent.
                evidence["launcher_rescue"] = api.rescue_bot()
                evidence["bot_restarted"] = True
                time.sleep(20)
                immediate = api.run_remote("postcheck")
                evidence["postcheck_after_rescue"] = immediate
            validate_postcheck(immediate)
            time.sleep(30)
            evidence["launcher_delayed"] = api.wait_launcher_running()
            delayed = api.run_remote("postcheck")
            evidence["postcheck_delayed"] = delayed
            validate_postcheck(delayed)
            evidence["status"] = "PASS"
            raise ControllerError("ALREADY_INSTALLED_VERIFIED")

        candidates, manifest, build = build_candidates(api)
        evidence["build"] = build
        api.ensure_remote_dir()
        uploads = {
            "task084_remote_installer.py": INSTALLER.read_bytes(),
            "task084_manifest.json": (
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
        }
        uploads.update({"task084_" + name + ".candidate": data for name, data in candidates.items()})
        for name, data in uploads.items():
            if name.endswith((".py", ".candidate")):
                compile(data.decode("utf-8"), name, "exec")
            remote_path = REMOTE + "/" + name
            api.upload(remote_path, data)
            if api.read(remote_path) != data:
                raise ControllerError("UPLOAD_READBACK:" + name)

        install = api.run_remote("install")
        evidence["install"] = install
        validate_install(install, manifest)
        evidence["service"] = api.restart_bot()
        evidence["bot_restarted"] = True
        time.sleep(8)
        evidence["launcher_immediate"] = api.wait_launcher_running()
        time.sleep(7)
        immediate = api.run_remote("postcheck")
        evidence["postcheck_immediate"] = immediate
        if immediate.get("status") != "PASS" and any(
            "START_SINGLETON_NOT_HELD" in str(item) for item in (immediate.get("errors") or [])
        ):
            evidence["launcher_rescue"] = api.rescue_bot()
            time.sleep(20)
            immediate = api.run_remote("postcheck")
            evidence["postcheck_after_rescue"] = immediate
        validate_postcheck(immediate)
        time.sleep(30)
        evidence["launcher_delayed"] = api.wait_launcher_running()
        delayed = api.run_remote("postcheck")
        evidence["postcheck_delayed"] = delayed
        validate_postcheck(delayed)
        evidence["status"] = "PASS"
    except Exception as exc:
        if isinstance(exc, ControllerError) and str(exc) == "ALREADY_INSTALLED_VERIFIED":
            pass
        else:
            evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if evidence.get("status") != "PASS" and api is not None and install and install.get("status") == "PASS":
            try:
                rollback = api.run_remote("rollback")
                evidence["rollback"] = rollback
                if rollback.get("status") != "PASS":
                    raise ControllerError("ROLLBACK_FAILED")
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
            finally:
                try:
                    evidence["rollback_service"] = api.restart_bot()
                    evidence["rollback_launcher"] = api.wait_launcher_running()
                except Exception as restart_exc:
                    evidence["errors"].append(
                        "ROLLBACK_RESTART_" + type(restart_exc).__name__ + ":" + str(restart_exc)
                    )
    evidence["finished_at_utc"] = utc_now()
    atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    write_report(evidence)
    return 0 if evidence["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    return run_self_test() if args.self_test else run_deploy()


if __name__ == "__main__":
    raise SystemExit(main())
