#!/usr/bin/env python3
"""Each edit applies once to the installed source (sanitized fixtures from LEAD-DESK-PROBE-20261112-R4, bezopasnost
re-checked unchanged by LEAD-DESK-PROBE-20261124) and leaves no single-owner path behind; a second run is refused."""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_bezopasnost  # noqa: E402
import edit_svyaz  # noqa: E402
import edits  # noqa: E402

CASES = (
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
                self.assertIn('ua_owners', result)
                with self.assertRaisesRegex(ValueError, 'FRAGMENT_NOT_UNIQUE'):
                    edits.apply(result.encode(), module.EDITS)

    def test_edited_files_compile(self):
        for module, fixture, _ in CASES:
            with self.subTest(module.NAME):
                source = (HERE / 'fixtures' / fixture).read_bytes()
                compile(stubbed(edits.apply(source, module.EDITS).decode()), module.NAME, 'exec')


if __name__ == '__main__':
    unittest.main()
