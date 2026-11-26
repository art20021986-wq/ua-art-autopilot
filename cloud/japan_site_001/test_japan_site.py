#!/usr/bin/env python3
"""JAPAN-STOCK-001 step 2: the exact edits on the live sources (fixtures: sanitized copies read by
JAPAN-STOCK-PROBE-20261126-R2 and the public home page), the country texts, the catalog card country and
status, the stage sync pill, and the country row in a browser-free check of the golden page."""
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_card_stage  # noqa: E402
import edit_catalog_guard  # noqa: E402
import edit_golden  # noqa: E402
import edit_home  # noqa: E402
import edit_site_counters  # noqa: E402
import edit_stage_sync  # noqa: E402
import edits  # noqa: E402

FIX = {'stranica.py': 'stranica.txt', 'master_card.py': 'master_card.txt',
       'catalog_design_guard.py': 'catalog_design_guard.txt', 'ua_site_counters.py': 'ua_site_counters.txt',
       'ua_stage_catalog_sync.py': 'ua_stage_catalog_sync.txt',
       'catalog_design_golden.html': 'catalog_design_golden.txt', 'video/index.html': 'index_public.txt'}
LIVE = {name: (HERE / 'fixtures' / file).read_text(encoding='utf-8') for name, file in FIX.items()}


def module(name, text, extra=None):
    folder = tempfile.mkdtemp()
    path = Path(folder) / (name + '.py')
    path.write_text(text, encoding='utf-8')
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {**(extra or {}), name: value}):
        spec.loader.exec_module(value)
    return value


def country_site(japan=()):
    fake = types.SimpleNamespace(country_of=lambda car_id: 'japan' if car_id in japan else 'korea',
                                 japan_ids=lambda: frozenset(japan))
    with patch.dict(sys.modules, {'ua_car_country': fake}):
        cs = module('ua_country_site', (HERE / 'ua_country_site.py').read_text(encoding='utf-8'))
    cs.country = lambda car, f=fake: f.country_of(car.get('id'))
    cs.japan_ids = fake.japan_ids
    return cs


class EditTests(unittest.TestCase):
    def test_every_anchor_once(self):
        cases = [(edit_card_stage.PAIRS[n], n) for n in ('stranica.py', 'master_card.py')]
        cases += [(e.PAIRS, e.NAME) for e in (edit_catalog_guard, edit_site_counters, edit_stage_sync, edit_golden,
                                               edit_home)]
        for pairs, name in cases:
            after = edits.replace_once(LIVE[name], pairs, name)
            with self.assertRaisesRegex(ValueError, 'EDIT_ANCHOR'):
                edits.replace_once(after, pairs, name)

    def test_card_builders_keep_stage_label_attribute(self):
        for name in ('stranica.py', 'master_card.py'):
            after = edits.replace_once(LIVE[name], edit_card_stage.PAIRS[name], name)
            self.assertIn('data-ua-stage-label="%s">%s</span>', after)
            self.assertIn('_ua_cs.current_stage(stage, details[stage - 1], _ua_country)', after)
        stranica = edits.replace_once(LIVE['stranica.py'], edit_card_stage.PAIRS['stranica.py'], 'stranica.py')
        self.assertNotIn('''c.append("<div class='chip'>%s</div>" % ekran(etap_tekst))''', stranica)

    def test_home_titles(self):
        after = edit_home.build(LIVE['video/index.html'].encode()).decode()
        self.assertIn('>Викуплені та перевірені в Кореї та Японії</b>', after)
        self.assertIn('>На поромі з Кореї та Японії до Грузії</b>', after)
        self.assertIn('data-ru="На пароме из Кореи и Японии в Грузию"', after)
        self.assertEqual(len(after) - len(LIVE['video/index.html']), sum(len(b) - len(a) for a, b in edit_home.PAIRS))


class TextTests(unittest.TestCase):
    def test_korean_texts_unchanged_and_new_chip(self):
        cs = country_site()
        self.assertEqual(cs.stage_chip({'id': 1}, 'Выкуплена · стоянка в Корее'),
                         "<div class='chip'>Выкуплена · стоянка в Корее</div>")
        self.assertEqual(cs.current_stage(1, 'Выкуплен · стоянка в Корее', 'korea'), ('🇰🇷', 'Выкуплен · стоянка в Корее'))
        self.assertEqual(cs.stage_name('Корея', 'korea'), 'Корея')
        self.assertIn(">🇰🇷 Автомобиль из Кореи<", cs.country_chip({'id': 1}))
        self.assertIn("data-uk='🇰🇷 Автомобіль з Кореї'", cs.country_chip({'id': 1}))

    def test_japan_texts(self):
        cs = country_site({5})
        self.assertIn(">🇯🇵 Автомобиль из Японии<", cs.country_chip({'id': 5}))
        self.assertIn("data-uk='Викуплена · стоянка в Японії'", cs.stage_chip({'id': 5}, 'Выкуплена · стоянка в Корее'))
        self.assertIn('На пароме · Япония → Грузия', cs.stage_chip({'id': 5}, 'На пароме · Корея → Грузия'))
        self.assertEqual(cs.stage_chip({'id': 5}, 'В Грузии · Поти/Батуми, оформление'),
                         "<div class='chip'>В Грузии · Поти/Батуми, оформление</div>")
        icon, text = cs.current_stage(1, 'Выкуплен · стоянка в Корее', 'japan')
        self.assertEqual(icon, '🇯🇵')
        self.assertIn('data-uk="Викуплений · стоянка в Японії"', text)
        self.assertEqual(cs.current_stage(3, 'Грузия · оформление', 'japan'), ('📋', 'Грузия · оформление'))
        self.assertIn('>Япония</span>', cs.stage_name('Корея', 'japan'))
        self.assertEqual(cs.stage_name('Паром', 'japan'), 'Паром')


class CatalogTests(unittest.TestCase):
    def guard(self, japan=()):
        text = edits.replace_once(LIVE['catalog_design_guard.py'], edit_catalog_guard.PAIRS, 'catalog_design_guard.py')
        return module('cdg_built', text, {'ua_country_site': country_site(japan)}), country_site(japan)

    def test_counters_and_shell_know_vykupleny(self):
        cdg, _ = self.guard()
        page = 'Выкуплены · 2 Викуплені · 2 Все · 3'
        counts = {'all': 9, 'kiev': 1, 'georgia': 1, 'sea': 1, 'korea': 6}
        self.assertEqual(cdg._update_counters(page, counts), 'Выкуплены · 6 Викуплені · 6 Все · 9')
        self.assertEqual(cdg._normalize_shell('Выкуплены · 2'), cdg._normalize_shell('Выкуплены · 7'))

    def test_golden_row_is_outside_the_filters(self):
        golden = edits.replace_once(LIVE['catalog_design_golden.html'], edit_golden.PAIRS, 'catalog_design_golden.html')
        cdg, _ = self.guard()
        audit = cdg.shell_audit(golden)
        self.assertEqual(audit['status'], 'PASS', audit)
        self.assertEqual(audit['filter_counts'], {k: 1 for k in ('all', 'kiev', 'georgia', 'sea', 'korea')})
        row = golden[golden.index('<div class="ua-country-row"'):golden.index('</div>', golden.index('<div class="ua-country-row"'))]
        self.assertNotIn('data-f', row)
        self.assertNotIn('filter-row', row)
        self.assertEqual(cdg._normalize_shell(golden), cdg._normalize_shell(cdg._update_counters(
            golden, {'all': 5, 'kiev': 1, 'georgia': 1, 'sea': 1, 'korea': 2})))
        self.assertIn('"Выкуплены","Викуплені"', golden)


    def test_build_catalog_with_a_japanese_car(self):
        golden = edits.replace_once(LIVE['catalog_design_golden.html'], edit_golden.PAIRS, 'catalog_design_golden.html')
        cdg, _ = self.guard(japan={2})
        rows = [{'id': 1, 'auto_number': 'UA-0001', 'status': 'kr_bought', 'published': 1, 'brand': 'Kia', 'model': 'K5',
                 'year': 2019, 'price_uah': 11500, 'vin': 'KNAGT41BBKA000001', 'photos': '[]'},
                {'id': 2, 'auto_number': 'UA-0002', 'status': 'kr_bought', 'published': 1, 'brand': 'Toyota',
                 'model': 'Aqua', 'year': 2018, 'price_uah': 9000, 'vin': '', 'photos': '[]'},
                {'id': 3, 'auto_number': 'UA-0003', 'status': 'sea_loaded', 'published': 1, 'brand': 'Kia', 'model': 'K3',
                 'year': 2018, 'price_uah': 9000, 'vin': '', 'photos': '[]'}]
        statuses = module('ua_delivery_status', (HERE / 'fixtures/ua_delivery_status.txt').read_text(encoding='utf-8'))
        with patch.dict(sys.modules, {'ua_delivery_status': statuses, 'ua_country_site': country_site({2})}):
            built = cdg.build_catalog(golden, rows, {r['auto_number']: '/x/%s.jpg' % r['auto_number'] for r in rows})
            self.assertEqual(cdg.audit_catalog(built, rows, golden)['status'], 'PASS')
        countries = sorted((code, c) for c, code in re.findall(r'<article\b[^>]*data-stage="(?:korea|sea)"[^>]*data-country="(\w+)"[^>]*>.*?'
                                    r'data-ua-card="(UA-\d+)"', built, re.S))
        self.assertEqual(countries, [('UA-0001', 'korea'), ('UA-0002', 'japan'), ('UA-0003', 'korea')])
        self.assertEqual(built.count('В Японии · выкуплен и проверен'), 2)  # data-ru and text
        self.assertEqual(built.count('В Корее · выкуплен и проверен'), 2)
        self.assertEqual(re.findall(r'data-f="korea"[^>]*>([^<]*)<', built), ['Выкуплены · 2'])


class StageSyncTests(unittest.TestCase):
    def sync(self, japan=()):
        text = edits.replace_once(LIVE['ua_stage_catalog_sync.py'], edit_stage_sync.PAIRS, 'ua_stage_catalog_sync.py')
        return module('scs_built', text)

    def test_pill_in_country(self):
        scs = self.sync()
        self.assertEqual(scs._phrase('В Корее · выкуплен и проверен', 1, 'ru', 'japan'), 'В Японии · выкуплен и проверен')
        self.assertEqual(scs._phrase('У Японії · викуплений', 1, 'uk', 'korea'), 'У Кореї · викуплений')
        self.assertEqual(scs._phrase('В Японии · выкуплен', 2, None, 'japan'), 'На пароме · выкуплен')
        self.assertEqual(scs._phrase('В Корее · x', 1), 'В Корее · x')


class CountersTests(unittest.TestCase):
    def test_labels(self):
        text = edits.replace_once(LIVE['ua_site_counters.py'], edit_site_counters.PAIRS, 'ua_site_counters.py')
        self.assertEqual(text.count("'korea':('Выкуплены','Викуплені')"), 1)
        self.assertNotIn("В Корее", text)


if __name__ == '__main__':
    unittest.main()
