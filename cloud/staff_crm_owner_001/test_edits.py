#!/usr/bin/env python3
"""Each edit applies once to the installed source (sanitized fixtures from LEAD-DESK-PROBE-20261124 and -R2; ai.txt and
cars_schema.txt are minimal stand-ins holding the exact probed lines) and leaves no owner-only path behind; a second
run is refused."""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_ai  # noqa: E402
import edit_bezopasnost  # noqa: E402
import edit_cars_schema  # noqa: E402
import edit_cars_ui  # noqa: E402
import edit_home_photo  # noqa: E402
import edit_home_stage  # noqa: E402
import edit_kr_prices  # noqa: E402
import edit_pay_bot  # noqa: E402
import edit_svyaz  # noqa: E402
import edit_team_bot  # noqa: E402
import edit_telegram_key  # noqa: E402
import edits  # noqa: E402

CASES = (
    (edit_team_bot, 'team_bot.txt', r'(?m)^(?!.*ROLE_ADMIN).*(staff\["role"\] == db\.ROLE_OWNER|staff_ids_by_role\(db\.ROLE_OWNER\))'),
    (edit_cars_ui, 'cars_ui.txt', r'== db\.ROLE_OWNER'),
    (edit_cars_schema, 'cars_schema.txt', r'role == "owner"|"admin"/"manager" — нет'),
    (edit_ai, 'ai.txt', r'role == "owner"'),
    (edit_home_photo, 'ua_home_photo_bot.txt', r'== db\.ROLE_OWNER'),
    (edit_home_stage, 'ua_home_stage_bot.txt', r'== db\.ROLE_OWNER'),
    (edit_kr_prices, 'ua_kr_prices_bot.txt', r'== db\.ROLE_OWNER'),
    (edit_telegram_key, 'ua_telegram_key.txt', r'== db\.ROLE_OWNER'),
    (edit_pay_bot, 'ua_pay_bot.txt', r'staff_ids_by_role\(db\.ROLE_OWNER\)'),
    (edit_bezopasnost, 'bezopasnost.txt', r'_soobshenie\(_vladelec\(\)|== str\(_vladelec\(\)\)'),
    (edit_svyaz, 'svyaz.txt', r'kto = _fayl'),
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
                result = edits.apply((HERE / 'fixtures' / fixture).read_bytes(), module.EDITS).decode()
                self.assertIsNone(re.search(single, result))
                self.assertIn("ua_full_access", result)
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


if __name__ == '__main__':
    unittest.main()
