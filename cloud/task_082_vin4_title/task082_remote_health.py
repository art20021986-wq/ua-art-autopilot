#!/usr/bin/env python3
"""Read-only live acceptance for CRM-VIN4-TITLE-001 v1.0."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path("/home/Carix")
SOURCE = ROOT / "cars_ui.py"
DB = ROOT / "crm.db"
RECEIPT = ROOT / "uploads" / "task082_health_receipt.json"
START = "# CRM-VIN4-TITLE-001-V1.0:START"
END = "# CRM-VIN4-TITLE-001-V1.0:END"
TOKEN_FILES = {"client": ROOT / "bot_token.txt", "crm": ROOT / "team_token.txt"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_json(value: dict) -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix="." + RECEIPT.name + ".", suffix=".tmp", dir=str(RECEIPT.parent))
    path = pathlib.Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(path, RECEIPT)
    finally:
        path.unlink(missing_ok=True)


def _bots() -> dict:
    values = {}
    token_hashes = []
    for label, path in TOKEN_FILES.items():
        item = {"ok": False}
        try:
            token = path.read_text(encoding="utf-8").strip()
            if ":" not in token or len(token) < 30:
                raise RuntimeError("TOKEN_FORMAT")
            token_hashes.append(_sha(token.encode()))
            request = urllib.request.Request(
                "https://api.telegram.org/bot%s/getMe" % token,
                headers={"User-Agent": "ua-art-task082-vin4/1"},
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.loads(response.read(200_000).decode())
            bot = payload.get("result") if isinstance(payload, dict) else None
            if not payload.get("ok") or not isinstance(bot, dict) or not bot.get("is_bot"):
                raise RuntimeError("GETME_REJECTED")
            item.update({
                "ok": True,
                "identity_sha256": _sha((str(bot.get("id")) + ":" + str(bot.get("username", ""))).encode()),
            })
        except urllib.error.HTTPError as exc:
            item["error"] = "HTTP_%d" % exc.code
        except Exception as exc:
            item["error"] = type(exc).__name__ + ":" + str(exc)
        values[label] = item
    return {"bots": values, "tokens_distinct": len(token_hashes) == 2 and len(set(token_hashes)) == 2}


def _cards(namespace: dict) -> tuple[list[dict], str]:
    uri = "file:%s?mode=ro" % DB
    connection = sqlite3.connect(uri, uri=True, timeout=20)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        rows = [dict(row) for row in connection.execute(
            "SELECT id,auto_number,brand,model,year,vin FROM cars ORDER BY id")]
    finally:
        connection.close()
    evidence = []
    for row in rows:
        vin4 = namespace["_ua082_vin4"](row)
        title = namespace["_ua082_vin4_title_html"](row)
        button = namespace["_ua082_vin4_button_label"](row)
        evidence.append({
            "id": row.get("auto_number"),
            "vin4": vin4,
            "vin_valid": vin4 is not None,
            "title_html": title,
            "button_label": button,
            "title_vin_count": title.count("VIN"),
            "button_vin_count": button.count("VIN"),
            "button_length": len(button),
        })
    return evidence, quick


def run() -> int:
    result = {
        "contract": "CRM-VIN4-TITLE-001-V1.0", "status": "FAIL",
        "read_only": True, "production_write": False, "errors": [],
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        raw = SOURCE.read_bytes()
        source = raw.decode("utf-8")
        compile(source, str(SOURCE), "exec")
        if source.count(START) != 1 or source.count(END) != 1:
            raise RuntimeError("MARKER_COUNT")
        # One definition plus two live call sites (card header + car list).
        if source.count("_ua082_vin4_title_html(card)") != 3:
            raise RuntimeError("TITLE_CALL_COUNT")
        # One definition plus one live call site (selection button).
        if source.count("_ua082_vin4_button_label(card)") != 2:
            raise RuntimeError("BUTTON_CALL_COUNT")
        block = source[source.index(START):source.index(END) + len(END)]
        namespace = {}
        exec(compile(block, "<task082-live-helper>", "exec"), namespace)
        cards, quick = _cards(namespace)
        expected_ids = ["UA-%04d" % number for number in range(1, 14)]
        if [card["id"] for card in cards] != expected_ids:
            raise RuntimeError("CARD_ID_SET")
        for card in cards:
            if not card["vin_valid"] or len(card["vin4"] or "") != 4:
                raise RuntimeError("VIN4_INVALID:" + str(card["id"]))
            if card["title_vin_count"] != 1 or card["button_vin_count"] != 1:
                raise RuntimeError("VIN_SUFFIX_COUNT:" + str(card["id"]))
            if card["button_length"] > 64 or "<" in card["button_label"] or ">" in card["button_label"]:
                raise RuntimeError("BUTTON_FORMAT:" + str(card["id"]))
            if not card["title_html"].endswith("VIN <b>%s</b>" % card["vin4"]):
                raise RuntimeError("TITLE_FORMAT:" + str(card["id"]))
            if not card["button_label"].endswith("VIN %s" % card["vin4"]):
                raise RuntimeError("BUTTON_SUFFIX:" + str(card["id"]))
        bots = _bots()
        if not bots["tokens_distinct"] or any(not item.get("ok") for item in bots["bots"].values()):
            raise RuntimeError("BOT_HEALTH")
        process = subprocess.run(
            ["pgrep", "-af", "start_safe.py"], text=True, capture_output=True, timeout=10,
        )
        process_lines = [line for line in process.stdout.splitlines() if "pgrep" not in line]
        if process.returncode != 0 or not process_lines:
            raise RuntimeError("LAUNCHER_PROCESS")
        if quick != "ok":
            raise RuntimeError("DB_QUICK_CHECK")
        result.update({
            "status": "PASS", "source_sha256": _sha(raw), "db_quick_check": quick,
            "card_count": len(cards), "cards": cards, "bot_health": bots,
            "launcher_process_count": len(process_lines),
        })
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    _atomic_json(result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(run())
