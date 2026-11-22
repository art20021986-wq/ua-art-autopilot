"""SEO-SITE-001 edits against copies of the live files (2026-11-22): korea.html, katalog.html, info.html,
ua_seo_metadata.py; the old card pages on a temporary root with a temporary CRM."""
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest

import candidate_builder
import edit_metadata
import korea_tags
import old_cards
import uk_head

F = Path(__file__).resolve().parent / 'fixtures'


def tag(page, pattern):
    found = re.findall(pattern, page)
    assert len(found) == 1, (pattern, found)
    return found[0]


class KoreaTests(unittest.TestCase):
    def test_share_tags_are_the_page_own(self):
        before = (F / 'korea_live.html').read_text(encoding='utf-8')
        after = korea_tags.build(before.encode()).decode()
        og = tag(after, r'<meta property="og:title"[^>]*>')
        self.assertIn('content="Аукціони Кореї онлайн — UA ART COMPANY"', og)
        self.assertIn('data-ru-content="Аукционы Кореи онлайн — UA ART COMPANY"', og)
        self.assertIn('data-ka-content="კორეის აუქციონები ონლაინ — UA ART COMPANY"', og)
        description = tag(after, r'<meta property="og:description" content="([^"]*)"')
        self.assertEqual(description, tag(after, r'<meta name="description" content="([^"]*)"'))
        self.assertEqual(tag(after, r'<meta property="og:url" content="([^"]*)"'), korea_tags.URL)
        self.assertNotIn('під ключ у Києві — UA ART COMPANY', after.split('</head>')[0])
        # Only the three share tags change.
        strip = lambda page: re.sub(r'<meta property="og:(?:title|description|url)"[^>]*>', '', page)
        self.assertEqual(strip(after), strip(before))
        with self.assertRaisesRegex(ValueError, 'KOREA_TAGS_ALREADY_OWN'):
            korea_tags.build(after.encode())


class UkHeadTests(unittest.TestCase):
    def check(self, name, title):
        before = (F / ('%s_live.html' % name)).read_text(encoding='utf-8')
        after = uk_head.build(before.encode()).decode()
        self.assertIn('<html lang="uk">', after)
        self.assertEqual(tag(after, r'<title[^>]*>([^<]*)</title>'), title)
        for pattern in (r'<meta name="description" content="([^"]*)" data-ru-content="([^"]*)" data-uk-content="([^"]*)"',):
            content, ru, uk = tag(after, pattern)
            self.assertEqual(content, uk)
        # The body (the switcher's source) is untouched.
        self.assertEqual(after.split('</head>', 1)[1], before.split('</head>', 1)[1])
        with self.assertRaisesRegex(ValueError, 'SOURCE_NOT_RUSSIAN'):
            uk_head.build(after.encode())
        return after

    def test_catalogue(self):
        after = self.check('katalog', 'Каталог авто в наявності й у дорозі — UA ART COMPANY')
        self.assertIn('<meta property="og:title" content="Каталог авто в наявності й у дорозі — UA ART COMPANY"', after)

    def test_terms(self):
        self.check('info', 'Умови купівлі та доставки авто — UA ART COMPANY')


class MetadataTests(unittest.TestCase):
    def test_lang_rule(self):
        before = (F / 'ua_seo_metadata.txt').read_text(encoding='utf-8')
        after = edit_metadata.build(before.encode()).decode()
        compile(after, 'ua_seo_metadata.py', 'exec')
        self.assertIn("    if name in ('katalog.html', 'info.html'):\n        lang = 'uk'", after)
        self.assertIn("    if name in ('podbor.html', 'katalog.html', 'info.html') and html and lang == 'uk':", after)
        self.assertEqual(len(after.splitlines()) - len(before.splitlines()), 2)
        with self.assertRaisesRegex(ValueError, 'METADATA_FRAGMENT'):
            edit_metadata.build(after.encode())


class OldCardsTests(unittest.TestCase):
    def root(self, crm=('UA-0001',), catalogue=''):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / 'video').mkdir()
        for name in ('UA-0007.html', 'UA-0007-de6e3ebe.html', 'UA-0007-diag.html', 'UA-0008.html', 'UA-0001.html',
                     'UA-0001-diag.html', 'UA-0070.html', 'UA-0007-x.html'):
            (root / 'video' / name).write_text('page', encoding='utf-8')
        (root / 'video' / 'katalog.html').write_text(catalogue, encoding='utf-8')
        with closing(sqlite3.connect(root / 'crm.db')) as connection:
            connection.execute('CREATE TABLE cars(auto_number TEXT)')
            connection.executemany('INSERT INTO cars VALUES(?)', [(c,) for c in crm])
            connection.commit()
        return root

    def test_only_the_four_codes(self):
        self.assertEqual(old_cards.find(self.root()), ('video/UA-0007-de6e3ebe.html', 'video/UA-0007-diag.html',
                                                       'video/UA-0007.html', 'video/UA-0008.html'))

    def test_code_back_in_crm_or_catalogue_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'CODE_STILL_LISTED:UA-0007'):
            old_cards.find(self.root(crm=('UA-0007',)))
        with self.assertRaisesRegex(ValueError, 'CODE_STILL_LISTED:UA-0019'):
            old_cards.find(self.root(catalogue='<a href="UA-0019.html">'))

    def test_builder_removes_them_and_edits_the_rest(self):
        root = self.root()
        for name, fixture in (('ua_seo_metadata.py', 'ua_seo_metadata.txt'), ('video/korea.html', 'korea_live.html'),
                              ('video/katalog.html', 'katalog_live.html'), ('video/info.html', 'info_live.html')):
            (root / name).write_bytes((F / fixture).read_bytes())
        names = candidate_builder.targets(root)
        result = candidate_builder.build({n: (root / n).read_bytes() for n in names})
        self.assertEqual(sorted(n for n, v in result.items() if v is None),
                         ['video/UA-0007-de6e3ebe.html', 'video/UA-0007-diag.html', 'video/UA-0007.html', 'video/UA-0008.html'])
        self.assertEqual(len([v for v in result.values() if v is not None]), 4)
        with self.assertRaisesRegex(ValueError, 'UNPLANNED'):
            candidate_builder.build({'video/UA-0001.html': b'x'})


if __name__ == '__main__':
    unittest.main()
