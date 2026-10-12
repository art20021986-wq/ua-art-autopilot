#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as a  # noqa: E402
from fixture_public import CATALOG, PRICES  # noqa: E402


K5 = {'auto_number': 'UA-0022', 'brand': 'Kia', 'model': 'K5', 'year': '2020', 'mileage_km': 167007,
      'engine_cc': 1999, 'fuel': 'LPI', 'gearbox': 'Автомат', 'vin': 'KNAG741BBLA032716',
      'price_uah': 21200, 'price_georgia': None, 'published': 1, 'status': 'kr_bought',
      'photos': json.dumps(['f%d' % i for i in range(59)]), 'hidden_photos': '[]'}

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.fragment = a.catalog_articles(CATALOG)['UA-0022']

    def test_catalog_card_matches_crm(self):
        car = a.audit_car(K5, None, self.fragment, PRICES)
        for name in ('catalog_fields', 'catalog_photo_count', 'price_catalog', 'price_live_json'):
            self.assertEqual(car[name]['result'], 'PASS', (name, car[name]))
        self.assertEqual(car['card_page_fields']['result'], 'SKIP')
        self.assertEqual(car['stage']['result'], 'SKIP')

    def test_each_mismatch_is_reported(self):
        changed = dict(K5, price_uah=21500, mileage_km=167008, photos=json.dumps(['x']))
        car = a.audit_car(changed, None, self.fragment, PRICES)
        self.assertIn('UA price', car['price_catalog']['reason'])
        self.assertIn('mileage', car['catalog_fields']['reason'])
        self.assertIn('photo count', car['catalog_photo_count']['reason'])

    def test_summary_finds_missing_extra_and_orphans(self):
        cards = [K5, dict(K5, auto_number='UA-0099', vin='X'), dict(K5, auto_number='UA-0050', published=0)]
        report = a.audit(cards, CATALOG, {}, PRICES, served={'video/katalog.html': False},
                         page_files=['UA-0008.html', 'UA-0022.html', 'katalog.html'])
        s = report['summary']
        self.assertEqual(s['missing_from_catalog'], ['UA-0099'])
        self.assertIn('UA-0001', s['catalog_not_in_crm'])
        self.assertEqual(s['card_pages_without_crm_car'], ['UA-0008.html'])
        self.assertEqual(s['served_bytes_differ_from_server'], ['video/katalog.html'])
        self.assertEqual([c['code'] for c in report['cars']], ['UA-0022', 'UA-0099'])

    def test_stage_and_description_from_card_page(self):
        page = ('<div class="etap proshel">Корея</div><div class="etap tut"><span class="krug">2</span>'
                ' В пути морем</div><p>Отличное состояние</p>')
        frag = '<article class="catalog-card" data-stage="sea"><div class="status-pill">Морем</div></article>'
        car = a.audit_car(dict(K5, description='Отличное  состояние'), page, frag, {})
        self.assertEqual(car['description']['result'], 'PASS')
        self.assertEqual(car['stage']['detail']['card_current_step'], '2 В пути морем')
        self.assertEqual(car['stage']['detail']['catalog_stage'], ['sea'])

if __name__ == '__main__':
    unittest.main()
