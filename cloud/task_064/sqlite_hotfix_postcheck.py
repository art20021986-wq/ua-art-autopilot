#!/usr/bin/env python3
"""Post-restart concurrency and integrity check for task_064."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request


BASE = pathlib.Path("/home/Carix")
DB_PY = BASE / "db.py"
CRM_DB = BASE / "crm.db"
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_064"
RECEIPT = SAFE / "postcheck_receipt.json"
MARKER = "CRM-DB-LOCK-EMERGENCY-001"
WORKERS = 4
ITERATIONS = 10
BOT_TOKEN_FILES = {
    "client": BASE / "bot_token.txt",
    "crm": BASE / "team_token.txt",
}
BOT_RUNTIME_FILES = {
    "launcher": BASE / "start_safe.py",
    "orchestrator": BASE / "run_all.py",
    "client": BASE / "lead_bot.py",
    "crm": BASE / "team_bot.py",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
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


def snapshot():
    connection = sqlite3.connect("file:/home/Carix/crm.db?mode=ro", uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        count = connection.execute("SELECT count(*) FROM cars").fetchone()[0]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(cars)")}
        result = {"quick_check": quick, "cars_count": count}
        if "auto_number" in columns:
            rows = connection.execute(
                "SELECT * FROM cars WHERE auto_number IN ('UA-0009','UA0009')"
            ).fetchall()
            result["ua0009_rows"] = len(rows)
            result["ua0009_sha256"] = sha(
                json.dumps([dict(row) for row in rows], ensure_ascii=False,
                           sort_keys=True, default=str).encode("utf-8")
            )
        return result
    finally:
        connection.close()


def telegram_bots_probe():
    results = {}
    token_hashes = []
    for label, path in BOT_TOKEN_FILES.items():
        item = {"ok": False, "token_file": path.name}
        try:
            token = path.read_text(encoding="utf-8").strip()
            if not token or ":" not in token or len(token) < 30:
                raise RuntimeError("TOKEN_FORMAT_INVALID")
            token_hashes.append(sha(token.encode("utf-8")))
            request = urllib.request.Request(
                "https://api.telegram.org/bot%s/getMe" % token,
                headers={"User-Agent": "ua-art-task064-bot-health/1"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read(200_000).decode("utf-8"))
            bot = payload.get("result") if isinstance(payload, dict) else None
            if not payload.get("ok") or not isinstance(bot, dict) or not bot.get("is_bot"):
                raise RuntimeError("TELEGRAM_GETME_REJECTED")
            item["ok"] = True
            item["identity_sha256"] = sha(
                (str(bot.get("id")) + ":" + str(bot.get("username", ""))).encode("utf-8")
            )
        except urllib.error.HTTPError as exc:
            item["error"] = "TELEGRAM_HTTP_%d" % exc.code
        except Exception as exc:
            item["error"] = type(exc).__name__ + ":" + str(exc)
        results[label] = item
    return {
        "bots": results,
        "tokens_distinct": len(token_hashes) == len(BOT_TOKEN_FILES)
        and len(set(token_hashes)) == len(BOT_TOKEN_FILES),
    }


def process_probe():
    result = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    matches = [
        line for line in result.stdout.splitlines()
        if "/home/Carix/start_safe.py" in line and "task064" not in line
    ]
    return {"running": bool(matches), "matching_processes": len(matches)}


def runtime_contract_probe():
    records = {}
    sources = {}
    for label, path in BOT_RUNTIME_FILES.items():
        data = path.read_bytes()
        source = data.decode("utf-8")
        compile(source, str(path), "exec")
        sources[label] = source
        records[label] = {"sha256": sha(data), "compiled": True}
    checks = {
        "client_builder": "build_application" in sources["client"],
        "client_catalog_button": "каталог" in "\n".join(sources.values()).casefold(),
        "crm_builder": "build_application" in sources["crm"],
        "both_apps_started": all(value in sources["orchestrator"] for value in (
            "lead_bot.build_application", "team_bot.build_application",
        )),
        "stable_launcher": "run_all.py" in sources["launcher"],
    }
    return {"ok": all(checks.values()), "checks": checks, "files": records}


def worker_code():
    return (
        "import sys\n"
        "sys.path.insert(0, '/home/Carix')\n"
        "import db\n"
        "for _ in range(%d):\n"
        "    with db.connect() as c:\n"
        "        c.execute('UPDATE cars SET updated_at=updated_at WHERE 0')\n"
        "print('TASK064_WORKER_PASS')\n" % ITERATIONS
    )


def concurrency_probe():
    code = worker_code()
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code],
            cwd=str(BASE),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(WORKERS)
    ]
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=90)
        results.append({
            "returncode": process.returncode,
            "pass_marker": "TASK064_WORKER_PASS" in stdout,
            "stderr_tail": stderr[-500:],
        })
    return results


def main() -> int:
    receipt = {
        "task_id": "task_064",
        "contract_id": MARKER,
        "status": "FAIL",
        "llm_tokens": 0,
        "write_probe": "UPDATE_WHERE_FALSE_ONLY",
        "errors": [],
    }
    try:
        source = DB_PY.read_text(encoding="utf-8")
        if MARKER not in source:
            raise RuntimeError("HOTFIX_MARKER_MISSING")
        compile(source, str(DB_PY), "exec")
        before = snapshot()
        if before["quick_check"] != "ok":
            raise RuntimeError("QUICK_CHECK_BEFORE_FAILED")
        bot_health = telegram_bots_probe()
        receipt["bot_health"] = bot_health
        if not bot_health["tokens_distinct"] or any(
            not item.get("ok") for item in bot_health["bots"].values()
        ):
            raise RuntimeError("BOT_TOKEN_HEALTH_FAILED")
        service = process_probe()
        receipt["service_process"] = service
        runtime = runtime_contract_probe()
        receipt["runtime_contract"] = runtime
        if not runtime["ok"]:
            raise RuntimeError("BOT_RUNTIME_CONTRACT_FAILED")
        workers = concurrency_probe()
        receipt["workers"] = workers
        if len(workers) != WORKERS or any(
            item["returncode"] != 0 or not item["pass_marker"] for item in workers
        ):
            raise RuntimeError("CONCURRENCY_PROBE_FAILED")
        after = snapshot()
        receipt["readonly_before"] = before
        receipt["readonly_after"] = after
        receipt["operations"] = WORKERS * ITERATIONS
        receipt["journal_present_after"] = (BASE / "crm.db-journal").exists()
        if after["quick_check"] != "ok":
            raise RuntimeError("QUICK_CHECK_AFTER_FAILED")
        if before["cars_count"] != after["cars_count"]:
            raise RuntimeError("CARD_COUNT_CHANGED")
        if before.get("ua0009_sha256") != after.get("ua0009_sha256"):
            raise RuntimeError("UA0009_CHANGED")
        receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
    atomic_json(RECEIPT, receipt)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
