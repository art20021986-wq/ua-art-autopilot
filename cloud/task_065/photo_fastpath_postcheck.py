#!/usr/bin/env python3
"""Production-safe verification for CRM-PHOTO-FASTPATH-001."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import tempfile
import threading
import types
import urllib.parse
import urllib.request


BASE = pathlib.Path("/home/Carix")
CARS_UI = BASE / "cars_ui.py"
TEAM_BOT = BASE / "team_bot.py"
DB_PY = BASE / "db.py"
CRM_DB = BASE / "crm.db"
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_065"
RECEIPT = SAFE / "postcheck_receipt.json"
MARKER = "CRM-PHOTO-FASTPATH-001"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def definition(source: str, name: str):
    tree = ast.parse(source)
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(nodes) != 1:
        raise RuntimeError("DEFINITION_INVALID:" + name)
    return nodes[0], ast.get_source_segment(source, nodes[0]) or ""


def live_db():
    con = sqlite3.connect("file:%s?mode=ro" % CRM_DB, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        journal = con.execute("PRAGMA journal_mode").fetchone()[0]
        cars = con.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
        ua9 = con.execute("SELECT COUNT(*) FROM cars WHERE auto_number='UA-0009'").fetchone()[0]
    finally:
        con.close()
    return {"quick_check": quick, "journal_mode": str(journal).lower(),
            "cars_count": cars, "ua0009_rows": ua9}


def get_me(token: str):
    url = "https://api.telegram.org/bot%s/getMe" % urllib.parse.quote(token, safe=":")
    with urllib.request.urlopen(url, timeout=20) as response:
        value = json.loads(response.read().decode("utf-8"))
    result = value.get("result") or {}
    return {"ok": bool(value.get("ok") and result.get("id")),
            "identity_sha256": sha(str(result.get("id", "")).encode())}


def bot_health():
    tokens = {}
    result = {"bots": {}}
    for name, filename in (("client", "bot_token.txt"), ("crm", "team_token.txt")):
        token = (BASE / filename).read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError("TOKEN_EMPTY:" + name)
        tokens[name] = token
        result["bots"][name] = get_me(token)
    result["tokens_distinct"] = tokens["client"] != tokens["crm"]
    return result


def helper_namespace(source: str, tempdir: pathlib.Path):
    tree = ast.parse(source)
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & {"_V165_SPOOL", "_V165_SPOOL_LOCK", "_V165_PROGRESS"}:
                body.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_v165_") or node.name == "media_spool_worker_job":
                body.append(node)
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    state = {"photos": []}

    def jload(value):
        if isinstance(value, list):
            return value
        if not value:
            return []
        return json.loads(value)

    def card_of(card_id):
        return {"id": int(card_id), "auto_number": "TEST-1",
                "photos": list(state["photos"]), "condition_photos": []}

    def save_media(card, target, file_id, actor_id, tag=""):
        if target == "photos" and not any(item["file_id"] == file_id for item in state["photos"]):
            state["photos"].append({"file_id": file_id, "tag": tag})
        return "ok"

    ns = {
        "S": types.SimpleNamespace(PHOTO_LIMIT=100, CONDITION_PHOTO_LIMIT=100),
        "jload": jload,
        "card_of": card_of,
        "save_media": save_media,
    }
    exec(compile(module, "cars_ui.fastpath.helpers", "exec"), ns)
    ns["_V165_SPOOL"] = str(tempdir / "spool.jsonl")
    ns["_V165_SPOOL_LOCK"] = str(tempdir / "spool.lock")
    return ns, state


def spool_test(source: str):
    with tempfile.TemporaryDirectory(prefix="task065-spool-") as directory:
        ns, state = helper_namespace(source, pathlib.Path(directory))
        accepted = []
        for index in range(100):
            accepted.append(ns["_v165_spool_enqueue"](
                1, "photos", "photo-%03d" % index, 7, ""))
        duplicate = ns["_v165_spool_enqueue"](1, "photos", "photo-017", 7, "")
        queued_before = len(ns["_v165_read_rows"]())
        drained = ns["_v165_spool_drain"](150)
        queued_after = len(ns["_v165_read_rows"]())
        status = ns["_v165_status"](1, "photos")
        ids = [item["file_id"] for item in state["photos"]]
        expected = ["photo-%03d" % index for index in range(100)]
        ok = (all(item["state"] == "accepted" for item in accepted)
              and duplicate["state"] == "duplicate"
              and queued_before == 100 and queued_after == 0
              and ids == expected and status["saved"] == 100
              and drained["processed"] == 100)
        return {"ok": ok, "accepted": len(accepted), "duplicate_state": duplicate["state"],
                "queued_before": queued_before, "queued_after": queued_after,
                "saved_unique": len(ids), "order_exact": ids == expected,
                "drain": drained, "status": status}


def sqlite_stress():
    with tempfile.TemporaryDirectory(prefix="task065-sqlite-") as directory:
        copy = pathlib.Path(directory) / "crm-copy.db"
        shutil.copy2(CRM_DB, copy)
        setup = sqlite3.connect(copy, timeout=30)
        setup.execute("PRAGMA journal_mode=DELETE")
        setup.close()
        errors = []
        lock = threading.Lock()

        def worker(number):
            try:
                con = sqlite3.connect(copy, timeout=30)
                con.execute("PRAGMA busy_timeout=30000")
                for _ in range(25):
                    con.execute("SELECT COUNT(*) FROM cars").fetchone()
                    con.execute("UPDATE cars SET updated_at=updated_at WHERE 0")
                    con.commit()
                con.close()
            except Exception as exc:
                with lock:
                    errors.append(type(exc).__name__ + ":" + str(exc))

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(40)
        alive = sum(thread.is_alive() for thread in threads)
        check = sqlite3.connect(copy).execute("PRAGMA quick_check").fetchone()[0]
        return {"ok": not errors and alive == 0 and check == "ok",
                "operations": 100, "errors": errors, "alive": alive,
                "quick_check": check}


def static_contract(cars: str, team: str, db_source: str):
    _, check = definition(cars, "_save_media_proverka")
    _, save = definition(cars, "save_media")
    _, catch = definition(cars, "catch_message")
    media = catch.split("voice_object =", 1)[0]
    fast_index = check.find('target in ("photos", "condition_photos")')
    get_file_index = check.find("_v140_sprosit(file_id)")
    checks = {
        "markers": (MARKER in cars and MARKER in team
                    and "CRM-DB-LOCK-EMERGENCY-001" in db_source),
        "photo_skips_getfile": 0 <= fast_index < get_file_index,
        "durable_before_db": "_v165_spool_enqueue" in media,
        "photo_stops_before_ai": "raise ApplicationHandlerStop" in media,
        "no_repeated_media_menu": "Фото и видео" not in media,
        "one_compact_card_button": '"Открыть карточку"' in cars,
        "raw_media_connection_removed": '_s152.connect("/home/Carix/crm.db"' not in save,
        "queued_db_connection": "with db.connect() as con" in save,
        "background_worker": "cars_ui.media_spool_worker_job" in team,
        "transaction_queue": ("factory=Soedinenie" in db_source
                              and "_ua_fayl_zahvatit" in db_source
                              and "_commit_s_povtorom" in db_source),
    }
    return {"ok": all(checks.values()), "checks": checks}


def main() -> int:
    evidence = {"task_id": "task_065", "contract_id": MARKER, "status": "FAIL",
                "llm_tokens": 0, "crm_db_write": False, "site_write": False,
                "errors": []}
    try:
        sources = {}
        for path in (CARS_UI, TEAM_BOT, DB_PY):
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
            sources[path.name] = source
        evidence["files_sha256"] = {
            name: sha(source.encode()) for name, source in sources.items()}
        evidence["static_contract"] = static_contract(
            sources["cars_ui.py"], sources["team_bot.py"], sources["db.py"])
        evidence["spool_test"] = spool_test(sources["cars_ui.py"])
        evidence["sqlite_stress"] = sqlite_stress()
        evidence["readonly_live_db"] = live_db()
        evidence["bot_health"] = bot_health()
        if not evidence["static_contract"]["ok"]:
            raise RuntimeError("STATIC_CONTRACT_FAILED")
        if not evidence["spool_test"]["ok"]:
            raise RuntimeError("SPOOL_100_TEST_FAILED")
        if not evidence["sqlite_stress"]["ok"]:
            raise RuntimeError("SQLITE_STRESS_FAILED")
        if evidence["readonly_live_db"]["quick_check"] != "ok":
            raise RuntimeError("LIVE_DB_CHECK_FAILED")
        health = evidence["bot_health"]
        if not health["tokens_distinct"] or not all(
                item["ok"] for item in health["bots"].values()):
            raise RuntimeError("BOT_HEALTH_FAILED")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    atomic_json(RECEIPT, evidence)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
