#!/usr/bin/env python3
"""FINANCE-OTP-001 on the live landing generator (FINANCE-001 fixture + FINANCE-001, SEO-HEADER-001, SEO-NAV-001 edits)."""
import hashlib
import importlib
import importlib.util
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CLOUD = HERE.parent
FIXTURES = CLOUD / 'finance_001' / 'fixtures'
MODULES = Path(tempfile.mkdtemp())
for name in ('ua_seo_order_models', 'ua_seo_quick_form', 'ua_seo_schema'):
    (MODULES / (name + '.py')).write_bytes((FIXTURES / (name + '.txt')).read_bytes())
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(CLOUD / 'seo_header_001'))
sys.path.insert(2, str(MODULES))
import candidate_builder  # noqa: E402
import logo_assets  # noqa: E402

FINANCE = ('seo/ua/kredyt-lizynh-avto.html', 'seo/ru/kredit-lizing-avto.html')
WIDGET = ('<script defer src="https://widgets.ponova.com.ua/embed/v1.js" data-key="2456" '
          'data-height-desktop="434" data-height-mobile="722"></script>')
LEASING = ('href="https://t.me/ulf_agent_bot?start=387da37d-92d7-4a21-8c69-13c14030906d=site" target="_blank" '
           'rel="sponsored noopener" data-finance-partner="hapai-leasing"')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def landings():
    source = (FIXTURES / 'ua_seo_landings.txt').read_bytes()
    for package in ('finance_001', 'seo_header_001', 'seo_nav_001'):
        source = load(package + '_edit', CLOUD / package / 'edit_landings.py').build(source)
    return source


def pages(finance_modules):
    """Every landing page rendered with the live generator and the given finance modules."""
    folder = Path(tempfile.mkdtemp())
    (folder / 'ua_seo_landings.py').write_bytes(landings())
    for name, value in finance_modules.items():
        (folder / name).write_bytes(value)
    sys.path.insert(0, str(folder))
    for name in ('ua_seo_landings', 'ua_finance_partners', 'ua_seo_finance'):
        sys.modules.pop(name, None)
    try:
        return importlib.import_module('ua_seo_landings').pages([], (), frozenset())
    finally:
        sys.path.remove(str(folder))


class Tags(HTMLParser):
    """Checks the page is well nested and collects ids."""
    VOID = {'meta', 'link', 'img', 'br', 'input', 'source'}

    def __init__(self):
        super().__init__()
        self.stack, self.ids = [], []

    def handle_starttag(self, tag, attrs):
        self.ids += [v for k, v in attrs if k == 'id']
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, tag


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        live = {name: (CLOUD / 'finance_001' / name).read_bytes() for name in candidate_builder.MODULES}
        cls.candidate = candidate_builder.build(live, {})
        cls.before = pages(live)
        cls.after = pages({k: v for k, v in cls.candidate.items() if k.endswith('.py')})

    def test_only_finance_pages_change(self):
        self.assertEqual(sorted(self.before), sorted(self.after))
        changed = sorted(name for name in self.after if self.before[name] != self.after[name])
        self.assertEqual(changed, sorted(FINANCE))

    def test_sections_widget_and_leasing_link(self):
        for name in FINANCE:
            page = self.after[name]
            self.assertEqual(page.count(WIDGET), 1, name)
            self.assertEqual(page.count(LEASING), 1, name)
            self.assertLess(page.index('id="kredyt"'), page.index(WIDGET))
            self.assertLess(page.index(WIDGET), page.index('id="lizynh"'))
            self.assertLess(page.index('id="lizynh"'), page.index(LEASING))
            self.assertIn('<a href="#kredyt">', page)
            self.assertIn('<a href="#lizynh">', page)
            self.assertIn('src="/video/finance/otp-bank.png" alt="OTP Bank" width="480" height="126"', page)
            self.assertIn('--acc:#52AE30', page)
            self.assertIn('<header class="site-header">', page)
            parser = Tags()
            parser.feed(page)
            self.assertEqual(parser.stack, [], name)
            self.assertEqual(len(parser.ids), len(set(parser.ids)), name)

    def test_seo_head(self):
        for name, lang in zip(FINANCE, ('uk', 'ru')):
            page = self.after[name]
            title = re.search(r'<title>(.*?)</title>', page).group(1)
            desc = re.search(r'<meta name="description" content="(.*?)">', page).group(1)
            self.assertLessEqual(len(title), 60)
            self.assertLessEqual(len(desc), 160)
            self.assertIn('ОТП Банк', title)
            self.assertEqual(page.count('<h1>'), 1)
            self.assertIn('<link rel="canonical" href="https://www.uaart.com.ua/video/%s">' % name, page)
            self.assertIn('hreflang="uk"', page)
            self.assertIn('hreflang="ru"', page)
            graph = json.loads(re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', page).group(1))['@graph']
            offers = [n for n in graph if n['@type'] == 'LoanOrCredit']
            self.assertEqual([o['provider']['@type'] for o in offers], ['BankOrCreditUnion', 'Organization'])
            self.assertTrue(offers[0]['url'].endswith('#kredyt') and offers[1]['url'].endswith('#lizynh'))
            faq = next(n for n in graph if n['@type'] == 'FAQPage')['mainEntity']
            for item in faq:  # structured questions are exactly the visible ones
                self.assertIn('<h3>%s</h3>' % item['name'], page)

    def test_other_modules_keep_their_data(self):
        sys.modules.pop('ua_finance_partners', None)
        new = load('new_partners', HERE / 'ua_finance_partners.py')
        old = load('old_partners', CLOUD / 'finance_001' / 'ua_finance_partners.py')
        for key in ('SLUG', 'DIRS', 'BUTTON'):
            self.assertEqual(getattr(new, key), getattr(old, key))
        self.assertEqual(new.page_path('ka'), old.page_path('ka'))
        self.assertEqual(new.partner('hapai-leasing')['href'], old.partner('hapai-leasing')['href'])
        self.assertEqual(new.partner('otp-credit')['name'], 'ОТП Банк')

    def test_logo_and_refusal_of_changed_live_module(self):
        logo = logo_assets.FILES['video/finance/otp-bank.png']
        self.assertEqual(logo[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(int.from_bytes(logo[16:20], 'big'), 480)
        self.assertEqual(int.from_bytes(logo[20:24], 'big'), 126)
        live = {name: (CLOUD / 'finance_001' / name).read_bytes() for name in candidate_builder.MODULES}
        live['ua_seo_finance.py'] += b'\n# someone else\n'
        with self.assertRaisesRegex(ValueError, 'LIVE_MODULE_CHANGED'):
            candidate_builder.build(live, {})


if __name__ == '__main__':
    unittest.main()
