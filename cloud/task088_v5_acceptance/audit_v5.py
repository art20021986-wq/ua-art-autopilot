#!/usr/bin/env python3
"""Offline FINAL v5.0 diagnostics; never a production or deployment receipt.

Invokes the actual candidate helper and runtime using their existing isolated
SQLite/HTML fixture scaffolding. Existing source files are read only. All runtime
writes go to TemporaryDirectory fixtures; Telegram and public reads are fakes.
The external private CRM source is only read and is never included in the report.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SYNC = HERE.parent / "task088_price_sync"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def fixture(cls):
    obj = cls()
    try:
        obj.setUp()
        yield obj
    finally:
        try:
            obj.tearDown()
        finally:
            obj.doCleanups()


def outcome(check_id, clauses, expected, observed, passed):
    return {"id": check_id, "v5_clauses": clauses,
            "status": "PASS" if passed else "FAIL",
            "expected": expected, "observed": observed}


def conscious_updates(hooks):
    with fixture(hooks.CarsHookTests) as f:
        amounts = [18000, 18500, 18300, 18900]
        accepted = []
        for index, amount in enumerate(amounts):
            accepted.append(f.edit(value=str(amount),
                                   identity=(700, 50 + index, 900 + index))[0])
        events = f.events()
        observed = {"accepted": accepted,
                    "revisions": [e["revision"] for e in events],
                    "states_before_worker": [e["state"] for e in events],
                    "georgia_usd": [e["georgia_usd"] for e in events],
                    "unique_operation_count": len({e["event_key"] for e in events}),
                    "stored_ua": f.card()["price_uah"],
                    "stored_ge": f.card()["price_georgia"]}
        expected = {"accepted": [True] * 4,
                    "states_before_worker": ["PENDING"] * 4,
                    "unique_operation_count": 4,
                    "stored_ua": 10000, "stored_ge": 18900,
                    "rule": "Every conscious input remains eligible for its own verified pipeline."}
        passed = (accepted == [True] * 4 and len(events) == 4
                  and observed["unique_operation_count"] == 4
                  and observed["states_before_worker"] == ["PENDING"] * 4
                  and observed["stored_ua"] == 10000
                  and observed["stored_ge"] == 18900)
        return outcome("conscious_inputs_not_superseded", [11, 16], expected, observed, passed)


def anomaly_confirmation(hooks, amount):
    with fixture(hooks.CarsHookTests) as f:
        before = dict(f.card())
        ok, reply = f.edit(value=str(amount), identity=(700, 60, 910))
        after = dict(f.card())
        confirmation_signal = bool(re.search(r"подтверд|подтверж|confirm", reply, re.I))
        observed = {"input_usd": amount, "write_accepted": ok,
                    "reply": reply, "stored_ge_before": before["price_georgia"],
                    "stored_ge_after": after["price_georgia"],
                    "whole_car_unchanged": before == after,
                    "outbox_event_count": len(f.events()),
                    "confirmation_signal": confirmation_signal}
        expected = {"write_accepted": False, "whole_car_unchanged": True,
                    "outbox_event_count": 0, "confirmation_signal": True,
                    "rule": "Display the actual suspicious amount and request confirmation before saving."}
        passed = (not ok and before == after and not f.events()
                  and confirmation_signal and str(amount) in reply.replace(" ", ""))
        return outcome(f"anomaly_{amount}_requires_confirmation", [12], expected, observed, passed)


def restart_recovery(runtime_tests):
    with fixture(runtime_tests.RuntimeTests) as f:
        with sqlite3.connect(f.db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            runtime_tests.outbox.claim(conn, event_key=f.key, nonce="c" * 64,
                                       now_ms=f.clock_ms)
            conn.commit()
        # Exact real checkpoint: a durable claim exists, _execute has not begun.
        # Recreate the worker as startup does; do not invoke manual recover().
        restarted = runtime_tests.runtime.Worker(f.binding)
        ticks = []
        for _ in range(2):
            f.clock_ms += 5000
            ticks.append(restarted.tick())
        event = f.event()
        observed = {"checkpoint": "CLAIM_COMMITTED_BEFORE_EXECUTE",
                    "worker_recreated": True, "ticks": ticks,
                    "state": event["state"], "reason": event["reason"],
                    "publication_receipt_present": bool(event["receipt_sha256"]),
                    "operator_reentry": False, "manual_recovery_called": False}
        expected = {"state": "PUBLISHED", "publication_receipt_present": True,
                    "operator_reentry": False,
                    "rule": "Automatically finish a confirmed operation after ordinary restart."}
        return outcome("restart_resumes_committed_operation", [17, 27], expected, observed,
                       event["state"] == "PUBLISHED" and bool(event["receipt_sha256"]))


def success_receipt(runtime_tests):
    with fixture(runtime_tests.RuntimeTests) as f:
        # The candidate event schema cannot currently persist this initiating
        # operator identity. The absence of ANY success receipt already fails.
        operator_chat_id = 700
        messages = []

        class FakeBot:
            async def send_message(self, **kwargs):
                messages.append(dict(kwargs))
                return SimpleNamespace(message_id=len(messages))

        result = f.worker.tick()
        asyncio.run(f.worker.deliver_notices(FakeBot()))
        success_messages = [m for m in messages
                            if "✅" in m.get("text", "") and "Завершено" in m["text"]]
        observed = {"pipeline_result": result, "event_state": f.event()["state"],
                    "initiating_operator_chat_id": operator_chat_id,
                    "configured_owner_chat_id": f.binding.owner_chat_id,
                    "queued_notice_kinds": [row[0] for row in f.notices()],
                    "fake_telegram_calls": messages,
                    "success_receipt_count": len(success_messages)}
        expected = {"event_state": "PUBLISHED", "success_receipt_count": 1,
                    "recipient_chat_id": operator_chat_id,
                    "receipt_contains": ["✅ Завершено", "Грузии", "UA-0001", "5 000"],
                    "rule": "Only after verification, send completion to the editing operator."}
        matching = [m for m in success_messages
                    if m.get("chat_id") == operator_chat_id
                    and "UA-0001" in m["text"] and "Грузии" in m["text"]
                    and "5000" in m["text"].replace(" ", "").replace("\u00a0", "")]
        passed = f.event()["state"] == "PUBLISHED" and len(success_messages) == 1 and len(matching) == 1
        return outcome("verified_success_receipt_to_operator", [15, 24, 27], expected, observed, passed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cars-ui-source", required=True, type=Path,
                        help="Private exact baseline cars_ui.py, read only; never copied into repo.")
    args = parser.parse_args()
    source = args.cars_ui_source.resolve()
    report = {"contract": "UA-ART-GE-UA-MARKET-PRICE-001 FINAL v5.0",
              "report_kind": "OFFLINE_CANDIDATE_DIAGNOSTICS",
              "observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "production_tested": False, "production_touched": False,
              "telegram_delivery": "FAKE_BOT_ONLY", "public_reads": "LOCAL_FIXTURE_ONLY",
              "source_hashes": {}, "checks": []}
    try:
        paths = [SYNC / name for name in ("outbox.py", "patch_cars_ui.py",
                 "uaart_price_sync_runtime.py", "uaart_price_sync_binding.py",
                 "test_cars_ui_hook.py", "test_runtime.py")]
        paths += [HERE.parent / "task088_stage3_renderer" / "uaart_market_prices.py",
                  HERE.parent / "task088_autopilot_owner_policy" / "owner_policy.py",
                  HERE.parent / "task088_autopilot_owner_policy" / "price_publication.py"]
        for path in paths:
            report["source_hashes"][str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
        report["source_hashes"]["private_cars_ui_source"] = hashlib.sha256(source.read_bytes()).hexdigest()
        sys.path.insert(0, str(SYNC))
        with patch.dict(os.environ, {"TASK088_CARS_UI_SOURCE": str(source)}), \
             patch.object(socket, "create_connection", side_effect=RuntimeError("OFFLINE_NETWORK_FORBIDDEN")), \
             patch.object(socket.socket, "connect", side_effect=RuntimeError("OFFLINE_NETWORK_FORBIDDEN")):
            runtimes = load("v5_runtime_fixtures", SYNC / "test_runtime.py")
            hooks = load("v5_hook_fixtures", SYNC / "test_cars_ui_hook.py")
            hooks.CarsHookTests.setUpClass()
            checks = [lambda: conscious_updates(hooks),
                      lambda: anomaly_confirmation(hooks, 245),
                      lambda: anomaly_confirmation(hooks, 245000),
                      lambda: restart_recovery(runtimes),
                      lambda: success_receipt(runtimes)]
            for index, check in enumerate(checks):
                try:
                    report["checks"].append(check())
                except Exception as exc:
                    report["checks"].append({"id": f"check_{index + 1}", "status": "ERROR",
                                             "error_type": type(exc).__name__, "message": str(exc)})
    except Exception as exc:
        report["setup_error"] = {"error_type": type(exc).__name__, "message": str(exc)}
    statuses = [item["status"] for item in report["checks"]]
    report["summary"] = {"pass": statuses.count("PASS"), "fail": statuses.count("FAIL"),
                         "error": statuses.count("ERROR") + int("setup_error" in report)}
    report["status"] = ("ERROR" if report["summary"]["error"] else
                        "FAIL" if report["summary"]["fail"] else "PASS")
    report["gate_implication"] = ("These offline checks cannot authorize Production or close Stage 4; "
                                  "any FAIL or ERROR blocks an overall v5 PASS claim.")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["status"] == "ERROR" else 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
