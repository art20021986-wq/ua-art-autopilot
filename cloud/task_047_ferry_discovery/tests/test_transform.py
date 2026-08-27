import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import transform  # noqa: E402


class TestChip(unittest.TestCase):
    def test_chip_snippet(self):
        html = '<div class="chip">В море · Корея → Грузия</div>'
        new_html, occ = transform.transform_html(html, "fixture.html", "sha")
        self.assertEqual(new_html, '<div class="chip">На пароме · Корея → Грузия</div>')
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0].form, "chip")
        self.assertEqual(occ[0].classification, "TARGET")
        self.assertEqual(occ[0].action, "REPLACE")


class TestEtapTut(unittest.TestCase):
    def test_etap_tut_snippet(self):
        html = '<div class="etap tut"><div class="krug">2</div>Море: Корея → Грузия</div>'
        new_html, occ = transform.transform_html(html, "fixture.html", "sha")
        self.assertEqual(
            new_html,
            '<div class="etap tut"><div class="krug">2</div>Паром: Корея → Грузия</div>',
        )
        self.assertTrue(any(o.form == "etap_tut" for o in occ))
        self.assertIn('<div class="krug">2</div>', new_html)


class TestFourStage(unittest.TestCase):
    def test_four_stage_sequence(self):
        html = "Корея / Море / Грузия / Киев"
        new_html, occ = transform.transform_html(html, "fixture.html", "sha")
        self.assertEqual(new_html, "Корея / Паром / Грузия / Киев")
        self.assertTrue(any(o.form == "four_stage" for o in occ))


class TestRoutePhrases(unittest.TestCase):
    def test_info_phrase_dash_form(self):
        html = "«Море Корея → Грузия — около 60 дней»"
        new_html, occ = transform.transform_html(html, "fixture.html", "sha")
        self.assertEqual(new_html, "«Паром Корея → Грузия — около 60 дней»")
        self.assertTrue(any(o.form == "route_phrase" for o in occ))

    def test_info_phrase_colon_form(self):
        html = "«Море: Корея → Грузия»"
        new_html, occ = transform.transform_html(html, "fixture.html", "sha")
        self.assertEqual(new_html, "«Паром: Корея → Грузия»")
        self.assertTrue(any(o.form == "route_phrase" for o in occ))


class TestStandaloneAmbiguous(unittest.TestCase):
    def test_unrelated_standalone_more_preserved(self):
        html = "Черное Море является ориентиром на карте"
        new_html, occ = transform.transform_html(html, "fixture.html", "sha")
        self.assertEqual(new_html, html)
        ambiguous = [o for o in occ if o.classification == "AMBIGUOUS"]
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0].action, "PRESERVE")
        self.assertEqual(ambiguous[0].before, "Море")


class TestSecrets(unittest.TestCase):
    def test_plain_token_detected_and_redacted(self):
        text = "token=abcdef123456"
        self.assertTrue(transform.scan_for_secrets(text))
        redacted = transform.redact_secrets(text)
        self.assertNotIn("abcdef123456", redacted)

    def test_json_token_detected_and_redacted(self):
        text = '{"token": "abcdef123"}'
        self.assertTrue(transform.scan_for_secrets(text))
        redacted = transform.redact_secrets(text)
        self.assertNotIn("abcdef123", redacted)

    def test_api_key_with_dash_and_space(self):
        text = "api-key : SECRETVALUE123"
        self.assertTrue(transform.scan_for_secrets(text))

    def test_password_json_form(self):
        text = '{"password": "hunter22"}'
        self.assertTrue(transform.scan_for_secrets(text))

    def test_safe_keys_not_flagged(self):
        text = '{"status": "ok", "sha256": "abc123def456", "container": "box", "tracking": "TRK123456"}'
        self.assertFalse(transform.scan_for_secrets(text))


if __name__ == "__main__":
    unittest.main()
