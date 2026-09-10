from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone

LABELS_ALL = {
    "brand": "марка",
    "model": "модель",
    "year": "год",
    "vin": "VIN",
    "fuel": "топливо",
    "engine_cc": "объём",
    "gearbox": "КПП",
    "drive": "привод",
    "mileage_km": "пробег",
    "color": "цвет",
    "condition_text": "тех. состояние",
    "price_uah": "цена Украины",
    "price_georgia": "цена Грузии",
    "sea_container": "контейнер",
    "diag_link": "ссылка на отчёт",
    "eta_days": "срок доставки",
    "auto_number": "номер авто",
    "diag_text": "описание диагностики",
}

EDITABLE = [
    ("auto_number", "Номер авто"),
    ("brand", "Марка"),
    ("model", "Модель"),
    ("year", "Год выпуска"),
    ("vin", "VIN"),
    ("fuel", "Топливо"),
    ("engine_cc", "Объём, см³"),
    ("gearbox", "КПП"),
    ("drive", "Привод"),
    ("mileage_km", "Пробег"),
    ("color", "Цвет"),
    ("condition_text", "Описание"),
    ("price_uah", "Цена Украины"),
    ("price_georgia", "Цена Грузии"),
]

NUMERIC = {"engine_cc", "mileage_km", "price_uah", "price_georgia"}

LEGACY_SCHEMA = """
CREATE TABLE cars (
    id INTEGER PRIMARY KEY,
    auto_number TEXT UNIQUE,
    brand TEXT,
    model TEXT,
    year TEXT,
    vin TEXT,
    fuel TEXT,
    engine_cc INTEGER,
    gearbox TEXT,
    drive TEXT,
    mileage_km INTEGER,
    color TEXT,
    condition_text TEXT,
    price_uah INTEGER,
    sea_container TEXT,
    diag_link TEXT,
    price_history TEXT DEFAULT '{}',
    status TEXT,
    updated_at TEXT
);
CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    field TEXT,
    old_value TEXT,
    new_value TEXT,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        """
        INSERT INTO cars(
            id, auto_number, brand, model, year, vin, fuel, engine_cc, gearbox, drive,
            mileage_km, color, condition_text, price_uah, sea_container, diag_link,
            price_history, status, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            1,
            "UA-0001",
            "Hyundai",
            "Sonata",
            "2021",
            "KMHL14JA1MA123456",
            "Бензин",
            2497,
            "AT",
            "FWD",
            54000,
            "Серый",
            "Без замечаний",
            14300,
            "MSCU1234567",
            "https://example.invalid/report",
            "{}",
            "georgia",
            now(),
        ),
    )
    conn.commit()
    return conn


def ensure_columns(conn: sqlite3.Connection) -> None:
    have = {row["name"] for row in conn.execute("PRAGMA table_info(cars)").fetchall()}
    for name, decl in (
        ("price_history", "TEXT"),
        ("cover_photo", "TEXT"),
        ("eta_manual", "TEXT"),
        ("price_georgia", "INTEGER"),
    ):
        if name not in have:
            conn.execute(f"ALTER TABLE cars ADD COLUMN {name} {decl}")
    conn.commit()


def card_of(conn: sqlite3.Connection, card_id: int) -> dict:
    row = conn.execute("SELECT * FROM cars WHERE id=?", (card_id,)).fetchone()
    return dict(row) if row else {}


def edit_menu_rows() -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    buf: list[tuple[str, str]] = []
    for key, label in EDITABLE:
        buf.append((key, label))
        if len(buf) == 2:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)
    return rows


def edit_prompt(conn: sqlite3.Connection, card_id: int, field: str) -> str:
    card = card_of(conn, card_id)
    label = dict(EDITABLE).get(field, field)
    now_value = card.get(field)
    hint = ""
    if field in {"price_uah", "price_georgia"}:
        hint = "\nТолько число, в долларах."
        if field == "price_georgia":
            hint += "\nПоле необязательное: если цены для Грузии нет, ничего не вводите."
    return (
        f"<b>{label}</b>\n"
        f"Сейчас: {now_value if now_value not in (None, '') else '—'}{hint}\n\n"
        "Пришлите новое значение текстом или голосом."
    )


def update_card_field(
    conn: sqlite3.Connection,
    card_id: int,
    field: str,
    value: int | str,
    actor_id: int = 1,
) -> None:
    old = card_of(conn, card_id)
    old_value = old.get(field) if old else None
    with conn:
        conn.execute(
            f"UPDATE cars SET {field}=?, updated_at=? WHERE id=?",
            (value, now(), card_id),
        )
        conn.execute(
            """
            INSERT INTO audit(actor_id, action, entity_type, entity_id, field, old_value, new_value, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (actor_id, "card_edit", "cars", card_id, field, _as_text(old_value), _as_text(value), now()),
        )


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def read_back(conn: sqlite3.Connection, field: str, card_id: int = 1) -> object:
    row = conn.execute(f"SELECT {field} FROM cars WHERE id=?", (card_id,)).fetchone()
    return row[0] if row else None


def apply_value(conn: sqlite3.Connection, card_id: int, field: str, raw: str, actor_id: int = 1) -> tuple[bool, str]:
    value = (raw or "").strip()
    if not value:
        return False, "Пустое значение не записываю."

    if field in NUMERIC:
        digits = value.lower().replace(" ", "").replace("\u00a0", "")
        for extra in ("цена", "стоимость", "$", "usd", "долларов", "долл"):
            digits = digits.replace(extra, "")
        digits = "".join(ch for ch in digits if ch.isdigit())
        if not digits:
            return False, "Не разобрал число. Пришлите цифрами."
        number = int(digits)
        update_card_field(conn, card_id, field, number, actor_id)
        return True, f"Записано: {number}"

    update_card_field(conn, card_id, field, value, actor_id)
    return True, "Записано."


def run_stage1_checks() -> dict:
    conn = open_db()
    ensure_columns(conn)

    menu_rows = edit_menu_rows()
    price_row = next(row for row in menu_rows if any(key == "price_uah" for key, _ in row))

    before_price = read_back(conn, "price_uah")
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(cars)").fetchall()]
    prompt_empty_ge = edit_prompt(conn, 1, "price_georgia")

    ua_ok, ua_msg = apply_value(conn, 1, "price_uah", "15 100", actor_id=11)
    price_uah_after = read_back(conn, "price_uah")
    price_georgia_after_ua = read_back(conn, "price_georgia")

    ge_ok, ge_msg = apply_value(conn, 1, "price_georgia", "16 200 USD", actor_id=11)
    price_uah_after_ge = read_back(conn, "price_uah")
    price_georgia_after_ge = read_back(conn, "price_georgia")

    audit_counts = {
        "price_uah": conn.execute("SELECT COUNT(*) FROM audit WHERE field='price_uah'").fetchone()[0],
        "price_georgia": conn.execute("SELECT COUNT(*) FROM audit WHERE field='price_georgia'").fetchone()[0],
    }
    conn.close()

    checks = [
        {
            "name": "ui_relabel_and_adjacent_field",
            "pass": price_row == [("price_uah", "Цена Украины"), ("price_georgia", "Цена Грузии")],
        },
        {
            "name": "schema_adds_price_georgia_without_renaming_price_uah",
            "pass": "price_uah" in columns and "price_georgia" in columns and before_price == 14300,
            "details": {"columns": columns, "price_uah_before": before_price},
        },
        {
            "name": "write_db_readback_price_uah",
            "pass": ua_ok and price_uah_after == 15100 and price_georgia_after_ua is None,
            "details": {"message": ua_msg, "price_uah_after": price_uah_after, "price_georgia_after": price_georgia_after_ua},
        },
        {
            "name": "write_db_readback_price_georgia",
            "pass": ge_ok and price_georgia_after_ge == 16200 and price_uah_after_ge == 15100,
            "details": {"message": ge_msg, "price_uah_after": price_uah_after_ge, "price_georgia_after": price_georgia_after_ge},
        },
        {
            "name": "empty_price_georgia_supported",
            "pass": "Сейчас: —" in prompt_empty_ge and "Поле необязательное" in prompt_empty_ge,
            "details": {"prompt": prompt_empty_ge},
        },
        {
            "name": "independent_audit_rows",
            "pass": audit_counts == {"price_uah": 1, "price_georgia": 1},
            "details": audit_counts,
        },
    ]
    return {
        "task_id": "UA-ART-GE-PRICE-CRM-001",
        "issue": 88,
        "stage": 1,
        "mode": "SIMULATED_LOCAL_CRM",
        "production_touched": False,
        "crm_live_write": False,
        "public_site_touched": False,
        "checks": checks,
        "all_pass": all(item["pass"] for item in checks),
        "generated_at_utc": now(),
    }


if __name__ == "__main__":
    print(json.dumps(run_stage1_checks(), ensure_ascii=False, indent=2))
