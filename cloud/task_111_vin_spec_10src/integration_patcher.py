#!/usr/bin/env python3
"""Idempotent UA111 update of the deployed UA110/UA099 integration blocks."""
from __future__ import annotations

import ast
import re


SPEC_START = "# >>> UA110 SIDECAR SPEC STORAGE V1"
SPEC_END = "# <<< UA110 SIDECAR SPEC STORAGE V1"
CRM_START = "# >>> UA110 VIN SPEC AUTO QUEUE V1"
CRM_END = "# <<< UA110 VIN SPEC AUTO QUEUE V1"


def _without(source: str, start: str, end: str) -> str:
    pattern = re.compile(
        r"(?:\n|^)" + re.escape(start) + r"[\s\S]*?" + re.escape(end) + r"\s*",
        re.MULTILINE,
    )
    return pattern.sub("\n", source).rstrip() + "\n"


def _compiled(source: str, name: str) -> str:
    compile(source, name, "exec")
    ast.parse(source)
    return source


SPEC_BLOCK = r'''
# >>> UA110 SIDECAR SPEC STORAGE V1
# Main CRM remains the source of truth and is always opened read-only here.
_UA110_MAIN_DB_PATH = DB_PATH
_UA110_SPEC_DB_PATH = pathlib.Path(
    os.environ.get("UA_ART_SPEC_DB", "/home/Carix/vin_specs_task111_v3.db")
)

def connect(readonly: bool = True) -> sqlite3.Connection:
    resolved = _UA110_SPEC_DB_PATH.resolve()
    if readonly:
        conn = sqlite3.connect("file:" + str(resolved) + "?mode=ro", uri=True, timeout=20)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = sqlite3.connect(str(resolved), timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn

def _ua110_main_connect() -> sqlite3.Connection:
    resolved = _UA110_MAIN_DB_PATH.resolve()
    conn = sqlite3.connect("file:" + str(resolved) + "?mode=ro", uri=True, timeout=20)
    conn.execute("PRAGMA query_only=ON")
    conn.row_factory = sqlite3.Row
    return conn

def _car_vin(uid: str) -> str:
    if not _UA110_MAIN_DB_PATH.is_file():
        return ""
    with _ua110_main_connect() as conn:
        row = conn.execute("SELECT vin FROM cars WHERE auto_number=?", (uid,)).fetchone()
    return str(row[0] or "").strip().upper() if row else ""

def _car_status(uid: str) -> str:
    if not _UA110_MAIN_DB_PATH.is_file():
        return ""
    with _ua110_main_connect() as conn:
        row = conn.execute("SELECT status FROM cars WHERE auto_number=?", (uid,)).fetchone()
    return str(row[0] or "").strip() if row else ""

def _car_mileage(uid: str) -> int | None:
    if not _UA110_MAIN_DB_PATH.is_file():
        return None
    with _ua110_main_connect() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(cars)")}
        if "mileage_km" not in columns:
            return None
        row = conn.execute("SELECT mileage_km FROM cars WHERE auto_number=?", (uid,)).fetchone()
    if not row or row[0] is None:
        return None
    try:
        return max(0, int(float(str(row[0]).replace(" ", "").replace(",", "."))))
    except (TypeError, ValueError):
        return None

_UA110_BASE_CRM_SUMMARY = crm_summary
_UA110_BASE_INJECT_PUBLIC_SPEC = inject_public_spec

def _ua110_sanitize_public_spec_fragments(source: str) -> str:
    """Remove complete, nested and orphaned legacy spec fragments.

    TASK099 already replaces one well-formed marker pair.  Interrupted or
    concurrent publications can leave START/END markers nested or orphaned;
    strip those remnants and any unmarked old spec element before invoking
    TASK099's authoritative renderer.
    """
    import re as _ua110_re
    if not isinstance(source, str) or not source:
        return source
    source = _ua110_re.sub(
        _ua110_re.escape(START) + r"[\s\S]*?" + _ua110_re.escape(END),
        "", source,
    )
    source = source.replace(START, "").replace(END, "")
    source = _ua110_re.sub(
        r"<details\b[^>]*\bdata-ua-additional-spec=['\"]1['\"][^>]*>"
        r"[\s\S]*?</details>",
        "", source, flags=_ua110_re.I,
    )
    return source

def inject_public_spec(source: str, value: Any) -> str:
    return _UA110_BASE_INJECT_PUBLIC_SPEC(
        _ua110_sanitize_public_spec_fragments(source), value
    )

def crm_summary(value: Any) -> str:
    base = _UA110_BASE_CRM_SUMMARY(value)
    try:
        import vin_spec_service as _ua110_service
        state = _ua110_service.card_state(value)
        labels = {
            "NOT_QUEUED": "VIN ещё не поставлен в очередь",
            "PENDING": "сбор поставлен в очередь",
            "RUNNING": "идёт сбор из пула 10 источников",
            "READY": "сбор завершён",
            "NEEDS_REVIEW": "нужна проверка менеджера",
            "FAILED": "сбор не выполнен",
        }
        status = labels.get(str(state.get("status")), str(state.get("status") or "—"))
        sync = str(state.get("site_sync_status") or "NOT_REQUIRED")
        if sync == "PASS":
            status += " · страница обновлена"
        elif sync == "FAIL":
            status += " · обновление страницы не прошло"
        return base + "\nVIN-автосбор: " + status
    except Exception:
        return base + "\nVIN-автосбор: статус временно недоступен"
# <<< UA110 SIDECAR SPEC STORAGE V1
'''.strip()


CRM_BLOCK = r'''
# >>> UA110 VIN SPEC AUTO QUEUE V1
import vin_spec_service as _ua110_vin_service

_UA110_BASE_REGISTER = register

async def additional_spec_screen(update, context):
    q, staff = await _ua099_require_staff(update)
    cid = int(q.data.split(":")[-1])
    card = _ua099_card(cid)
    uid = _ua099_uid(card)
    rows = _ua099_spec.fetch_specs(uid, include_hidden=True)
    lines = ["<b>%s · Дополнительная спецификация</b>" % _ua099_html.escape(uid),
             _ua099_html.escape(_ua099_spec.crm_summary(uid)), ""]
    keyboard = []
    for item in rows:
        visible = "👁" if int(item.get("is_visible") or 0) else "🚫"
        manual = "✍️" if int(item.get("is_manual") or 0) else "✓"
        lines.append("%s %s <b>%s</b>: %s" % (
            visible, manual, _ua099_html.escape(str(item["label_ru"])),
            _ua099_html.escape(str(item["field_value"]))))
        label = str(item["label_ru"])[:36]
        keyboard.append([InlineKeyboardButton(
            "%s %s" % (visible, label),
            callback_data="car_spec_item:%d:%d" % (cid, int(item["id"])))])
    if not rows:
        lines.append("Подтверждённые дополнительные характеристики пока не найдены.")
    keyboard.append([InlineKeyboardButton(
        "🔄 Повторить сбор по VIN", callback_data="car_spec_refresh:%d" % cid
    )])
    if card.get("published"):
        keyboard.append([InlineKeyboardButton(
            "Обновить опубликованную страницу", callback_data="car_spec_publish:%d" % cid)])
    keyboard.append([InlineKeyboardButton("← Вернуться к карточке", callback_data="car_open:%d" % cid)])
    await q.message.reply_text("\n".join(lines), parse_mode="HTML",
                               reply_markup=InlineKeyboardMarkup(keyboard),
                               disable_web_page_preview=True)
    raise ApplicationHandlerStop

async def _ua110_refresh_spec(update, context):
    q, staff = await _ua099_require_staff(update)
    cid = int(q.data.split(":")[-1])
    card = _ua099_card(cid)
    uid = _ua099_uid(card)
    try:
        queued = _ua110_vin_service.retry_card(uid)
        text = ("Повторный сбор по VIN поставлен в очередь. Основные поля CRM не изменяются."
                if queued else "Не удалось поставить VIN в очередь: проверьте формат VIN в карточке.")
    except Exception as exc:
        text = "Не удалось поставить сбор в очередь: " + type(exc).__name__
    await q.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← К дополнительной спецификации", callback_data="car_spec:%d" % cid
        )]]),
    )
    raise ApplicationHandlerStop

def register(app):
    _UA110_BASE_REGISTER(app)
    _ua110_vin_service.start_worker()
    app.add_handler(CallbackQueryHandler(
        _ua110_refresh_spec, pattern=r"^car_spec_refresh:\d+$"
    ), group=-4)
# <<< UA110 VIN SPEC AUTO QUEUE V1
'''.strip()


def patch_additional_spec(source: str) -> str:
    source = _without(source, SPEC_START, SPEC_END)
    for name in (
        "connect", "fetch_specs", "crm_summary", "_car_vin", "_car_status",
        "inject_public_spec",
    ):
        if not re.search(r"^def\s+" + name + r"\s*\(", source, re.MULTILINE):
            raise RuntimeError("SPEC_ENTRYPOINT_MISSING:" + name)
    return _compiled(source.rstrip() + "\n\n" + SPEC_BLOCK + "\n", "ua_additional_spec.py")


def patch_cars_ui(source: str) -> str:
    source = _without(source, CRM_START, CRM_END)
    for marker in ("# >>> UA099 ADDITIONAL SPEC CRM V1", "def register(app):", "def additional_spec_screen"):
        if marker not in source:
            raise RuntimeError("CRM_CONTRACT_MISSING:" + marker)
    return _compiled(source.rstrip() + "\n\n" + CRM_BLOCK + "\n", "cars_ui.py")


def selftest() -> None:
    spec = (
        "import os,pathlib,sqlite3\nfrom typing import Any\nDB_PATH=pathlib.Path('/x')\n"
        "def connect(readonly=True): pass\n"
        "def fetch_specs(value,include_hidden=False): return []\n"
        "def crm_summary(value): return 'x'\n"
        "def inject_public_spec(source,value): return source\n"
        "def _car_vin(uid): return ''\ndef _car_status(uid): return ''\n"
    )
    once = patch_additional_spec(spec)
    assert once == patch_additional_spec(once) and once.count(SPEC_START) == 1
    crm = (
        "# >>> UA099 ADDITIONAL SPEC CRM V1\n"
        "def additional_spec_screen(update,context): pass\n"
        "def register(app): pass\n"
        "# <<< UA099 ADDITIONAL SPEC CRM V1\n"
    )
    once = patch_cars_ui(crm)
    assert once == patch_cars_ui(once) and once.count(CRM_START) == 1
    print("UA111_INTEGRATION_PATCHER_SELFTEST_PASS")


if __name__ == "__main__":
    selftest()
