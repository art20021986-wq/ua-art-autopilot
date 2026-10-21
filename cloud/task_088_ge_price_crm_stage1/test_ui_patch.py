"""Normal-import helper regressions and static historical-route checks.

Supplied source is never executed; these tests make no live-handler PASS claim.
"""
import ast
import json
import re
import sqlite3
import sys
import types
import itertools
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

def parametrize(names, values):
    names = [name.strip() for name in names.split(",")]
    def decorate(fn):
        items = []
        for value in values:
            value = value if len(names) > 1 else (value,)
            items.append(dict(zip(names, value)))
        fn.cases = getattr(fn, "cases", []) + [items]
        return fn
    return decorate


def raises(error, match=None):
    case = unittest.TestCase()
    return case.assertRaisesRegex(error, match) if match else case.assertRaises(error)

HERE = Path(__file__).resolve().parent
import ui_patch as ui
EVIDENCE = json.loads((HERE.parent / "task_080_price_recognition/evidence/live_gate_a.json").read_text())


def historical(name):
    return next(x["source"] for x in EVIDENCE["sources"]["cars_ui.py"]["definitions"]
                if x["name"] == name)


def fixture_source():
    """Full audited handlers + minimal menu contract; menu is not a live capture."""
    snippets = EVIDENCE["sources"]["cars_ui.py"]["price_snippets"]
    labels = next(x["source"] for x in snippets if "LABELS_ALL = {" in x["source"])
    labels = labels[labels.index("LABELS_ALL = {"):labels.index("\n}\n") + 3]
    editable = next(x["source"] for x in snippets if "NUMERIC = {" in x["source"])
    editable = editable[editable.index("EDITABLE = ["):editable.index("\n\n\nasync def edit_menu")]
    menu_contract = '''
async def edit_menu(update, context):
    cid = 1
    rows = [[InlineKeyboardButton(label, callback_data="car_setf:%d:%s" % (cid, field))]
            for field, label in EDITABLE]
    rows.append([InlineKeyboardButton("Назад", callback_data="car_open:%d" % cid)])
    return InlineKeyboardMarkup(rows)

async def ask_field(update, context):
    field = context.user_data["field"]
    hint = ""
    if field == "engine_cc":
        hint = "Объём"
    elif field == "price_uah":
        hint = "\\nТолько число, в долларах."
    return hint
'''
    return "from __future__ import annotations\n" + labels + "\n" + editable + "\n" + menu_contract + "\n" + "\n".join(
        historical(name) for name in ("set_field", "apply_value", "auto_catch", "catch_message"))


class Button:
    def __init__(self, text, callback_data):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.rows = rows


class Stop(Exception):
    pass


class Message:
    photo = video = video_note = document = audio = None
    chat_id = 123
    message_id = 456

    def __init__(self, text="", voice=False):
        self.text = text
        self.voice = types.SimpleNamespace(file_id="test-voice") if voice else None
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return self

    async def edit_text(self, text, **kwargs):
        self.replies.append(text)


def runtime(tmp_path):
    path = tmp_path / "crm.db"
    with sqlite3.connect(path) as conn:
        conn.executescript('''
        CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, price_uah INTEGER,
            price_georgia INTEGER, price_history TEXT, status TEXT, updated_at TEXT,
            vin TEXT, mileage_km INTEGER);
        INSERT INTO cars VALUES(1,'UA-0001',12000,NULL,'{"1":12000}', 'sea_loaded', 'old',
            'VIN-UNCHANGED',40000);
        CREATE TABLE audit(actor_id INTEGER,action TEXT,entity_type TEXT,entity_id INTEGER,
            field TEXT,old_value TEXT,new_value TEXT,created_at TEXT);
        ''')
    connections = []

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        connections.append(conn)
        return conn

    def card_of(cid):
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM cars WHERE id=?", (cid,)).fetchone()
            return dict(row) if row is not None else None

    ns = {"db": types.SimpleNamespace(connect=connect, now=lambda: "new"),
          "S": types.SimpleNamespace(num=lambda v: str(v), stage_of=lambda status: 2),
          "jdump": json.dumps, "price_history": lambda card: json.loads(card["price_history"] or "{}"),
          "card_of": card_of, "InlineKeyboardButton": Button, "InlineKeyboardMarkup": Markup,
          "ApplicationHandlerStop": Stop, "_re": re}
    patched, metadata = ui.patch_text(fixture_source())
    ns.update({name: getattr(ui, name) for name in (
        "_task088_price_rows", "_task088_ge_number", "_task088_apply_selected_price")})
    return ns, path, connections, metadata


def test_preserves_legacy_handlers_except_explicit_selection_branches():
    original = fixture_source()
    after, metadata = ui.patch_text(original)
    for name, inserted in (("apply_value", ui.GE_APPLY_BRANCH),
                           ("auto_catch", ui.GE_AUTO_BRANCH),
                           ("catch_message", ui.GE_CATCH_BRANCH)):
        old = ast.get_source_segment(original, ui._function(original, name))
        new = ast.get_source_segment(after, ui._function(after, name))
        assert new.replace(inserted, "", 1) == old
    assert metadata["site_changes"] == 0
    assert metadata["before_sha256"] != metadata["after_sha256"]


def test_adjacent_button_helper_keeps_existing_callbacks_and_other_fields(runtime):
    ns, _, _, _ = runtime
    candidate, _ = ui.patch_text(fixture_source())
    fields = ast.literal_eval(ui._assignment(candidate, "EDITABLE").value)
    original_rows = [[Button(label, "car_setf:1:" + field)] for field, label in fields]
    original_rows.append([Button("Назад", "car_open:1")])
    rows = ns["_task088_price_rows"](original_rows)
    price_row = next(row for row in rows if any(b.text == "Цена Украины" for b in row))
    assert [(b.text, b.callback_data) for b in price_row] == [
        ("Цена Украины", "car_setf:1:price_uah"), ("Цена Грузии", "car_setf:1:price_georgia")]
    keep = lambda values: [(b.text, b.callback_data) for row in values for b in row
                            if b.callback_data not in ("car_setf:1:price_uah", "car_setf:1:price_georgia")]
    assert keep(rows) == keep(original_rows)
    assert sum(b.callback_data == "car_setf:1:price_georgia" for row in rows for b in row) == 1


def test_manager_button_rows_without_prices_remain_unchanged(runtime):
    ns, _, _, _ = runtime
    rows = [[Button("VIN", "car_setf:1:vin")], [Button("Назад", "car_open:1")]]
    result = ns["_task088_price_rows"](rows)
    assert result == rows
    assert all("price_" not in b.callback_data for row in result for b in row)


def test_ge_only_or_duplicate_price_menu_fails_closed(runtime):
    ns, _, _, _ = runtime
    with raises(RuntimeError):
        ns["_task088_price_rows"]([[Button("GE", "car_setf:1:price_georgia")]])
    with raises(RuntimeError):
        ns["_task088_price_rows"]([[Button("UA", "car_setf:1:price_uah"),
                                    Button("GE", "car_setf:1:price_georgia"),
                                    Button("GE", "car_setf:1:price_georgia")]])


@parametrize("text", ["11400", "11 400 $", "$ 11 400", "цена 11400", "стоимость 11 400 USD"])
def test_ge_write_commits_then_reads_fresh_without_touching_ua(runtime, text):
    ns, path, connections, _ = runtime
    before = ns["card_of"](1)
    with patch.dict(sys.modules, {"price_parser": None}):
        ok, answer = ns["_task088_apply_selected_price"](1, "price_georgia", text, 77)
    assert ok, answer
    after = ns["card_of"](1)
    assert after == dict(before, price_georgia=11400, updated_at="new")
    assert len(connections) == 2 and connections[0] is not connections[1]
    assert "11400" in answer and "Грузии" in answer
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT field,new_value FROM audit").fetchall() == [("price_georgia", "11400")]


def test_ua_selected_write_preserves_ge_and_stage_history(runtime):
    ns, path, _, _ = runtime
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE cars SET price_georgia=9900")
    with patch.dict(sys.modules, {"price_parser": None}):
        ok, answer = ns["_task088_apply_selected_price"](1, "price_uah", "13000", 77)
    assert ok and "13000" in answer
    car = ns["card_of"](1)
    assert (car["price_uah"], car["price_georgia"]) == (13000, 9900)
    assert json.loads(car["price_history"]) == {"1": 12000, "2": 13000}
    assert car["vin"] == "VIN-UNCHANGED" and car["mileage_km"] == 40000


@parametrize("text", ["11,4 тыс", "11.4к", "цена 11,4 тысяч долларов", "11 400 $", "11400"])
def test_existing_ua_dollar_integer_and_thousands_formats_remain_supported(runtime, text):
    ns, _, _, _ = runtime
    with patch.dict(sys.modules, {"price_parser": None}):
        ok, answer = ns["_task088_apply_selected_price"](1, "price_uah", text, 77)
    assert ok, answer
    assert ns["card_of"](1)["price_uah"] == 11400


@parametrize("text", ["", "-11400", "0", "11000 12000", "12000 / 14000", "12000 грн", "12000 GEL", "9999999999999999999999"])
def test_invalid_ge_values_never_write(runtime, text):
    ns, path, connections, _ = runtime
    before = ns["card_of"](1)
    with patch.dict(sys.modules, {"price_parser": None}):
        ok, _ = ns["_task088_apply_selected_price"](1, "price_georgia", text, 77)
    assert not ok
    assert ns["card_of"](1) == before
    assert connections == []


def test_shared_price_parser_field_cannot_redirect_ge(runtime):
    ns, _, _, _ = runtime
    calls = []

    def parse(text, **kwargs):
        calls.append((text, kwargs))
        return types.SimpleNamespace(ok=True, value=11400, field="price_uah")

    with patch.dict(sys.modules, {"price_parser": types.SimpleNamespace(parse_sale_price_message=parse)}):
        ok, _ = ns["_task088_apply_selected_price"](1, "price_georgia", "одиннадцать тысяч четыреста долларов", 77)
    assert ok and calls[0][1] == {"in_price_uah_wait": True}
    car = ns["card_of"](1)
    assert (car["price_uah"], car["price_georgia"]) == (12000, 11400)


@parametrize("field, trigger_sql", [
    ("price_georgia", "UPDATE cars SET price_uah=1 WHERE id=NEW.id;"),
    ("price_uah", "UPDATE cars SET price_georgia=1 WHERE id=NEW.id;"),
    ("price_georgia", "UPDATE cars SET vin='CORRUPT' WHERE id=NEW.id;")])
def test_cross_write_triggers_rollback_before_commit(runtime, field, trigger_sql):
    ns, path, _, _ = runtime
    before = ns["card_of"](1)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TRIGGER crosswrite AFTER UPDATE OF %s ON cars BEGIN %s END" % (field, trigger_sql))
    with patch.dict(sys.modules, {"price_parser": None}):
        ok, _ = ns["_task088_apply_selected_price"](1, field, "13000", 77)
    assert not ok
    assert ns["card_of"](1) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 0


def test_audit_failure_rolls_back_price(runtime):
    ns, path, _, _ = runtime
    before = ns["card_of"](1)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE audit")
    with patch.dict(sys.modules, {"price_parser": None}):
        ok, _ = ns["_task088_apply_selected_price"](1, "price_georgia", "11000", 77)
    assert not ok and ns["card_of"](1) == before


def test_historical_handler_static_route_uses_selected_field_after_voice_decoding():
    candidate, _ = ui.patch_text(fixture_source())
    catch = ast.get_source_segment(candidate, ui._function(candidate, "catch_message"))
    assert catch.count(ui.GE_CATCH_BRANCH) == 1
    route = catch.index(ui.GE_CATCH_BRANCH)
    assert route > catch.index('asyncio.to_thread(ai.transcribe, audio_bytes, filename)')
    assert route < catch.index('if not wait:')
    assert route < catch.index('field = "price_uah"')
    assert 'wait["card_id"], wait["field"], input_text, user_id' in ui.GE_CATCH_BRANCH


def test_static_selected_route_keeps_wait_unless_writer_confirms():
    node = ast.parse("def selected():\n" + ui.GE_CATCH_BRANCH.replace("await ", "")).body[0]
    selected = node.body[0]
    pop_if = selected.body[1]
    assert isinstance(pop_if, ast.If) and isinstance(pop_if.test, ast.Name) and pop_if.test.id == "ok"
    assert 'context.user_data.pop("car_wait", None)' in ast.unparse(pop_if).replace("'", '"')
    assert all(not isinstance(n, ast.Assign) or all(not isinstance(t, ast.Name) or t.id != "field"
                                                   for t in n.targets) for n in ast.walk(selected))


def test_auto_catch_static_guard_precedes_legacy_ua_parser():
    candidate, _ = ui.patch_text(fixture_source())
    auto = ast.get_source_segment(candidate, ui._function(candidate, "auto_catch"))
    assert auto.count(ui.GE_AUTO_BRANCH) == 1
    assert auto.index(ui.GE_AUTO_BRANCH) < auto.index('apply_value(cid, "price_uah"')


@parametrize("mutation", [
    lambda s: s.replace('def apply_value(card_id, field, raw, actor_id):', 'def apply_value(cid, field, raw, actor_id):'),
    lambda s: s.replace('if not wait:', 'if wait is None:'),
    lambda s: s.replace('car_setf:%d:%s', 'unknown_callback:%d:%s'),
    lambda s: s + '\nprice_georgia = "partial prior installation"\n',
    lambda s: s + '\n' + historical("apply_value"),
])
def test_unknown_or_partial_source_fails_closed(mutation):
    with raises(ui.PatchRefused):
        ui.patch_text(mutation(fixture_source()))


def test_repeat_requires_review_instead_of_assuming_existing_ge_is_correct():
    after, _ = ui.patch_text(fixture_source())
    with raises(ui.PatchRefused, match="ALREADY_OR_PARTIALLY"):
        ui.patch_text(after)


def test_static_evidence_never_claims_runtime_or_live_pass():
    after, _ = ui.patch_text(fixture_source())
    result = ui.verify_candidate_runtime(after)
    assert result["status"] == "NOT_VERIFIED"
    assert result["reason"] == "RUNTIME_PROOF_UNAVAILABLE_NO_DYNAMIC_SOURCE_EXECUTION"
    assert result["proof"] == "static_source_shape_only"
    assert result["live_bot_verified"] is False and result["external_messages"] == 0
    assert result["static_evidence"]["helper_sources_match"] is True


def test_static_evidence_checks_embedded_helper_matches_normal_import():
    after, _ = ui.patch_text(fixture_source())
    after = after.replace('TASK088_OTHER_CAR_CROSS_WRITE', 'UNREVIEWED_MODIFICATION')
    result = ui.verify_candidate_runtime(after)
    assert result["status"] == "NOT_VERIFIED"
    assert "STATIC_HELPER_DRIFT" in result["reason"]


def test_unseen_ui_dependency_cannot_be_reported_as_runtime_verified():
    source = fixture_source().replace('    cid = 1\n', '    cid = live_dependency()\n')
    after, _ = ui.patch_text(source)
    result = ui.verify_candidate_runtime(after)
    assert result["status"] == "NOT_VERIFIED" and result["live_bot_verified"] is False


def test_audit_trigger_cross_write_rolls_back(runtime):
    ns, path, _, _ = runtime
    before = ns["card_of"](1)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TRIGGER auditcross AFTER INSERT ON audit BEGIN UPDATE cars SET price_uah=1; END")
    with patch.dict(sys.modules, {"price_parser": None}):
        ok, _ = ns["_task088_apply_selected_price"](1, "price_georgia", "11000", 77)
    assert not ok and ns["card_of"](1) == before


@parametrize("field, table, trigger_body", [
    ("price_georgia", "cars", "UPDATE cars SET price_uah=1 WHERE id=2;"),
    ("price_uah", "cars", "UPDATE cars SET price_georgia=1 WHERE id=2;"),
    ("price_georgia", "audit", "DELETE FROM cars WHERE id=2;"),
])
def test_trigger_modifying_another_car_rolls_back_whole_transaction(runtime, field, table, trigger_body):
    ns, path, _, _ = runtime
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO cars SELECT 2,'UA-0002',14000,11000,price_history,status,updated_at,vin,mileage_km FROM cars WHERE id=1")
        event = "UPDATE OF " + field if table == "cars" else "INSERT"
        conn.execute("CREATE TRIGGER othercar AFTER %s ON %s BEGIN %s END" % (event, table, trigger_body))
        before = conn.execute("SELECT * FROM cars ORDER BY id").fetchall()
    with patch.dict(sys.modules, {"price_parser": None}):
        ok, _ = ns["_task088_apply_selected_price"](1, field, "13000", 77)
    assert not ok
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM cars ORDER BY id").fetchall() == before
        assert conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 0


class TestUI(unittest.TestCase):
    pass


def _make_test(fn, arguments):
    def run(self):
        with tempfile.TemporaryDirectory() as temp:
            kwargs = dict(arguments)
            if "runtime" in inspect.signature(fn).parameters:
                kwargs["runtime"] = runtime(Path(temp))
                with patch.dict(ui.__dict__, kwargs["runtime"][0]):
                    fn(**kwargs)
            else:
                fn(**kwargs)
    return run


for _name, _fn in list(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        _combinations = itertools.product(*getattr(_fn, "cases", [[{}]]))
        for _index, _parts in enumerate(_combinations):
            _arguments = {key: value for part in _parts for key, value in part.items()}
            setattr(TestUI, _name + "_%02d" % _index, _make_test(_fn, _arguments))


if __name__ == "__main__":
    unittest.main()
