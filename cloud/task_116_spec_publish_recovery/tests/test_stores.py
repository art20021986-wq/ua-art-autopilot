from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
from pathlib import Path

import pytest

from recovery_core import (
    BaseCandidate,
    BaseFillPlan,
    RecoveryGuardError,
    SpecFact,
    plan_base_fill,
    vin_sha256,
)
from spec_revision_store import get_active, initialize, record_rejected_candidate, stage_and_activate
from vin_base_spec_service import apply_fill_plan, row_digest


VIN = "1HGBH41JXMN109186"  # Synthetic fixture; not the VIN of UA-0017.


def spec_rows(count: int, prefix: str = "a") -> list[SpecFact]:
    return [
        SpecFact(
            field_key=f"f{i}",
            label_ru=f"F {i}",
            display_value=f"{prefix}{i}",
            category="engine",
            confidence=0.95,
            evidence_count=1,
            source_domains=("auto-data.net",),
        )
        for i in range(count)
    ]


def make_crm(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE cars (id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT, "
            "brand TEXT, model TEXT, year TEXT, fuel TEXT, engine_cc INTEGER, "
            "gearbox TEXT, drive TEXT, mileage_km INTEGER, color TEXT)"
        )
        con.execute(
            "CREATE TABLE audit (id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT, "
            "entity_type TEXT, entity_id INTEGER, field TEXT, old_value TEXT, "
            "new_value TEXT, created_at TEXT)"
        )
        con.execute(
            "INSERT INTO cars(id,auto_number,vin,brand,model,color) VALUES(1,'UA-0017',?,?,?,?)",
            (VIN, "Mercedes-Benz", "", "белая"),
        )


def get_row(path: Path) -> dict[str, object]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return dict(con.execute("SELECT * FROM cars WHERE id=1").fetchone())
    finally:
        con.close()


def test_revision_store_never_replaces_same_vin_active(tmp_path: Path) -> None:
    path = tmp_path / "spec.db"
    first = stage_and_activate(
        path,
        uid="UA-0017",
        vin=VIN,
        policy_version="P1",
        revision_id="rev-1",
        rows=spec_rows(10, "old"),
    )
    second = stage_and_activate(
        path,
        uid="UA-0017",
        vin=VIN,
        policy_version="P1",
        revision_id="rev-2",
        rows=spec_rows(10, "new"),
    )
    assert first["status"] == "ACTIVATED"
    assert second["status"] == "UNCHANGED"
    assert second["active_digest"] == first["active_digest"]
    active = get_active(path, "UA-0017")
    assert active and active.revision_id == "rev-1"
    assert active.facts[0].display_value.startswith("old")


def test_partial_or_failed_revision_leaves_active_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "spec.db"
    stage_and_activate(
        path,
        uid="UA-0017",
        vin=VIN,
        policy_version="P1",
        revision_id="rev-1",
        rows=spec_rows(10),
    )
    before = get_active(path, "UA-0017")
    with pytest.raises(RecoveryGuardError, match="SPEC_NOT_READY"):
        stage_and_activate(
            path,
            uid="UA-0017",
            vin="WDDMH0BBXDV171918",
            policy_version="P1",
            revision_id="rev-2",
            rows=spec_rows(9),
        )
    record_rejected_candidate(
        path,
        uid="UA-0017",
        vin="WDDMH0BBXDV171918",
        policy_version="P1",
        revision_id="rev-rejected",
        visible_count=9,
        reject_code="SPEC_NOT_READY",
    )
    after = get_active(path, "UA-0017")
    assert before and after and before.digest == after.digest


def test_activation_failure_rolls_back_archive_and_candidate(tmp_path: Path) -> None:
    path = tmp_path / "spec.db"
    stage_and_activate(
        path,
        uid="UA-0017",
        vin=VIN,
        policy_version="P1",
        revision_id="rev-1",
        rows=spec_rows(10),
    )
    with pytest.raises(RuntimeError, match="INJECTED_AFTER_ACTIVATION"):
        stage_and_activate(
            path,
            uid="UA-0017",
            vin="WDDMH0BBXDV171918",
            policy_version="P1",
            revision_id="rev-2",
            rows=spec_rows(10, "b"),
            fault="after_activation",
        )
    active = get_active(path, "UA-0017")
    assert active and active.revision_id == "rev-1"
    with sqlite3.connect(path) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM ua116_spec_revision WHERE revision_id='rev-2'"
        ).fetchone()[0] == 0


def test_corrupt_active_cannot_be_archived_or_replaced_by_new_vin(tmp_path: Path) -> None:
    path = tmp_path / "spec.db"
    stage_and_activate(
        path,
        uid="UA-0017",
        vin=VIN,
        policy_version="P1",
        revision_id="rev-sealed",
        rows=spec_rows(10),
    )
    # Simulate an out-of-band/tampered DB, bypassing the normal immutable trigger.
    with sqlite3.connect(path) as con:
        con.execute("DROP TRIGGER ua116_spec_fact_no_update")
        con.execute(
            "UPDATE ua116_spec_fact SET display_value='tampered' "
            "WHERE revision_id='rev-sealed' AND field_key='f0'"
        )
    with pytest.raises(RecoveryGuardError, match="SPEC_DIGEST_MISMATCH"):
        stage_and_activate(
            path,
            uid="UA-0017",
            vin="WDDMH0BBXDV171918",
            policy_version="P1",
            revision_id="rev-must-not-activate",
            rows=spec_rows(10, "new"),
        )
    with sqlite3.connect(path) as con:
        assert con.execute(
            "SELECT status FROM ua116_spec_revision WHERE revision_id='rev-sealed'"
        ).fetchone()[0] == "ACTIVE"
        assert con.execute(
            "SELECT COUNT(*) FROM ua116_spec_revision "
            "WHERE revision_id='rev-must-not-activate'"
        ).fetchone()[0] == 0


def test_primary_writer_is_atomic_empty_only_and_audited(tmp_path: Path) -> None:
    db_path = tmp_path / "crm.db"
    make_crm(db_path)
    before = get_row(db_path)
    candidates = [
        BaseCandidate("brand", "Other", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)),
        BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)),
        BaseCandidate("engine_cc", "1700", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)),
        BaseCandidate("mileage_km", "104000", "same_vin_crm", "crm:same-vin", 0.99, vin_sha256(VIN)),
        BaseCandidate("color", "чёрная", "same_vin_crm", "crm:same-vin", 0.99, vin_sha256(VIN)),
    ]
    plan = plan_base_fill(before, candidates, expected_vin=VIN)
    receipt = apply_fill_plan(
        db_path,
        card_id=1,
        uid="UA-0017",
        expected_vin=VIN,
        plan=plan,
        actor_id=7,
        expected_row_digest=row_digest(before),
        preview_root=tmp_path,
    )
    after = get_row(db_path)
    assert after["brand"] == "Mercedes-Benz"
    assert after["model"] == "B-Class"
    assert after["engine_cc"] == 1700
    assert after["mileage_km"] == 104000
    assert after["color"] == "белая"
    assert receipt["written_fields"] == ["engine_cc", "mileage_km", "model"]
    with sqlite3.connect(db_path) as con:
        audit = con.execute(
            "SELECT field,new_value,action FROM audit ORDER BY field"
        ).fetchall()
    assert [(field, value) for field, value, _action in audit] == [
        ("engine_cc", "1700"),
        ("mileage_km", "104000"),
        ("model", "B-Class"),
    ]
    for field, value, action in audit:
        prefix, payload = action.split(" ", 1)
        metadata = json.loads(payload)
        assert prefix == "vin_base_spec_empty_only"
        assert metadata["before_row_digest"] == row_digest(before)
        assert metadata["plan_audit_digest"] == plan.audit_digest
        assert metadata["provenance"] == plan.provenance[field]
        assert len(metadata["value_digest"]) == 64


def test_primary_writer_rejects_forged_provenance_at_write_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "crm.db"
    make_crm(db_path)
    before = get_row(db_path)
    forged = plan_base_fill(
        before,
        [
            BaseCandidate(
                "model", "Forged", "vin_decoder", "not-vpic.example", 0.99,
                vin_sha256(VIN),
            )
        ],
        expected_vin=VIN,
    )
    with pytest.raises(RecoveryGuardError, match="BASE_PLAN_SOURCE_INVALID"):
        apply_fill_plan(
            db_path,
            card_id=1,
            uid="UA-0017",
            expected_vin=VIN,
            plan=forged,
            actor_id=None,
            expected_row_digest=row_digest(before),
            preview_root=tmp_path,
        )
    assert get_row(db_path)["model"] == ""


@pytest.mark.parametrize("fault", ["after_update", "after_audit"])
def test_primary_writer_fault_rolls_back_data_and_audit(tmp_path: Path, fault: str) -> None:
    db_path = tmp_path / "crm.db"
    make_crm(db_path)
    before = get_row(db_path)
    plan = plan_base_fill(
        before,
        [BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN))],
        expected_vin=VIN,
    )
    with pytest.raises(RuntimeError):
        apply_fill_plan(
            db_path,
            card_id=1,
            uid="UA-0017",
            expected_vin=VIN,
            plan=plan,
            actor_id=7,
            expected_row_digest=row_digest(before),
            preview_root=tmp_path,
            fault=fault,
        )
    assert get_row(db_path)["model"] == ""
    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 0


def test_primary_writer_rejects_stale_card_revision(tmp_path: Path) -> None:
    db_path = tmp_path / "crm.db"
    make_crm(db_path)
    before = get_row(db_path)
    plan = plan_base_fill(
        before,
        [BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN))],
        expected_vin=VIN,
    )
    with sqlite3.connect(db_path) as con:
        con.execute("UPDATE cars SET fuel='бензин' WHERE id=1")
    with pytest.raises(RecoveryGuardError, match="STALE_CARD_REVISION"):
        apply_fill_plan(
            db_path,
            card_id=1,
            uid="UA-0017",
            expected_vin=VIN,
            plan=plan,
            actor_id=7,
            expected_row_digest=row_digest(before),
            preview_root=tmp_path,
        )


def test_primary_writer_rejects_hardlinked_preview_database(tmp_path: Path) -> None:
    db_path = tmp_path / "crm.db"
    alias_path = tmp_path / "could-be-live.db"
    make_crm(db_path)
    os.link(db_path, alias_path)
    before = get_row(db_path)
    plan = plan_base_fill(
        before,
        [BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN))],
        expected_vin=VIN,
    )
    with pytest.raises(RecoveryGuardError, match="CRM_DB_HARDLINK_FORBIDDEN"):
        apply_fill_plan(
            db_path,
            card_id=1,
            uid="UA-0017",
            expected_vin=VIN,
            plan=plan,
            actor_id=7,
            expected_row_digest=row_digest(before),
            preview_root=tmp_path,
        )
    assert get_row(db_path)["model"] == ""


def test_primary_writer_binds_plan_before_digest_to_expected_digest(tmp_path: Path) -> None:
    db_path = tmp_path / "crm.db"
    make_crm(db_path)
    before = get_row(db_path)
    plan = plan_base_fill(
        before,
        [BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN))],
        expected_vin=VIN,
    )
    forged = dataclasses.replace(plan, before_digest="0" * 64)
    with pytest.raises(RecoveryGuardError, match="PLAN_BEFORE_DIGEST_MISMATCH"):
        apply_fill_plan(
            db_path,
            card_id=1,
            uid="UA-0017",
            expected_vin=VIN,
            plan=forged,
            actor_id=7,
            expected_row_digest=row_digest(before),
            preview_root=tmp_path,
        )
    assert get_row(db_path)["model"] == ""


@pytest.mark.parametrize(
    ("metadata_patch", "error"),
    [
        ({"source_kind": "untrusted_scrape"}, "BASE_PLAN_SOURCE_KIND_INVALID"),
        ({"source": ""}, "BASE_PLAN_SOURCE_INVALID"),
        ({"confidence": 0.89}, "BASE_PLAN_CONFIDENCE_INVALID"),
        ({"vin_sha256": "0" * 64}, "BASE_PLAN_VIN_MISMATCH"),
    ],
)
def test_primary_writer_revalidates_provenance_at_write_boundary(
    tmp_path: Path, metadata_patch: dict[str, object], error: str
) -> None:
    db_path = tmp_path / "crm.db"
    make_crm(db_path)
    before = get_row(db_path)
    plan = plan_base_fill(
        before,
        [BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN))],
        expected_vin=VIN,
    )
    metadata = dict(plan.provenance["model"])
    metadata.update(metadata_patch)
    forged = BaseFillPlan(
        writes=dict(plan.writes),
        provenance={"model": metadata},
        preserved=plan.preserved,
        rejected=plan.rejected,
        before_digest=plan.before_digest,
    )
    with pytest.raises(RecoveryGuardError, match=error):
        apply_fill_plan(
            db_path,
            card_id=1,
            uid="UA-0017",
            expected_vin=VIN,
            plan=forged,
            actor_id=7,
            expected_row_digest=row_digest(before),
            preview_root=tmp_path,
        )
    assert get_row(db_path)["model"] == ""


def test_primary_writer_rolls_back_trigger_side_effects(tmp_path: Path) -> None:
    db_path = tmp_path / "crm.db"
    make_crm(db_path)
    with sqlite3.connect(db_path) as con:
        con.execute("ALTER TABLE cars ADD COLUMN trigger_touched TEXT")
        con.execute(
            "CREATE TRIGGER mutate_unrelated_after_base_fill AFTER UPDATE OF model ON cars "
            "BEGIN UPDATE cars SET trigger_touched='unexpected' WHERE id=NEW.id; END"
        )
    before = get_row(db_path)
    plan = plan_base_fill(
        before,
        [BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN))],
        expected_vin=VIN,
    )
    with pytest.raises(RecoveryGuardError, match="BASE_SPEC_TRIGGER_SIDE_EFFECT"):
        apply_fill_plan(
            db_path,
            card_id=1,
            uid="UA-0017",
            expected_vin=VIN,
            plan=plan,
            actor_id=7,
            expected_row_digest=row_digest(before),
            preview_root=tmp_path,
        )
    after = get_row(db_path)
    assert after["model"] == ""
    assert after["trigger_touched"] is None
    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 0
