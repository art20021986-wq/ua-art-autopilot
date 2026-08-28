from __future__ import annotations

import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ai_fast_schema as fast
import patch_installer
import patch_payload
import task059_controller as controller


class FakeFilter:
    ALLOWED = {
        "brand": ("brand", "марка"),
        "model": ("model", "модель"),
        "year": ("year", "год"),
        "vin": ("vin", "вин"),
        "fuel": ("fuel", "топливо"),
        "engine_cc": ("engine_cc", "объем двигателя"),
        "mileage_km": ("mileage_km", "пробег"),
        "gearbox": ("gearbox", "коробка передач"),
        "price_total": ("price_total", "цена usd"),
    }

    @staticmethod
    def clean(parsed, extra_text=""):
        fields = parsed.get("fields", {})
        return {
            key: item.get("value") if isinstance(item, dict) else item
            for key, item in fields.items()
            if key in FakeFilter.ALLOWED
        }


class FastSchemaTests(unittest.TestCase):
    def test_unknown_fields_are_removed(self):
        parsed = {
            "type": "car",
            "fields": {
                "brand": {"value": "Kia"},
                "model": {"value": "K5"},
                "city": {"value": "Киев"},
                "seller": {"value": "лишнее"},
            },
            "summary": "Киев, продавец и прочее",
            "question": "Куда вставить город?",
        }
        safe = fast.sanitize_parsed(parsed, FakeFilter)
        self.assertEqual(set(safe["fields"]), {"brand", "model"})
        self.assertNotIn("Киев", str(safe))
        self.assertIsNone(safe["question"])

    def test_multiline_labels_use_only_crm_schema(self):
        data = fast.labeled_text_data(
            "Марка: Kia\nМодель: K5\nОбъем двигателя: 2000\n"
            "Коробка передач: автомат\nГород: Киев",
            FakeFilter,
        )
        self.assertEqual(data["engine_cc"], "2000")
        self.assertEqual(data["gearbox"], "автомат")
        self.assertNotIn("city", data)

    def test_prompt_is_schema_closed_and_bounded(self):
        module = types.SimpleNamespace(SYSTEM_PROMPT="S", IMAGE_PROMPT="I", MAX_TOKENS=4096)
        fast.install_prompt(module, FakeFilter)
        self.assertIn(fast.PROMPT_MARKER, module.SYSTEM_PROMPT)
        self.assertIn("brand", module.IMAGE_PROMPT)
        self.assertEqual(module.MAX_TOKENS, 700)
        fast.install_prompt(module, FakeFilter)
        self.assertEqual(module.SYSTEM_PROMPT.count(fast.PROMPT_MARKER), 1)


class PatchContractTests(unittest.TestCase):
    def test_candidate_replaces_only_two_handlers(self):
        source = (
            "VALUE = 1\n\n"
            "async def run_ai_draft(update, context, inbox_id, kind, text, file_id):\n"
            "    return 'old'\n\n"
            "def untouched():\n    return 42\n\n"
            "async def ai_save(update, context):\n    return 'old'\n"
        )
        candidate = patch_installer.replace_functions(
            source,
            {
                "run_ai_draft": patch_payload.RUN_AI_DRAFT_SOURCE,
                "ai_save": patch_payload.AI_SAVE_SOURCE,
            },
        )
        compile(candidate, "candidate", "exec")
        self.assertIn("def untouched():\n    return 42", candidate)
        self.assertNotIn("ai_filter.autosave", candidate)
        self.assertNotIn("ai.review(", candidate)
        self.assertIn("PHOTO_HARD_SECONDS", candidate)

    def test_save_is_user_button_only_and_vin_deduplicated(self):
        source = patch_payload.AI_SAVE_SOURCE
        self.assertIn("ai_filter.store", source)
        self.assertIn("publish=True", source)
        self.assertNotIn("collect_media", source)
        self.assertNotIn("source_text", source)

    def test_receipt_contract_rejects_publication_or_db_change(self):
        valid = {
            "task_id": "task_059",
            "mode": "P0_AI_FAST_SCHEMA_INSTALL",
            "status": "PASS",
            "errors": [],
            "crm_db_write": False,
            "site_write": False,
            "service_restarted": False,
            "ua0010_published": False,
            "rollback_performed": False,
            "site_hashes_unchanged": True,
            "already_applied": False,
            "production_write": True,
            "db_sha256_before": "a" * 64,
            "db_sha256_after": "a" * 64,
            "files": {
                controller.PROD_TEAM: {"after": "b" * 64},
                controller.PROD_HELPER: {"after": "c" * 64},
            },
        }
        self.assertIs(controller.validate_receipt(valid), valid)
        for key in ("crm_db_write", "site_write", "ua0010_published"):
            bad = dict(valid)
            bad[key] = True
            with self.assertRaises(controller.ControllerError):
                controller.validate_receipt(bad)


if __name__ == "__main__":
    unittest.main()
