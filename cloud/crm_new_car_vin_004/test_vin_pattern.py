#!/usr/bin/env python3
"""Similar cars: group VIN 1-8 + 10, only agreed fields, only without an exact lot; order with the other sources.

ua_vin_lots is the installed module (cloud/crm_new_car_vin_003, hash pinned); ai_filter and ai_fast_schema are the exact
installed modules (CRM-PHOTO-AUTOFILL-001 test helper).
"""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.append(str(ROOT / 'cloud/crm_new_car_vin_003'))  # installed ua_vin_lots (read only)
import candidate_builder  # noqa: E402
import ua_vin_decode as decode  # noqa: E402
import ua_vin_lots as lots  # noqa: E402
import ua_vin_pattern as pattern  # noqa: E402

VPIC_REJECTS = {'ErrorCode': '1,5,14,400', 'ModelYear': '1992'}


def lot(vin, **values):
    base = {'vin': vin, 'title': 'Hyundai Sonata', 'maker': 'Hyundai', 'year': 2022, 'engine_cc': 1999,
            'mileage_km': 50000, 'fuel': 'gasoline', 'transmission': 'AT'}
    return dict(base, **values)


GROUP = [lot('KMHL141EBNA100001'), lot('KMHL141EBNA100002', engine_cc=2000, mileage_km=90000),
         lot('KMHL141EBNA100003')]


def photo_helper():
    own = {name: sys.modules.pop(name) for name in ('candidate_builder', 'release_constants') if name in sys.modules}
    sys.path.insert(0, str(ROOT / 'cloud/crm_photo_card_001'))
    try:
        import test_photo_card
    finally:
        sys.path.pop(0)
        sys.modules.update(own)
    return test_photo_card


def opener(url, timeout):
    return io.BytesIO(json.dumps({'Results': [VPIC_REJECTS]}).encode())


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.lots_file = self.dir / 'lots.json'
        self.db = self.dir / 'archive.sqlite3'

    def fill(self, archived, week=()):
        self.lots_file.write_text(json.dumps({'lots': list(archived)}))
        lots.archive(self.lots_file, self.db)
        self.lots_file.write_text(json.dumps({'lots': list(week)}))


class PatternTests(Base):
    def test_group_is_vin_1_to_8_and_year_character(self):
        self.fill(GROUP + [lot('KMHL141EBPA100004'), lot('KMHL341DBNA100005')])
        self.assertEqual(sorted(l['vin'] for l in pattern.similar('KMHL141EBNA246813', self.db)),
                         [l['vin'] for l in GROUP])

    def test_agreed_fields_only_engine_1999_equals_2000_no_mileage(self):
        self.fill(GROUP)
        got = pattern.agreed(pattern.similar('KMHL141EBNA246813', self.db), lots.raw_fields)
        self.assertEqual(got, {'model': 'Sonata', 'year': 2022, 'fuel': 'gasoline', 'gearbox': 'at', 'engine_cc': 2000})

    def test_disagreement_leaves_the_field_out(self):
        self.fill([lot('KMHL141EBNA100001'), lot('KMHL141EBNA100002', fuel='lpg', engine_cc=1600)])
        got = pattern.agreed(pattern.similar('KMHL141EBNA246813', self.db), lots.raw_fields)
        self.assertNotIn('fuel', got)
        self.assertNotIn('engine_cc', got)
        self.assertEqual(got['model'], 'Sonata')

    def test_one_similar_lot_is_not_enough(self):
        self.fill(GROUP[:1])
        self.assertEqual(pattern.agreed(pattern.similar('KMHL141EBNA246813', self.db), lots.raw_fields), {})

    def test_no_archive_and_short_vin(self):
        self.assertEqual(pattern.similar('KMHL141EBNA246813', self.dir / 'none.sqlite3'), [])
        self.fill(GROUP)
        self.assertEqual(pattern.similar('ZVW30-1234567', self.db), [])


class OrderTests(Base):
    def setUp(self):
        super().setUp()
        patcher, _ = photo_helper().crm_modules(self.dir)
        self.addCleanup(patcher.stop)
        for name, value in (('LOTS', self.lots_file), ('ARCHIVE', self.db)):
            p = patch.object(lots, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_similar_cars_fill_a_vin_no_source_knows(self):
        self.fill(GROUP)
        self.assertEqual(decode.fields('KMHL141EBNA246813', opener),
                         {'model': 'Sonata', 'year': 2022, 'fuel': 'бензин', 'engine_cc': 2000, 'gearbox': 'автомат'})

    def test_exact_lot_wins_and_pattern_is_not_used(self):
        self.fill(GROUP + [lot('KMHL141EBNA246813', engine_cc=0, fuel='', mileage_km=80000)])
        got = decode.fields('KMHL141EBNA246813', opener)
        self.assertEqual(got.get('mileage_km'), 80000)
        self.assertNotIn('engine_cc', got)  # the exact lot has none; similar cars are not asked
        self.assertNotIn('fuel', got)

    def test_nothing_known(self):
        self.lots_file.write_text(json.dumps({'lots': []}))
        self.assertEqual(decode.fields('KMHL141EBNA246813', opener), {})


class BuilderTests(unittest.TestCase):
    def test_pins(self):
        installed = ROOT / 'cloud/crm_new_car_vin_003'
        for name, table in (('ua_vin_decode.py', candidate_builder.SOURCE_SHA256),
                            ('ua_vin_lots.py', candidate_builder.DEPENDENCY_SHA256)):
            self.assertEqual(hashlib.sha256((installed / name).read_bytes()).hexdigest(), table[name])

    def test_refuses_drift(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'ua_vin_decode.py': b'x'}, {})


if __name__ == '__main__':
    unittest.main()
