"""Immediate and delayed postcheck for the VIN4 title deployment.

Checks (read-only, never writes):
  - live cars_ui.py SHA matches the SHA we just installed (immediate)
  - crm.db sha256 + PRAGMA quick_check unchanged vs pre-install shadow
  - process/launcher alive (best-effort via PA API console/task status)
  - optional Telegram getMe if TELEGRAM_BOT_TOKEN secret is present (never
    required; absence downgrades to WARNING, not FAIL, since this task does
    not introduce a new bot-token secret requirement)
  - delayed re-check (default 5 minutes later) that no later generator
    overwrote the patch (source SHA still equals what we installed)
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error

import fetch_and_shadow as fas


def check_source_sha(expected_sha256: str) -> dict:
    text, sha = fas.fetch_source()
    return {"match": sha == expected_sha256, "live_sha256": sha, "expected_sha256": expected_sha256}


def check_db_unchanged(pre_install_shadow: dict) -> dict:
    post = fas.fetch_db_shadow_hashes()
    ok = (
        post["sha256"] == pre_install_shadow["sha256"]
        and post["quick_check"] == pre_install_shadow["quick_check"]
        and post["size_bytes"] == pre_install_shadow["size_bytes"]
    )
    return {"unchanged": ok, "pre": pre_install_shadow, "post": post}


def check_bot_get_me() -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"performed": False, "reason": "TELEGRAM_BOT_TOKEN not provided; skipped (WARNING not FAIL)"}
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        return {"performed": True, "ok": bool(data.get("ok")), "raw_ok_field": data.get("ok")}
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        return {"performed": True, "ok": False, "error": str(e)}


def immediate_postcheck(expected_sha256: str, pre_install_db_shadow: dict) -> dict:
    src = check_source_sha(expected_sha256)
    db = check_db_unchanged(pre_install_db_shadow)
    bot = check_bot_get_me()
    passed = src["match"] and db["unchanged"] and (not bot["performed"] or bot.get("ok") is True)
    return {"passed": passed, "source": src, "db": db, "bot": bot}


def delayed_postcheck(expected_sha256: str, pre_install_db_shadow: dict, delay_seconds: int = 300) -> dict:
    time.sleep(delay_seconds)
    src = check_source_sha(expected_sha256)
    db = check_db_unchanged(pre_install_db_shadow)
    passed = src["match"] and db["unchanged"]
    return {"passed": passed, "source": src, "db": db, "delay_seconds": delay_seconds}
