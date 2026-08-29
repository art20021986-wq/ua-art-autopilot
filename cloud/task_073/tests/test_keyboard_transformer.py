import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import keyboard_transformer as kt


class TestKeyboardTransformer(unittest.TestCase):
    def _sample_keyboard(self):
        return {
            "top_menu": [
                {"label": "Описание", "callback": "cb_desc", "action": "edit_description"},
                {"label": "Загружено в контейнер", "callback": "cb_loaded", "action": "loaded_to_container"},
                {"label": "В пути", "callback": "cb_transit", "action": "in_transit"},
                {"label": "Каталог", "callback": "cb_catalog", "action": "show_in_catalog"},
            ],
            "sections": {
                "container_section": {
                    "title": "Номер и дата контейнера",
                    "buttons": [
                        {"label": "Загружено в контейнер", "callback": "cb_loaded", "action": "loaded_to_container"},
                        {"label": "В пути", "callback": "cb_transit", "action": "in_transit"},
                        {"label": "Изменить дату", "callback": "cb_date", "action": "edit_date"},
                    ],
                }
            },
        }

    def test_audit_before_transform_has_outer_duplicates(self):
        kb = self._sample_keyboard()
        audit = kt.audit_keyboard(kb)
        self.assertEqual(audit["outer_duplicate_count"], 2)

    def test_transform_removes_outer_and_keeps_inner_once(self):
        kb = self._sample_keyboard()
        new_kb = kt.transform_keyboard(kb)
        audit = kt.audit_keyboard(new_kb)
        self.assertEqual(audit["outer_duplicate_count"], 0)
        for action, count in audit["inner_counts"].items():
            self.assertEqual(count, 1)
        inner = new_kb["sections"]["container_section"]["buttons"]
        callbacks = {b["action"]: b["callback"] for b in inner}
        self.assertEqual(callbacks["loaded_to_container"], "cb_loaded")
        self.assertEqual(callbacks["in_transit"], "cb_transit")
        top_actions = [b["action"] for b in new_kb["top_menu"]]
        self.assertIn("edit_description", top_actions)
        self.assertIn("show_in_catalog", top_actions)
        self.assertNotIn("loaded_to_container", top_actions)
        self.assertNotIn("in_transit", top_actions)

    def test_transform_is_idempotent(self):
        kb = self._sample_keyboard()
        once = kt.transform_keyboard(kb)
        twice = kt.transform_keyboard(once)
        self.assertEqual(once, twice)

    def test_missing_container_section_fails_closed(self):
        kb = {"top_menu": [{"label": "x", "callback": "c", "action": "loaded_to_container"}], "sections": {}}
        with self.assertRaises(ValueError):
            kt.transform_keyboard(kb)

    def test_future_card_dynamic_ua9913(self):
        kb = self._sample_keyboard()
        kb["card_id"] = "UA-9913"
        new_kb = kt.transform_keyboard(kb)
        audit = kt.audit_keyboard(new_kb)
        self.assertEqual(audit["outer_duplicate_count"], 0)


if __name__ == "__main__":
    unittest.main()
