#!/usr/bin/env python3
"""SERVICE-WORDS-001: the candidate on the live pages (fetched 2026-11-12) and the installed module chain."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_service_words as W  # noqa: E402

F = HERE / 'fixtures'
PAGES = sorted(p.name for p in (F / 'pages').glob('*.html'))


def page_name(fixture):
    """Fixture file names are the site paths with '/' as '__'."""
    return fixture.replace('__', '/')


def source():
    value = {page_name(n): (F / 'pages' / n).read_bytes() for n in PAGES}
    value['site_ge_inject.py'] = (F / 'site_ge_inject.txt').read_bytes()
    value['ua_seo_landings.py'] = (F / 'ua_seo_landings.txt').read_bytes()
    value['catalog_design_golden.html'] = value['video/katalog.html']
    return value


class Release(unittest.TestCase):
    def setUp(self):
        self.source = source()
        self.result = candidate_builder.build(self.source, {})

    def test_no_word_left_on_any_live_page(self):
        self.assertGreaterEqual(len(PAGES), 10)
        for name, value in self.source.items():
            if not name.endswith('.html'):
                continue
            after = self.result.get(name, value).decode('utf-8')
            self.assertFalse(W.has_word(after), (name, W.WORD.search(after) and after[W.WORD.search(after).start() - 80:][:160]))
            self.assertEqual(W.apply(after), after)

    def test_approved_wording(self):
        home = self.result['video/index.html'].decode()
        self.assertIn('data-ru="Заказать авто" data-uk="Замовити авто" data-ka="ავტომობილის შეკვეთა">Замовити авто<', home)
        self.assertIn('Супровід, доставка та оформлення автомобілів', home)
        self.assertIn('href="podbor.html"', home)  # the address stays
        catalog = self.result['video/katalog.html'].decode()
        self.assertIn('Замовте автомобіль із закордонних аукціонів — ми супроводимо його до Києва', catalog)
        landing = self.result.get('video/seo/ru/avto-pod-zakaz-kiev.html', b'').decode()
        self.assertIn('Проверяем историю и отчёт аукциона выбранного автомобиля', landing)
        self.assertIn('депозит 500 $', landing)  # the 500 $ deposit stays (owner)

    def test_prepayment_instead_of_deposit(self):
        home = self.result['video/index.html'].decode()
        for words in ('депозит — 1 000', 'Депозит 1 000', 'დეპოზიტი — 1 000', 'დეპოზიტი 1 000'):
            self.assertNotIn(words, home)
        self.assertIn('data-uk="Оплата на цьому кроці: послуга — 600 $, передоплата — 1 000 $"', home)
        self.assertIn('Передоплата 1 000 $ зараховується у вартість авто', home)
        self.assertIn('Предоплата 1 000 $ засчитывается в стоимость авто', home)

    def test_only_listed_phrases_change(self):
        for name, value in self.source.items():
            if name not in self.result or not name.endswith('.html'):
                continue
            before = value.decode('utf-8')
            for old, new in W.PAIRS:
                before = before.replace(old, new)
            self.assertEqual(before, self.result[name].decode('utf-8'), name)

    def test_pairs_ordered_longest_first(self):
        olds = [old for old, _ in W.PAIRS]
        for i, old in enumerate(olds):
            for later in olds[i + 1:]:
                self.assertFalse(old in later and old != later, (old, later))

    def test_tails_and_refusal(self):
        inject = self.result['site_ge_inject.py'].decode()
        self.assertTrue(inject.rstrip().endswith('return ua_service_words.apply(_ua_service_base_inject(source))'))
        self.assertIn('_ua_terms_base_inject = inject_html', inject)  # the earlier chain stays before it
        landings = self.result['ua_seo_landings.py'].decode()
        self.assertIn('_ua_service_base_pages = pages', landings)
        for name in ('site_ge_inject.py', 'ua_seo_landings.py'):
            compile(self.result[name], name, 'exec')
            with self.assertRaisesRegex(ValueError, 'SERVICE_ALREADY_APPLIED'):
                candidate_builder.edit(name, self.result[name])

    def load(self, folder, name, base):
        """The appended tail run on top of a stand-in base definition, imported as a module."""
        code = self.result[name].decode()
        path = Path(folder) / ('chain_' + name)
        path.write_text(base + code[code.index('# SERVICE-WORDS-001'):], encoding='utf-8')
        spec = importlib.util.spec_from_file_location('chain_' + name[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_chains_run(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'ua_service_words.py').write_bytes(self.result['ua_service_words.py'])
            sys.path.insert(0, folder)
            try:
                inject = self.load(folder, 'site_ge_inject.py',
                                   'def inject_html(source):\n    return source + "<b>Подобрать авто</b>"\n')
                self.assertEqual(inject.inject_html('<p>'), '<p><b>Заказать авто</b>')
                landings = self.load(folder, 'ua_seo_landings.py',
                                     'def pages(*a, **k):\n    return {"seo/ua/x.html": "<p>Викуп і підбір</p>"}\n')
                self.assertEqual(landings.pages([], set(), set()), {'seo/ua/x.html': '<p>Викуп на аукціоні</p>'})
            finally:
                sys.path.remove(folder)

    def test_untouched(self):
        for html in ('<a href="podbor.html">k</a>', '<p>депозит 500 $</p>', '<p>Подробнее</p>'):
            self.assertEqual(W.apply(html), html)


if __name__ == '__main__':
    unittest.main()
