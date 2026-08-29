import asyncio
import json
import re
import sqlite3
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from integration_patcher import (  # noqa: E402
    LIVE_MANIFEST,
    PatchRefused,
    transform_audited_block,
)


_EVIDENCE_PATHS = (
    ROOT / "evidence_live_gate_a.json",  # local independent verification copy
    ROOT / "evidence" / "live_gate_a.json",  # repository/Actions layout
)
EVIDENCE_PATH = next((path for path in _EVIDENCE_PATHS if path.exists()), None)
if EVIDENCE_PATH is None:
    raise RuntimeError("TASK080_LIVE_EVIDENCE_MISSING")
EVIDENCE = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def audited_block(path, name):
    anchor = next(item for item in LIVE_MANIFEST[path].blocks if item.name == name)
    key = "assignments" if anchor.kind == "assignment" else "definitions"
    item = next(item for item in EVIDENCE["sources"][path][key] if item["name"] == name)
    assert item["sha256"] == anchor.sha256
    return anchor, item["source"]


def transformed(path, name):
    anchor, source = audited_block(path, name)
    return transform_audited_block(path, anchor.kind, name, source, anchor.sha256)


def test_every_changed_live_block_hashes_and_compiles():
    changed = 0
    for path, file_anchor in LIVE_MANIFEST.items():
        if path == "db.py":
            continue
        for anchor in file_anchor.blocks:
            before_anchor, before = audited_block(path, anchor.name)
            after = transform_audited_block(
                path, before_anchor.kind, anchor.name, before, anchor.sha256
            )
            assert after != before
            compile(after, "%s:%s" % (path, anchor.name), "exec")
            changed += 1
    assert changed == 9


def test_hash_mismatch_fails_closed_before_transform():
    anchor, source = audited_block("cars_ui.py", "apply_value")
    try:
        transform_audited_block(
            "cars_ui.py", anchor.kind, anchor.name, source + "# drift\n", anchor.sha256
        )
    except PatchRefused as exc:
        assert "BLOCK_HASH_MISMATCH" in str(exc)
    else:
        raise AssertionError("drifted source was not refused")


def _make_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE cars (
          id INTEGER PRIMARY KEY, auto_number TEXT NOT NULL,
          price_uah INTEGER, price_history TEXT, status TEXT,
          updated_at TEXT, description TEXT
        );
        CREATE TABLE audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER,
          action TEXT NOT NULL, entity_type TEXT, entity_id INTEGER,
          field TEXT, old_value TEXT, new_value TEXT, created_at TEXT NOT NULL
        );
        INSERT INTO cars
          (id,auto_number,price_uah,price_history,status,description)
          VALUES (1,'UA-0001',NULL,NULL,'sea_loaded','preserve');
        """
    )
    con.commit()
    con.close()


def _db_connect(path):
    def connect():
        con = sqlite3.connect(path, timeout=2)
        con.row_factory = sqlite3.Row
        return con
    return connect


def _card(path, cid=1):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT * FROM cars WHERE id=?", (cid,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def test_patched_apply_value_writes_only_sale_price_atomically():
    source = transformed("cars_ui.py", "apply_value")
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        _make_db(path)
        namespace = {
            "card_of": lambda cid: _card(path, cid),
            "db": types.SimpleNamespace(
                connect=_db_connect(path), now=lambda: "2026-08-29T08:00:00"
            ),
            "S": types.SimpleNamespace(
                stage_of=lambda status: 2,
                num=lambda value: format(int(value), ",").replace(",", " "),
                check_vin=lambda value: (True, "ok"),
            ),
            "NUMERIC": {"engine_cc", "mileage_km", "price_uah"},
            "set_field": lambda *args: None,
        }
        exec(source, namespace)
        apply_value = namespace["apply_value"]
        ok, _ = apply_value(
            1,
            "price_uah",
            "Стоимость автомобиля 11 400 долларов",
            77,
            expected_auto_number="UA-0001",
        )
        assert ok
        card = _card(path)
        assert card["price_uah"] == 11400
        assert json.loads(card["price_history"]) == {"2": 11400}
        assert card["description"] == "preserve"
        con = sqlite3.connect(path)
        try:
            audit = con.execute(
                "SELECT field,new_value FROM audit ORDER BY id"
            ).fetchall()
        finally:
            con.close()
        assert audit == [("price_uah", "11400")]
        ok, answer = apply_value(
            1, "price_uah", "цена 12000", 77,
            expected_auto_number="UA-0001"
        )
        assert not ok and "измени цену" in answer
        assert _card(path)["price_uah"] == 11400
        ok, _ = apply_value(
            1, "price_uah", "измени цену на 12000", 77,
            expected_auto_number="UA-0001"
        )
        assert ok and _card(path)["price_uah"] == 12000


def test_local_ocr_and_fast_schema_share_price_parser():
    local_source = transformed("local_ocr.py", "fields_from_text")
    local_ns = {
        "re": re,
        "CAR_LINE_RE": re.compile(r"(?!)"),
        "BRANDS": {},
        "VIN_RE": re.compile(r"(?!)"),
        "_put": lambda data, allowed, field, value: (
            data.__setitem__(field, value) if field in allowed else None
        ),
    }
    exec(local_source, local_ns)
    local_value = local_ns["fields_from_text"](
        "ціна авто одинадцять тисяч чотириста доларів", {"price_uah"}
    )
    assert local_value == {"price_uah": 11400}

    fast_source = transformed("ai_fast_schema.py", "fast_text_data")
    fast_ns = {
        "labeled_text_data": lambda text, filt: {},
        "clean_car": lambda parsed, filt, text: {},
        "parsed_from_data": lambda data: data,
        "car_fields": lambda filt: {"price_uah"},
    }
    exec(fast_source, fast_ns)
    fast_value = fast_ns["fast_text_data"](
        "ціна авто одинадцять тисяч чотириста доларів", object()
    )
    assert fast_value == {"price_uah": 11400}


def test_generic_labels_can_only_target_price_uah():
    labeled = transformed("ai_fast_schema.py", "labeled_text_data")
    assert '"цена": _choose(allowed, "price_uah")' in labeled
    assert '"ціна": _choose(allowed, "price_uah")' in labeled
    assert '"цена": _choose(allowed, "price_total", "price_buy")' not in labeled
    allowed_source = transformed("ai_filter.py", "ALLOWED")
    namespace = {}
    exec(allowed_source, namespace)
    assert "price_uah" in namespace["ALLOWED"]
    assert "price_total" not in namespace["ALLOWED"]
    assert "price_buy" not in namespace["ALLOWED"]


class _Button:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _Markup:
    def __init__(self, rows):
        self.rows = rows


class _Message:
    def __init__(self, *, text=None, caption=None, message_id=1, photo=None):
        self.text = text
        self.caption = caption
        self.message_id = message_id
        self.chat_id = 501
        self.photo = photo
        self.video = None
        self.video_note = None
        self.document = None
        self.audio = None
        self.voice = None
        self.replies = []

    async def reply_text(self, value, **kwargs):
        self.replies.append((value, kwargs))
        return types.SimpleNamespace(edit_text=lambda *args, **kwargs: None)


def _auto_namespace(calls):
    def apply_value(*args, **kwargs):
        calls.append((args, kwargs))
        return True, "Записано: 11 400"

    return {
        "apply_value": apply_value,
        "VIN_RE": re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.I),
        "_re": re,
        "InlineKeyboardMarkup": _Markup,
        "InlineKeyboardButton": _Button,
        "PHRASES": [],
        "EDITABLE": [],
        "LABELS_ALL": {},
        "set_field": lambda *args: None,
        "log": types.SimpleNamespace(warning=lambda *args, **kwargs: None),
    }


def test_typed_text_photo_caption_and_duplicate_use_one_path():
    source = transformed("cars_ui.py", "auto_catch")
    calls = []
    namespace = _auto_namespace(calls)
    exec(source, namespace)
    context = types.SimpleNamespace(chat_data={}, user_data={})
    card = {"id": 1, "auto_number": "UA-0001"}

    typed = _Message(text="Стоимость автомобиля 11 400 долларов", message_id=10)
    assert asyncio.run(namespace["auto_catch"](typed, card, 77, context))
    assert len(calls) == 1 and len(typed.replies) == 1
    assert calls[0][0][1] == "price_uah"

    # Same Telegram update is silent and never reaches the writer twice.
    assert asyncio.run(namespace["auto_catch"](typed, card, 77, context))
    assert len(calls) == 1 and len(typed.replies) == 1

    caption = _Message(
        caption="ціна авто одинадцять тисяч чотириста доларів",
        message_id=11,
        photo=[object()],
    )
    assert asyncio.run(namespace["auto_catch"](caption, card, 77, context))
    assert len(calls) == 2 and len(caption.replies) == 1
    assert calls[1][0][1] == "price_uah"


def test_bare_number_and_ambiguous_price_never_reach_writer():
    source = transformed("cars_ui.py", "auto_catch")
    calls = []
    namespace = _auto_namespace(calls)
    exec(source, namespace)
    context = types.SimpleNamespace(chat_data={}, user_data={})
    card = {"id": 1, "auto_number": "UA-0001"}

    bare = _Message(text="11400", message_id=20)
    assert not asyncio.run(namespace["auto_catch"](bare, card, 77, context))
    assert calls == [] and bare.replies == []

    ambiguous = _Message(text="цена 11400 или 12000", message_id=21)
    assert asyncio.run(namespace["auto_catch"](ambiguous, card, 77, context))
    assert calls == [] and len(ambiguous.replies) == 1
    assert "Карточка не изменена" in ambiguous.replies[0][0]


class _Stop(Exception):
    pass


class _ContextTypes:
    DEFAULT_TYPE = object


def _catch_namespace(card_of, apply_value=None):
    return {
        "Update": object,
        "ContextTypes": _ContextTypes,
        "ApplicationHandlerStop": _Stop,
        "card_of": card_of,
        "apply_value": apply_value or (lambda *args, **kwargs: (False, "not written")),
        "InlineKeyboardMarkup": _Markup,
        "InlineKeyboardButton": _Button,
        "_int": int,
        "S": types.SimpleNamespace(
            status_label=lambda status: str(status), money=lambda value: str(value)
        ),
    }


def _stub_imports():
    names = ("ai", "ai_fast_schema", "ai_filter", "local_ocr")
    before = {name: sys.modules.get(name) for name in names}
    for name in names:
        sys.modules[name] = types.ModuleType(name)
    return before


def _restore_imports(before):
    for name, module in before.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def test_no_active_card_price_asks_to_open_and_writes_nothing():
    source = transformed("cars_ui.py", "catch_message")
    calls = []
    namespace = _catch_namespace(lambda cid: None, lambda *a, **k: calls.append((a, k)))
    exec(source, namespace)
    msg = _Message(text="цена авто 11400", message_id=30)
    update = types.SimpleNamespace(
        effective_message=msg,
        effective_user=types.SimpleNamespace(id=77),
    )
    context = types.SimpleNamespace(user_data={}, chat_data={})
    before = _stub_imports()
    try:
        try:
            asyncio.run(namespace["catch_message"](update, context))
        except _Stop:
            pass
        else:
            raise AssertionError("handler did not stop")
    finally:
        _restore_imports(before)
    assert calls == []
    assert len(msg.replies) == 1 and "Откройте нужную карточку" in msg.replies[0][0]


def test_explicit_price_wait_enables_bare_number_and_overwrite():
    source = transformed("cars_ui.py", "catch_message")
    calls = []

    def apply_value(*args, **kwargs):
        calls.append((args, kwargs))
        return False, "test stop"

    card = {
        "id": 1, "auto_number": "UA-0001", "price_uah": 11000,
        "status": "sea_loaded"
    }
    namespace = _catch_namespace(lambda cid: dict(card), apply_value)
    exec(source, namespace)
    msg = _Message(text="11400", message_id=31)
    update = types.SimpleNamespace(
        effective_message=msg,
        effective_user=types.SimpleNamespace(id=77),
    )
    context = types.SimpleNamespace(
        user_data={"car_wait": {"card_id": 1, "field": "price_uah"}},
        chat_data={},
    )
    before = _stub_imports()
    try:
        try:
            asyncio.run(namespace["catch_message"](update, context))
        except _Stop:
            pass
    finally:
        _restore_imports(before)
    assert len(calls) == 1
    assert calls[0][0][1] == "price_uah"
    assert calls[0][1]["in_price_uah_wait"] is True
    assert calls[0][1]["correction"] is True


def test_voice_duplicate_is_silent_before_transcription_or_write():
    source = transformed("cars_ui.py", "catch_message")
    namespace = _catch_namespace(
        lambda cid: {"id": 1, "auto_number": "UA-0001"}
    )
    exec(source, namespace)
    voice = types.SimpleNamespace(file_id="voice-file")
    msg = _Message(message_id=32)
    msg.voice = voice
    update = types.SimpleNamespace(
        effective_message=msg,
        effective_user=types.SimpleNamespace(id=77),
        effective_chat=types.SimpleNamespace(id=501),
    )
    marker = "501:32"
    context = types.SimpleNamespace(
        user_data={"car_voice_active": 1},
        chat_data={"crm_voice_seen": [marker]},
    )
    before = _stub_imports()
    try:
        try:
            asyncio.run(namespace["catch_message"](update, context))
        except _Stop:
            pass
    finally:
        _restore_imports(before)
    assert msg.replies == []


def test_candidate_removes_legacy_price_writers_from_active_paths():
    auto = transformed("cars_ui.py", "auto_catch")
    catch = transformed("cars_ui.py", "catch_message")
    cas = transformed("cars_ui.py", "_v168_cas_write")
    assert 'golo = _re.fullmatch' not in auto
    assert 'if field == "price_uah":\n            continue' in auto
    assert "remember_price(card, user_id)" not in catch
    assert "elif data and skipped and not override" not in catch
    assert "from crm_price_atomic import write_price" in cas
