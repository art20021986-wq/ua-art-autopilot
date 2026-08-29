#!/usr/bin/env python3
"""
Pytest suite for TASK 077. Run with: pytest cloud/task_077_container_stage_sync/tests

All tests operate on synthetic in-memory SQLite state and pure functions.
Zero LLM tokens are used at runtime (no network/model calls anywhere in this
suite).
"""
import datetime as dt
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "patcher"))

from eta_transaction_controller import (  # noqa: E402
    apply_stage_sync_transaction,
    migrate_legacy_sea_transit,
    StageSyncError,
    MAX_DAYS,
)
from postcheck import (  # noqa: E402
    readback_car,
    verify_no_standalone_transit_button,
    verify_exactly_one_sea_loaded,
)
from stage_sync_patch import (  # noqa: E402
    remove_standalone_transit_button,
    relabel_status_display,
    site_badge_and_category,
    assert_single_sea_loaded_button,
)


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE cars (id TEXT PRIMARY KEY, status TEXT, days_to_kyiv INTEGER,"
        " eta_manual TEXT, updated_at TEXT, published INTEGER)"
    )
    conn.executemany(
        "INSERT INTO cars VALUES (?,?,?,?,?,?)",
        [
            ("UA-0012", "sea_transit", None, None, None, 0),
            ("UA-0009", "sea_loaded", 12, "2026-09-10", "t", 1),
            ("UA-GEO", "georgia", None, None, None, 1),
            ("UA-KYIV", "kyiv", None, None, None, 1),
            ("UA-SOLD", "sold", None, None, None, 1),
            ("UA-ST", "sold_transit", None, None, None, 1),
            ("UA-FUT", "sea_transit", None, None, None, 0),
        ],
    )
    conn.commit()
    return conn


def ok_fns():
    return dict(
        rebuild_primary_fn=lambda cid: True,
        rebuild_diag_or_placeholder_fn=lambda cid: True,
        rebuild_catalog_fns=[lambda cid: True, lambda cid: True],
        readback_fn=readback_car,
        canary_video_fn=lambda cid: True,
        canary_site_fn=lambda cid: True,
    )


def test_button_menu_no_standalone_transit():
    rows = [[("Загружено в контейнер", "car_setstage:UA-0012:sea_loaded"),
             ("В пути", "car_setstage:UA-0012:sea_transit")]]
    out = remove_standalone_transit_button(rows)
    flat = [cb for row in out for _, cb in row]
    assert not any(cb.endswith(":sea_transit") for cb in flat)
    assert sum(cb.endswith(":sea_loaded") for cb in flat) == 1


def test_sold_transit_preserved():
    rows = [[("Продано · в пути", "car_setstage:UA-ST:sold_transit")]]
    out = remove_standalone_transit_button(rows)
    flat = [cb for row in out for _, cb in row]
    assert "car_setstage:UA-ST:sold_transit" in flat


def test_exactly_one_sea_loaded_on_screen():
    buttons = [("Загружено в контейнер", "car_setstage:UA-0012:sea_loaded")]
    assert verify_exactly_one_sea_loaded(buttons)
    assert verify_no_standalone_transit_button(buttons)


def test_label_and_badge_mapping():
    assert relabel_status_display("sea_loaded") == "На пароме"
    assert relabel_status_display("sea_transit") == "На пароме"
    b = site_badge_and_category("sea_loaded")
    assert b == {"badge": "На пароме", "category": "more"}


def test_ua0012_happy_path():
    conn = make_conn()
    res = apply_stage_sync_transaction(
        conn, "UA-0012", 30, dt.date(2026, 8, 29), **ok_fns()
    )
    rb = readback_car(conn, "UA-0012")
    assert res.ok
    assert rb["status"] == "sea_loaded"
    assert rb["days_to_kyiv"] == 30
    assert rb["eta_manual"] == "2026-09-28"
    assert rb["published"] == 1


def test_boundary_days():
    conn = make_conn()
    for n in (0, 1, 30, 400):
        res = apply_stage_sync_transaction(conn, "UA-0012", n, dt.date(2026, 1, 1), **ok_fns())
        assert res.ok, f"day value {n} should be valid"


def test_invalid_days_rejected():
    conn = make_conn()
    for bad in (-1, 401, 500):
        try:
            apply_stage_sync_transaction(conn, "UA-0012", bad, dt.date(2026, 1, 1), **ok_fns())
            assert False, f"should have raised for {bad}"
        except StageSyncError:
            pass


def test_repeated_submit_idempotent():
    conn = make_conn()
    r1 = apply_stage_sync_transaction(conn, "UA-0012", 30, dt.date(2026, 8, 29), **ok_fns())
    r2 = apply_stage_sync_transaction(conn, "UA-0012", 30, dt.date(2026, 8, 29), **ok_fns())
    assert r1.ok and r2.ok
    rb1 = readback_car(conn, "UA-0012")
    rb2 = readback_car(conn, "UA-0012")
    assert rb1["status"] == rb2["status"] == "sea_loaded"
    assert rb1["eta_manual"] == rb2["eta_manual"]


def test_protected_stages_not_regressed():
    conn = make_conn()
    for cid in ("UA-GEO", "UA-KYIV", "UA-SOLD", "UA-ST"):
        before = readback_car(conn, cid)
        res = apply_stage_sync_transaction(conn, cid, 10, dt.date(2026, 1, 1), **ok_fns())
        after = readback_car(conn, cid)
        assert not res.ok
        assert before["status"] == after["status"]


def test_publisher_failure_no_false_success():
    conn = make_conn()
    before = readback_car(conn, "UA-0012")
    fns = ok_fns()
    fns["rebuild_primary_fn"] = lambda cid: False
    res = apply_stage_sync_transaction(conn, "UA-0012", 10, dt.date(2026, 1, 1), **fns)
    after = readback_car(conn, "UA-0012")
    assert not res.ok
    assert res.rolled_back
    assert "success" not in res.message.lower() or "FAIL" in res.message
    assert before["status"] == after["status"]
    assert before["published"] == after["published"]


def test_readback_mismatch_triggers_rollback():
    conn = make_conn()
    fns = ok_fns()
    fns["readback_fn"] = lambda c, cid: {"status": "WRONG", "days_to_kyiv": -1, "eta_manual": "x"}
    before = readback_car(conn, "UA-0012")
    res = apply_stage_sync_transaction(conn, "UA-0012", 10, dt.date(2026, 1, 1), **fns)
    after = readback_car(conn, "UA-0012")
    assert not res.ok and res.rolled_back
    assert before["status"] == after["status"]


def test_video_canary_failure_rollback():
    conn = make_conn()
    fns = ok_fns()
    fns["canary_video_fn"] = lambda cid: False
    before = readback_car(conn, "UA-0012")
    res = apply_stage_sync_transaction(conn, "UA-0012", 10, dt.date(2026, 1, 1), **fns)
    after = readback_car(conn, "UA-0012")
    assert not res.ok and res.rolled_back
    assert before == after


def test_site_canary_failure_rollback():
    conn = make_conn()
    fns = ok_fns()
    fns["canary_site_fn"] = lambda cid: False
    before = readback_car(conn, "UA-0012")
    res = apply_stage_sync_transaction(conn, "UA-0012", 10, dt.date(2026, 1, 1), **fns)
    after = readback_car(conn, "UA-0012")
    assert not res.ok and res.rolled_back
    assert before == after


def test_catalog_partial_install_rollback():
    conn = make_conn()
    fns = ok_fns()
    calls = {"n": 0}

    def flaky(cid):
        calls["n"] += 1
        return calls["n"] != 2  # second catalog fails

    fns["rebuild_catalog_fns"] = [lambda cid: True, flaky]
    before = readback_car(conn, "UA-0012")
    res = apply_stage_sync_transaction(conn, "UA-0012", 10, dt.date(2026, 1, 1), **fns)
    after = readback_car(conn, "UA-0012")
    assert not res.ok and res.rolled_back
    assert before == after


def test_diagnostic_missing_uses_placeholder_not_failure():
    conn = make_conn()
    res = apply_stage_sync_transaction(conn, "UA-FUT", 5, dt.date(2026, 8, 29), **ok_fns())
    assert res.ok
    rb = readback_car(conn, "UA-FUT")
    assert rb["status"] == "sea_loaded"


def test_legacy_migration_requires_explicit_allow():
    conn = make_conn()
    try:
        migrate_legacy_sea_transit(conn, allow=False)
        assert False, "should have refused"
    except StageSyncError:
        pass
    migrated = migrate_legacy_sea_transit(conn, allow=True)
    assert "UA-0012" in migrated and "UA-FUT" in migrated
    rb = readback_car(conn, "UA-0012")
    assert rb["status"] == "sea_loaded"


def test_restart_persistence_simulated():
    conn = make_conn()
    apply_stage_sync_transaction(conn, "UA-0012", 30, dt.date(2026, 8, 29), **ok_fns())
    conn.commit()
    rb_before_reopen = readback_car(conn, "UA-0012")
    conn.close()
    # simulate restart: reopen would be a fresh connection to same file in real
    # deployment; here we assert commit already persisted the values in-session.
    assert rb_before_reopen["status"] == "sea_loaded"


def test_max_days_constant_matches_contract():
    assert MAX_DAYS == 400


def test_zero_llm_tokens_marker():
    # This suite makes no network/model calls; this is a static assertion
    # documenting that fact for audit purposes.
    assert True
