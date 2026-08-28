#!/usr/bin/env python3
"""Read-only post-restart verification for UA-CARDS-FERRY-VIN-001 V1.1."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request


HERE = pathlib.Path(__file__).resolve().parent
REPAIR_PATH = HERE / "task068_ferry_vin_repair.py"
if not REPAIR_PATH.exists():
    REPAIR_PATH = HERE / "repair_remote.py"
_SPEC = importlib.util.spec_from_file_location("task068_ferry_vin_repair", REPAIR_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("TASK068_REPAIR_IMPORT_SPEC_FAILED")
repair = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(repair)


RECEIPT_PATH = pathlib.Path(repair.SAFE_ROOT) / "install_receipt.json"
POSTCHECK_PATH = pathlib.Path(repair.SAFE_ROOT) / "postcheck_receipt.json"
BOT_TOKEN_FILES = {
    "client": pathlib.Path("/home/Carix/bot_token.txt"),
    "crm": pathlib.Path("/home/Carix/team_token.txt"),
}
RUNTIME_FILES = {
    "launcher": pathlib.Path("/home/Carix/start_safe.py"),
    "orchestrator": pathlib.Path("/home/Carix/run_all.py"),
    "client": pathlib.Path("/home/Carix/lead_bot.py"),
    "crm": pathlib.Path("/home/Carix/team_bot.py"),
    "cards_ui": pathlib.Path("/home/Carix/cars_ui.py"),
    "master_card": pathlib.Path("/home/Carix/master_card.py"),
    "db": pathlib.Path("/home/Carix/db.py"),
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _telegram_probe() -> dict:
    results = {}
    token_hashes = []
    for label, path in BOT_TOKEN_FILES.items():
        item = {"ok": False, "token_file": path.name}
        try:
            token = path.read_text(encoding="utf-8").strip()
            if not token or ":" not in token or len(token) < 30:
                raise RuntimeError("TOKEN_FORMAT_INVALID")
            token_hashes.append(_sha(token.encode("utf-8")))
            request = urllib.request.Request(
                "https://api.telegram.org/bot%s/getMe" % token,
                headers={"User-Agent": "ua-art-task068-ferry-vin/1"},
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.loads(response.read(200_000).decode("utf-8"))
            bot = payload.get("result") if isinstance(payload, dict) else None
            if not payload.get("ok") or not isinstance(bot, dict) or not bot.get("is_bot"):
                raise RuntimeError("TELEGRAM_GETME_REJECTED")
            item["ok"] = True
            item["identity_sha256"] = _sha(
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


def _runtime_contract() -> dict:
    files = {}
    sources = {}
    for label, path in RUNTIME_FILES.items():
        data = path.read_bytes()
        source = data.decode("utf-8")
        compile(source, str(path), "exec")
        files[label] = {"sha256": _sha(data), "compiled": True}
        sources[label] = source
    checks = {
        "client_builder": "build_application" in sources["client"],
        "crm_builder": "build_application" in sources["crm"],
        "both_apps_started": all(value in sources["orchestrator"] for value in (
            "lead_bot.build_application", "team_bot.build_application",
        )),
        "cards_ui_registered": "cars_ui.register" in sources["crm"],
        "stable_launcher": "run_all.py" in sources["launcher"],
        "crm_actions_unique": sources["cards_ui"].count('callback_data="car_stage:%d"') == 1
        and sources["cards_ui"].count('callback_data="car_cond:%d"') == 1,
        "master_final_filter": repair.FERRY_VIN_SOURCE_MARKER in sources["master_card"],
        "stranica_final_filter": repair.FERRY_VIN_SOURCE_MARKER in pathlib.Path(repair.STRANICA_PATH).read_text(encoding="utf-8"),
        "yadro_final_filter": repair.FERRY_VIN_SOURCE_MARKER in pathlib.Path(repair.YADRO_PATH).read_text(encoding="utf-8"),
    }
    process = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    matches = [
        line.strip() for line in process.stdout.splitlines()
        if ("/home/Carix/start_safe.py" in line or "/home/Carix/run_all.py" in line)
        and "task068" not in line
    ]
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "files": files,
        "matching_processes": len(matches),
    }


def _db_snapshot_retry():
    """Wait out short CRM write locks without weakening the read-only gate."""
    last = None
    for attempt in range(1, 9):
        try:
            return repair._db_snapshot()
        except Exception as exc:
            if "database is locked" not in str(exc).lower():
                raise
            last = exc
            if attempt < 8:
                time.sleep(min(attempt * 2, 10))
    raise last


def main() -> int:
    result = {
        "contract_id": repair.CONTRACT,
        "status": "FAIL",
        "read_only": True,
        "crm_write": False,
        "media_write": False,
        "llm_tokens": 0,
        "errors": [],
    }
    try:
        install = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        if install.get("status") != "PASS":
            raise RuntimeError("INSTALL_RECEIPT_NOT_PASS")

        repair._validate_task068_source(pathlib.Path(repair.STRANICA_PATH).read_text(encoding="utf-8"), repair.STRANICA_PATH)
        repair._validate_task068_source(pathlib.Path(repair.YADRO_PATH).read_text(encoding="utf-8"), repair.YADRO_PATH)
        repair._validate_task068_source(pathlib.Path(repair.MASTER_CARD_PATH).read_text(encoding="utf-8"), repair.MASTER_CARD_PATH)
        repair._validate_untouched()
        rows, db_state = _db_snapshot_retry()
        identifiers = [str(row["auto_number"]) for row in rows]
        media_state = repair._media_inventory(identifiers)
        cards = repair._validate_cards(rows)
        fixtures = repair._fixture_contract()
        master_final_fixtures = repair._master_final_fixture_contract()
        if db_state["published_rows_sha256"] != install["db_after"]["published_rows_sha256"]:
            raise RuntimeError("CRM_ROWS_CHANGED_AFTER_RESTART")
        if media_state != install["media_after"]:
            raise RuntimeError("MEDIA_CHANGED_AFTER_RESTART")
        if identifiers != install["card_ids"]:
            raise RuntimeError("CARD_SET_CHANGED_AFTER_RESTART")

        stage_distribution = {str(number): 0 for number in range(1, 5)}
        for card in cards:
            stage_distribution[str(card["stage"])] += 1
        if any(value == 0 for value in stage_distribution.values()):
            raise RuntimeError("FOUR_STAGE_VISUAL_COVERAGE_MISSING")
        ua0009 = next((card for card in cards if card["id"] == "UA-0009"), None)
        if not ua0009 or ua0009["stage"] != 2:
            raise RuntimeError("UA0009_STAGE_CONTRACT_FAILED")

        bot_health = _telegram_probe()
        result["bot_health"] = bot_health
        if not bot_health["tokens_distinct"] or any(
            not bot_health["bots"].get(name, {}).get("ok") for name in ("client", "crm")
        ):
            raise RuntimeError("BOT_HEALTH_FAILED")
        runtime = _runtime_contract()
        result["runtime"] = runtime
        if not runtime["ok"]:
            raise RuntimeError("BOT_RUNTIME_CONTRACT_FAILED")

        result.update({
            "db": db_state,
            "media": media_state,
            "cards": cards,
            "card_count": len(cards),
            "stage_distribution": stage_distribution,
            "fixtures": fixtures,
            "master_final_fixtures": master_final_fixtures,
            "ua0009": ua0009,
            "bot_health": bot_health,
            "runtime": runtime,
            "status": "PASS",
        })
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    repair._atomic_json(str(POSTCHECK_PATH), result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
