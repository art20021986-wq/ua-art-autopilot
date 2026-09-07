from __future__ import annotations

import datetime as dt
import dataclasses
from pathlib import Path

import pytest

from recovery_core import (
    BaseCandidate,
    HIDDEN_STATUS_CODES,
    RecoveryGuardError,
    SpecFact,
    WorkerHealth,
    activate_candidate,
    assert_change_scope,
    assert_spec_unchanged,
    build_candidate_revision,
    card_identity_errors,
    classify_stage_callback,
    exact_catalog_link_count,
    filter_selectable_statuses,
    is_exact_card_artifact,
    plan_base_fill,
    publication_preflight,
    resolved_under,
    stable_digest,
    vin_sha256,
    worker_health_errors,
)


VIN = "1HGBH41JXMN109186"  # Synthetic fixture; not the VIN of UA-0017.


def facts(count: int, prefix: str = "v") -> list[SpecFact]:
    return [
        SpecFact(
            field_key=f"field_{i:02d}",
            label_ru=f"Поле {i}",
            display_value=f"{prefix}{i}",
            category="engine" if i < 4 else "dimensions",
            unit="мм" if i >= 4 else "",
            confidence=0.95,
            evidence_count=2,
            source_domains=("auto-data.net", "cars-data.com"),
        )
        for i in range(count)
    ]


def complete_card() -> dict[str, object]:
    return {
        "auto_number": "UA-0017",
        "brand": "Mercedes-Benz",
        "model": "B-Class",
        "year": "2010",
        "vin": VIN,
        "fuel": "бензин",
        "engine_cc": 1700,
        "gearbox": "автомат",
        "drive": "передний",
        "mileage_km": 104000,
        "color": "белая",
    }


@pytest.mark.parametrize("count", [0, 4, 9])
def test_public_spec_requires_ten_visible_rows(count: int) -> None:
    with pytest.raises(RecoveryGuardError, match="SPEC_NOT_READY"):
        build_candidate_revision(
            "UA-0017", VIN, "P1", facts(count), revision_id=f"r{count}"
        )


def test_automatic_fact_cannot_self_declare_untrusted_manual_status() -> None:
    rows = [
        {
            "field_key": f"untrusted_{index}",
            "label_ru": f"Поле {index}",
            "display_value": str(index),
            "manual": "garbage",
            "confidence": 0,
            "evidence_count": 0,
            "source_domains": [],
        }
        for index in range(10)
    ]
    with pytest.raises(RecoveryGuardError, match="BOOLEAN_VALUE_INVALID"):
        build_candidate_revision(
            "UA-0017", VIN, "P1", rows, revision_id="untrusted-manual"
        )


def test_same_vin_active_spec_is_immutable() -> None:
    first = build_candidate_revision(
        "UA-0017", VIN, "P1", facts(10, "old"), revision_id="r1"
    )
    _, active = activate_candidate(None, first)
    refresh = build_candidate_revision(
        "UA-0017", VIN, "P1", facts(10, "new"), revision_id="r2"
    )
    archived, after = activate_candidate(active, refresh)
    assert archived is None
    assert after is active
    assert_spec_unchanged(active, after)


def test_vin_change_archives_instead_of_deleting() -> None:
    first = build_candidate_revision(
        "UA-0017", VIN, "P1", facts(10), revision_id="r1"
    )
    _, active = activate_candidate(None, first)
    second_vin = "WDDMH0BBXDV171918"
    second = build_candidate_revision(
        "UA-0017", second_vin, "P1", facts(10, "b"), revision_id="r2"
    )
    archived, replacement = activate_candidate(active, second)
    assert archived and archived.status == "ARCHIVED"
    assert archived.digest == active.digest
    assert replacement.status == "ACTIVE"
    assert replacement.vin_sha256 == vin_sha256(second_vin)


def test_base_fill_is_empty_only_and_source_scoped() -> None:
    current = {"brand": "Mercedes-Benz", "model": "", "mileage_km": "", "color": "white"}
    candidates = [
        BaseCandidate("brand", "Other", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)),
        BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.96, vin_sha256(VIN)),
        BaseCandidate("mileage_km", "104000", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)),
        BaseCandidate("mileage_km", "104000", "same_vin_crm", "crm:same-vin", 0.99, vin_sha256(VIN)),
        BaseCandidate("color", "black", "same_vin_crm", "crm:same-vin", 0.99, vin_sha256(VIN)),
    ]
    plan = plan_base_fill(current, candidates, expected_vin=VIN)
    assert plan.writes == {"mileage_km": "104000", "model": "B-Class"}
    assert set(plan.preserved) == {"brand", "color"}
    assert "mileage_km:VEHICLE_FACT_NOT_VERIFIED" in plan.rejected


def test_base_candidate_wrong_vin_is_rejected() -> None:
    plan = plan_base_fill(
        {"model": ""},
        [BaseCandidate("model", "B", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, "0" * 64)],
        expected_vin=VIN,
    )
    assert not plan.writes
    assert plan.rejected == ("model:VIN_MISMATCH",)


def test_base_fill_preserves_entire_operator_alias_group() -> None:
    plan = plan_base_fill(
        {"engine": "2.0 л, оператор", "engine_cc": ""},
        [
            BaseCandidate(
                "engine_cc", "1700", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)
            )
        ],
        expected_vin=VIN,
    )
    assert plan.writes == {}
    assert plan.preserved == ("engine_cc",)

    conflict = plan_base_fill(
        {"engine": "", "engine_cc": ""},
        [
            BaseCandidate(
                "engine", "2.0 л", "same_vin_crm", "crm", 0.99, vin_sha256(VIN)
            ),
            BaseCandidate(
                "engine_cc", "1700", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)
            ),
        ],
        expected_vin=VIN,
    )
    assert conflict.writes == {}
    assert set(conflict.rejected) == {
        "engine:ALIAS_GROUP_CONFLICT",
        "engine_cc:ALIAS_GROUP_CONFLICT",
    }


def test_worker_heartbeat_must_be_live_and_clean() -> None:
    now = dt.datetime(2026, 9, 7, 12, 0, tzinfo=dt.timezone.utc)
    healthy = WorkerHealth("w1", "2026-09-07T11:59:30Z", "2026-09-07T11:59:30Z")
    assert worker_health_errors(healthy, now=now) == ()
    stale = WorkerHealth("w1", "2026-09-07T11:50:00Z", "2026-09-07T11:50:00Z")
    assert worker_health_errors(stale, now=now) == ("VIN_WORKER_STALE",)
    failed = WorkerHealth("w1", "2026-09-07T11:59:30Z", "", "boom")
    assert worker_health_errors(failed, now=now) == (
        "VIN_WORKER_SUCCESS_MISSING",
        "VIN_WORKER_LAST_CYCLE_ERROR",
    )


def test_preflight_pass_and_duplicate_vin_fail() -> None:
    candidate = build_candidate_revision(
        "UA-0017", VIN, "P1", facts(10), revision_id="r1"
    )
    _, active = activate_candidate(None, candidate)
    now = dt.datetime(2026, 9, 7, 12, 0, tzinfo=dt.timezone.utc)
    health = WorkerHealth("w", "2026-09-07T12:00:00Z", "2026-09-07T12:00:00Z")
    result = publication_preflight(
        uid="UA-0017",
        vin=VIN,
        card=complete_card(),
        active_spec=active,
        worker_health=health,
        now=now,
    )
    assert result.ok
    blocked = publication_preflight(
        uid="UA-0017",
        vin=VIN,
        card=complete_card(),
        active_spec=active,
        worker_health=health,
        duplicate_active_uids=("UA-0002",),
        now=now,
    )
    assert not blocked.ok
    assert blocked.codes == ("DUPLICATE_ACTIVE_VIN:UA-0002",)


def test_http_200_generic_fallback_is_not_a_card() -> None:
    generic = "<html><h1>Автомобили</h1>Открыть все автомобили</html>"
    errors = card_identity_errors(
        generic, uid="UA-0017", vin=VIN, expected_spec_rows=10
    )
    assert "TARGET_IDENTITY_MARKER_MISSING" in errors
    assert "GENERIC_FALLBACK_PAGE" in errors


def test_card_identity_binds_spec_count_and_digest() -> None:
    revision = build_candidate_revision(
        "UA-0017", VIN, "P1", facts(10), revision_id="r1"
    )
    _, active = activate_candidate(None, revision)
    rows = "".join('<div class="ua-addspec-row"></div>' for _ in range(10))
    html = (
        f'<section class="ua-additional-spec" data-ua-card="UA-0017" '
        f'data-ua-spec-sha256="{active.digest}">'
        + VIN
        + rows
        + "</section>"
    )
    assert card_identity_errors(
        html,
        uid="UA-0017",
        vin=VIN,
        expected_spec_rows=10,
        expected_spec_digest=active.digest,
    ) == ()


def test_card_identity_ignores_inert_hidden_and_out_of_section_evidence() -> None:
    revision = build_candidate_revision(
        "UA-0017", VIN, "P1", facts(10), revision_id="visible-r1"
    )
    _, active = activate_candidate(None, revision)
    rows = "".join(
        f'<div class="ua-addspec-row"><dt>{fact.label_ru}</dt>'
        f'<dd>{fact.display_value}</dd></div>'
        for fact in active.visible_facts
    )
    forged = (
        "<!--"
        f'<section class="ua-additional-spec" data-ua-card="UA-0017" '
        f'data-ua-spec-sha256="{active.digest}">{VIN}{rows}</section>'
        "-->"
    )
    assert "TARGET_VIN_MISSING" in card_identity_errors(
        forged,
        uid="UA-0017",
        vin=VIN,
        expected_spec_rows=10,
        expected_spec_digest=active.digest,
        expected_spec=active,
    )
    for wrapper in (
        '<div hidden>%s</div>',
        '<div aria-hidden="true">%s</div>',
        '<div inert>%s</div>',
        '<div style="display: none !important">%s</div>',
        '<div class="hidden">%s</div>',
        '<script>%s</script>',
        '<template>%s</template>',
    ):
        hidden = wrapper % (
            f'<section class="ua-additional-spec" data-ua-card="UA-0017" '
            f'data-ua-spec-sha256="{active.digest}">{VIN}{rows}</section>'
        )
        assert card_identity_errors(
            hidden,
            uid="UA-0017",
            vin=VIN,
            expected_spec_rows=10,
            expected_spec_digest=active.digest,
            expected_spec=active,
        )
    outside = (
        f'<main data-ua-card="UA-0017">{VIN}</main>'
        f'<section class="ua-additional-spec" data-ua-spec-sha256="{active.digest}"></section>'
        + rows
    )
    assert "SPEC_ROWS_OUTSIDE_SECTION:10" in card_identity_errors(
        outside,
        uid="UA-0017",
        vin=VIN,
        expected_spec_rows=10,
        expected_spec_digest=active.digest,
        expected_spec=active,
    )


def test_spec_content_rejects_suffix_and_revision_integrity_rejects_coercion() -> None:
    revision = build_candidate_revision(
        "UA-0017", VIN, "P1", facts(10), revision_id="strict-r1"
    )
    _, active = activate_candidate(None, revision)
    rows = "".join(
        f'<div class="ua-addspec-row"><dt>{fact.label_ru}</dt><dd>'
        f'{fact.display_value}{" MALICIOUS" if index == 0 else ""}</dd></div>'
        for index, fact in enumerate(active.visible_facts)
    )
    html = (
        f'<section class="ua-additional-spec" data-ua-card="UA-0017" '
        f'data-ua-spec-sha256="{active.digest}">{VIN}{rows}</section>'
    )
    errors = card_identity_errors(
        html,
        uid="UA-0017",
        vin=VIN,
        expected_spec_rows=10,
        expected_spec_digest=active.digest,
        expected_spec=active,
    )
    assert "SPEC_FACT_CONTENT_MISSING:field_00" in errors

    extra = html.replace("</dd>", "</dd><b>FORGED</b>", 1)
    assert "SPEC_ROW_EXTRA_TEXT:0" in card_identity_errors(
        extra,
        uid="UA-0017",
        vin=VIN,
        expected_spec_rows=10,
        expected_spec_digest=active.digest,
        expected_spec=active,
    )

    duplicate = html.replace(
        'data-ua-card="UA-0017"',
        'data-ua-card="UA-9999" data-ua-card="UA-0017"',
        1,
    )
    assert any(
        code.startswith("HTML_DUPLICATE_SECURITY_ATTRIBUTE")
        for code in card_identity_errors(
            duplicate,
            uid="UA-0017",
            vin=VIN,
            expected_spec_rows=10,
            expected_spec_digest=active.digest,
            expected_spec=active,
        )
    )

    forged_fact = dataclasses.replace(active.facts[0], visible="false")
    forged = dataclasses.replace(active, facts=(forged_fact,) + active.facts[1:])
    result = publication_preflight(
        uid="UA-0017",
        vin=VIN,
        card=complete_card(),
        active_spec=forged,
        worker_health=WorkerHealth(
            "w", "2026-09-07T12:00:00Z", "2026-09-07T12:00:00Z"
        ),
        now=dt.datetime(2026, 9, 7, 12, 0, tzinfo=dt.timezone.utc),
    )
    assert "SPEC_FACT_BOOLEAN_INVALID:field_00" in result.codes


def test_preflight_rejects_wrong_card_uid_even_when_vin_matches() -> None:
    candidate = build_candidate_revision(
        "UA-0017", VIN, "P1", facts(10), revision_id="identity-r1"
    )
    _, active = activate_candidate(None, candidate)
    wrong = {**complete_card(), "auto_number": "UA-9999"}
    result = publication_preflight(
        uid="UA-0017",
        vin=VIN,
        card=wrong,
        active_spec=active,
        worker_health=WorkerHealth(
            "w", "2026-09-07T12:00:00Z", "2026-09-07T12:00:00Z"
        ),
        now=dt.datetime(2026, 9, 7, 12, 0, tzinfo=dt.timezone.utc),
    )
    assert "STALE_CARD_UID" in result.codes


def test_catalog_and_artifact_matching_do_not_prefix_collide() -> None:
    html = '<a href="UA-00170.html">x</a><a href="UA-0017.html?v=1">ok</a>'
    assert exact_catalog_link_count(html, "UA-0017") == 1
    assert is_exact_card_artifact("UA-0017.html", "UA-0017")
    assert is_exact_card_artifact("UA-0017-diag.html", "UA-0017")
    assert not is_exact_card_artifact("UA-00170.html", "UA-0017")


def test_statuses_are_hidden_not_deleted() -> None:
    statuses = {
        "kr_bought": (1, "Выкуплено, на нашей парковке"),
        "sea_loaded": (2, "Загружено в контейнер"),
        "sea_transit": (2, "В пути"),
        "ge_waiting": (3, "Авто в Грузии"),
        "ua_arrived": (4, "В Киеве"),
        "ua_handed": (4, "Передано клиенту"),
        "sold": (4, "Продано"),
    }
    filtered = filter_selectable_statuses(statuses)
    assert not (set(filtered) & HIDDEN_STATUS_CODES)
    assert set(statuses) & HIDDEN_STATUS_CODES == HIDDEN_STATUS_CODES
    assert set(filtered) == {"ge_waiting", "ua_arrived", "sold"}
    assert classify_stage_callback("car_setstage:17:sea_transit")[0] == "BLOCKED_LEGACY_STATUS"
    assert classify_stage_callback("car_setstage:17:ge_waiting")[0] == "PASS_TO_CANONICAL_HANDLER"


def test_preview_path_and_change_scope_guards(tmp_path: Path) -> None:
    root = tmp_path / "preview"
    root.mkdir()
    assert resolved_under(root, root / "video" / "UA-0017.html").is_relative_to(root)
    with pytest.raises(RecoveryGuardError, match="WRITE_OUTSIDE_PREVIEW"):
        resolved_under(root, tmp_path / "elsewhere")
    before = {"UA-0001.html": "a", "UA-0017.html": "x"}
    after = {"UA-0001.html": "a", "UA-0017.html": "y"}
    assert assert_change_scope(before, after, allowed_exact_paths=("UA-0017.html",)) == (
        "UA-0017.html",
    )
    with pytest.raises(RecoveryGuardError, match="SITE_FOUNDATION_CHANGED"):
        assert_change_scope(before, {**after, "UA-0001.html": "z"}, allowed_exact_paths=("UA-0017.html",))


def test_stable_digest_is_order_independent_for_mapping() -> None:
    assert stable_digest({"a": 1, "b": 2}) == stable_digest({"b": 2, "a": 1})
