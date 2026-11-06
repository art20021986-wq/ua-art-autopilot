#!/usr/bin/env python3
"""LEAD-FOLDERS-001: the candidate built from the live sources (fixtures: the probes' sanitized copies)."""
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_bots  # noqa: E402

FILES = {'cars_ui.py': 'cars_ui.txt', 'lead_bot.py': 'lead_bot.txt', 'ua_order/bindings.py': 'ua_order/bindings.txt',
         'ua_lead_desk.py': 'ua_lead_desk.txt', 'ua_lead_desk_view.py': 'ua_lead_desk_view.txt',
         'ua_lead_desk_store.py': 'ua_lead_desk_store.txt', 'ua_site_leads.py': 'ua_site_leads.txt'}


def compiles(text, name):
    """Fixtures with [REDACTED] lines are compiled on the server by the preview; here only the others."""
    if '[REDACTED]' not in text:
        compile(text, name, 'exec')


class CandidateTests(unittest.TestCase):
    def build(self):
        source = {name: (FIXTURES / path).read_bytes() for name, path in FILES.items()}
        pins = {name: hashlib.sha256(value).hexdigest() for name, value in source.items()}
        with patch.dict(candidate_builder.SOURCE_SHA256, pins), patch.dict(candidate_builder.DEPENDENCY_SHA256, clear=True):
            return candidate_builder.build(source, {})

    def test_files(self):
        result = self.build()
        self.assertIsNone(result.pop('ua_site_leads.py'))
        self.assertEqual(sorted(result), sorted(set(FILES) - {'ua_site_leads.py'} | set(candidate_builder.NEW)))
        for name, value in result.items():
            compiles(value.decode(), name)

    def test_crm_clients_screen_delegates(self):
        text = self.build()['cars_ui.py'].decode()
        start = text.index('async def clients_screen(')
        body = text[start:text.index('async def crm_leads(')]
        self.assertIn('await ua_crm_orders.clients_screen(update, context)', body)
        self.assertNotIn('ua_site_leads', text)
        self.assertIn('        ua_crm_orders.register(app)\n', text)
        self.assertIn('callback_data="cards_clients"', text)  # the «Клиенты» button itself stays

    def test_client_bot_registers_desk_after_orders(self):
        text = self.build()['lead_bot.py'].decode()
        self.assertLess(text.index('_register_orders(app, owner_id=MANAGER_CHAT_ID)'),
                        text.index('ua_lead_desk.register(app, owner_id=MANAGER_CHAT_ID)'))

    def test_new_enquiry_message_opens_lead(self):
        text = self.build()['ua_order/bindings.py'].decode()
        self.assertIn("('Открыть лид', f'ld:o:or:{row[\"id\"]}')", text)
        self.assertNotIn("orders:open:{row", text)

    def test_edits_refused_twice(self):
        result = self.build()
        for name in edit_bots.EDITS:
            with self.assertRaises(ValueError):
                edit_bots.build(name, result[name])

    def test_wrong_source_refused(self):
        source = {name: (FIXTURES / path).read_bytes() for name, path in FILES.items()}
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build(source, {})


if __name__ == '__main__':
    unittest.main()
