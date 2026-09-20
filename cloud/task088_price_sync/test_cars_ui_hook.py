"""AST-extracted pinned production handlers, isolated durable SQLite fixtures."""
import ast
import asyncio
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import AsyncMock, patch

import outbox
import uaart_price_sync_confirmation as confirmations
from patch_cars_ui import SOURCE_SHA256, CURRENT_SOURCE_SHA256, patch_source


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
            CREATE TABLE staff(user_id INTEGER PRIMARY KEY, active INTEGER, role TEXT);
            INSERT INTO staff VALUES(700,1,'manager'),(701,1,'admin'),(702,1,'owner'),(703,1,'viewer');
            CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT, published INTEGER,
                price_uah INTEGER,price_georgia INTEGER,price_history TEXT,
                status TEXT,updated_at TEXT,title TEXT);
            INSERT INTO cars VALUES(10,'UA-0010','TESTVIN0000000010',1,10000,8000,'{}','georgia','old','Keep title');
            INSERT INTO cars VALUES(29,'UA-0029','TESTVIN0000000029',0,NULL,NULL,'{}','korea','old','Draft');
            CREATE TABLE audit(actor_id INTEGER,action TEXT,entity_type TEXT,entity_id INTEGER,
                field TEXT,old_value TEXT,new_value TEXT,created_at TEXT);
        """)
        self.db.execute("BEGIN IMMEDIATE")
        outbox.install(self.db)
        confirmations.install(self.db)
        self.db.commit()
        self.modules = patch.dict(sys.modules, {"uaart_price_sync_outbox": outbox,
            "uaart_price_sync_confirmation": confirmations,
            "uaart_price_sync_runtime": types.SimpleNamespace(require_crm_price_ready=lambda: None)})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        names = {"_task088_ge_number", "_task088_apply_selected_price", "_v168_empty",
                 "_v168_cas_write", "apply_value", "voice_undo", "auto_catch", "voice_change_plan", "catch_message"}
        nodes = [node for node in ast.parse(self.patched).body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and (node.name in names or node.name.startswith("_task088_"))]
        self.ns = {
            "db": types.SimpleNamespace(connect=self.connect, now=lambda: "new",
                ROLE_OWNER="owner", ROLE_ADMIN="admin", ROLE_MANAGER="manager"),
            "S": types.SimpleNamespace(stage_of=lambda status: 3, num=lambda value: str(value)),
            "price_history": lambda row: json.loads(row["price_history"]),
            "jdump": json.dumps, "Update": object,
            "ContextTypes": types.SimpleNamespace(DEFAULT_TYPE=object),
            "ApplicationHandlerStop": HandlerStop, "LABELS_ALL": {"price_georgia": "Грузия"},
            "_v168_ack": AsyncMock(), "InlineKeyboardButton": lambda text, **kwargs: {"text": text, **kwargs},
            "InlineKeyboardMarkup": lambda values: values,
            "card_of": self.card, "_re": re, "VIN_RE": re.compile(r"\b[A-Z]{17}\b"),
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<extracted-current-crm>", "exec"), self.ns)
        self.helper = self.ns["_task088_apply_selected_price"]

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        self.connections.append(conn)
        self.addCleanup(conn.close)
        return conn

    def card(self, cid=10):
        return dict(self.db.execute("SELECT * FROM cars WHERE id=?", (cid,)).fetchone())

    def provenance(self, identity=(700, 50, 900), actor_id=700):
        return dict(source="TELEGRAM_UPDATE", chat_id=identity[0], message_id=identity[1],
                    update_id=identity[2], actor_id=actor_id, chat_type="private", bot_id=12345)

    def edit(self, field="price_georgia", value="8200", identity=(700, 50, 900), cid=10,
             actor_id=700, **kwargs):
        return self.helper(cid, field, value, actor_id, sync_identity=identity,
                           sync_provenance=self.provenance(identity, actor_id) if identity else None, **kwargs)

    def events(self):
        return [outbox.get_operation(self.db, row[0]) for row in self.db.execute(
            f"SELECT event_key FROM {outbox.V5_TABLE} ORDER BY car_id,sequence")]

    def callback(self, answer, decision="yes", actor_id=700, chat_id=700):
        token = answer.confirmation if hasattr(answer, "confirmation") else answer
        message = types.SimpleNamespace(message_id=70, reply_text=AsyncMock())
        user = types.SimpleNamespace(id=actor_id)
        query = types.SimpleNamespace(data="price5:%s:%s" % (decision, token), from_user=user, message=message)
        update = types.SimpleNamespace(callback_query=query, effective_message=message,
            effective_chat=types.SimpleNamespace(id=chat_id, type="private"), effective_user=user, update_id=990)
        context = types.SimpleNamespace(user_data={}, bot=types.SimpleNamespace(id=12345))
        with self.assertRaises(HandlerStop):
            asyncio.run(self.ns["_task088_price_confirmation"](update, context))
        return message.reply_text.call_args.args[0]

    def test_pin_rejects_source_drift(self):
        self.assertIn(hashlib.sha256(self.source.encode()).hexdigest(), (SOURCE_SHA256, CURRENT_SOURCE_SHA256))
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA256"):
            patch_source(self.source + "\n")

    def test_nonprice_handlers_and_stage_job_remain_unchanged(self):
        allowed = {"_task088_apply_selected_price", "apply_value", "auto_catch", "_v168_cas_write",
                   "catch_message", "voice_undo", "voice_change_plan", "register"}
        def functions(source):
            return {node.name: ast.dump(node) for node in ast.parse(source).body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        original, modified = functions(self.source), functions(self.patched)
        for name in original:
            if name not in allowed:
                self.assertEqual(original[name], modified[name], name)
        self.assertEqual(self.patched.count("uaart_price_sync_runtime.register(app)"), 1)
        self.assertEqual(self.patched.count("uaart_price_sync_binding.bootstrap_if_configured("), 1)
        self.assertEqual(self.patched.count("run_repeating(_ua004_stage_reconcile_job, interval=15"), 1)
        self.assertIn('pattern=r"^price5:(?:yes|no):[0-9a-f]{32}$"', self.patched)

    def test_all_real_price_callers_forward_stable_identity_and_provenance(self):
        for function in ast.parse(self.patched).body:
            if isinstance(function, ast.AsyncFunctionDef) and function.name in {"catch_message", "auto_catch", "voice_undo"}:
                for node in ast.walk(function):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in (
                            "_task088_apply_selected_price", "apply_value", "auto_catch", "_v168_cas_write"):
                        keywords = {keyword.arg for keyword in node.keywords}
                        self.assertTrue({"sync_identity", "sync_provenance"} <= keywords)

    def test_intent_precedes_mutation_and_independent_connection_readback(self):
        original = outbox.submit
        seen = []
        before = self.card()
        def spy(conn, **kwargs):
            seen.append(conn)
            self.assertTrue(conn.in_transaction)
            self.assertEqual(dict(conn.execute("SELECT * FROM cars WHERE id=10").fetchone()), before)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 0)
            return original(conn, **kwargs)
        with patch.object(outbox, "submit", side_effect=spy):
            ok, answer = self.edit()
        self.assertTrue(ok, answer)
        self.assertEqual(self.card(), before)
        self.assertTrue(answer.queued)
        self.assertNotIn("Завершено", answer)
        self.assertEqual(self.events()[0]["state"], "QUEUED")
        self.assertIsNot(seen[0], self.connections[-1])

    def test_all_four_operator_inputs_are_queued_without_superseding(self):
        for number, value in enumerate((18000, 18500, 18300, 18900)):
            self.assertTrue(self.edit(value=str(value), identity=(700, 50 + number, 900 + number))[0])
        self.assertEqual([event["value"] for event in self.events()], ["18000.00", "18500.00", "18300.00", "18900.00"])
        self.assertEqual([event["state"] for event in self.events()], ["QUEUED"] * 4)
        self.assertEqual(self.card()["price_georgia"], 8000)

    def test_same_amount_new_message_is_a_new_intent(self):
        self.assertTrue(self.edit()[0])
        self.assertTrue(self.edit(identity=(700, 51, 901))[0])
        self.assertEqual(len(self.events()), 2)

    def test_technical_replay_does_not_duplicate_old_or_new_intent(self):
        self.assertTrue(self.edit()[0])
        self.assertTrue(self.edit(value="8500", identity=(700, 51, 901))[0])
        self.assertTrue(self.edit()[0])
        self.assertEqual(len(self.events()), 2)
        self.assertFalse(self.edit(value="9999")[0])
        self.assertEqual(len(self.events()), 2)

    def test_cross_market_inputs_and_car_scopes_are_distinct(self):
        self.assertTrue(self.edit()[0])
        self.assertTrue(self.edit("price_uah", "10500")[0])
        events = self.events()
        self.assertEqual({event["field"] for event in events}, {"price_uah", "price_georgia"})
        self.assertEqual([event["sequence"] for event in events], [1, 2])
        self.assertEqual((self.card()["price_uah"], self.card()["price_georgia"]), (10000, 8000))

    def test_enqueue_failure_rolls_back_all_effects(self):
        before = self.card()
        with patch.object(outbox, "submit", side_effect=RuntimeError("disk failure")):
            self.assertFalse(self.edit()[0])
        self.assertEqual(self.card(), before)
        self.assertEqual(self.events(), [])

    def test_outbox_trigger_cross_car_write_is_rolled_back(self):
        self.db.execute(f"CREATE TRIGGER bad_outbox AFTER INSERT ON {outbox.V5_TABLE} "
                        "BEGIN UPDATE cars SET title='Corrupted' WHERE id=29; END")
        self.db.commit()
        before, other = self.card(), self.card(29)
        self.assertFalse(self.edit()[0])
        self.assertEqual(self.card(), before)
        self.assertEqual(self.card(29), other)
        self.assertEqual(self.events(), [])

    def test_outbox_trigger_audit_insert_is_rolled_back(self):
        self.db.execute(f"CREATE TRIGGER bad_outbox AFTER INSERT ON {outbox.V5_TABLE} "
                        "BEGIN INSERT INTO audit(actor_id,field) VALUES(700,'unauthorized'); END")
        self.db.commit()
        self.assertFalse(self.edit()[0])
        self.assertEqual(self.events(), [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 0)

    def test_unpublished_intent_uses_same_fifo_without_early_price_write(self):
        self.assertTrue(self.edit(cid=29)[0])
        self.assertEqual(self.card(29)["published"], 0)
        self.assertIsNone(self.card(29)["price_georgia"])
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.events()[0]["state"], "QUEUED")
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit").fetchone()[0], 0)

    def test_no_identity_or_provenance_cannot_mutate(self):
        before = self.card()
        self.assertFalse(self.edit(identity=None)[0])
        self.assertFalse(self.helper(10, "price_georgia", "8200", 700, sync_identity=(700, 50, 900))[0])
        self.assertEqual(self.card(), before)
        self.assertEqual(self.events(), [])

    def test_each_authorized_operator_can_submit_both_markets(self):
        for actor in (700, 701, 702):
            for field in ("price_uah", "price_georgia"):
                self.assertTrue(self.edit(field, actor_id=actor, identity=(actor, 50, 900))[0])
        self.assertEqual(len(self.events()), 6)
        self.assertFalse(self.edit(actor_id=703, identity=(703, 50, 900))[0])

    def test_anomalous_prices_show_exact_amount_and_do_not_commit(self):
        before = self.card()
        for i, amount in enumerate((245, 245000)):
            ok, answer = self.edit(value=str(amount), identity=(700, 50 + i, 900 + i))
            self.assertFalse(ok)
            self.assertIn(format(amount, ",").replace(",", " ") + " $", answer)
            self.assertTrue(answer.confirmation)
            self.assertEqual(self.card(), before)
        self.assertEqual(self.events(), [])

    def test_anomaly_confirmation_survives_new_context_and_connection(self):
        ok, answer = self.edit(value="245000")
        self.assertFalse(ok)
        token = answer.confirmation
        # Callback has no user_data, old handler/message object or process cache.
        result = self.callback(token)
        self.assertIn("245 000 $", result)
        self.assertEqual(self.events()[0]["value"], "245000.00")
        self.assertEqual(confirmations.get(self.connect(), token)["state"], "CONFIRMED")
        self.assertEqual(self.card()["price_georgia"], 8000)

    def test_confirmation_replay_only_accepts_once(self):
        _, answer = self.edit(value="245")
        self.callback(answer)
        self.callback(answer)
        self.assertEqual(len(self.events()), 1)

    def test_cancelled_confirmation_never_saves_and_new_input_can_repeat(self):
        _, first = self.edit(value="245")
        self.assertIn("отменено", self.callback(first, "no"))
        self.callback(first)
        self.assertEqual(self.events(), [])
        _, second = self.edit(value="245", identity=(700, 51, 901))
        self.assertNotEqual(first.confirmation, second.confirmation)
        self.callback(second)
        self.assertEqual(len(self.events()), 1)

    def test_same_technical_anomaly_delivery_reuses_proposal(self):
        _, one = self.edit(value="245")
        _, two = self.edit(value="245")
        self.assertEqual(one.confirmation, two.confirmation)
        self.assertEqual(self.db.execute(f"SELECT count(*) FROM {confirmations.TABLE}").fetchone()[0], 1)

    def test_confirmation_cannot_be_used_by_another_operator_or_chat(self):
        _, answer = self.edit(value="245")
        self.callback(answer, actor_id=701)
        self.callback(answer, chat_id=701)
        self.assertEqual(self.events(), [])
        self.assertEqual(confirmations.get(self.db, answer.confirmation)["state"], "PENDING")

    def test_revoked_operator_cannot_submit_confirm_or_cancel(self):
        _, answer = self.edit(value="245")
        self.db.execute("UPDATE staff SET active=0 WHERE user_id=700")
        self.db.commit()
        self.assertFalse(self.edit(value="8500", identity=(700, 51, 901))[0])
        self.callback(answer)
        self.callback(answer, "no")
        self.assertEqual(self.events(), [])
        self.assertEqual(confirmations.get(self.db, answer.confirmation)["state"], "PENDING")

    def test_confirmation_ledger_is_immutable_and_permanent(self):
        _, answer = self.edit(value="245")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(f"DELETE FROM {confirmations.TABLE}")
        self.db.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(f"UPDATE {confirmations.TABLE} SET payload_json='{{}}'")
        self.db.rollback()
        self.assertEqual(confirmations.get(self.db, answer.confirmation)["state"], "PENDING")

    def test_draft_anomaly_confirmation_submits_same_fifo_transaction(self):
        _, answer = self.edit(cid=29, value="245")
        self.callback(answer)
        self.assertIsNone(self.card(29)["price_georgia"])
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(confirmations.get(self.db, answer.confirmation)["state"], "CONFIRMED")
        self.callback(answer)
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit").fetchone()[0], 0)

    def test_voice_cas_and_nullable_undo_have_queue_guards(self):
        cas = self.ns["_v168_cas_write"]
        args = dict(sync_identity=(700, 50, 900), sync_provenance=self.provenance())
        self.assertFalse(cas(10, "price_georgia", 8000, 8500, 700, False, **args)[0])
        self.assertFalse(cas(10, "price_georgia", 7999, 8500, 700, True, **args)[0])
        self.assertTrue(cas(10, "price_georgia", 8000, 8500, 700, True, **args)[0])
        self.assertTrue(self.edit(value="", identity=(700, 51, 901), expected_price=(8000,), restore_price=(None,))[0])
        self.assertIsNone(self.events()[-1]["value"])
        self.assertEqual((self.card()["price_uah"], self.card()["price_georgia"]), (10000, 8000))

    def test_explicit_same_voice_price_is_an_operator_action(self):
        plan = self.ns["voice_change_plan"]
        changes, _ = plan(self.card(), {"price_georgia": 8000}, {"price_georgia"}, True)
        self.assertEqual(changes, [("price_georgia", 8000, 8000)])

    def test_actual_numeric_autocatch_returns_confirmation_buttons(self):
        msg = types.SimpleNamespace(text="245", photo=None, video=None, video_note=None,
                                    document=None, reply_text=AsyncMock())
        context = types.SimpleNamespace(user_data={})
        done = asyncio.run(self.ns["auto_catch"](msg, self.card(), 700, context,
            sync_identity=(700, 50, 900), sync_provenance=self.provenance()))
        self.assertTrue(done)
        rows = msg.reply_text.call_args.kwargs["reply_markup"]
        self.assertTrue(rows[0][0]["callback_data"].startswith("price5:yes:"))
        self.assertEqual(self.events(), [])

    def test_real_explicit_ge_button_handler_shows_confirmation_before_write(self):
        msg = types.SimpleNamespace(text="245000", voice=None, audio=None, video_note=None,
            message_id=50, reply_text=AsyncMock())
        update = types.SimpleNamespace(effective_message=msg, update_id=900,
            effective_user=types.SimpleNamespace(id=700),
            effective_chat=types.SimpleNamespace(id=700, type="private"))
        context = types.SimpleNamespace(user_data={"car_wait": {"card_id": 10, "field": "price_georgia"}},
                                        bot=types.SimpleNamespace(id=12345))
        with patch.dict(sys.modules, {name: types.SimpleNamespace() for name in
                ("ai", "ai_fast_schema", "ai_filter", "local_ocr")}):
            with self.assertRaises(HandlerStop):
                asyncio.run(self.ns["catch_message"](update, context))
        answer = msg.reply_text.call_args.args[0]
        self.assertIn("Цена Грузии — 245 000 $", answer)
        rows = msg.reply_text.call_args.kwargs["reply_markup"]
        self.assertTrue(rows[0][0]["callback_data"].startswith("price5:yes:"))
        self.assertEqual(self.events(), [])
        self.assertEqual(self.card()["price_georgia"], 8000)

    def test_draft_technical_replay_does_not_duplicate_audit(self):
        self.assertTrue(self.edit(cid=29)[0])
        self.assertTrue(self.edit(cid=29)[0])
        self.assertEqual(len(self.events()), 1)
        self.assertTrue(self.edit(cid=29, identity=(700, 51, 901))[0])
        self.assertEqual(len(self.events()), 2)

    def test_anomaly_proposal_trigger_cannot_corrupt_other_car(self):
        self.db.execute(f"CREATE TRIGGER bad_proposal AFTER INSERT ON {confirmations.TABLE} "
                        "BEGIN UPDATE cars SET title='Corrupted' WHERE id=29; END")
        self.db.commit()
        before = self.card(29)
        self.assertFalse(self.edit(value="245")[0])
        self.assertEqual(self.card(29), before)
        self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {confirmations.TABLE}").fetchone()[0], 0)

    def test_confirmation_decision_failure_rolls_back_submit(self):
        _, answer = self.edit(value="245")
        self.db.execute(f"CREATE TRIGGER bad_confirm AFTER UPDATE ON {confirmations.TABLE} "
                        "BEGIN UPDATE cars SET title='Corrupted' WHERE id=29; END")
        self.db.commit()
        before = self.card(29)
        self.callback(answer)
        self.assertEqual(self.card(29), before)
        self.assertEqual(self.events(), [])
        self.assertEqual(confirmations.get(self.db, answer.confirmation)["state"], "PENDING")

    def test_draft_confirmation_trigger_audit_corruption_rolls_back_everything(self):
        _, answer = self.edit(cid=29, value="245")
        self.db.execute(f"CREATE TRIGGER bad_confirm AFTER UPDATE ON {confirmations.TABLE} "
                        "BEGIN INSERT INTO audit(actor_id,field) VALUES(700,'Corrupted'); END")
        self.db.commit()
        before = self.card(29)
        self.callback(answer)
        self.assertEqual(self.card(29), before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 0)
        self.assertEqual(confirmations.get(self.db, answer.confirmation)["state"], "PENDING")

    def test_non_usd_input_is_never_converted_or_enqueued(self):
        for text in ("24500 UAH", "24500 GEL", "24500 EUR", "0", "-24500"):
            self.assertFalse(self.edit(value=text)[0])
        self.assertEqual(self.events(), [])

    def test_successive_explicit_voice_corrections_do_not_bind_stale_old_price(self):
        cas = self.ns["_v168_cas_write"]
        for index,value in enumerate((18000,18500,18300,18900)):
            identity = (700,50+index,900+index)
            ok,answer = cas(10,"price_georgia",8000,value,700,True,
                sync_identity=identity,sync_provenance=self.provenance(identity))
            self.assertTrue(ok,answer)
        self.assertEqual(self.card()["price_georgia"],8000)
        self.assertEqual([json.loads(event["expected_old_json"]) for event in self.events()],
                         [[8000],[18000],[18500],[18300]])
        self.assertEqual([event["value"] for event in self.events()],
                         ["18000.00","18500.00","18300.00","18900.00"])

    def current_crm_runtime_fixture(self):
        from test_v5_runtime import V5RuntimeTests
        fixture = V5RuntimeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.now = time.time_ns() // 1000000 + 10000
        with sqlite3.connect(fixture.db) as conn:
            conn.execute("CREATE TABLE staff(user_id INTEGER PRIMARY KEY, active INTEGER, role TEXT)")
            conn.execute("INSERT INTO staff VALUES(700,1,'manager')")
        def connect():
            conn = sqlite3.connect(fixture.db)
            conn.row_factory = sqlite3.Row
            self.addCleanup(conn.close)
            return conn
        self.ns["db"].connect = connect
        return fixture

    def test_actual_crm_corrections_complete_every_fifo_runtime_operation(self):
        fixture = self.current_crm_runtime_fixture()
        cas = self.ns["_v168_cas_write"]
        values = (18000,18500,18300,18900)
        keys = []
        for index,value in enumerate(values):
            identity = (700,50+index,900+index)
            ok,answer = cas(1,"price_georgia",8000,value,700,True,
                sync_identity=identity,sync_provenance=self.provenance(identity))
            self.assertTrue(ok,answer)
            keys.append(self.ns["_task088_sync_key"](identity,700,1,"price_georgia"))
        for key,value in zip(keys,values):
            result = fixture.worker.tick()
            self.assertEqual(fixture.event(key)["state"],"COMPLETED",result)
            self.assertEqual(fixture.row()["price_georgia"],value)
            self.assertEqual(fixture.row()["price_uah"],20000)
        # A replay of the original first voice message stays idempotent after
        # all later intentions completed and the displayed old value changed.
        self.assertTrue(cas(1,"price_georgia",8000,18000,700,True,
            sync_identity=(700,50,900),sync_provenance=self.provenance())[0])
        self.assertEqual(fixture.row()["price_georgia"],18900)
        self.assertEqual(len(fixture.notices()),4)
        # The legacy whole-generator fence consumes the real runtime's final
        # audit/receipt envelope, not a parallel invented fixture schema.
        import contextlib
        from patch_guard import HELPER
        guard = {"contextlib":contextlib,"sqlite3":sqlite3,"DB":fixture.db,"PublishError":RuntimeError}
        exec(compile(HELPER,"<actual-v5-publication-fence>","exec"),guard)
        with guard["_task088_price_quiescence"]():
            pass

    def test_causal_voice_sequence_still_blocks_external_drift_before_commit(self):
        fixture = self.current_crm_runtime_fixture()
        cas = self.ns["_v168_cas_write"]
        for index,value in enumerate((18000,18500)):
            identity = (700,50+index,900+index)
            self.assertTrue(cas(1,"price_georgia",8000,value,700,True,
                sync_identity=identity,sync_provenance=self.provenance(identity))[0])
        fixture.worker.tick()
        with sqlite3.connect(fixture.db) as conn:
            conn.execute("UPDATE cars SET price_georgia=18333 WHERE id=1")
        fixture.worker.tick()
        key = self.ns["_task088_sync_key"]((700,51,901),700,1,"price_georgia")
        event = fixture.event(key)
        self.assertEqual(event["state"],"CLAIMED")
        self.assertEqual(event["blocked"],1)
        self.assertEqual(event["last_error"],"V5_OPERATOR_CAS_CONFLICT")
        self.assertEqual(fixture.row()["price_georgia"],18333)
        self.assertEqual(sum(row[1]=="SUCCESS" for row in fixture.notices()),1)

    def test_old_draft_message_replay_after_publication_does_not_become_new_operation(self):
        self.assertTrue(self.edit(cid=29)[0])
        self.db.execute("UPDATE cars SET published=1,price_uah=15000,price_georgia=9000 WHERE id=29")
        self.db.commit()
        self.assertTrue(self.edit(cid=29)[0])
        self.assertEqual(self.card(29)["price_georgia"],9000)
        self.assertEqual(len(self.events()),1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit").fetchone()[0],0)

    def test_old_published_message_replay_after_unpublication_cannot_run_stage2_again(self):
        self.assertTrue(self.edit()[0])
        self.db.execute("UPDATE cars SET published=0 WHERE id=10");self.db.commit()
        self.assertTrue(self.edit()[0])
        self.assertEqual(self.card()["price_georgia"],8000)
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit").fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
