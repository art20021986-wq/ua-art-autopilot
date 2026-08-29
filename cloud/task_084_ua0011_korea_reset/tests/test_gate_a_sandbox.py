"""Offline synthetic-fixture test suite for TASK 084.

No network, no live CRM, no PythonAnywhere access. Runs entirely against
fixtures/ua_cards_fixture.json which stands in for UA-0001..UA-0011.

Run with: python -m pytest cloud/task_084_ua0011_korea_reset/tests/test_gate_a_sandbox.py -q
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox_transform import apply_korea_bought_reset, diff_fields  # noqa: E402
from guards import (  # noqa: E402
    forbid_container_or_eta_when_kr_bought,
    require_media_mapping_before_catalog_write,
    reject_superseded_task_082_ferry_status,
    ua0009_publication_guard,
    GuardViolation,
)
from renderer_fix import render_card  # noqa: E402

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fixtures",
    "ua_cards_fixture.json",
)


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_ua0011_target_delta_matches_owner_directive():
    cards = load_fixture()
    before = cards["UA-0011"]
    after = apply_korea_bought_reset(before)

    assert after["status"] == "kr_bought"
    assert after["container_number"] == ""
    assert after["arrival_date"] == ""

    changed = diff_fields(before, after)
    assert set(changed.keys()) == {"status", "container_number", "arrival_date"}

    # Everything else, including media and VIN, is untouched.
    assert after["vin"] == before["vin"]
    assert after["media"] == before["media"]
    assert after["price"] == before["price"]


def test_ua0011_transform_is_idempotent_over_10_reruns():
    cards = load_fixture()
    base = cards["UA-0011"]
    results = []
    current = base
    for _ in range(10):
        current = apply_korea_bought_reset(current)
        results.append(current)

    # No drift after the first application: results 2..10 must be identical.
    for i in range(1, len(results)):
        assert results[i] == results[0], "Drift detected across repeated sandbox runs"

    # No duplicate distinct states beyond the single converged state.
    unique_states = {json.dumps(r, sort_keys=True) for r in results}
    assert len(unique_states) == 1


def test_guard_forbids_container_or_eta_when_kr_bought():
    with pytest_raises(GuardViolation):
        forbid_container_or_eta_when_kr_bought("kr_bought", "CONT-1", None)
    with pytest_raises(GuardViolation):
        forbid_container_or_eta_when_kr_bought("kr_bought", None, "2026-09-01")
    # Passes silently when both are empty.
    forbid_container_or_eta_when_kr_bought("kr_bought", "", "")
    forbid_container_or_eta_when_kr_bought("kr_bought", None, None)


def test_guard_rejects_superseded_task_082_ferry_status():
    with pytest_raises(GuardViolation):
        reject_superseded_task_082_ferry_status("on_ferry", "KMHE341DBKA544289")
    with pytest_raises(GuardViolation):
        reject_superseded_task_082_ferry_status("na_paromye", "KMHE341DBKA544289")
    # A legitimate non-ferry status does not raise.
    reject_superseded_task_082_ferry_status("kr_bought", "KMHE341DBKA544289")


def test_guard_blocks_catalog_write_without_media_mapping():
    with pytest_raises(GuardViolation):
        require_media_mapping_before_catalog_write([], "SOME-VIN")
    with pytest_raises(GuardViolation):
        require_media_mapping_before_catalog_write(
            [{"id": "x", "belongs_to_vin": "OTHER-VIN", "role": "cover"}], "SOME-VIN"
        )
    # Passes with correct own cover photo first.
    require_media_mapping_before_catalog_write(
        [{"id": "x", "belongs_to_vin": "SOME-VIN", "role": "cover"}], "SOME-VIN"
    )


def test_all_cards_ua0001_to_ua0011_render_full_template_never_fallback():
    cards = load_fixture()
    for name, card in cards.items():
        rendered = render_card(card)
        assert rendered["used_fallback_template"] is False
        assert rendered["template"] == "full_unified_template"
        # Structure must remain stable even when optional fields are absent.
        assert "info_block" in rendered
        assert "gallery" in rendered
        assert "cover_photo" in rendered


def test_ua0011_after_reset_renders_full_card_with_photo_first():
    cards = load_fixture()
    after = apply_korea_bought_reset(cards["UA-0011"])
    rendered = render_card(after)
    assert rendered["used_fallback_template"] is False
    assert rendered["stage_label"] == "\u0412 \u041a\u043e\u0440\u0435\u0435"
    assert rendered["cover_photo"]["belongs_to_vin"] == after["vin"]
    assert rendered["cover_photo"]["role"] == "cover"
    # container_number/arrival_date omitted from info_block because empty.
    assert "container_number" not in rendered["info_block"]
    assert "arrival_date" not in rendered["info_block"]


def test_ua0009_publication_guard_stays_blocked():
    cards = load_fixture()
    flag = cards["UA-0009"].get("safe_to_publish", "NO")
    ua0009_publication_guard(flag)  # must not raise, flag is 'NO'
    with pytest_raises(GuardViolation):
        ua0009_publication_guard("YES")


def test_10_full_sandbox_runs_all_cards_zero_duplicates_zero_drift():
    cards = load_fixture()
    snapshots = []
    for _ in range(10):
        run_result = {}
        for name, card in cards.items():
            if name == "UA-0011":
                transformed = apply_korea_bought_reset(card)
            else:
                transformed = dict(card)  # untouched cards must stay untouched
            run_result[name] = render_card(transformed)
        snapshots.append(json.dumps(run_result, sort_keys=True))

    unique_snapshots = set(snapshots)
    assert len(unique_snapshots) == 1, "Detected drift or non-determinism across 10 sandbox runs"
    assert len(snapshots) == 10


# --- minimal pytest.raises shim so this file also runs under plain unittest ---
try:
    from pytest import raises as pytest_raises  # type: ignore
except ImportError:  # pragma: no cover
    import contextlib

    @contextlib.contextmanager
    def pytest_raises(exc_type):
        try:
            yield
        except exc_type:
            return
        else:
            raise AssertionError(f"Expected {exc_type} to be raised")
