#!/usr/bin/env python3
"""Read-only post-restart acceptance for TASK 069 Gate B."""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import time
import urllib.parse
import urllib.request

import task069_gate_b_installer as gate


RECEIPT = gate.SAFE / "gate_b_postcheck_receipt.json"


class CheckFailed(RuntimeError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def telegram_health() -> dict:
    bots = {}
    hashes = {}
    for name, token_file in (("client", "bot_token.txt"), ("crm", "team_token.txt")):
        token = (gate.ROOT / token_file).read_text(encoding="utf-8").strip()
        check(bool(token), "EMPTY_TOKEN:" + name)
        hashes[name] = hashlib.sha256(token.encode("utf-8")).hexdigest()
        started = time.monotonic()
        try:
            url = "https://api.telegram.org/bot%s/getMe" % urllib.parse.quote(token, safe=":")
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read(100_001).decode("utf-8"))
            bots[name] = {
                "ok": bool(data.get("ok") and (data.get("result") or {}).get("id")),
                "latency_seconds": round(time.monotonic() - started, 3),
            }
        except Exception as exc:
            bots[name] = {
                "ok": False,
                "error": type(exc).__name__,
                "latency_seconds": round(time.monotonic() - started, 3),
            }
    return {"bots": bots, "tokens_distinct": hashes.get("client") != hashes.get("crm")}


def process_health() -> dict:
    result = subprocess.run(
        ["pgrep", "-af", "(/home/Carix/start_safe.py|/home/Carix/run_all.py)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
        check=False,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {"ok": result.returncode == 0 and bool(lines), "matches": len(lines)}


def main() -> int:
    value = {
        "contract_id": gate.CONTRACT,
        "mode": "POST_RESTART_READ_ONLY",
        "status": "FAIL",
        "generated_at_utc": gate.utc_now(),
        "production_write": False,
        "crm_db_write": False,
        "site_write": False,
        "runtime_llm_tokens": 0,
        "errors": [],
    }
    try:
        install = json.loads(gate.read_bytes(gate.INSTALL_RECEIPT, 2_000_000).decode("utf-8"))
        check(install.get("contract_id") == gate.CONTRACT, "INSTALL_CONTRACT")
        check(install.get("status") == "PASS", "INSTALL_NOT_PASS")
        candidate_data, candidate = gate.validate_candidate(gate.read_bytes(gate.SOURCE, gate.MAX_SOURCE))
        check(candidate["already_applied"] is True, "CANDIDATE_NOT_INSTALLED")
        check(
            gate.sha(candidate_data) == install.get("candidate", {}).get("candidate_sha256"),
            "CANDIDATE_SHA",
        )

        current = gate.db_snapshot()
        before = install["database_before"]
        after = install["database_after"]
        check(current["quick_check"] == "ok", "DB_QUICK_CHECK")
        check(current["card_ids"] == before["card_ids"], "CARD_SET")
        check(set(gate.MINIMUM_CARD_IDS).issubset(current["card_ids"]), "MINIMUM_CARD_SET")
        check(current["target"]["sea_container"] == gate.TARGET_CONTAINER, "UA0011_CONTAINER")
        check(current["protected_rows_sha256"] == before["protected_rows_sha256"], "PROTECTED_ROWS")
        check(after["protected_rows_sha256"] == before["protected_rows_sha256"], "INSTALL_PROTECTED_ROWS")
        before_owners = list(before.get("container_owners") or [])
        expected_owners = sorted(
            before_owners + [{"id": current["target"]["id"], "auto_number": gate.TARGET_CARD}],
            key=lambda row: row["id"],
        )
        # Idempotent deployments may already include UA-0011 in the baseline.
        deduplicated = []
        for owner in expected_owners:
            if owner not in deduplicated:
                deduplicated.append(owner)
        check(current["container_owners"] == deduplicated, "CONTAINER_OWNER_SET")
        check(after["container_owners"] == deduplicated, "INSTALL_CONTAINER_OWNER_SET")

        # Explicitly anchor UA-0009 and every currently discovered card.
        check("UA-0009" in current["card_ids"], "UA0009_MISSING")
        check(len(current["card_ids"]) >= 11, "CARD_COUNT")
        health = telegram_health()
        check(health["tokens_distinct"], "BOT_TOKENS_NOT_DISTINCT")
        check(all(health["bots"][name]["ok"] for name in ("client", "crm")), "BOT_GETME")
        process = process_health()
        check(process["ok"], "PRODUCTION_PROCESS_NOT_FOUND")

        value.update({
            "candidate": candidate,
            "database": current,
            "bots": health,
            "process": process,
            "ua_0009_protected": True,
            "all_cards_protected": True,
            "status": "PASS",
        })
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    gate.atomic_json(RECEIPT, value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
