#!/usr/bin/env python3
"""BOUGHT-WORD-001: the edits on the files installed by JAPAN-SITE-INSTALL (the catalog guard as built from its sanitized
fixture, ua_country_site.py from the repository) and the home title."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / 'japan_site_001'))
import edit_catalog_guard as step2_guard  # noqa: E402
import edit_home  # noqa: E402
import edit_labels  # noqa: E402
import edits  # noqa: E402

SITE = HERE.parent / 'japan_site_001'
GUARD = edits.replace_once((SITE / 'fixtures/catalog_design_guard.txt').read_text(encoding='utf-8'),
                           step2_guard.PAIRS, 'catalog_design_guard.py')
COUNTRY = (SITE / 'ua_country_site.py').read_text(encoding='utf-8')
STEP2_HOME = (SITE / 'fixtures/index_public.txt').read_text(encoding='utf-8')


class EditTests(unittest.TestCase):
    def test_labels_without_the_word(self):
        for name, text in (('catalog_design_guard.py', GUARD), ('ua_country_site.py', COUNTRY)):
            after = edits.replace_once(text, dict(edit_labels.EDITS)[name], name)
            self.assertNotIn('проверен', after)
            self.assertNotIn('перевірен', after)
            with self.assertRaisesRegex(ValueError, 'EDIT_ANCHOR'):
                edits.replace_once(after, dict(edit_labels.EDITS)[name], name)
        self.assertIn('1: ("В Корее · выкуплен", "У Кореї · викуплений"),',
                      edits.replace_once(GUARD, dict(edit_labels.EDITS)['catalog_design_guard.py'], 'x'))

    def test_home_title_from_the_installed_one(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('step2_home', SITE / 'edit_home.py')
        step2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(step2)
        installed = step2.build(STEP2_HOME.encode()).decode()
        after = edit_home.build(installed.encode()).decode()
        self.assertIn('>Викуплені в Кореї та Японії</b>', after)
        self.assertIn('data-ru="Выкуплены в Корее и Японии"', after)
        self.assertNotIn('перевірені', after)
        self.assertNotIn('проверены', after)
        self.assertNotIn('შემოწმებული"', after)
        self.assertIn('>На поромі з Кореї та Японії до Грузії</b>', after)


if __name__ == '__main__':
    unittest.main()
