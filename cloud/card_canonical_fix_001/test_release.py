#!/usr/bin/env python3
"""The check edit on master_card.py's proverit as FINANCE-PROBE-20261103-R4 read it (lines 1906-1939)."""
from pathlib import Path
import re
import unittest

import candidate_builder
import edit_guard

HERE = Path(__file__).resolve().parent
LIVE = (HERE / 'fixtures' / 'proverit.txt').read_text(encoding='utf-8')
ORIGIN = 'https://www.uaart.com.ua'
# Enough of master_card.py's own names for the check to run (stand-ins, not the live code).
PRELUDE = (HERE / 'fixtures' / 'prelude.txt').read_text(encoding='utf-8')


def checker(text):
    scope = {}
    exec(PRELUDE + text, scope)
    return scope['proverit']


def card(canonical):
    return ('<link rel="canonical" href="%s"><a class="kn_kupit" href="#">Завдаток 500 $</a>'
            '<a href="UA-0013-diag.html">d</a>' % canonical)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.after = candidate_builder.build({edit_guard.NAME: LIVE.encode()}, {})[edit_guard.NAME].decode()

    def test_language_version_canonical_accepted(self):
        before, after = checker(LIVE), checker(self.after)
        self.assertIn('SEO068 canonical', before(card(ORIGIN + '/video/ua/UA-0013.html'), 'UA-0013'))
        self.assertEqual(after(card(ORIGIN + '/video/ua/UA-0013.html'), 'UA-0013'), [])
        self.assertEqual(after(card(ORIGIN + '/video/UA-0013.html'), 'UA-0013'), [])

    def test_everything_else_still_refused(self):
        after = checker(self.after)
        for wrong in (ORIGIN + '/video/ru/UA-0013.html', ORIGIN + '/video/ua/UA-0099.html', 'https://evil.example/video/ua/UA-0013.html'):
            self.assertIn('SEO068 canonical', after(card(wrong), 'UA-0013'))
        two = card(ORIGIN + '/video/UA-0013.html') + '<link rel="canonical" href="%s/video/ua/UA-0013.html">' % ORIGIN
        self.assertIn('SEO068 canonical', after(two, 'UA-0013'))
        self.assertIn('SEO068 CTA', after(card(ORIGIN + '/video/ua/UA-0013.html').replace('Завдаток 500 $', 'x'), 'UA-0013'))

    def test_only_the_canonical_lines_change(self):
        removed = [l for l in LIVE.splitlines() if l not in self.after.splitlines()]
        self.assertEqual(removed, ['        if canonicals != [expected]:'])
        with self.assertRaisesRegex(ValueError, 'GUARD_FRAGMENT'):
            edit_guard.build(edit_guard.NAME, self.after.encode())


if __name__ == '__main__':
    unittest.main()
