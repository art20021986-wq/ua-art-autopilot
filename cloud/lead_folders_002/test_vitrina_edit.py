#!/usr/bin/env python3
"""vitrina.py edit (fixture: the live file as LEAD-DESK-PROBE-20261106-R7 read it, sanitized)."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_vitrina  # noqa: E402

LIVE = (HERE / 'fixtures/vitrina.txt').read_bytes()


class VitrinaEdit(unittest.TestCase):
    def test_owner_button_and_pending_message(self):
        text = edit_vitrina.build(LIVE).decode()
        self.assertIn("[[(ua_lead_desk.BUTTON, ua_lead_desk.CALLBACK)], [('📊 Аналитика', 'v_analytics')]]", text)
        self.assertNotIn("'orders:list'", text)
        start = text.index('    tekst = (soobshchenie.text or "").strip()')
        self.assertLess(text.index('if ua_lead_desk.pending(app, kto):', start), text.index('if tekst.startswith("/start")', start))
        compile(text, 'vitrina.py', 'exec')

    def test_refused_twice(self):
        with self.assertRaises(ValueError):
            edit_vitrina.build(edit_vitrina.build(LIVE))


if __name__ == '__main__':
    unittest.main()
