"""SEO-HOME-001 edits against copies of the live files (2026-11-19): ua_card_lang.py, ua_seo_metadata.py, the home
page, a card and its Ukrainian version."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

import candidate_builder
import edit_card_lang
import edit_metadata
import page_edits
from titles import NEW, OLD

F = Path(__file__).resolve().parent / 'fixtures'


def module(source, name):
    """Load the module text from a temporary file, as the server imports it."""
    folder = Path(tempfile.mkdtemp())
    (folder / (name + '.py')).write_bytes(source)
    spec = importlib.util.spec_from_file_location(name, folder / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class CardLangTests(unittest.TestCase):
    def test_absolute_sends_the_card_home(self):
        before = (F / 'ua_card_lang.txt').read_bytes()
        old, new = module(before, 'old_lang'), module(edit_card_lang.build(before), 'new_lang')
        card = (F / 'card_base_live.html').read_text(encoding='utf-8')
        result = new.absolute(card)
        self.assertNotIn(page_edits.LINK_OLD, result)
        self.assertEqual(result.count(page_edits.LINK_NEW), 2)
        # Nothing else changes.
        self.assertEqual(result, old.absolute(card).replace(page_edits.LINK_OLD, page_edits.LINK_NEW))

    def test_applied_or_missing_fragment_is_refused(self):
        after = edit_card_lang.build((F / 'ua_card_lang.txt').read_bytes())
        for source in (after, b'def absolute(source):\n    return source\n'):
            with self.assertRaisesRegex(ValueError, 'CARD_LANG_FRAGMENT'):
                edit_card_lang.build(source)


class MetadataTests(unittest.TestCase):
    def test_only_the_home_title_changes(self):
        before = (F / 'ua_seo_metadata.txt').read_text(encoding='utf-8')
        after = edit_metadata.build(before.encode()).decode()
        compile(after, 'ua_seo_metadata.py', 'exec')
        for lang in ('ru', 'uk'):
            self.assertNotIn("'%s'" % OLD[lang], after)
            self.assertEqual(after.count(NEW[lang]), 1)
        self.assertEqual(after.replace(NEW['ru'], OLD['ru']).replace(NEW['uk'], OLD['uk']), before)
        self.assertIn("SEO_REVISION = 'SPEED-001'", after)

    def test_applied_is_refused(self):
        after = edit_metadata.build((F / 'ua_seo_metadata.txt').read_bytes())
        with self.assertRaisesRegex(ValueError, 'METADATA_HOME_TITLE'):
            edit_metadata.build(after)

    def test_new_title_keeps_the_home_name(self):
        # page_name reads the canonical first; the title words «под заказ / замовлення» would name podbor.html.
        home = page_edits.home((F / 'index_live.html').read_bytes()).decode()
        self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua/video/index.html">', home)


class PageTests(unittest.TestCase):
    def test_home_title_everywhere_and_nothing_else(self):
        before = (F / 'index_live.html').read_text(encoding='utf-8')
        after = page_edits.home(before.encode()).decode()
        self.assertEqual((after.count(NEW['ru']), after.count(NEW['uk'])), (2, 4))
        self.assertFalse(any(OLD[lang] in after for lang in OLD))
        self.assertEqual(after.replace(NEW['ru'], OLD['ru']).replace(NEW['uk'], OLD['uk']), before)
        self.assertIn('>%s</title>' % NEW['uk'], after)
        self.assertIn('property="og:title" content="%s"' % NEW['uk'], after)
        with self.assertRaisesRegex(ValueError, 'HOME_TITLE_STATE'):
            page_edits.home(after.encode())

    def test_card_link_home(self):
        before = (F / 'card_ua_live.html').read_text(encoding='utf-8')
        after = page_edits.card(before.encode()).decode()
        self.assertEqual(after.count(page_edits.LINK_NEW), 2)
        self.assertEqual(after.replace(page_edits.LINK_NEW, page_edits.LINK_OLD), before)
        with self.assertRaisesRegex(ValueError, 'CARD_LINK_COUNT'):
            page_edits.card(after.encode())


class BuilderTests(unittest.TestCase):
    def test_targets_and_build(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        card = (F / 'card_ua_live.html').read_bytes()
        for name, value in (('ua_card_lang.py', (F / 'ua_card_lang.txt').read_bytes()),
                            ('ua_seo_metadata.py', (F / 'ua_seo_metadata.txt').read_bytes()),
                            ('video/index.html', (F / 'index_live.html').read_bytes()),
                            ('video/ua/UA-0001.html', card), ('video/ru/UA-0001.html', card),
                            ('video/ru/UA-0002.html', card.replace(page_edits.LINK_OLD.encode(), page_edits.LINK_NEW.encode())),
                            ('video/UA-0001.html', card), ('video/ua/UA-0001-diag.html', card)):
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(value)
        names = candidate_builder.targets(root)
        self.assertEqual(names, ('ua_card_lang.py', 'ua_seo_metadata.py', 'video/index.html',
                                 'video/ua/UA-0001.html', 'video/ru/UA-0001.html'))
        result = candidate_builder.build({n: (root / n).read_bytes() for n in names})
        self.assertEqual(set(result), set(names))
        self.assertTrue(all(result[n] != (root / n).read_bytes() for n in names))

    def test_no_card_versions_is_refused(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        with self.assertRaisesRegex(ValueError, 'NO_CARD_VERSIONS'):
            candidate_builder.targets(root)


if __name__ == '__main__':
    unittest.main()
