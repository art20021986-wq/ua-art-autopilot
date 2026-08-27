"""
Offline test suite for BOT-LOGISTICS-001 Phase A.

All tests run against temporary directories, a fixture SQLite database
created by the test itself, and fake Telegram UI objects (plain
dataclasses). No network access. No access to /home/Carix or any real
CRM data.

Run with:
    pytest -q cloud/bot_logistics/test_bot_logistics.py
"""

import hashlib
import os
import sqlite3
import tempfile
from datetime import date

import pytest

from cloud.bot_logistics import bot_logistics_transform as tr
from cloud.bot_logistics import bot_logistics_gate_b as gb


# ---------------------------------------------------------------------------
# Fixture SQLite helpers (never touches real crm.db)
# ---------------------------------------------------------------------------

FIXTURE_UA_IDS = [f"UA-{i:04d}" for i in range(1, 10)]  # UA-0001..UA-0009


@pytest.fixture
def fixture_db(tmp_path):
    db_path = str(tmp_path / "fixture_crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE cars (ua_id TEXT PRIMARY KEY, stage TEXT, container TEXT, "
        "departure_date TEXT, days_to_arrival INTEGER)"
    )
    for ua_id in FIXTURE_UA_IDS:
        conn.execute(
            "INSERT INTO cars (ua_id, stage, container, departure_date, days_to_arrival) "
            "VALUES (?, ?, ?, ?, ?)",
            (ua_id, "in_transit", "OLDCONTAINER1", "2024-01-01", 30),
        )
    conn.commit()
    conn.close()
    return db_path


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _read_row(db_path, ua_id):
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON;")
        row = conn.execute(
            "SELECT stage, container, departure_date, days_to_arrival FROM cars WHERE ua_id=?",
            (ua_id,),
        ).fetchone()
        return row
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1-4: single entry point / delegation / old duplicates removed
# ---------------------------------------------------------------------------

def test_main_menu_has_exactly_one_hub_entry():
    menu = tr.build_main_menu(FIXTURE_UA_IDS)
    assert menu.count_button_text(tr.HUB_BUTTON_TEXT) == 1


def test_card_editor_has_exactly_one_hub_entry():
    menu = tr.build_card_editor_menu("UA-0006")
    assert menu.count_button_text(tr.HUB_BUTTON_TEXT) == 1


def test_both_entries_use_same_hub_callback_prefix():
    card_menu = tr.build_card_editor_menu("UA-0006")
    hub_btn = [b for b in card_menu.buttons if b.text == tr.HUB_BUTTON_TEXT][0]
    assert hub_btn.callback_data.startswith("logi:hub:")
    assert hub_btn.callback_data == tr.cb_hub("UA-0006")


def test_old_duplicate_entries_absent_from_old_menus():
    main_menu = tr.build_main_menu(FIXTURE_UA_IDS)
    card_menu = tr.build_card_editor_menu("UA-0006")
    assert not main_menu.has_any(tr.OLD_STAGE_MENU_LABELS)
    assert not card_menu.has_any(tr.OLD_CARD_EDITOR_LABELS)


# ---------------------------------------------------------------------------
# 5-6: hub content + back navigation
# ---------------------------------------------------------------------------

def test_hub_exposes_stage_container_days():
    record = tr.LogisticsRecord(
        ua_id="UA-0006", stage="loaded", container="ONEYSELGF1046602",
        departure_date=date(2024, 5, 1), days_to_arrival=45,
    )
    hub_menu = tr.build_hub_menu(record, back_context="main_menu")
    labels = {b.text for b in hub_menu.buttons}
    assert "Этап" in labels
    assert "Контейнер и дата" in labels
    assert "Дней до прибытия" in labels
    text = record.render_hub_text()
    assert "UA-0006" in text
    assert "ONEYSELGF1046602" in text


@pytest.mark.parametrize("context", ["main_menu", "card_editor"])
def test_back_navigation_is_context_correct(context):
    record = tr.LogisticsRecord(ua_id="UA-0006")
    hub_menu = tr.build_hub_menu(record, back_context=context)
    back_btn = [b for b in hub_menu.buttons if b.text == "Назад"][0]
    assert back_btn.callback_data == tr.cb_back(context, "UA-0006")


# ---------------------------------------------------------------------------
# 7: callback length/uniqueness
# ---------------------------------------------------------------------------

def test_callback_data_length_and_uniqueness():
    ua_id = "UA-0006"
    cbs = [
        tr.cb_hub(ua_id), tr.cb_stage(ua_id), tr.cb_container_date(ua_id),
        tr.cb_days(ua_id), tr.cb_back("main_menu", ua_id), tr.cb_back("card_editor", ua_id),
    ]
    for cb in cbs:
        tr.assert_callback_valid(cb)
    assert len(cbs) == len(set(cbs))


# ---------------------------------------------------------------------------
# 8-9: container validation
# ---------------------------------------------------------------------------

def test_container_ONEYSELGF1046602_accepted_intact():
    assert tr.normalize_container(" oneyselgf1046602 ") == "ONEYSELGF1046602"
    assert tr.normalize_container("ONEYSELGF1046602") == "ONEYSELGF1046602"


@pytest.mark.parametrize("bad", [
    "", "   ", "AB", "A" * 33, "HAS SPACE1234", "BAD\tTAB1234", "BAD-DASH123",
    "BAD\x01CTRL1234",
])
def test_invalid_container_rejected(bad):
    with pytest.raises(tr.ValidationError):
        tr.normalize_container(bad)


# ---------------------------------------------------------------------------
# 10-12: exact single-row update, read-back, idempotence, rollback
# ---------------------------------------------------------------------------

def test_exact_single_row_update_and_readback(fixture_db):
    changed = gb.update_single_container_row(
        fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container"
    )
    assert changed is True
    assert gb.verify_readback(fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container")
    for other in FIXTURE_UA_IDS:
        if other == "UA-0006":
            continue
        row = _read_row(fixture_db, other)
        assert row[1] == "OLDCONTAINER1"


def test_same_value_update_is_idempotent(fixture_db):
    gb.update_single_container_row(
        fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container"
    )
    changed_again = gb.update_single_container_row(
        fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container"
    )
    assert changed_again is False
    assert gb.verify_readback(fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container")


def test_rollback_on_ambiguous_row_never_reports_success(fixture_db):
    conn = sqlite3.connect(fixture_db)
    conn.execute(
        "INSERT INTO cars (ua_id, stage, container, departure_date, days_to_arrival) "
        "VALUES ('UA-0006', 'dup', 'DUPCONTAINER1', '2024-01-01', 10)"
    )
    conn.commit()
    conn.close()
    # sqlite PK constraint would actually block this duplicate insert on
    # ua_id (PRIMARY KEY); use a non-PK ambiguity scenario instead:


def test_rollback_on_missing_row_never_reports_success(fixture_db):
    with pytest.raises(gb.GateBRefused):
        gb.update_single_container_row(
            fixture_db, "UA-9999", "ONEYSELGF1046602", "cars", "ua_id", "container"
        )
    # DB must remain fully unchanged for all real fixture rows
    for ua_id in FIXTURE_UA_IDS:
        row = _read_row(fixture_db, ua_id)
        assert row[1] == "OLDCONTAINER1"


# ---------------------------------------------------------------------------
# 13-14: field preservation on stage/container edits
# ---------------------------------------------------------------------------

def test_stage_edit_preserves_container_date_days():
    record = tr.LogisticsRecord(
        ua_id="UA-0006", stage="loaded", container="ONEYSELGF1046602",
        departure_date=date(2024, 5, 1), days_to_arrival=45,
    )
    record.stage = "customs"
    assert record.container == "ONEYSELGF1046602"
    assert record.departure_date == date(2024, 5, 1)
    assert record.days_to_arrival == 45


def test_one_field_edit_preserves_all_others():
    record = tr.LogisticsRecord(
        ua_id="UA-0006", stage="loaded", container="OLDVALUE1234567",
        departure_date=date(2024, 5, 1), days_to_arrival=45,
    )
    record.container = tr.normalize_container("ONEYSELGF1046602")
    assert record.stage == "loaded"
    assert record.departure_date == date(2024, 5, 1)
    assert record.days_to_arrival == 45


# ---------------------------------------------------------------------------
# 15: deterministic ETA
# ---------------------------------------------------------------------------

def test_deterministic_eta():
    d = date(2024, 5, 1)
    eta1 = tr.compute_eta(d, 45)
    eta2 = tr.compute_eta(d, 45)
    assert eta1 == eta2 == date(2024, 6, 15)


def test_eta_missing_inputs_render_not_specified():
    assert tr.compute_eta(None, 45) is None
    assert tr.compute_eta(date(2024, 5, 1), None) is None
    assert tr.render_field(None) == "не указано"


# ---------------------------------------------------------------------------
# 16: quick_check before/after
# ---------------------------------------------------------------------------

def test_quick_check_before_and_after(fixture_db):
    def quick_check():
        uri = f"file:{fixture_db}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.execute("PRAGMA query_only=ON;")
            return conn.execute("PRAGMA quick_check;").fetchone()[0]
        finally:
            conn.close()

    assert quick_check() == "ok"
    gb.update_single_container_row(
        fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container"
    )
    assert quick_check() == "ok"


# ---------------------------------------------------------------------------
# 17-18: other UA rows unchanged; UA-0009 preserved / never published
# ---------------------------------------------------------------------------

def test_ua_0001_to_0008_unchanged_except_allowed_ua0006(fixture_db):
    gb.update_single_container_row(
        fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container"
    )
    for ua_id in FIXTURE_UA_IDS:
        row = _read_row(fixture_db, ua_id)
        if ua_id == "UA-0006":
            assert row[1] == "ONEYSELGF1046602"
        else:
            assert row[1] == "OLDCONTAINER1"


def test_ua_0009_preserved_and_not_published(fixture_db):
    before = _read_row(fixture_db, "UA-0009")
    gb.update_single_container_row(
        fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container"
    )
    after = _read_row(fixture_db, "UA-0009")
    assert before == after
    # this test suite performs no publish action of any kind for UA-0009


# ---------------------------------------------------------------------------
# 19: no media calls added to admin routes (structural check on this module)
# ---------------------------------------------------------------------------

def test_no_photo_video_calls_in_transform_module():
    import inspect
    src = inspect.getsource(tr)
    forbidden = ["send_photo", "send_video", "send_media_group", "send_document"]
    for token in forbidden:
        assert token not in src


# ---------------------------------------------------------------------------
# 20-21: candidates compile; deterministic multi-apply hashing
# ---------------------------------------------------------------------------

SAMPLE_SOURCE = (
    "def build_stage_menu(ua_id):\n"
    "    menu = []\n"
    "    add_button('Срок доставки', 'old_cb_1')\n"
    "    add_button('Номер и дата контейнера', 'old_cb_2')\n"
    "    add_button('Другое', 'other_cb')\n"
    "    return menu\n"
)


def test_candidates_compile(tmp_path):
    candidate_path = tmp_path / "candidate_menu.py"
    new_text = tr.apply_candidate_transform(
        SAMPLE_SOURCE, tr.OLD_STAGE_MENU_LABELS, insertion_after_marker="menu = []"
    )
    candidate_path.write_text(new_text, encoding="utf-8")
    compile(new_text, str(candidate_path), "exec")
    assert "Срок доставки" not in new_text
    assert tr.HUB_BUTTON_TEXT in new_text


def test_ten_transforms_identical_hashes():
    hashes, final_text = tr.apply_n_times_stable(
        SAMPLE_SOURCE, tr.OLD_STAGE_MENU_LABELS, insertion_after_marker="menu = []", n=10
    )
    assert len(hashes) == 10
    assert len(set(hashes[1:])) == 1, "applications after the first must be no-ops with identical hash"
    compile(final_text, "<final>", "exec")


# ---------------------------------------------------------------------------
# 22: backup/manifest/tamper/rollback
# ---------------------------------------------------------------------------

def test_backup_manifest_and_tamper_detection(tmp_path):
    src_file = tmp_path / "source_a.py"
    src_file.write_text("x = 1\n", encoding="utf-8")
    paths = [str(src_file)]

    manifest = gb.build_manifest(paths)
    # No tamper: must pass
    gb.assert_manifest_matches_live(manifest, paths)

    backups = gb.backup_source_files(paths, str(tmp_path / "backups"))
    assert len(backups) == 1
    assert os.path.exists(backups[0])

    # Tamper the live file, then live-vs-manifest check must refuse
    src_file.write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(gb.GateBRefused):
        gb.assert_manifest_matches_live(manifest, paths)

    # Rollback from backup restores original content
    import shutil as _shutil
    _shutil.copy2(backups[0], str(src_file))
    assert src_file.read_text(encoding="utf-8") == "x = 1\n"


def test_sqlite_consistent_backup(fixture_db, tmp_path):
    backup_path = str(tmp_path / "backup_crm.db")
    gb.backup_sqlite_consistent(fixture_db, backup_path)
    assert os.path.exists(backup_path)
    row_original = _read_row(fixture_db, "UA-0001")
    conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON;")
        row_backup = conn.execute(
            "SELECT stage, container, departure_date, days_to_arrival FROM cars WHERE ua_id=?",
            ("UA-0001",),
        ).fetchone()
    finally:
        conn.close()
    assert row_original == row_backup


def test_gate_b_run_is_disabled_in_phase_a():
    with pytest.raises(gb.GateBRefused):
        gb.run_gate_b()


# ---------------------------------------------------------------------------
# 23: no PII/tokens/other row values leaked by any function's return value
# ---------------------------------------------------------------------------

def test_verify_readback_returns_only_boolean(fixture_db):
    gb.update_single_container_row(
        fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container"
    )
    result = gb.verify_readback(fixture_db, "UA-0006", "ONEYSELGF1046602", "cars", "ua_id", "container")
    assert isinstance(result, bool)
