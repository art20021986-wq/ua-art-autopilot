#!/usr/bin/env python3
"""Verify single-drain and session/total photo counters."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import sqlite3
import tempfile
import threading
import time
import types
import urllib.parse
import urllib.request


BASE = pathlib.Path("/home/Carix")
CARS_UI = BASE / "cars_ui.py"
CRM_DB = BASE / "crm.db"
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_065"
RECEIPT = SAFE / "counter_v2_postcheck_receipt.json"
MARKER = "CRM-PHOTO-COUNTER-002"
VOICE_MARKER = "CRM-VOICE-FIELDS-003"


def sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
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


def jload(value):
    if isinstance(value, list):
        return value
    return json.loads(value) if value else []


def helper_namespace(source, directory, baseline=5):
    tree = ast.parse(source)
    body = []
    wanted_assignments = {"_V165_SPOOL", "_V165_SPOOL_LOCK", "_V165_DRAIN_LOCK",
                          "_V165_PROGRESS"}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & wanted_assignments:
                body.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_v165_") or node.name.startswith("_v166_"):
                body.append(node)
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    state = {"photos": [{"file_id": "base-%02d" % index, "tag": ""}
                         for index in range(baseline)]}

    def card_of(card_id):
        return {"id": int(card_id), "auto_number": "TEST",
                "photos": list(state["photos"]), "condition_photos": []}

    def save_media(card, target, file_id, actor_id, tag=""):
        # Deliberately expose stale read/write if more than one drain runs.
        snapshot = list(state["photos"])
        time.sleep(0.002)
        if not any(item["file_id"] == file_id for item in snapshot):
            snapshot.append({"file_id": file_id, "tag": tag})
            state["photos"] = snapshot
        return "ok"

    ns = {"S": types.SimpleNamespace(PHOTO_LIMIT=100, CONDITION_PHOTO_LIMIT=100),
          "jload": jload, "card_of": card_of, "save_media": save_media}
    exec(compile(module, "cars_ui.counter-v2.helpers", "exec"), ns)
    ns["_V165_SPOOL"] = str(directory / "spool.jsonl")
    ns["_V165_SPOOL_LOCK"] = str(directory / "spool.lock")
    ns["_V165_DRAIN_LOCK"] = str(directory / "drain.lock")
    return ns, state


def concurrent_case(source, baseline, session_count, workers):
    with tempfile.TemporaryDirectory(prefix="task065-counter-v2-") as directory:
        ns, state = helper_namespace(source, pathlib.Path(directory), baseline)
        session = ["session-%03d" % index for index in range(session_count)]
        for file_id in session:
            result = ns["_v165_spool_enqueue"](18, "photos", file_id, 7, "")
            if result["state"] != "accepted":
                raise RuntimeError("ENQUEUE_FAILED")
        barrier = threading.Barrier(workers)
        results = []
        result_lock = threading.Lock()

        def worker():
            barrier.wait()
            value = ns["_v165_spool_drain"](100)
            with result_lock:
                results.append(value)

        threads = [threading.Thread(target=worker) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(20)
        status = ns["_v165_status"](18, "photos", session)
        ids = [item["file_id"] for item in state["photos"]]
        expected_total = baseline + session_count
        ok = (not any(thread.is_alive() for thread in threads)
              and len(ids) == expected_total and len(set(ids)) == expected_total
              and ids[:baseline] == ["base-%02d" % index for index in range(baseline)]
              and ids[baseline:] == session
              and status["session_saved"] == session_count
              and status["saved"] == expected_total
              and status["queued"] == 0
              and sum(item["processed"] for item in results) == session_count)
        return {"ok": ok, "workers": results, "saved_total": len(ids),
                "saved_unique": len(set(ids)), "session_saved": status["session_saved"],
                "queued": status["queued"], "order_exact": ids[baseline:] == session}


def concurrency_test(source):
    current_batch = concurrent_case(source, baseline=5, session_count=17, workers=4)
    full_capacity = concurrent_case(source, baseline=0, session_count=100, workers=6)
    return {"ok": current_batch["ok"] and full_capacity["ok"],
            "batch_17": current_batch, "capacity_100": full_capacity}


def live_card():
    con = sqlite3.connect("file:%s?mode=ro" % CRM_DB, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        row = con.execute("SELECT id,photos FROM cars WHERE auto_number='UA-0011'").fetchone()
        if not row:
            raise RuntimeError("UA0011_MISSING")
        values = []
        for item in jload(row["photos"]):
            value = item.get("file_id") if isinstance(item, dict) else item
            if value:
                values.append(str(value))
        spool = pathlib.Path("/home/Carix/.crm_media_spool.jsonl")
        queued = 0
        if spool.exists():
            for line in spool.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                    queued += int(item.get("card_id") == row["id"])
                except Exception:
                    pass
        return {"quick_check": quick, "photos_total": len(values),
                "photos_unique": len(set(values)), "duplicate_count": len(values)-len(set(values)),
                "queued": queued}
    finally:
        con.close()


def get_me(token):
    url = "https://api.telegram.org/bot%s/getMe" % urllib.parse.quote(token, safe=":")
    with urllib.request.urlopen(url, timeout=20) as response:
        value = json.loads(response.read().decode("utf-8"))
    return bool(value.get("ok") and (value.get("result") or {}).get("id"))


def bot_health():
    client = (BASE / "bot_token.txt").read_text(encoding="utf-8").strip()
    crm = (BASE / "team_token.txt").read_text(encoding="utf-8").strip()
    return {"client_ok": get_me(client), "crm_ok": get_me(crm),
            "tokens_distinct": client != crm}


def static_contract(source):
    tree = ast.parse(source)
    funcs = {node.name: ast.get_source_segment(source, node) or "" for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    checks = {
        "marker": MARKER in source,
        "voice_marker": VOICE_MARKER in source,
        "drain_lock": "LOCK_NB" in funcs.get("_v165_spool_drain", ""),
        "one_owned_drain": "_v166_drain_owned" in source,
        "progress_does_not_drain": "_v165_spool_drain" not in funcs.get("_v165_progress_job", ""),
        "session_counter": "session_saved" in funcs.get("_v165_status", ""),
        "clear_labels": "Добавлено сейчас" in funcs.get("_v165_progress_job", ""),
        "session_in_wait": 'wait.setdefault("_fast_session_ids"' in funcs.get("catch_message", ""),
        "voice_updates_open_card": "override = bool(voice_object)" in funcs.get("catch_message", ""),
    }
    return {"ok": all(checks.values()), "checks": checks}


def voice_regression(source):
    tree = ast.parse(source)
    wanted = {"_v167_voice_explicit_fields", "voice_change_plan"}
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in wanted]
    found = {node.name for node in nodes}
    if found != wanted:
        return {"ok": False, "error": "VOICE_FUNCTIONS_MISSING",
                "found": sorted(found)}
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, "cars_ui.voice-regression", "exec"), namespace)
    phrase = "тип топлива LPI, объем двигателя 2000, цвет белый"
    allowed = {"fuel", "engine_cc", "color"}
    parsed = namespace["_v167_voice_explicit_fields"](phrase, allowed)
    existing = {"fuel": "gasoline", "engine_cc": 1600, "color": "чёрный"}
    changes, skipped = namespace["voice_change_plan"](
        existing, parsed, allowed, override=True)
    changed = {field: value for field, _old, value in changes}
    expected = {"fuel": "LPI", "engine_cc": 2000, "color": "белый"}
    _, catch = next((node, ast.get_source_segment(source, node) or "")
                    for node in tree.body
                    if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "catch_message")
    open_card_only = ("active_card = card_of(active_id)" in catch
                      and "Новая карточка автоматически не создаётся" in catch)
    automatic_override = ("override = bool(voice_object)" in catch
                          and "explicit_data = _v167_voice_explicit_fields" in catch)
    ok = (parsed == expected and changed == expected and not skipped
          and open_card_only and automatic_override)
    return {"ok": ok, "phrase": phrase, "parsed": parsed,
            "changes": changed, "skipped": skipped,
            "open_card_only": open_card_only,
            "automatic_override": automatic_override,
            "new_card_created": False, "llm_tokens": 0}


def main():
    evidence = {"task_id": "task_065", "contract_id": MARKER,
                "contract_ids": [MARKER, VOICE_MARKER], "status": "FAIL",
                "llm_tokens": 0, "errors": []}
    try:
        source = CARS_UI.read_text(encoding="utf-8")
        compile(source, str(CARS_UI), "exec")
        evidence["cars_ui_sha256"] = sha(source.encode())
        evidence["static_contract"] = static_contract(source)
        evidence["concurrency_test"] = concurrency_test(source)
        evidence["voice_regression"] = voice_regression(source)
        evidence["live_ua0011"] = live_card()
        evidence["bot_health"] = bot_health()
        if not evidence["static_contract"]["ok"]:
            raise RuntimeError("STATIC_CONTRACT_FAILED")
        if not evidence["concurrency_test"]["ok"]:
            raise RuntimeError("CONCURRENT_DRAIN_TEST_FAILED")
        if not evidence["voice_regression"]["ok"]:
            raise RuntimeError("VOICE_REGRESSION_FAILED")
        live = evidence["live_ua0011"]
        if live["quick_check"] != "ok" or live["duplicate_count"] != 0:
            raise RuntimeError("LIVE_UA0011_INVALID")
        if not all(evidence["bot_health"].values()):
            raise RuntimeError("BOT_HEALTH_FAILED")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    atomic_json(RECEIPT, evidence)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
