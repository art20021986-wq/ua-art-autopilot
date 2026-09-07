from __future__ import annotations

import concurrent.futures
import sqlite3
import sys
import types
from pathlib import Path
from typing import Any

import pytest

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
            "VALUES(1,'UA-0017',?, '104000','белая')",
            (VIN_1,),
        )
        con.execute(
            "INSERT INTO cars(id,auto_number,vin,mileage_km,color) "
            "VALUES(2,'UA-0018',?, '120000','чёрная')",
            (VIN_2,),
        )


def _facts(prefix: str = "spec") -> list[SpecFact]:
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
    return [
        BaseCandidate(field, value, "vin_decoder", "vpic.nhtsa.dot.gov", 0.96, digest)
        for field, value in values.items()
    ]


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    main_db = tmp_path / "crm.db"
    spec_db = tmp_path / "spec.db"
    _create_crm(main_db)

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
        with sqlite3.connect(main_db) as con:
            row = con.execute(
                "SELECT model FROM cars WHERE id=?", (int(card["car_id"]),)
            ).fetchone()
        # This assertion is the integration contract: primary CRM filling is
        # complete before the additional-spec service is allowed to enqueue.
        assert row and row[0] == "B-Class"
        service.events.append(("additional_enqueued", card["car_uid"], card["vin"]))
        service.states[card["car_uid"]] = {
            "status": "PENDING",
            "vin": card["vin"],
        }

    def process_card_now(uid):
        state = service.states[uid]
        if not service.ready:
            state.update(status="NEEDS_REVIEW")
            return dict(state)
        service.counter += 1
        stage_and_activate(
            spec_db,
            uid=uid,
            vin=state["vin"],
            policy_version="TEST-POLICY",
            revision_id=f"test-{service.counter}-{vin_sha256(state['vin'])[:12]}",
            rows=_facts(str(service.counter)),
        )
        state.update(status="READY")
        return dict(state)

    def card_state(uid):
        return dict(service.states.get(uid, {"status": "NOT_QUEUED", "vin": ""}))

    service.read_cards = read_cards
    service.enqueue_card = enqueue_card
    service.process_card_now = process_card_now
    service.card_state = card_state
    additional = types.ModuleType("ua_additional_spec")

    monkeypatch.setitem(sys.modules, "vin_spec_service", service)
    monkeypatch.setitem(sys.modules, "ua_additional_spec", additional)
    monkeypatch.setattr(bridge, "decode_primary_candidates", _decoded)
    # The save-path assertions end before optional additional enrichment.  A
    # no-op target retains a real Thread object without racing fake modules.
    monkeypatch.setattr(bridge, "_prepare_card", lambda *_args, **_kwargs: {})
    bridge._locks.clear()
    bridge._threads.clear()
    return main_db, spec_db, service


def _card(path: Path, card_id: int = 1) -> dict[str, Any]:
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        return dict(con.execute("SELECT * FROM cars WHERE id=?", (card_id,)).fetchone())


def test_saved_vin_fills_primary_synchronously_before_additional(runtime) -> None:
    main_db, spec_db, service = runtime
    result = bridge.handle_saved_vin(card_id=1, vin=VIN_1, actor_id=77)

    assert result["status"] == "PENDING"
    assert any(item["status"] == "APPLIED" for item in result["primary_fill_results"])
    after = _card(main_db)
    assert after["model"] == "B-Class"
    assert after["engine_cc"] == "1700"
    assert after["mileage_km"] == "104000"  # operator value preserved
    assert service.events == [("additional_enqueued", "UA-0017", VIN_1)]
    with sqlite3.connect(main_db) as con:
        assert con.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 9
    with sqlite3.connect(spec_db) as con:
        status = con.execute(
            "SELECT status FROM ua116_primary_fill_job WHERE car_uid='UA-0017'"
        ).fetchone()[0]
    assert status == "APPLIED"


def test_decoder_outage_never_reports_incomplete_primary_as_ready(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_db, _spec_db, service = runtime

    def unavailable(_vin: str):
        raise OSError("decoder offline")

    monkeypatch.setattr(bridge, "decode_primary_candidates", unavailable)
    result = bridge.handle_saved_vin(card_id=1, vin=VIN_1, actor_id=77)

    assert result["status"] == "BLOCKED"
    assert result["code"] == "BASE_SPEC_INCOMPLETE"
    assert _card(main_db)["model"] is None
    assert service.events == []


def test_publish_preflight_synchronously_repairs_primary_without_publishing(runtime) -> None:
    main_db, _spec_db, _service = runtime
    before = _card(main_db)
    assert before["model"] is None and before["published"] == 0

    result = bridge.prepare_for_publish(before)

    assert result["ok"] is True
    after = _card(main_db)
    assert after["model"] == "B-Class"
    assert after["published"] == 0
    assert result["visible_spec_rows"] == 10


def test_duplicate_vin_is_durable_and_fails_closed_before_any_fill(runtime) -> None:
    main_db, spec_db, _service = runtime
    with sqlite3.connect(main_db) as con:
        con.execute("UPDATE cars SET vin=?,published=1 WHERE id=2", (VIN_1,))

    result = bridge.handle_saved_vin(card_id=1, vin=VIN_1, actor_id=77)

    assert result["status"] == "BLOCKED"
    assert result["code"] == "DUPLICATE_ACTIVE_VIN"
    assert _card(main_db)["model"] is None
    with sqlite3.connect(main_db) as con:
        assert con.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 0
    with sqlite3.connect(spec_db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM ua116_primary_fill_job"
        ).fetchone()[0] == 0


def test_unpublished_cards_cannot_claim_same_durable_vin(runtime) -> None:
    main_db, _spec_db, _service = runtime
    with sqlite3.connect(main_db) as con:
        con.execute("UPDATE cars SET vin=? WHERE id=2", (VIN_1,))
    bridge.reserve_vin(uid="UA-0017", vin=VIN_1)
    with pytest.raises(RecoveryGuardError, match="VIN_RESERVED_BY_OTHER_CARD"):
        bridge.reserve_vin(uid="UA-0018", vin=VIN_1)


def test_concurrent_vin_claims_have_exactly_one_winner(runtime) -> None:
    main_db, spec_db, _service = runtime
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
        owners = con.execute("SELECT car_uid FROM ua116_vin_reservation").fetchall()
    assert len(owners) == 1


def test_vin_change_never_reuses_old_active_revision(runtime) -> None:
    main_db, spec_db, service = runtime
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
    assert "SPEC_NOT_READY" in result["owner_text"] or result["code"] != "READY"
    active = get_active(spec_db, "UA-0017")
    assert active and active.revision_id == "old-vin-revision"
    assert active.vin_sha256 == vin_sha256(VIN_1)


def test_superseded_running_job_wins_over_late_failure(runtime) -> None:
    _main_db, spec_db, _service = runtime
    bridge.reserve_vin(uid="UA-0017", vin=VIN_1)
    bridge.enqueue_primary_fill(card_id=1, uid="UA-0017", vin=VIN_1, actor_id=7)
    job = bridge._claim_primary_job("UA-0017")
    assert job and job["status"] == "RUNNING"
    with sqlite3.connect(spec_db) as con:
        con.execute(
            "UPDATE ua116_primary_fill_job SET status='SUPERSEDED' WHERE id=?",
            (job["id"],),
        )
    assert bridge._finish_primary_job(job["id"], status="FAILED") == "SUPERSEDED"
    with sqlite3.connect(spec_db) as con:
        assert con.execute(
            "SELECT status FROM ua116_primary_fill_job WHERE id=?", (job["id"],)
        ).fetchone()[0] == "SUPERSEDED"
