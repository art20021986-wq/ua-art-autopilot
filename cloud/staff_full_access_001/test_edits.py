#!/usr/bin/env python3
"""Each edit applies once to the installed source (sanitized fixtures from LEAD-DESK-PROBE-20261112-R2) and leaves
no single-owner path behind; a second run is refused."""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_client_ui  # noqa: E402
import edit_lead_bot  # noqa: E402
import edit_lead_desk  # noqa: E402
import edit_order_bindings  # noqa: E402
import edit_order_host  # noqa: E402
import edits  # noqa: E402

CASES = (
    (edit_lead_bot, 'lead_bot.txt', r'ADMIN_IDS|chat_id=MANAGER_CHAT_ID|owner_id=MANAGER_CHAT_ID|MANAGER_CHAT_ID\'\)'),
    (edit_client_ui, 'client_ui.txt', r'VLADELEC\b'),
    (edit_order_bindings, 'order_bindings.txt', r'owner_id\s*=\s*int|== owner_id'),
    (edit_order_host, 'order_host.txt', r'owner_id'),
    (edit_lead_desk, 'ua_lead_desk.txt', r'owner_id|\[owner\]'),
)


class EditTests(unittest.TestCase):
    def test_applies_once_and_no_single_owner_left(self):
        for module, fixture, single in CASES:
            with self.subTest(module.NAME):
                source = (HERE / 'fixtures' / fixture).read_bytes()
                result = edits.apply(source, module.EDITS).decode()
                self.assertIsNone(re.search(single, result))
                self.assertIn('owners', result)
                with self.assertRaisesRegex(ValueError, 'FRAGMENT_NOT_UNIQUE'):
                    edits.apply(result.encode(), module.EDITS)

    def test_files_without_redactions_still_compile(self):
        for module, fixture, _ in CASES:
            source = (HERE / 'fixtures' / fixture).read_bytes()
            if b'[REDACTED]' in source:
                continue
            with self.subTest(module.NAME):
                compile(edits.apply(source, module.EDITS), module.NAME, 'exec')

    def test_drifted_source_stops(self):
        with self.assertRaisesRegex(ValueError, 'FRAGMENT_NOT_UNIQUE'):
            edits.apply(b'def register(app, *, owners):\n', edit_order_host.EDITS)


if __name__ == '__main__':
    unittest.main()
