#!/usr/bin/env python3
"""vitrina.py edit (fixture: the live file after LEAD-DESK-FIX-INSTALL-20261107, sanitized)."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_vitrina  # noqa: E402

LIVE = (HERE / 'fixtures/vitrina.txt').read_bytes()


class VitrinaEdit(unittest.TestCase):
    def test_button_removed_rest_unchanged(self):
        text = edit_vitrina.build(LIVE).decode()
        self.assertNotIn('("Условия и гарантии"', text)
        self.assertNotIn('info.html', text)
        self.assertIn('        knopki = []  # CLIENT-TERMS-001', text)
        self.assertIn('[("Авто в наличии и в пути", "v_cars")]', text)
        self.assertIn("[[(ua_lead_desk.BUTTON, ua_lead_desk.CALLBACK)], [('📊 Аналитика', 'v_analytics')]]", text)
        self.assertEqual(len(LIVE.decode().splitlines()) - 2, len(text.splitlines()))
        compile(text, 'vitrina.py', 'exec')

    def test_applied_refused(self):
        with self.assertRaises(ValueError):
            edit_vitrina.build(edit_vitrina.build(LIVE))


if __name__ == '__main__':
    unittest.main()
