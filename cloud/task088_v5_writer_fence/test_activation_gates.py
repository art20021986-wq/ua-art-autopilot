"""Absent-anchor CRM must not run protected background or manual mutations."""
import asyncio
import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integrate_private_sources as integration
import publication_fence as fence


SYNC = ("save_media", "_v165_spool_enqueue", "_v165_spool_remove", "_v165_spool_drain", "_v166_drain_owned")
MANUAL = ("photo_remove", "photo_remove_all", "video_remove_all", "diag_clear", "delete_ok")
JOBS = ("media_spool_worker_job", "_ua004_stage_reconcile_job")


class ActivationGates(unittest.TestCase):
    def setUp(self):
        self.state = False
        self.effects = []
        runtime = types.ModuleType("uaart_price_sync_runtime")
        runtime.activation_available = lambda: self.state
        def require():
            if self.state is False:
                raise RuntimeError("PRICE_SYNC_RUNTIME_NOT_CONFIGURED")
        runtime.require_crm_publication_ready = require
        self.runtime = patch.dict(sys.modules, {"uaart_price_sync_runtime": runtime})
        self.runtime.start(); self.addCleanup(self.runtime.stop)
        self.ns = {}
        self.messages = []
        async def ack(query):
            return None
        async def reply(text):
            self.messages.append(text)
        self.stop = type("ApplicationHandlerStop", (Exception,), {})
        self.update = types.SimpleNamespace(callback_query=types.SimpleNamespace(
            message=types.SimpleNamespace(reply_text=reply)))
        self.ns.update(_v168_ack=ack, ApplicationHandlerStop=self.stop)
        for name in SYNC:
            self.ns[name] = lambda *a, _name=name, **k: self.effects.append(_name)
        for name in MANUAL + JOBS + ("_ua004_sync_current_stage",):
            async def original(*a, _name=name, **k):
                self.effects.append(_name)
                return "effect"
            self.ns[name] = original
        exec(integration.ACTIVATION_BLOCK, self.ns)

    def test_background_stage_and_postregister_media_job_do_not_touch_data(self):
        for name in JOBS:
            result = asyncio.run(self.ns[name](object()))
            self.assertEqual(result, {"status": "SKIPPED_UNCONFIGURED_CRM"})
        self.assertEqual(self.effects, [])

    def test_direct_media_and_manual_handlers_refuse_before_first_effect(self):
        for name in SYNC:
            with self.subTest(entry=name), self.assertRaisesRegex(RuntimeError, "NOT_CONFIGURED"):
                self.ns[name](object())
        for name in MANUAL:
            with self.subTest(entry=name), self.assertRaises(self.stop):
                asyncio.run(self.ns[name](self.update, object()))
        self.assertEqual(self.effects, [])
        self.assertEqual(self.messages, ["Изменение пока недоступно. Ничего не изменено."] * len(MANUAL))

    def test_stage_data_saved_status_does_not_claim_site_updated(self):
        result = asyncio.run(self.ns["_ua004_sync_current_stage"]({"published": 1}))
        self.assertIn("ожидает", result)
        self.assertEqual(self.effects, [])

    def test_native_missing_binding_replies_before_creating_an_operation(self):
        runtime = sys.modules["uaart_price_sync_runtime"]
        runtime.BINDING_KEY = "verified"
        runtime.Binding = type("Binding", (), {})
        query = self.update.callback_query
        query.data = "car_pub:1"
        async def staff(update):
            return query, {"active": 1}
        async def reply(text, **kwargs):
            self.messages.append(text)
        query.message.reply_text = reply
        ns = {"_ua099_require_staff": staff, "_ua099_back": lambda cid: None,
              "ApplicationHandlerStop": self.stop}
        exec(integration.VISIBILITY_BLOCK, ns)
        def forbidden(*a, **k):
            self.fail("An absent binding must not create a visibility operation")
        ns["_ua114_visibility_request"] = forbidden
        context = types.SimpleNamespace(application=types.SimpleNamespace(bot_data={}))
        with self.assertRaises(self.stop):
            asyncio.run(ns["toggle_publish"](self.update, context))
        self.assertEqual(self.messages, ["Изменение видимости пока недоступно. Ничего не изменено."])

    def test_valid_and_external_process_states_preserve_existing_callbacks(self):
        for state in (True, None):
            self.state = state
            self.effects.clear()
            for name in SYNC:
                self.ns[name](object())
            for name in MANUAL + JOBS:
                asyncio.run(self.ns[name](object(), object()))
            asyncio.run(self.ns["_ua004_sync_current_stage"]({"published": 1}))
            self.assertEqual(set(self.effects), set(SYNC + MANUAL + JOBS + ("_ua004_sync_current_stage",)))

    def test_fence_denies_unconfigured_crm_before_even_creating_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock"
            with self.assertRaisesRegex(RuntimeError, "NOT_CONFIGURED"):
                with fence.PublicationFence(lock_path=path, _test_only_path=True):
                    self.fail("unconfigured fence entered")
            self.assertFalse(path.exists())
            self.state = None
            with fence.PublicationFence(lock_path=path, _test_only_path=True):
                fence.require_publication_fence(lock_path=path)
                self.state = False
                with self.assertRaisesRegex(RuntimeError, "NOT_CONFIGURED"):
                    fence.require_publication_fence(lock_path=path)


if __name__ == "__main__":
    unittest.main()
