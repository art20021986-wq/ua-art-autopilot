from cloud.task_088_ge_price_crm_stage1.simulator import (
    apply_value,
    card_of,
    edit_menu_rows,
    edit_prompt,
    ensure_columns,
    open_db,
    read_back,
)


def test_edit_menu_shows_two_independent_price_fields_side_by_side():
    rows = edit_menu_rows()
    assert [("price_uah", "Цена Украины"), ("price_georgia", "Цена Грузии")] in rows


def test_ensure_columns_keeps_existing_price_uah_and_adds_price_georgia():
    conn = open_db()
    ensure_columns(conn)
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(cars)").fetchall()]
    assert "price_uah" in columns
    assert "price_georgia" in columns
    assert read_back(conn, "price_uah") == 14300
    assert read_back(conn, "price_georgia") is None
    conn.close()


def test_write_then_db_then_readback_for_georgia_price():
    conn = open_db()
    ensure_columns(conn)
    ok, _ = apply_value(conn, 1, "price_georgia", "16 500 $", actor_id=7)
    assert ok is True
    assert read_back(conn, "price_georgia") == 16500
    assert read_back(conn, "price_uah") == 14300
    audit = conn.execute(
        "SELECT old_value, new_value FROM audit WHERE field='price_georgia' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert tuple(audit) == (None, "16500")
    conn.close()


def test_prices_are_independent_in_both_directions():
    conn = open_db()
    ensure_columns(conn)
    apply_value(conn, 1, "price_georgia", "16100", actor_id=7)
    apply_value(conn, 1, "price_uah", "14900", actor_id=7)
    card = card_of(conn, 1)
    assert card["price_uah"] == 14900
    assert card["price_georgia"] == 16100
    conn.close()


def test_empty_georgia_price_is_allowed_to_remain_unset():
    conn = open_db()
    ensure_columns(conn)
    prompt = edit_prompt(conn, 1, "price_georgia")
    assert read_back(conn, "price_georgia") is None
    assert "Сейчас: —" in prompt
    assert "Поле необязательное" in prompt
    conn.close()
