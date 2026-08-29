"""
Sandbox tests for eta_release_candidate.py (TASK 079).

These tests run only against temporary SQLite files and temporary
directories. They never touch any production path. This test file is
provided for independent execution (e.g. by the Codex controller, matching
the TASK 015/021 acceptance pattern). Results claimed in
release_candidate_report.md are only valid once this suite has actually been
executed and its real output captured.
"""

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "patcher"))

import eta_release_candidate as erc  # noqa: E402


@pytest.fixture()
def db_path(tmp_path):
    p = str(tmp_path / "sandbox.db")
    conn = sqlite3.connect(p)
    erc.init_sandbox_db(conn)
    conn.close()
    return p


def _insert_car(conn, id_, vin, status, days=None, eta=None, published=0,
                 description="desc", price="1000"):
    conn.execute(
        "INSERT INTO cars (id, vin, status, days_to_kyiv, eta_manual, published, "
        "description, price, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (id_, vin, status, days, eta, published, description, price, "2026-01-01T00:00:00"),
    )
    conn.commit()


def _fresh_conn(db_path):
    c = sqlite3.connect(db_path)
    c.isolation_level = None
    return c


# --- N-range validation -----------------------------------------------------

@pytest.mark.parametrize("n", [0, 1, 30, 400])
def test_valid_n_values(db_path, n):
    conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "ge_waiting")
    result = erc.write_eta_transaction(conn, 1, n, "tester")
    assert result.n_days == n
    conn.close()


@pytest.mark.parametrize("n", [-1, 401, 3.5])
def test_invalid_n_values(db_path, n):
    conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "ge_waiting")
    with pytest.raises(erc.ValidationError):
        erc.write_eta_transaction(conn, 1, n, "tester")
    conn.close()


def test_non_integer_car_id_rejected(db_path):
    conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "ge_waiting")
    with pytest.raises(erc.ValidationError):
        erc.write_eta_transaction(conn, "1", 10, "tester")
    conn.close()


# --- idempotence -------------------------------------------------------------

def test_idempotent_repeated_write(db_path):
    conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "ge_waiting")
    r1 = erc.write_eta_transaction(conn, 1, 30, "tester")
    r2 = erc.write_eta_transaction(conn, 1, 30, "tester")
    assert r1.eta == r2.eta
    row = erc.read_car_row(conn, 1)
    assert row.days_to_kyiv == 30
    conn.close()


# --- protected statuses & ferry normalization -------------------------------

@pytest.mark.parametrize("status", ["ge_waiting", "ge_to_kyiv", "ua_arrived", "sold_new"])
def test_protected_statuses_not_normalized(db_path, status):
    conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", status)
    result = erc.write_eta_transaction(conn, 1, 30, "tester", allow_ferry_normalization=True)
    assert result.status_after == status
    conn.close()


@pytest.mark.parametrize("status", sorted(erc.ALLOWED_FERRY_NORMALIZATION_SOURCES))
def test_allowed_ferry_normalization(db_path, status):
    conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", status)
    result = erc.write_eta_transaction(conn, 1, 30, "tester", allow_ferry_normalization=True)
    assert result.status_after == erc.FERRY_STATUS
    conn.close()


def test_legacy_status_rejected(db_path):
    conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "v_puti")
    with pytest.raises(erc.ValidationError):
        erc.write_eta_transaction(conn, 1, 30, "tester")
    conn.close()


# --- commit-before-publish proof --------------------------------------------

def test_commit_happens_before_publisher(db_path, tmp_path):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "sea_loaded")
    staging_dir = str(tmp_path / "stage")

    seen_row_during_publish = {}

    def spy_publisher(files):
        row = erc.read_car_row(ro_conn, 1)
        seen_row_during_publish["days"] = row.days_to_kyiv
        return erc.default_publisher(files)

    result = erc.apply_eta_change(
        conn, ro_conn, staging_dir, 1, 30, "tester", publisher=spy_publisher
    )
    assert result.success
    assert seen_row_during_publish["days"] == 30
    conn.close()
    ro_conn.close()


# --- preimage published preservation ----------------------------------------

@pytest.mark.parametrize("pub", [0, 1])
def test_published_preimage_preserved_on_success(db_path, tmp_path, pub):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "sea_loaded", published=pub)
    staging_dir = str(tmp_path / "stage")
    result = erc.apply_eta_change(conn, ro_conn, staging_dir, 1, 30, "tester")
    assert result.success
    row = erc.read_car_row(conn, 1)
    assert row.published == pub
    conn.close()
    ro_conn.close()


# --- injected failures & rollback -------------------------------------------

def test_injected_publisher_failure_rolls_back(db_path, tmp_path):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "sea_loaded", days=5, eta="2026-01-06", published=1)
    staging_dir = str(tmp_path / "stage")

    def failing_publisher(files):
        return False

    result = erc.apply_eta_change(
        conn, ro_conn, staging_dir, 1, 30, "tester", publisher=failing_publisher
    )
    assert not result.success
    assert result.rolled_back
    row = erc.read_car_row(conn, 1)
    assert row.days_to_kyiv == 5
    assert row.eta_manual == "2026-01-06"
    assert row.published == 1
    conn.close()
    ro_conn.close()


def test_injected_readback_failure_rolls_back(db_path, tmp_path):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "sea_loaded", days=5, eta="2026-01-06")
    staging_dir = str(tmp_path / "stage")
    result = erc.apply_eta_change(
        conn, ro_conn, staging_dir, 1, 30, "tester", inject_readback_failure=True
    )
    assert not result.success
    assert result.rolled_back
    row = erc.read_car_row(conn, 1)
    assert row.days_to_kyiv == 5
    conn.close()
    ro_conn.close()


def test_injected_partial_install_failure_rolls_back(db_path, tmp_path):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "sea_loaded", days=5, eta="2026-01-06")
    staging_dir = str(tmp_path / "stage")
    result = erc.apply_eta_change(
        conn, ro_conn, staging_dir, 1, 30, "tester", inject_install_partial_failure=True
    )
    assert not result.success
    assert result.rolled_back
    row = erc.read_car_row(conn, 1)
    assert row.days_to_kyiv == 5
    conn.close()
    ro_conn.close()


def test_delayed_overwrite_detected_by_publisher_and_rolled_back(db_path, tmp_path):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "sea_loaded", days=5, eta="2026-01-06")
    staging_dir = str(tmp_path / "stage")

    def overwrite():
        card_path = os.path.join(staging_dir, "card_UA-TEST.html")
        os.makedirs(os.path.dirname(card_path), exist_ok=True)
        with open(card_path, "wb") as f:
            f.write(b"CORRUPTED")

    result = erc.apply_eta_change(
        conn,
        ro_conn,
        staging_dir,
        1,
        30,
        "tester",
        inject_delayed_overwrite=overwrite,
    )
    assert not result.success
    assert result.rolled_back
    conn.close()
    ro_conn.close()


# --- exact file/DB restoration -----------------------------------------------

def test_exact_file_byte_restoration(db_path, tmp_path):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "sea_loaded", days=5, eta="2026-01-06")
    staging_dir = str(tmp_path / "stage")
    card_path = os.path.join(staging_dir, "card_UA-TEST.html")
    os.makedirs(staging_dir, exist_ok=True)
    with open(card_path, "wb") as f:
        f.write(b"ORIGINAL BYTES")

    def failing_publisher(files):
        return False

    erc.apply_eta_change(conn, ro_conn, staging_dir, 1, 30, "tester", publisher=failing_publisher)
    with open(card_path, "rb") as f:
        assert f.read() == b"ORIGINAL BYTES"
    conn.close()
    ro_conn.close()


# --- multi-car acceptance scenarios -----------------------------------------

def test_ua0009_0010_0011_target_state(db_path, tmp_path):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(conn, 9, "UA-0009", "sea_loaded", days=13, eta="2026-09-28")
    _insert_car(conn, 10, "UA-0010", "sea_loaded", days=None, eta="2026-09-28")
    _insert_car(conn, 11, "UA-0011", "sea_loaded", days=None, eta="2026-09-28")
    staging_dir = str(tmp_path / "stage")

    for cid in (9, 10, 11):
        result = erc.apply_eta_change(conn, ro_conn, staging_dir, cid, 30, "tester")
        assert result.success
        row = erc.read_car_row(conn, cid)
        assert row.days_to_kyiv == 30
        assert row.eta_manual == "2026-09-28" or row.eta_manual is not None
        assert row.status == "sea_loaded"
    conn.close()
    ro_conn.close()


def test_ua0012_with_diagnostic_placeholder(db_path, tmp_path):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(conn, 12, "UA-0012", "korea_port")
    staging_dir = str(tmp_path / "stage")
    result = erc.apply_eta_change(
        conn,
        ro_conn,
        staging_dir,
        12,
        30,
        "tester",
        allow_ferry_normalization=True,
        include_diagnostic=False,
    )
    assert result.success
    row = erc.read_car_row(conn, 12)
    assert row.status == "sea_loaded"
    diag_path = os.path.join(staging_dir, "diag_UA-0012.html")
    with open(diag_path, "rb") as f:
        assert b"PLACEHOLDER" in f.read()
    conn.close()
    ro_conn.close()


# --- preservation of unrelated fields ----------------------------------------

def test_unrelated_fields_untouched(db_path, tmp_path):
    conn = _fresh_conn(db_path)
    ro_conn = _fresh_conn(db_path)
    _insert_car(
        conn, 1, "UA-TEST", "sea_loaded", description="VIN123 price stays", price="5000"
    )
    staging_dir = str(tmp_path / "stage")
    erc.apply_eta_change(conn, ro_conn, staging_dir, 1, 30, "tester")
    row = erc.read_car_row(conn, 1)
    assert row.description == "VIN123 price stays"
    assert row.price == "5000"
    conn.close()
    ro_conn.close()


# --- toggle_publish ----------------------------------------------------------

def test_toggle_publish_success_message_only_after_pass(db_path):
    conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "sea_loaded", published=0)

    def ok_publisher(files):
        return True

    result = erc.toggle_publish(conn, 1, 1, "tester", ok_publisher, [])
    assert result.success
    assert "\u043c\u0430\u0448\u0438\u043d\u0430" in result.message.lower()
    conn.close()


def test_toggle_publish_failure_restores_preimage(db_path):
    conn = _fresh_conn(db_path)
    _insert_car(conn, 1, "UA-TEST", "sea_loaded", published=0)

    def bad_publisher(files):
        return False

    result = erc.toggle_publish(conn, 1, 1, "tester", bad_publisher, [])
    assert not result.success
    row = erc.read_car_row(conn, 1)
    assert row.published == 0
    conn.close()


# --- stale-date sanitization --------------------------------------------------

def test_stale_arrival_sentence_removed():
    text = (
        "\u041c\u0430\u0448\u0438\u043d\u0430 \u0432 \u0433\u0430\u0440\u0430\u0436\u0456. "
        "\u041a\u043b\u0456\u0454\u043d\u0442 \u043e\u0442\u0440\u0438\u043c\u0430\u0454 \u0430\u0432\u0442\u043e "
        "\u0441\u0430\u043c\u043e\u0441\u0442\u0456\u0439\u043d\u043e \u043f\u0440\u0438\u0431\u0443\u0442\u0442\u044f "
        "9 \u0432\u0435\u0440\u0435\u0441\u043d\u044f 2026. "
        "\u0421\u0435\u0440\u0432\u0456\u0441\u043d\u0430 \u0437\u0430\u043c\u0456\u043d\u0430 \u043c\u0430\u0441\u043b\u0430 "
        "\u0431\u0443\u043b\u0430 15 \u0441\u0456\u0447\u043d\u044f 2026."
    )
    result = erc.sanitize_stale_arrival_sentence(text)
    assert "\u0432\u0435\u0440\u0435\u0441\u043d\u044f" not in result
    assert "\u0441\u0456\u0447\u043d\u044f 2026" in result
    assert "\u0433\u0430\u0440\u0430\u0436\u0456" in result


def test_unrelated_dates_preserved():
    text = (
        "\u0410\u0432\u0442\u043e \u043a\u0443\u043f\u043b\u0435\u043d\u043e \u043d\u0430 \u0430\u0443\u043a\u0446\u0456\u043e\u043d\u0456 "
        "3 \u0441\u0456\u0447\u043d\u044f 2026. \u0420\u0435\u0454\u0441\u0442\u0440\u0430\u0446\u0456\u044e \u043f\u043b\u0430\u043d\u0443\u0454\u0442\u044c\u0441\u044f "
        "\u043d\u0430 12 \u0433\u0440\u0443\u0434\u043d\u044f 2026."
    )
    result = erc.sanitize_stale_arrival_sentence(text)
    assert "\u0430\u0443\u043a\u0446\u0456\u043e\u043d\u0456" in result
    assert "\u0440\u0435\u0454\u0441\u0442\u0440\u0430\u0446\u0456\u044e" in result


# --- deterministic anchor refusal --------------------------------------------

def test_anchor_mismatch_raises(tmp_path):
    fake = tmp_path / "db.py"
    fake.write_text("# not the real file")
    with pytest.raises(erc.AnchorMismatchError):
        erc.verify_full_file_anchor(str(fake), "db.py")


def test_unregistered_anchor_key_raises(tmp_path):
    fake = tmp_path / "x.py"
    fake.write_text("x=1")
    with pytest.raises(erc.AnchorMismatchError):
        erc.verify_full_file_anchor(str(fake), "unknown.py")
