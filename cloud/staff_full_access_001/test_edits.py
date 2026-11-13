#!/usr/bin/env python3
"""Each edit applies once to the installed source (sanitized fixtures from LEAD-DESK-PROBE-20261112-R2/R3) and leaves
no single-owner path behind; a second run is refused."""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_analitika_bot  # noqa: E402
import edit_analitika_knopka  # noqa: E402
import edit_bezopasnost  # noqa: E402
import edit_client_ui  # noqa: E402
import edit_karta_klienta  # noqa: E402
import edit_lead_bot  # noqa: E402
import edit_lead_desk  # noqa: E402
import edit_order_bindings  # noqa: E402
import edit_order_host  # noqa: E402
import edit_svyaz  # noqa: E402
import edit_vitrina  # noqa: E402
import edits  # noqa: E402

CASES = (
    (edit_lead_bot, 'lead_bot.txt', r'ADMIN_IDS|chat_id=MANAGER_CHAT_ID|owner_id=MANAGER_CHAT_ID|MANAGER_CHAT_ID\'\)'),
    (edit_client_ui, 'client_ui.txt', r'VLADELEC\b'),
    (edit_vitrina, 'vitrina.txt', r'vladelec = fajl|== fajl\("vladelec.txt"\)'),
    (edit_order_bindings, 'order_bindings.txt', r'owner_id\s*=\s*int|== owner_id'),
    (edit_order_host, 'order_host.txt', r'owner_id'),
    (edit_lead_desk, 'ua_lead_desk.txt', r'owner_id|\[owner\]'),
    (edit_bezopasnost, 'bezopasnost.txt', r'_soobshenie\(_vladelec\(\)|== str\(_vladelec\(\)\)'),
    (edit_karta_klienta, 'karta_klienta.txt', r'komu = _chitat'),
    (edit_svyaz, 'svyaz.txt', r'kto = _fayl'),
    (edit_analitika_bot, 'analitika_bot.txt', r'id in VLADELEC\n'),
    (edit_analitika_knopka, 'analitika_knopka.txt', r'== int\(vladelec_id'),
)



def stubbed(text):
    """A sanitized line ([REDACTED]) becomes a statement of the right indent, so the edited file can be compiled."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == '[REDACTED]':
            before = next((x for x in reversed(lines[:i]) if x.strip()), '')
            after = next((x for x in lines[i + 1:] if x.strip()), '')
            indent = lambda x: len(x) - len(x.lstrip())
            opener = indent(after) > indent(before) and not before.rstrip().endswith(':')
            width = indent(before) if opener else indent(after)
            lines[i] = ' ' * width + ('if True:' if opener else 'pass')
    return '\n'.join(lines)


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

    def test_edited_files_compile(self):
        for module, fixture, _ in CASES:
            source = (HERE / 'fixtures' / fixture).read_bytes()
            try:  # where the stubs fit the original, they must fit the edited file (the server compiles the real one)
                compile(stubbed(source.decode()), module.NAME, 'exec')
            except SyntaxError:
                continue
            with self.subTest(module.NAME):
                compile(stubbed(edits.apply(source, module.EDITS).decode()), module.NAME, 'exec')

    def test_drifted_source_stops(self):
        with self.assertRaisesRegex(ValueError, 'FRAGMENT_NOT_UNIQUE'):
            edits.apply(b'def register(app, *, owners):\n', edit_order_host.EDITS)


if __name__ == '__main__':
    unittest.main()
