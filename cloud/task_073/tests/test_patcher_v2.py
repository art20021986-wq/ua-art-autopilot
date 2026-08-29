"""Offline unit tests for cloud/task_073/tools/patcher_v2.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import patcher_v2 as patcher  # noqa: E402


KONTEYNER_FIXTURE = '''
class InlineKeyboardButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


def _ekran(cid, car):
    rows = [
        [InlineKeyboardButton("Номер контейнера", callback_data=f"car_setcontainer:{cid}")],
        [InlineKeyboardButton("Дата загрузки", callback_data=f"car_setdate:{cid}")],
        [InlineKeyboardButton("Назад", callback_data=f"car_back:{cid}")],
    ]
    return rows


def gde_mashina(cid, car):
    rows = [
        [InlineKeyboardButton("В пути", callback_data=f"car_setstage:{cid}:sea_transit")],
        [InlineKeyboardButton("Загружено в контейнер", callback_data=f"car_setstage:{cid}:sea_loaded")],
        [InlineKeyboardButton("На складе", callback_data=f"car_setstage:{cid}:warehouse")],
    ]
    return rows
'''


CARS_UI_FIXTURE = '''
class InlineKeyboardButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


def stage_menu(cid, car):
    rows = [
        [InlineKeyboardButton("Загружено в контейнер", callback_data=f"car_setstage:{cid}:sea_loaded")],
        [InlineKeyboardButton("В пути", callback_data=f"car_setstage:{cid}:sea_transit")],
        [InlineKeyboardButton("На складе", callback_data=f"car_setstage:{cid}:warehouse")],
    ]
    return rows


async def toggle_publish(update, context, cid):
    preimage_published = repo.get_car(cid).get("published")
    repo.set_field(cid, "published", 1)
    ok, text = publikaciya.opublikovat(cid)
    await update.effective_message.reply_text("Машина видна клиентам в каталоге.")
'''


STRANICA_FIXTURE = '''
import os


def _ua_seo068_normalize(auto_number, html):
    if not os.path.exists(f"/site/video/{auto_number}-diag.html"):
        raise ValueError(f"SEO068_DIAGNOSTIC_TARGET_MISSING:{auto_number}")
    if "canonical" not in html:
        raise ValueError("SEO068_CANONICAL_MISSING")
    return html
'''


class TestEkranInnerActions(unittest.TestCase):
    def test_insert_once(self):
        result = patcher.transform_ekran_add_inner_actions(KONTEYNER_FIXTURE)
        self.assertTrue(result.changed)
        self.assertEqual(result.source.count('sea_loaded"'), 1)
        self.assertEqual(result.source.count('sea_transit"'), 1)
        compile(result.source, "<t>", "exec")

    def test_idempotent(self):
        first = patcher.transform_ekran_add_inner_actions(KONTEYNER_FIXTURE)
        second = patcher.transform_ekran_add_inner_actions(first.source)
        self.assertFalse(second.changed)
        self.assertEqual(first.source, second.source)

    def test_fail_closed_on_missing_anchor(self):
        broken = KONTEYNER_FIXTURE.replace("Назад", "Back")
        with self.assertRaises(patcher.PatchAnchorError):
            patcher.transform_ekran_add_inner_actions(broken)


class TestOuterStrip(unittest.TestCase):
    def test_gde_mashina_strip(self):
        result = patcher.transform_gde_mashina_remove_outer(KONTEYNER_FIXTURE)
        self.assertTrue(result.changed)
        self.assertNotIn("sea_loaded", result.source)
        self.assertNotIn("sea_transit", result.source)
        self.assertIn("warehouse", result.source)
        compile(result.source, "<t>", "exec")

    def test_stage_menu_strip(self):
        result = patcher.transform_stage_menu_remove_outer(CARS_UI_FIXTURE)
        self.assertTrue(result.changed)
        self.assertNotIn("sea_loaded", result.source)
        self.assertNotIn("sea_transit", result.source)
        compile(result.source, "<t>", "exec")

    def test_idempotent_strip(self):
        first = patcher.transform_gde_mashina_remove_outer(KONTEYNER_FIXTURE)
        second = patcher.transform_gde_mashina_remove_outer(first.source)
        self.assertFalse(second.changed)


class TestTogglePublish(unittest.TestCase):
    def test_rollback_guard_inserted(self):
        result = patcher.transform_toggle_publish_respect_ok(CARS_UI_FIXTURE)
        self.assertTrue(result.changed)
        self.assertIn("ROLLBACK_ON_PUBLISH_FAIL_073", result.source)
        self.assertIn("Машина видна клиентам в каталоге.", result.source)
        compile(result.source, "<t>", "exec")

    def test_idempotent(self):
        first = patcher.transform_toggle_publish_respect_ok(CARS_UI_FIXTURE)
        second = patcher.transform_toggle_publish_respect_ok(first.source)
        self.assertFalse(second.changed)


class TestSeo068(unittest.TestCase):
    def test_removes_stale_precondition_only(self):
        result = patcher.transform_seo068_drop_stale_precondition(STRANICA_FIXTURE)
        self.assertTrue(result.changed)
        self.assertNotIn("SEO068_DIAGNOSTIC_TARGET_MISSING", result.source)
        self.assertIn("SEO068_CANONICAL_MISSING", result.source)
        compile(result.source, "<t>", "exec")

    def test_fail_closed_when_anchor_missing(self):
        broken = STRANICA_FIXTURE.replace("SEO068_DIAGNOSTIC_TARGET_MISSING", "OTHER_GUARD")
        with self.assertRaises(patcher.PatchAnchorError):
            patcher.transform_seo068_drop_stale_precondition(broken)


if __name__ == "__main__":
    unittest.main()
