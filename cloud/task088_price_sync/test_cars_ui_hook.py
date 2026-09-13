"""Run AST-extracted current CRM functions against isolated SQLite fixtures."""
import ast
import asyncio
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

import outbox
from patch_cars_ui import SOURCE_SHA256, patch_source


class HandlerStop(Exception):
    pass


class CarsHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = pathlib.Path(os.environ.get("TASK088_CARS_UI_SOURCE", str(
            pathlib.Path(__file__).resolve().parents[2] / "live_source_private" / "cars_ui.py")))
        cls.source = path.read_text()
        cls.patched = patch_source(cls.source)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / "crm.sqlite"
        self.connections = []
        self.db = self.connect()
        self.db.executescript("""
            CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INTEGER,
                price_uah INTEGER,price_georgia INTEGER,price_history TEXT,
                status TEXT,updated_at TEXT,title TEXT);
            INSERT INTO cars VALUES(10,'UA-0010',1,10000,8000,'{}','georgia','old','Keep title');
            INSERT INTO cars VALUES(29,'UA-0029',0,NULL,NULL,'{}','korea','old','Draft');
            CREATE TABLE audit(actor_id INTEGER,action TEXT,entity_type TEXT,entity_id INTEGER,
                field TEXT,old_value TEXT,new_value TEXT,created_at TEXT);
        """)
        self.db.execute("BEGIN IMMEDIATE")
        outbox.install(self.db)
        self.db.commit()
        self.outbox_module = patch.dict(sys.modules, {"uaart_price_sync_outbox": outbox})
        self.outbox_module.start()
        self.addCleanup(self.outbox_module.stop)
        names = {"_task088_ge_number", "_task088_apply_selected_price", "_task088_sync_identity",
                 "_task088_sync_amount", "_task088_sync_precheck", "_task088_sync_enqueue",
                 "_task088_sync_readback", "_v168_empty", "_v168_cas_write", "apply_value", "voice_undo"}
        nodes = [node for node in ast.parse(self.patched).body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
        self.ns = {
            "db": types.SimpleNamespace(connect=self.connect, now=lambda: "new"),
            "S": types.SimpleNamespace(stage_of=lambda status: 3, num=lambda value: str(value)),
            "price_history": lambda row: json.loads(row["price_history"]),
            "jdump": json.dumps, "Update": object,
            "ContextTypes": types.SimpleNamespace(DEFAULT_TYPE=object),
            "ApplicationHandlerStop": HandlerStop, "LABELS_ALL": {"price_georgia": "Грузия"},
            "_v168_ack": AsyncMock(), "InlineKeyboardButton": lambda *a, **k: (a, k),
            "InlineKeyboardMarkup": lambda values: values,
            "card_of": self.card,
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<extracted-current-crm>", "exec"), self.ns)
        self.helper = self.ns["_task088_apply_selected_price"]

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        self.connections.append(db)
        self.addCleanup(db.close)
        return db

    def card(self, cid=10):
        return dict(self.db.execute("SELECT * FROM cars WHERE id=?", (cid,)).fetchone())

    def edit(self, field="price_georgia", value="8200", identity=(700, 50, 900), cid=10, **kwargs):
        return self.helper(cid, field, value, 700, sync_identity=identity, **kwargs)

    def events(self):
        return [dict(row) for row in self.db.execute(f"SELECT * FROM {outbox.TABLE} ORDER BY car_id,revision")]

    def test_pin_rejects_any_source_drift(self):
        self.assertEqual(hashlib.sha256(self.source.encode()).hexdigest(), SOURCE_SHA256)
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA256"):
            patch_source(self.source + "\n")

    def test_stage_job_and_nonprice_handlers_remain_unchanged(self):
        allowed = {"_task088_apply_selected_price", "apply_value", "auto_catch", "_v168_cas_write",
                   "catch_message", "voice_undo", "register"}
        def functions(source):
            return {node.name: ast.dump(node) for node in ast.parse(source).body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        original, modified = functions(self.source), functions(self.patched)
        for name in original:
            if name not in allowed:
                self.assertEqual(original[name], modified[name], name)
        self.assertEqual(self.patched.count("uaart_price_sync_runtime.register(app)"), 1)
        self.assertEqual(self.patched.count("uaart_price_sync_binding.bootstrap(app,"), 1)
        self.assertEqual(self.patched.count("run_repeating(_ua004_stage_reconcile_job, interval=15"), 1)

    def test_real_catch_and_price_callers_forward_stable_identity(self):
        names = {"catch_message", "auto_catch"}
        for function in ast.parse(self.patched).body:
            if isinstance(function, ast.AsyncFunctionDef) and function.name in names:
                for node in ast.walk(function):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in (
                            "_task088_apply_selected_price", "apply_value", "auto_catch", "_v168_cas_write"):
                        self.assertIn("sync_identity", [keyword.arg for keyword in node.keywords])
        update = types.SimpleNamespace(effective_chat=types.SimpleNamespace(id=700),
            effective_message=types.SimpleNamespace(message_id=50), update_id=900)
        self.assertEqual(self.ns["_task088_sync_identity"](update), (700, 50, 900))

    def test_price_audit_and_outbox_share_exact_transaction(self):
        original = outbox.enqueue
        seen = []
        def spy(conn, **kwargs):
            seen.append(conn)
            self.assertTrue(conn.in_transaction)
            self.assertEqual(conn.execute("SELECT price_georgia FROM cars WHERE id=10").fetchone()[0], 8200)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1)
            self.assertEqual(self.card()["price_georgia"], 8000)
            return original(conn, **kwargs)
        with patch.object(outbox, "enqueue", side_effect=spy):
            ok, answer = self.edit()
        self.assertTrue(ok, answer)
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.card()["price_georgia"], 8200)
        self.assertEqual(self.events()[0]["georgia_usd"], "8200.00")
        self.assertNotIn("Опубликовано", answer)

    def test_enqueue_failure_rolls_back_price_and_audit(self):
        before = self.card()
        with patch.object(outbox, "enqueue", side_effect=RuntimeError("disk or schema failure")):
            ok, _ = self.edit()
        self.assertFalse(ok)
        self.assertEqual(self.card(), before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 0)
        self.assertEqual(self.events(), [])

    def test_outbox_trigger_cannot_commit_cross_car_side_effect(self):
        self.db.execute(f"CREATE TRIGGER bad_outbox AFTER INSERT ON {outbox.TABLE} "
                        "BEGIN UPDATE cars SET title='Corrupted' WHERE id=29; END")
        self.db.commit()
        before, other = self.card(), self.card(29)
        self.assertFalse(self.edit()[0])
        self.assertEqual(self.card(), before)
        self.assertEqual(self.card(29), other)
        self.assertEqual(self.events(), [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 0)

    def test_outbox_trigger_cannot_commit_audit_corruption(self):
        self.db.execute(f"CREATE TRIGGER bad_outbox AFTER INSERT ON {outbox.TABLE} "
                        "BEGIN UPDATE audit SET new_value='wrong'; END")
        self.db.commit()
        before = self.card()
        self.assertFalse(self.edit()[0])
        self.assertEqual(self.card(), before)
        self.assertEqual(self.events(), [])

    def test_two_prices_are_independent_and_ukraine_history_is_atomic(self):
        other = self.card(29)
        self.assertTrue(self.edit()[0])
        self.assertTrue(self.edit("price_uah", "10500", identity=(700, 51, 901))[0])
        saved = self.card()
        self.assertEqual((saved["price_uah"], saved["price_georgia"]), (10500, 8200))
        self.assertEqual(json.loads(saved["price_history"]), {"3": 10500})
        self.assertEqual(saved["title"], "Keep title")
        self.assertEqual(self.card(29), other)
        self.assertEqual([row[0] for row in self.db.execute("SELECT field FROM audit")],
                         ["price_georgia", "price_uah", "price_history"])
        self.assertEqual([row["state"] for row in self.events()], ["SUPERSEDED", "PENDING"])

    def test_unpublished_card_remains_manual_and_needs_no_outbox_event(self):
        self.assertTrue(self.edit(cid=29, identity=None)[0])
        self.assertEqual(self.card(29)["published"], 0)
        self.assertEqual(self.card(29)["price_georgia"], 8200)
        self.assertEqual(self.events(), [])

    def test_published_price_needs_stable_identity_before_any_write(self):
        before = self.card()
        for identity in (None, (700, None, 900), (700, 50, True)):
            self.assertFalse(self.edit(identity=identity)[0])
        self.assertEqual(self.card(), before)
        self.assertEqual(self.events(), [])

    def test_repeated_event_does_not_repeat_price_or_audit(self):
        self.assertTrue(self.edit()[0])
        first = self.card()
        self.assertTrue(self.edit()[0])
        self.assertEqual(self.card(), first)
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1)

    def test_duplicate_requires_independent_fresh_readback(self):
        self.assertTrue(self.edit()[0])
        calls = []
        def racing_connect():
            calls.append(1)
            if len(calls) == 2:
                self.db.execute("UPDATE cars SET price_georgia=8900 WHERE id=10")
                self.db.commit()
            return self.connect()
        self.ns["db"].connect = racing_connect
        self.assertFalse(self.edit()[0])
        self.assertEqual(self.card()["price_georgia"], 8900)
        self.assertEqual(len(self.events()), 1)

    def test_conflicting_or_old_delivery_never_overwrites_newer_price(self):
        self.assertTrue(self.edit()[0])
        self.assertFalse(self.edit(value="9999")[0])
        self.assertTrue(self.edit(value="8500", identity=(700, 51, 901))[0])
        self.assertFalse(self.edit()[0])
        self.assertEqual(self.card()["price_georgia"], 8500)
        self.assertEqual(len(self.events()), 2)

    def test_chat_and_field_are_part_of_mutation_identity(self):
        self.assertTrue(self.edit()[0])
        self.assertTrue(self.edit(value="8500", identity=(701, 50, 900))[0])
        self.assertTrue(self.edit("price_uah", "10500", identity=(701, 50, 900))[0])
        self.assertEqual(len({event["event_key"] for event in self.events()}), 3)

    def test_apply_value_routes_ukraine_and_georgia_through_same_helper(self):
        for field, value, update in (("price_uah", "10500", 900), ("price_georgia", "8500", 901)):
            ok, answer = self.ns["apply_value"](10, field, value, 700, sync_identity=(700, 50, update))
            self.assertTrue(ok, answer)
        self.assertEqual(len(self.events()), 2)

    def test_voice_price_cas_keeps_fill_and_conflict_guards(self):
        cas = self.ns["_v168_cas_write"]
        self.assertFalse(cas(10, "price_georgia", 8000, 8500, 700, False,
                            sync_identity=(700, 50, 900))[0])
        self.assertFalse(cas(10, "price_georgia", 7999, 8500, 700, True,
                            sync_identity=(700, 50, 900))[0])
        self.assertTrue(cas(10, "price_georgia", 8000, 8500, 700, True,
                           sync_identity=(700, 50, 900))[0])
        self.assertEqual(self.card()["price_uah"], 10000)
        self.assertEqual(self.events()[0]["georgia_usd"], "8500.00")

    def test_internal_nullable_ge_restore_preserves_ukraine_and_enqueues(self):
        self.assertTrue(self.edit()[0])
        self.assertTrue(self.edit(value="", identity=(700, 52, 902), expected_price=(8200,),
                                  restore_price=(None,))[0])
        self.assertEqual(self.card()["price_uah"], 10000)
        self.assertIsNone(self.card()["price_georgia"])
        self.assertIsNone(self.events()[-1]["georgia_usd"])
        self.assertFalse(self.edit(value="", identity=(700, 53, 903), expected_price=(8200,),
                                   restore_price=(8000,))[0])
        self.assertIsNone(self.card()["price_georgia"])

    def test_actual_voice_undo_uses_guarded_nullable_restore(self):
        self.assertTrue(self.edit()[0])
        message = types.SimpleNamespace(message_id=70, reply_text=AsyncMock())
        query = types.SimpleNamespace(data="car_vundo:10:voice1", from_user=types.SimpleNamespace(id=700),
                                      message=message)
        update = types.SimpleNamespace(callback_query=query, effective_message=message,
            effective_chat=types.SimpleNamespace(id=700), update_id=990)
        context = types.SimpleNamespace(user_data={"voice_undo": {"card_id": 10, "token": "voice1",
            "changes": [{"field": "price_georgia", "new": 8200, "old": None}]}})
        with self.assertRaises(HandlerStop):
            asyncio.run(self.ns["voice_undo"](update, context))
        self.assertIsNone(self.card()["price_georgia"])
        self.assertEqual(self.card()["price_uah"], 10000)
        self.assertIsNone(self.events()[-1]["georgia_usd"])
        message.reply_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
