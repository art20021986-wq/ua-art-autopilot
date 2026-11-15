#!/usr/bin/env python3
"""VIN-KOREA-001: the auction lot source, its order with vPIC, and the CRM vocabulary.

The Sonata lot is the real entry of video/korea/lots.json (2026-11-15) for the VIN the owner typed; the vPIC rows are
real answers (the owner's Mercedes; the Korean VIN, which vPIC rejects). ai_filter and ai_fast_schema are the exact
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
import candidate_builder  # noqa: E402
import ua_vin_decode as decode  # noqa: E402
import ua_vin_lots as lots  # noqa: E402

KOREAN = 'KMHL141EBNA246813'
SONATA = {'id': '20261113041716', 'title': 'Hyundai Sonata', 'maker': 'Hyundai', 'trim': 'Premium Plus', 'year': 2022,
          'mileage_km': 80000, 'score': 'AC', 'engine_cc': 2000, 'fuel': 'gasoline', 'transmission': 'AT',
          'house': 'SK Rent Car Auction', 'lot_no': '0596', 'vin': KOREAN, 'photos': []}
VPIC_KOREAN = {'Make': '', 'ModelYear': '1992', 'ErrorCode': '1,5,14,400'}
MERCEDES = {'Model': 'E-Class', 'ModelYear': '2019', 'DisplacementCC': '2000', 'FuelTypePrimary': 'Gasoline',
            'TransmissionStyle': 'Automatic', 'DriveType': 'AWD/All-Wheel Drive', 'ErrorCode': '0'}


def photo_helper():
    own = {name: sys.modules.pop(name) for name in ('candidate_builder', 'release_constants') if name in sys.modules}
    sys.path.insert(0, str(ROOT / 'cloud/crm_photo_card_001'))
    try:
        import test_photo_card
    finally:
        sys.path.pop(0)
        sys.modules.update(own)
    return test_photo_card


def opener_for(row):
    def opener(url, timeout):
        return io.BytesIO(json.dumps({'Results': [row]}).encode())
    return opener


def failing_opener(url, timeout):
    raise OSError('offline')


class LotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'lots.json'
        self.path.write_text(json.dumps({'lots': [{'vin': 'KNABX511BCT120617', 'title': 'Kia Morning'}, SONATA]}))

    def test_exact_vin_only(self):
        self.assertEqual(lots.lot_of(KOREAN, self.path)['lot_no'], '0596')
        self.assertIsNone(lots.lot_of(KOREAN[:-1] + '4', self.path))

    def test_raw_fields_in_crm_codes(self):
        self.assertEqual(lots.raw_fields(SONATA), {'model': 'Sonata', 'year': 2022, 'engine_cc': 2000,
                                                   'mileage_km': 80000, 'fuel': 'gasoline', 'gearbox': 'at'})

    def test_unknown_values_left_out(self):
        lot = dict(SONATA, fuel='hydrogen', transmission='Semi AT', engine_cc=0, title='Hyundai', year=None)
        self.assertEqual(lots.raw_fields(lot), {'mileage_km': 80000})


class SourceOrderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher, _ = photo_helper().crm_modules(Path(temp.name))
        self.addCleanup(patcher.stop)
        self.path = Path(temp.name) / 'lots.json'
        self.path.write_text(json.dumps({'lots': [SONATA]}))
        patcher = patch.object(lots, 'LOTS', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_korean_vin_from_the_lot(self):
        self.assertEqual(decode.fields(KOREAN, opener_for(VPIC_KOREAN)),
                         {'model': 'Sonata', 'year': 2022, 'engine_cc': 2000, 'mileage_km': 80000,
                          'fuel': 'бензин', 'gearbox': 'автомат'})

    def test_lot_kept_when_vpic_is_offline(self):
        self.assertEqual(decode.fields(KOREAN, failing_opener)['model'], 'Sonata')

    def test_vin_without_lot_uses_vpic(self):
        self.assertEqual(decode.fields('WDDZF4KB1KA596783', opener_for(MERCEDES)),
                         {'model': 'E-Class', 'year': 2019, 'engine_cc': 2000, 'fuel': 'бензин', 'gearbox': 'автомат',
                          'drive': 'полный'})

    def test_lot_wins_and_vpic_adds_what_is_missing(self):
        self.path.write_text(json.dumps({'lots': [dict(SONATA, vin='WDDZF4KB1KA596783', year=2020)]}))
        got = decode.fields('WDDZF4KB1KA596783', opener_for(MERCEDES))
        self.assertEqual((got['model'], got['year'], got['drive'], got['mileage_km']), ('Sonata', 2020, 'полный', 80000))

    def test_missing_lot_file_and_offline_vpic_give_nothing(self):
        self.path.unlink()
        self.assertEqual(decode.fields(KOREAN, failing_opener), {})


class BuilderTests(unittest.TestCase):
    def test_pins(self):
        installed = (ROOT / 'cloud/crm_new_car_vin_002/ua_vin_decode.py').read_bytes()
        self.assertEqual(hashlib.sha256(installed).hexdigest(), candidate_builder.SOURCE_SHA256['ua_vin_decode.py'])

    def test_refuses_drift(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'ua_vin_decode.py': b'x'}, {})


if __name__ == '__main__':
    unittest.main()
