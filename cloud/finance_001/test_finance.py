#!/usr/bin/env python3
"""FINANCE-001: partners data, the finance landing page, the CRM bot screen and the cars_ui edit."""
from contextlib import closing
import importlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(FIXTURES))
import edit_cars_ui  # noqa: E402
import edit_landings  # noqa: E402
import ua_finance_crm  # noqa: E402
import ua_finance_partners as finance  # noqa: E402

LINK = 'https://t.me/ulf_agent_bot?start=387da37d-92d7-4a21-8c69-13c14030906d=site'


def landings():
    """The live generator with this release's edit, imported from a temporary folder."""
    folder = tempfile.mkdtemp()
    Path(folder, 'ua_seo_landings.py').write_bytes(edit_landings.build((FIXTURES / 'ua_seo_landings.py').read_bytes()))
    sys.path.insert(0, folder)
    sys.modules.pop('ua_seo_landings', None)
    try:
        return importlib.import_module('ua_seo_landings')
    finally:
        sys.path.remove(folder)


class PartnersTests(unittest.TestCase):
    def test_owner_link_unchanged_and_ids_unique(self):
        self.assertEqual(finance.partner('hapai-leasing')['href'], LINK)
        ids = [p['id'] for p in finance.PARTNERS]
        self.assertEqual(len(ids), len(set(ids)))
        for p in finance.PARTNERS:
            self.assertIn(p['kind'], finance.KINDS)
            self.assertTrue(p['uk']['cta'] and p['ru']['cta'])

    def test_page_path_per_language(self):
        self.assertEqual(finance.page_path('uk'), '/video/seo/ua/kredyt-lizynh-avto.html')
        self.assertEqual(finance.page_path('ru'), '/video/seo/ru/kredit-lizing-avto.html')
        self.assertEqual(finance.page_path('ka'), finance.page_path('uk'))


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = landings()
        cls.pages = cls.L.pages([], (), frozenset())

    def test_both_languages_written_with_seo_head(self):
        for lang, other in (('uk', 'ru'), ('ru', 'uk')):
            html = self.pages[finance.page_path(lang)[len('/video/'):]]
            self.assertIn('<html lang="%s">' % lang, html)
            self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua%s">' % finance.page_path(lang), html)
            self.assertIn('hreflang="%s" href="https://www.uaart.com.ua%s"' % (other, finance.page_path(other)), html)
            self.assertIn('<h1>%s</h1>' % finance.PAGE[lang]['h1'], html)
            self.assertEqual(html.count('<title>'), 1)
            self.assertIn('"@type":"LoanOrCredit"', html)
            self.assertIn('"@type":"BreadcrumbList"', html)
            self.assertIn("/ua/a.js?v=1", html)

    def test_partner_link_is_sponsored_and_counted(self):
        html = self.pages['seo/ua/kredyt-lizynh-avto.html']
        self.assertIn('href="%s" target="_blank" rel="sponsored noopener" data-finance-partner="hapai-leasing"'
                      % LINK.replace('&', '&amp;'), html)
        self.assertIn('Розрахувати лізинг', html)
        self.assertIn('alt="ХАПАЙ Авто"', html)

    def test_other_pages_unchanged(self):
        names = {k for k in self.pages if 'kred' not in k}
        self.assertTrue(names)
        self.assertEqual(len(self.pages) - len(names), 2)

    def test_edit_refused_twice(self):
        once = edit_landings.build((FIXTURES / 'ua_seo_landings.py').read_bytes())
        with self.assertRaisesRegex(ValueError, 'LANDINGS_FRAGMENT_NOT_UNIQUE'):
            edit_landings.build(once)


class CrmTests(unittest.TestCase):
    def database(self, rows):
        path = Path(tempfile.mkdtemp(), 'analytics.db')
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, eid TEXT, sid TEXT, vid TEXT, ts INTEGER, tip TEXT, '
                       'stranica TEXT, avto TEXT, znachenie TEXT)')
            db.executemany('INSERT INTO events(ts,tip,stranica,znachenie) VALUES(?,?,?,?)', rows)
        return path

    def test_counts_and_latest(self):
        now = 1_793_000_000  # 2026-10-26
        page = '/video/seo/ua/kredyt-lizynh-avto.html'
        path = self.database([
            (now - 60, 'finance', page + '?card=UA-0013', 'hapai-leasing'),
            (now - 3 * 86400, 'finance', page + '?model=kia-k5&strana=korea', 'hapai-leasing'),
            (now - 40 * 86400, 'finance', page, 'hapai-leasing'),
            (now - 30, 'telegram', page, 'Розрахувати лізинг')])
        text = ua_finance_crm.report(now, path)
        self.assertIn('<b>ХАПАЙ Авто</b> — Сегодня: 1 · 7 дней: 2 · 30 дней: 2', text)
        self.assertIn('карточка UA-0013', text)
        self.assertIn('подбор: Kia K5', text)
        self.assertEqual(text.count('ХАПАЙ Авто,'), 2)

    def test_empty(self):
        self.assertIn('переходов пока нет', ua_finance_crm.report(1_793_000_000, self.database([])))


class CarsUiTests(unittest.TestCase):
    SOURCE = ('def clients_screen():\n    rows = []\n'
              '    rows.append([InlineKeyboardButton("Заявки из бота", callback_data="crm_leads")])\n\n'
              'def register(app):\n    pass\n')

    def test_button_and_register_block(self):
        text = edit_cars_ui.build('cars_ui.py', self.SOURCE.encode()).decode()
        self.assertLess(text.index('ua_finance_crm.BUTTON'), text.index('"Заявки из бота"'))
        self.assertTrue(text.rstrip().endswith("log.warning('ua_finance_crm не подключён: %s', e)"))
        compile(text, 'cars_ui.py', 'exec')
        with self.assertRaisesRegex(ValueError, 'CARS_UI_FRAGMENT'):
            edit_cars_ui.build('cars_ui.py', text.encode())


if __name__ == '__main__':
    unittest.main()
