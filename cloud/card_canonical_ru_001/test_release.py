#!/usr/bin/env python3
"""The three CARD-CANONICAL-RU-001 edits. Fixtures: proverit as FINANCE-PROBE-20261103-R4 read it with the
CARD-CANONICAL-FIX-001 edit applied; ua_card_lang.py as CARD-LANG-PROBE-20261108 read it."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import candidate_builder
import edit_card_lang
import edit_guard
import edit_metadata

HERE = Path(__file__).resolve().parent
LIVE = (HERE / 'fixtures' / 'proverit.txt').read_text(encoding='utf-8')
CARD_LANG = (HERE / 'fixtures' / 'ua_card_lang.py').read_bytes()
ORIGIN = 'https://www.uaart.com.ua'
# Enough of master_card.py's own names for the check to run (stand-ins, not the live code).
PRELUDE = (HERE / 'fixtures' / 'prelude.txt').read_text(encoding='utf-8')


def checker(text):
    """The check as a module (stand-ins + the check text), imported from a temporary folder."""
    path = Path(tempfile.mkdtemp()) / 'proverit_check.py'
    path.write_text(PRELUDE + text, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('proverit_check_%d' % id(text), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.proverit


def card(canonical):
    return ('<link rel="canonical" href="%s"><a class="kn_kupit" href="#">Завдаток 500 $</a>'
            '<a href="UA-0013-diag.html">d</a>' % canonical)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.after = edit_guard.build(LIVE.encode()).decode()

    def test_russian_version_accepted_and_old_ones_kept(self):
        before, after = checker(LIVE), checker(self.after)
        self.assertIn('SEO068 canonical', before(card(ORIGIN + '/video/ru/UA-0013.html'), 'UA-0013'))
        for good in ('/video/ru/UA-0013.html', '/video/ua/UA-0013.html', '/video/UA-0013.html'):
            self.assertEqual(after(card(ORIGIN + good), 'UA-0013'), [])

    def test_everything_else_still_refused(self):
        after = checker(self.after)
        for wrong in (ORIGIN + '/video/ru/UA-0099.html', ORIGIN + '/video/en/UA-0013.html',
                      'https://evil.example/video/ru/UA-0013.html'):
            self.assertIn('SEO068 canonical', after(card(wrong), 'UA-0013'))
        two = card(ORIGIN + '/video/UA-0013.html') + '<link rel="canonical" href="%s/video/ru/UA-0013.html">' % ORIGIN
        self.assertIn('SEO068 canonical', after(two, 'UA-0013'))
        self.assertIn('SEO068 CTA', after(card(ORIGIN + '/video/ru/UA-0013.html').replace('Завдаток 500 $', 'x'), 'UA-0013'))

    def test_applied_edit_refused(self):
        with self.assertRaisesRegex(ValueError, 'GUARD_FRAGMENT'):
            edit_guard.build(self.after.encode())


class CardLangTests(unittest.TestCase):
    def module(self, source):
        path = Path(tempfile.mkdtemp()) / 'ua_card_lang_check.py'
        path.write_bytes(source)
        spec = importlib.util.spec_from_file_location('ua_card_lang_check_%d' % id(source), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_canonical_is_the_russian_version_only_when_both_exist(self):
        module = self.module(edit_card_lang.build(CARD_LANG))
        root = Path(tempfile.mkdtemp())
        self.assertEqual(module.canonical('UA-0013.html', root), ORIGIN + '/video/UA-0013.html')
        for folder in ('ua', 'ru'):
            (root / folder).mkdir()
            (root / folder / 'UA-0013.html').write_text('x')
        self.assertEqual(module.canonical('UA-0013.html', root), ORIGIN + '/video/ru/UA-0013.html')

    def test_only_the_canonical_changes(self):
        after = edit_card_lang.build(CARD_LANG).decode()
        removed = [l for l in CARD_LANG.decode().splitlines() if l not in after.splitlines()]
        self.assertEqual(removed, ['    """The canonical URL of a card: its Ukrainian version once it exists, else the card itself."""',
                                   "        return '%s/video/%s/%s' % (ORIGIN, DIRS['uk'], name)"])
        with self.assertRaisesRegex(ValueError, 'CARD_LANG_FRAGMENT'):
            edit_card_lang.build(after.encode())


class MetadataTests(unittest.TestCase):
    def test_revision_replaced_once(self):
        out = edit_metadata.build(b"X = 1\nSEO_REVISION = 'OWN-COUNTER-001'\nY = 2\n")
        self.assertEqual(out, b"X = 1\nSEO_REVISION = 'CARD-CANONICAL-RU-001'\nY = 2\n")
        for bad in (b'X = 1\n', b"SEO_REVISION = 'A'\nSEO_REVISION = 'B'\n"):
            with self.assertRaisesRegex(ValueError, 'METADATA_REVISION'):
                edit_metadata.build(bad)

    def test_candidate_has_the_three_files(self):
        source = {'ua_card_lang.py': CARD_LANG, 'master_card.py': LIVE.encode(),
                  'ua_seo_metadata.py': b"SEO_REVISION = 'SPEED-001'\n"}
        self.assertEqual(sorted(candidate_builder.build(source, {})), sorted(source))


if __name__ == '__main__':
    unittest.main()
