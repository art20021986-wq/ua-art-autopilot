"""Offline tests for TASK 075 stage_transform.py using synthetic fixtures
only. No real CRM/PythonAnywhere data is used or accessed.

Run with: python -m pytest cloud/task_075/tests/test_stage_transform.py -v
or:       python -m unittest cloud.task_075.tests.test_stage_transform
"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from stage_transform import (  # noqa: E402
    SandboxFail,
    build_card,
    days_since_transition,
    dedupe_one_card_per_stage,
    migrate_ferry_route_cards,
    normalize_stage,
    render_card_html,
    run_pipeline,
    stage3_expired,
    stage_text,
)

BASE_HOST = "https://example-sandbox.invalid/media"


def _fixture_items():
    now = datetime(2024, 1, 20)
    return [
        {"id": "UA-0001", "status": "Корея, готовим", "crm_photo_count": 1, "photo": "a1.jpg", "transition_at": now - timedelta(days=1)},
        {"id": "UA-0002", "status": "Паром, старый текст маршрут X", "crm_photo_count": 1, "photo": "a2.jpg", "transition_at": now - timedelta(days=2)},
        {"id": "UA-0003", "status": "Грузия, ожидание", "crm_photo_count": 1, "photo": "a3.jpg", "transition_at": now - timedelta(days=16)},
        {"id": "UA-0004", "status": "В Киеве осмотр", "crm_photo_count": 1, "photo": "a4.jpg", "transition_at": now - timedelta(days=3)},
        {"id": "UA-0005", "status": "транзит", "crm_photo_count": 1, "photo": "a5.jpg", "transition_at": now},
        {"id": "UA-0006", "status": "предоплата внесена", "crm_photo_count": 1, "photo": "a6.jpg", "transition_at": now},
        {"id": "UA-0007", "status": "Корея, готовим", "crm_photo_count": 2, "photo": "a7.jpg", "transition_at": now - timedelta(days=5)},
        {"id": "UA-0008", "status": "Паром, старый текст маршрут Y", "crm_photo_count": 1, "photo": "a8.jpg", "transition_at": now - timedelta(days=4)},
        {"id": "UA-0009", "status": "Грузия, готово", "crm_photo_count": 1, "photo": "a9.jpg", "transition_at": now - timedelta(days=1)},
        {"id": "UA-0010", "status": "В Киеве осмотр", "crm_photo_count": 1, "photo": "a10.jpg", "transition_at": now - timedelta(days=1)},
        {"id": "UA-0011", "status": "Паром, старый текст маршрут Z", "crm_photo_count": 1, "photo": "a11.jpg", "transition_at": now},
    ]


class StageMappingTests(unittest.TestCase):
    def test_hidden_statuses(self):
        self.assertIsNone(normalize_stage("транзит"))
        self.assertIsNone(normalize_stage("предоплата внесена"))

    def test_four_stage_mapping(self):
        self.assertEqual(normalize_stage("Едет из Кореи"), "korea")
        self.assertEqual(normalize_stage("На пароме"), "more")
        self.assertEqual(normalize_stage("В Грузии стоит"), "gruzia")
        self.assertEqual(normalize_stage("Прибыл в Киев"), "kiev")

    def test_stage_text_values(self):
        self.assertEqual(stage_text("more"), "На пароме · маршрут — Киев")
        self.assertEqual(stage_text("gruzia"), "В Грузии · маршрут — Киев")
        self.assertEqual(stage_text("kiev"), "В Киеве · можно посмотреть")


class MediaGuardTests(unittest.TestCase):
    def test_missing_photo_is_sandbox_fail(self):
        with self.assertRaises(SandboxFail):
            build_card("UA-XXXX", "Корея", 0, None, BASE_HOST, datetime.now())

    def test_no_text_only_card_possible(self):
        card = build_card("UA-0001", "Корея", 1, "a1.jpg", BASE_HOST, datetime.now())
        self.assertTrue(card.photo_url)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.result = run_pipeline(_fixture_items(), BASE_HOST)

    def test_pipeline_pass(self):
        self.assertEqual(self.result["status"], "PASS")

    def test_all_11_unique_ids(self):
        cards = self.result["cards"]
        ids = [c.id for c in cards]
        # UA-0005 and UA-0006 are hidden (транзит / предоплата), so 9 remain visible
        self.assertEqual(len(ids), len(set(ids)))
        pairs = [(c.stage, c.category) for c in cards]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_ua0009_specific_gate(self):
        cards = {c.id: c for c in self.result["cards"]}
        self.assertIn("UA-0009", cards)
        card = cards["UA-0009"]
        self.assertEqual(card.crm_photo_count > 0, True)
        self.assertEqual(card.stage, card.category)
        self.assertTrue(card.photo_url)

    def test_round2_ferry_text_migrated_for_all_ferry_cards(self):
        cards = [c for c in self.result["cards"] if c.stage == "more"]
        self.assertGreaterEqual(len(cards), 3)  # UA-0002, UA-0008, UA-0011
        for c in cards:
            self.assertEqual(c.text, "На пароме · маршрут — Киев")


class Round3TemplateTests(unittest.TestCase):
    def test_base_tag_precedes_css(self):
        card = build_card("UA-0001", "Корея", 1, "a1.jpg", BASE_HOST, datetime.now())
        html = render_card_html(card, "https://example-sandbox.invalid/", ["style.css"])
        base_idx = html.index("<base")
        css_idx = html.index("<link")
        self.assertLess(base_idx, css_idx)

    def test_render_requires_absolute_photo(self):
        card = build_card("UA-0001", "Корея", 1, "a1.jpg", BASE_HOST, datetime.now())
        html = render_card_html(card, "https://example-sandbox.invalid/", [])
        self.assertIn("https://", html)

    def test_no_article_or_plitka_markup(self):
        card = build_card("UA-0001", "Корея", 1, "a1.jpg", BASE_HOST, datetime.now())
        html = render_card_html(card, "https://example-sandbox.invalid/", [])
        self.assertNotIn("article", html)
        self.assertNotIn("plitka", html)

    def test_stage3_uses_transition_date_not_payment_flag(self):
        now = datetime(2024, 1, 20)
        card = build_card("UA-0003", "Грузия", 1, "a3.jpg", BASE_HOST, now - timedelta(days=16))
        # days_since_transition takes no payment flag parameter at all
        self.assertTrue(stage3_expired(card, now, threshold_days=15))
        card2 = build_card("UA-0009", "Грузия", 1, "a9.jpg", BASE_HOST, now - timedelta(days=1))
        self.assertFalse(stage3_expired(card2, now, threshold_days=15))

    def test_days_since_transition_signature_has_no_payment_arg(self):
        import inspect
        sig = inspect.signature(days_since_transition)
        self.assertNotIn("payment", sig.parameters)
        self.assertNotIn("prepaid", sig.parameters)


class TransitionSequenceTests(unittest.TestCase):
    def test_1_2_3_4_progression(self):
        now = datetime(2024, 1, 20)
        seq = ["korea", "more", "gruzia", "kiev"]
        statuses = ["Едет из Кореи", "На пароме", "В Грузии", "Прибыл в Киев"]
        stages = [normalize_stage(s) for s in statuses]
        self.assertEqual(stages, seq)


if __name__ == "__main__":
    unittest.main()
