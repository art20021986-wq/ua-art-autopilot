#!/usr/bin/env python3
"""Dependency-free integration checks for the TASK116 runtime bridge."""
from __future__ import annotations

import concurrent.futures
import contextlib
import datetime as dt
import sqlite3
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Iterator


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import ua116_runtime_bridge as bridge
from recovery_core import BaseCandidate, RecoveryGuardError, SpecFact, vin_sha256
from spec_revision_store import get_active, stage_and_activate


# SYNTHETIC_TEST_VIN values: never associate these fixtures with a real card.
VIN_1 = "1HGBH41JXMN109186"
VIN_2 = "1M8GDM9AXKP042788"


def _create_crm(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE cars ("
            "id INTEGER PRIMARY KEY, auto_number TEXT NOT NULL UNIQUE, vin TEXT NOT NULL, "
            "published INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'draft', "
            "brand TEXT, model TEXT, year TEXT, trim TEXT, body TEXT, fuel TEXT, "
            "engine TEXT, engine_cc TEXT, gearbox TEXT, drive TEXT, mileage TEXT, "
            "mileage_km TEXT, color TEXT)"
        )
        con.execute(
            "CREATE TABLE audit (id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT, "
            "entity_type TEXT, entity_id INTEGER, field TEXT, old_value TEXT, "
            "new_value TEXT, created_at TEXT)"
        )
        con.execute(
            "INSERT INTO cars(id,auto_number,vin,mileage_km,color) "
            "VALUES(1,'UA-0017',?,'104000','белая')",
            (VIN_1,),
        )
        con.execute(
            "INSERT INTO cars(id,auto_number,vin,mileage_km,color) "
            "VALUES(2,'UA-0018',?,'120000','чёрная')",
            (VIN_2,),
        )


def _facts(prefix: str) -> list[SpecFact]:
    return [
        SpecFact(
            field_key=f"f{i}",
            label_ru=f"Поле {i}",
            display_value=f"{prefix}-{i}",
            category="engine",
            confidence=0.96,
            evidence_count=1,
            source_domains=("auto-data.net",),
        )
        for i in range(10)
    ]


def _decoded(vin: str) -> list[BaseCandidate]:
    digest = vin_sha256(vin)
    values = {
        "brand": "Mercedes-Benz",
        "model": "B-Class",
        "year": "2010",
        "trim": "B170",
        "body": "hatchback",
        "fuel": "бензин",
        "engine_cc": "1700",
        "gearbox": "автомат",
        "drive": "передний",
    }
    if vin == VIN_2:
        values.update({"model": "C-Class", "year": "2012", "trim": "C180", "engine_cc": "1800"})
    return [
        BaseCandidate(field, value, "vin_decoder", "vpic.nhtsa.dot.gov", 0.96, digest)
        for field, value in values.items()
    ]


def _card(path: Path, card_id: int = 1) -> dict[str, Any]:
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM cars WHERE id=?", (card_id,)).fetchone()
    assert row is not None
    return dict(row)


@contextlib.contextmanager
def _environment(root: Path) -> Iterator[tuple[Path, Path, types.ModuleType]]:
    root.mkdir(parents=True, exist_ok=True)
    main_db, spec_db = root / "crm.db", root / "spec.db"
    _create_crm(main_db)

    # A deliberately stale legacy heartbeat proves that the fresh TASK116
    # heartbeat wins by timestamp rather than table precedence.
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()
    with sqlite3.connect(spec_db) as con:
        con.execute(
            "CREATE TABLE vin_spec_state (key TEXT PRIMARY KEY,value TEXT,updated_at TEXT)"
        )
        con.executemany(
            "INSERT INTO vin_spec_state(key,value,updated_at) VALUES(?,?,?)",
            (
                ("worker_instance_id", "legacy-old", old),
                ("last_cycle_at", old, old),
                ("last_success_at", old, old),
                ("last_cycle_error", "", old),
                ("queue_depth", "0", old),
            ),
        )

    service = types.ModuleType("vin_spec_service")
    service.MAIN_DB = str(main_db)
    service.SPEC_DB = str(spec_db)
    service.states = {}
    service.ready = True
    service.events = []
    service.counter = 0

    def read_cards():
        with sqlite3.connect(main_db) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute("SELECT * FROM cars ORDER BY id").fetchall()
        return [
            {"car_id": row["id"], "car_uid": row["auto_number"], "vin": row["vin"]}
            for row in rows
        ]

    def enqueue_card(card, **_kwargs):
        # This is deliberately checked at the fake legacy boundary, not after
        # the bridge returns: base fill must precede additional-spec enqueue.
        expected_model = "C-Class" if card["vin"] == VIN_2 else "B-Class"
        assert _card(main_db, int(card["car_id"]))["model"] == expected_model
        service.events.append((card["car_uid"], card["vin"]))
        service.states[card["car_uid"]] = {
            "status": "PENDING",
            "vin": card["vin"],
        }

    def process_card_now(uid):
        state = service.states[uid]
        if not service.ready:
            state["status"] = "NEEDS_REVIEW"
            return dict(state)
        service.counter += 1
        stage_and_activate(
            spec_db,
            uid=uid,
            vin=state["vin"],
            policy_version="STDLIB-TEST",
            revision_id=f"stdlib-{service.counter}-{vin_sha256(state['vin'])[:12]}",
            rows=_facts(str(service.counter)),
        )
        state["status"] = "READY"
        return dict(state)

    def card_state(uid):
        return dict(service.states.get(uid, {"status": "NOT_QUEUED", "vin": ""}))

    service.read_cards = read_cards
    service.enqueue_card = enqueue_card
    service.process_card_now = process_card_now
    service.card_state = card_state
    additional = types.ModuleType("ua_additional_spec")

    sentinel = object()
    old_modules = {
        name: sys.modules.get(name, sentinel)
        for name in ("vin_spec_service", "ua_additional_spec")
    }
    old_decoder, old_prepare = bridge.decode_primary_candidates, bridge._prepare_card
    sys.modules["vin_spec_service"] = service
    sys.modules["ua_additional_spec"] = additional
    bridge.decode_primary_candidates = _decoded
    # Optional async enrichment is outside these synchronous boundary checks.
    bridge._prepare_card = lambda *_args, **_kwargs: {}
    bridge._locks.clear()
    bridge._threads.clear()
    try:
        yield main_db, spec_db, service
    finally:
        bridge.decode_primary_candidates = old_decoder
        bridge._prepare_card = old_prepare
        bridge._locks.clear()
        bridge._threads.clear()
        for name, value in old_modules.items():
            if value is sentinel:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def _case_sync_primary_before_additional(root: Path) -> None:
    with _environment(root) as (main_db, spec_db, service):
        result = bridge.handle_saved_vin(card_id=1, vin=VIN_1, actor_id=7)
        assert result["status"] == "PENDING"
        assert any(item["status"] == "APPLIED" for item in result["primary_fill_results"])
        assert _card(main_db)["model"] == "B-Class"
        assert service.events == [("UA-0017", VIN_1)]
        with sqlite3.connect(spec_db) as con:
            status = con.execute(
                "SELECT status FROM ua116_primary_fill_job WHERE car_uid='UA-0017'"
            ).fetchone()[0]
        assert status == "APPLIED"


def _case_duplicate_and_concurrent_reservation(root: Path) -> None:
    with _environment(root) as (main_db, spec_db, _service):
        with sqlite3.connect(main_db) as con:
            con.execute("UPDATE cars SET vin=? WHERE id=2", (VIN_1,))
        bridge._initialize_runtime_tables(spec_db)

        def claim(uid: str) -> str:
            try:
                bridge.reserve_vin(uid=uid, vin=VIN_1)
                return "RESERVED"
            except RecoveryGuardError as exc:
                return exc.code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("UA-0017", "UA-0018")))
        assert sorted(results) == ["RESERVED", "VIN_RESERVED_BY_OTHER_CARD"]
        with sqlite3.connect(spec_db) as con:
            assert con.execute("SELECT COUNT(*) FROM ua116_vin_reservation").fetchone()[0] == 1


def _case_decoder_outage_fail_closed(root: Path) -> None:
    with _environment(root) as (main_db, _spec_db, service):
        def unavailable(_vin: str):
            raise OSError("decoder offline")

        bridge.decode_primary_candidates = unavailable
        result = bridge.handle_saved_vin(card_id=1, vin=VIN_1, actor_id=7)
        assert result["status"] == "BLOCKED"
        assert result["code"] == "BASE_SPEC_INCOMPLETE"
        assert _card(main_db)["model"] is None
        assert service.events == []


def _case_exact_vin_revision(root: Path) -> None:
    with _environment(root) as (main_db, spec_db, service):
        stage_and_activate(
            spec_db,
            uid="UA-0017",
            vin=VIN_1,
            policy_version="OLD",
            revision_id="old-vin-revision",
            rows=_facts("old"),
        )
        with sqlite3.connect(main_db) as con:
            con.execute("UPDATE cars SET vin=? WHERE id=1", (VIN_2,))
        assert bridge._active_for_exact_vin("UA-0017", VIN_2) is None
        service.ready = False
        result = bridge.prepare_for_publish(_card(main_db))
        assert result["ok"] is False
        active = get_active(spec_db, "UA-0017")
        assert active is not None and active.revision_id == "old-vin-revision"
        assert active.vin_sha256 == vin_sha256(VIN_1)


def _case_vin_correction_replaces_only_system_values(root: Path) -> None:
    with _environment(root) as (main_db, spec_db, _service):
        first = bridge.handle_saved_vin(card_id=1, vin=VIN_1, actor_id=7)
        assert first["status"] == "PENDING"
        with sqlite3.connect(main_db) as con:
            # This operator edit must survive the VIN correction.
            con.execute("UPDATE cars SET trim='ручная комплектация',vin=? WHERE id=1", (VIN_2,))
        second = bridge.handle_saved_vin(card_id=1, vin=VIN_2, actor_id=8)
        assert second["status"] == "PENDING", second
        card = _card(main_db)
        assert card["model"] == "C-Class"
        assert card["year"] == "2012"
        assert card["engine_cc"] == "1800"
        assert card["trim"] == "ручная комплектация"
        assert card["mileage_km"] == "104000" and card["color"] == "белая"
        with sqlite3.connect(spec_db) as con:
            stale = con.execute(
                "SELECT COUNT(*) FROM ua116_primary_field_provenance "
                "WHERE car_uid='UA-0017' AND active=1 AND vin_sha256=?",
                (vin_sha256(VIN_1),),
            ).fetchone()[0]
        assert stale == 0
        with sqlite3.connect(main_db) as con:
            restored = con.execute(
                "SELECT COUNT(*) FROM audit WHERE action LIKE 'ua116_vin_correction_restore %'"
            ).fetchone()[0]
        assert restored >= 1


def _case_publish_preflight_does_not_publish(root: Path) -> None:
    with _environment(root) as (main_db, _spec_db, _service):
        before = _card(main_db)
        assert before["published"] == 0 and before["model"] is None
        result = bridge.prepare_for_publish(before)
        assert result["ok"] is True
        after = _card(main_db)
        assert after["published"] == 0
        assert after["model"] == "B-Class"
        assert result["visible_spec_rows"] == 10
        health = bridge._read_worker_health()
        assert health is not None
        assert health.worker_instance_id.startswith("task116-publish:")


def run() -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    cases = (
        ("sync_primary_before_additional", _case_sync_primary_before_additional),
        ("duplicate_and_concurrent_reservation", _case_duplicate_and_concurrent_reservation),
        ("decoder_outage_fail_closed", _case_decoder_outage_fail_closed),
        ("exact_vin_revision", _case_exact_vin_revision),
        ("vin_correction_replaces_only_system_values", _case_vin_correction_replaces_only_system_values),
        ("publish_preflight_no_publish_and_fresh_heartbeat", _case_publish_preflight_does_not_publish),
    )
    with tempfile.TemporaryDirectory(prefix="ua116-runtime-stdlib-") as temporary:
        base = Path(temporary)
        for index, (name, callback) in enumerate(cases):
            try:
                callback(base / f"case-{index}")
            except Exception as exc:
                checks.append(
                    {"name": name, "status": "FAIL", "error": type(exc).__name__ + ":" + str(exc)}
                )
            else:
                checks.append({"name": name, "status": "PASS"})
    passed = sum(item["status"] == "PASS" for item in checks)
    return {
        "status": "PASS" if passed == len(checks) else "FAIL",
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }


if __name__ == "__main__":
    import json

    outcome = run()
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    raise SystemExit(0 if outcome["status"] == "PASS" else 1)
