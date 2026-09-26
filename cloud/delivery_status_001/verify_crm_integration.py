"""Exercise isolated CRM handlers from verified source with mocked I/O."""

import ast
import datetime
import hashlib
import logging
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import delivery_status as policy
from integration_patch import patch_menu, patch_stage_set


FUNCTION_SHA256 = {
    "stage_set": "0e2d101a38834781acb5d9a8668ecacff3acec9a61d03f842dfbdb8129432aa4",
    "stage_menu": "768e216898902c1c6d0f51761962ae61c4d4abc4fdb147862528abc66e5137ff",
}


class HandlerStop(Exception):
    pass


class CRMIntegrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        root = Path(os.environ.get("DELIVERY_SOURCE_ROOT", "/home/Carix"))
        self.card = {"id": 1, "auto_number": "UA-0001", "status": "kr_bought", "published": 1}
        self.writes = []
        self.query = SimpleNamespace(data="car_stage:1", from_user=SimpleNamespace(id=1),
                                     message=SimpleNamespace(reply_text=AsyncMock()))
        self.update = SimpleNamespace(callback_query=self.query)
        self.context = SimpleNamespace()
        self.guard = SimpleNamespace(safe_callback_answer=AsyncMock(return_value=("test", 0)),
                                     remaining=Mock(return_value=5), finish_operation=Mock())
        self.sync = AsyncMock(return_value="")
        self.namespace = {
            "ApplicationHandlerStop": HandlerStop, "_v168_ack": AsyncMock(),
            "drop_wait": Mock(), "card_of": lambda _: self.card, "set_field": self.set_field,
            "_date": datetime.date, "eta_of": lambda _: (None, None),
            "_ua004_sync_current_stage": self.sync, "log": logging.getLogger(__name__),
            "InlineKeyboardButton": lambda text, **kw: SimpleNamespace(text=text, **kw),
            "InlineKeyboardMarkup": lambda rows: SimpleNamespace(inline_keyboard=rows),
            "S": SimpleNamespace(STAGES=[(n, label) for _, _, n, label in policy.CHOICES],
                                  stage_of=policy.stage_number,
                                  status_label=lambda s: policy.public_label(s) or "Скрыт из каталога"),
        }
        self.modules = patch.dict(sys.modules, {"ua_delivery_status": policy, "crm_online_guard": self.guard})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        for name, transform in (("stage_set", patch_stage_set), ("stage_menu", patch_menu)):
            full = root / "cars_ui.py"
            if full.is_file():
                source = full.read_text(encoding="utf-8")
                nodes = [n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == name]
                self.assertEqual(len(nodes), 1)
                fragment = ast.get_source_segment(source, nodes[0])
            else:
                fragment = (root / (name + ".py")).read_text(encoding="utf-8").rstrip("\n")
            self.assertEqual(hashlib.sha256(fragment.encode()).hexdigest(), FUNCTION_SHA256[name])
            exec(compile("from __future__ import annotations\n" + transform(fragment), name, "exec"), self.namespace)

    def set_field(self, card_id, field, value, actor_id):
        self.writes.append((card_id, field, value, actor_id))
        self.card[field] = value

    async def invoke(self, name):
        with self.assertRaises(HandlerStop):
            await self.namespace[name](self.update, self.context)

    async def test_menu_exposes_only_four_canonical_callbacks(self):
        await self.invoke("stage_menu")
        markup = self.query.message.reply_text.call_args.kwargs["reply_markup"]
        codes = [button.callback_data for row in markup.inline_keyboard for button in row
                 if button.callback_data.startswith("car_setstage:")]
        self.assertEqual(codes, ["car_setstage:1:" + code for code in ("korea", "ferry", "georgia", "kyiv")])

    async def test_hidden_card_menu_does_not_claim_korea(self):
        self.card["status"] = "archive"
        await self.invoke("stage_menu")
        message = self.query.message.reply_text.call_args.args[0]
        self.assertIn("Скрыт из каталога", message)
        self.assertNotIn("Этап 1 из 4", message)

    async def test_four_active_callbacks_persist_and_sync(self):
        for public, stored, _, _ in policy.CHOICES:
            with self.subTest(status=public):
                self.query.data = "car_setstage:1:" + public
                await self.invoke("stage_set")
                self.assertEqual(self.card["status"], stored)
        self.assertEqual(self.sync.await_count, 4)

    async def test_forbidden_and_unknown_callbacks_hide_and_sync(self):
        for value in ("sold_transit", "ge_to_kyiv", "sold", "archive", "unexpected", ""):
            with self.subTest(status=value):
                self.query.data = "car_setstage:1:" + value
                await self.invoke("stage_set")
                self.assertEqual(self.card["status"], "hidden")
        self.assertEqual(self.sync.await_count, 6)

    async def test_malformed_callback_never_writes(self):
        for value in (None, 1, {}, "bad", "car_setstage:x:ferry"):
            self.query.data = value
            await self.invoke("stage_set")
        self.assertEqual(self.writes, [])
        self.sync.assert_not_awaited()

    async def test_missing_card_never_writes(self):
        self.card = None
        self.query.data = "car_setstage:1:ferry"
        await self.invoke("stage_set")
        self.assertEqual(self.writes, [])
        self.sync.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
