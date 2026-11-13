#!/usr/bin/env python3
"""NEW-CAR-VIN-SPEC: vPIC answers -> CRM fields, and the VIN input creates the card with them.

vPIC rows are real answers read on 2026-11-13 (the owner's Mercedes, a Honda, an unknown European Mercedes).
photo_card, ai_filter and ai_fast_schema are the exact installed modules (CRM-PHOTO-AUTOFILL-001 test helper);
telegram and db are stubs.
"""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_vin_decode as decode  # noqa: E402

VIN = 'WDDZF4KB1KA596783'
MERCEDES = {'Make': 'MERCEDES-BENZ', 'Model': 'E-Class', 'ModelYear': '2019', 'DisplacementCC': '2000',
            'DisplacementL': '2', 'FuelTypePrimary': 'Gasoline', 'TransmissionStyle': 'Automatic',
            'DriveType': 'AWD/All-Wheel Drive', 'ErrorCode': '0', 'ElectrificationLevel': ''}
HONDA = {'Make': 'HONDA', 'Model': 'Accord', 'ModelYear': '2003', 'DisplacementCC': '2998.832712',
         'FuelTypePrimary': 'Gasoline', 'TransmissionStyle': 'Automatic', 'DriveType': '', 'ErrorCode': '0'}
UNKNOWN = {'Make': 'MERCEDES-BENZ', 'ModelYear': '2002', 'ErrorCode': '1,8'}
CRM = {'model': 'E-Class', 'year': 2019, 'engine_cc': 2000, 'fuel': 'бензин', 'gearbox': 'автомат', 'drive': 'полный'}


def photo_helper():
    """The CRM-PHOTO-AUTOFILL-001 test module (exact installed CRM modules), imported under its own name."""
    own = {name: sys.modules.pop(name) for name in ('candidate_builder', 'release_constants') if name in sys.modules}
    sys.path.insert(0, str(ROOT / 'cloud/crm_photo_card_001'))
    try:
        import test_photo_card  # binds the photo package's candidate_builder inside that module
    finally:
        sys.path.pop(0)
        sys.modules.update(own)
    return test_photo_card


def opener_for(row, calls=None):
    def opener(url, timeout):
        if calls is not None:
            calls.append((url, timeout))
        return io.BytesIO(json.dumps({'Results': [row]}).encode())
    return opener


class Message:
    def __init__(self, text=''):
        self.text, self.replies, self.edits = text, [], []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return self

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class CrmTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher, _ = photo_helper().crm_modules(Path(temp.name))
        self.addCleanup(patcher.stop)
        self.ai_filter = sys.modules['ai_filter']

    def test_owner_mercedes_fills_every_main_field(self):
        calls = []
        self.assertEqual(decode.fields(VIN, opener_for(MERCEDES, calls)), CRM)
        self.assertEqual(calls, [('https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/%s?format=json' % VIN, 8.0)])

    def test_rounding_and_missing_values(self):
        self.assertEqual(decode.fields('1HGCM82633A004352', opener_for(HONDA)),
                         {'model': 'Accord', 'year': 2003, 'engine_cc': 2999, 'fuel': 'бензин', 'gearbox': 'автомат'})

    def test_unclean_decode_gives_nothing(self):
        self.assertEqual(decode.fields('WDD2452322J660244', opener_for(UNKNOWN)), {})

    def test_vocabulary_codes(self):
        cases = [({'TransmissionStyle': 'Manual/Standard'}, {'gearbox': 'механика'}),
                 ({'TransmissionStyle': 'Continuously Variable Transmission (CVT)'}, {'gearbox': 'вариатор'}),
                 ({'TransmissionStyle': 'Dual-Clutch Transmission (DCT)'}, {'gearbox': 'робот'}),
                 ({'TransmissionStyle': 'Automated Manual Transmission (AMT)'}, {'gearbox': 'робот'}),
                 ({'DriveType': 'FWD/Front-Wheel Drive'}, {'drive': 'передний'}),
                 ({'DriveType': 'RWD/Rear-Wheel Drive'}, {'drive': 'задний'}),
                 ({'DriveType': '4WD/4-Wheel Drive/4x4'}, {'drive': 'полный'}),
                 ({'DriveType': '4x2'}, {}),
                 ({'FuelTypePrimary': 'Diesel'}, {'fuel': 'дизель'}),
                 ({'FuelTypePrimary': 'Electric'}, {'fuel': 'электро'}),
                 ({'FuelTypePrimary': 'Gasoline', 'ElectrificationLevel': 'HEV (Strong Hybrid)'}, {'fuel': 'гибрид'}),
                 ({'FuelTypePrimary': 'Gasoline', 'FuelTypeSecondary': 'Electric'}, {'fuel': 'гибрид'}),
                 ({'FuelTypePrimary': 'Compressed Natural Gas (CNG)'}, {}),
                 ({'ModelYear': '2002x', 'DisplacementCC': 'abc', 'Model': 'Not Applicable'}, {})]
        for row, expected in cases:
            self.assertEqual(decode.fields(VIN, opener_for(dict(row, ErrorCode='0'))), expected, row)


class BotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher, _ = photo_helper().crm_modules(Path(temp.name))
        self.addCleanup(patcher.stop)
        self.ai_filter = sys.modules['ai_filter']
        self.stop = sys.modules['telegram.ext'].ApplicationHandlerStop
        sys.modules['db'].get_staff = {7: {'user_id': 70, 'active': 1}}.get
        sys.modules.pop('ua_new_car_bot', None)
        import ua_new_car_bot
        self.bot = ua_new_car_bot
        self.context = types.SimpleNamespace(user_data={self.bot.WAIT: True})
        self.update = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=7),
                                            effective_message=Message(VIN))

    def run_text(self):
        try:
            asyncio.run(self.bot.text(self.update, self.context))
        except self.stop:
            pass
        return self.update.effective_message

    def test_card_gets_the_decoded_fields_and_the_vin_brand(self):
        with patch.object(decode, 'fetch', return_value=MERCEDES), \
                patch.object(self.ai_filter, 'find_by_vin', return_value=None), \
                patch.object(self.ai_filter, 'store', return_value=(43, 'UA-0026', True)) as store:
            message = self.run_text()
        store.assert_called_once_with(dict(CRM, brand='Mercedes-Benz', vin=VIN), 70, None)
        self.assertEqual(message.replies, ['🔎 Расшифровываю VIN…'])
        text = message.edits[0][0]
        for value in ('UA-0026', 'E-Class', '2019', 'автомат', 'полный'):
            self.assertIn(value, text)
        self.assertEqual(self.context.user_data, {'car_last': 43})

    def test_decoder_failure_still_creates_the_card_with_the_brand(self):
        with patch.object(decode, 'fetch', side_effect=TimeoutError), \
                patch.object(self.ai_filter, 'find_by_vin', return_value=None), \
                patch.object(self.ai_filter, 'store', return_value=(44, 'UA-0027', True)) as store, \
                self.assertLogs('ua_new_car_bot', 'WARNING'):
            self.run_text()
        store.assert_called_once_with({'brand': 'Mercedes-Benz', 'vin': VIN}, 70, None)

    def test_existing_vin_still_creates_nothing(self):
        with patch.object(decode, 'fetch', return_value=MERCEDES), \
                patch.object(self.ai_filter, 'find_by_vin', return_value={'id': 25, 'auto_number': 'UA-0025'}), \
                patch.object(self.ai_filter, 'store') as store:
            message = self.run_text()
        store.assert_not_called()
        self.assertIn('Карточка с таким VIN-кодом уже существует', message.edits[0][0])

    def test_wrong_vin_is_not_sent_to_vpic(self):
        self.update.effective_message = Message('WDD2452322')
        with patch.object(decode, 'fetch') as fetch:
            message = self.run_text()
        fetch.assert_not_called()
        self.assertEqual(message.replies, [self.bot.RETRY])


class BuilderTests(unittest.TestCase):
    def test_pins(self):
        installed = (ROOT / 'cloud/crm_new_car_vin_001/ua_new_car_bot.py').read_bytes()
        self.assertEqual(hashlib.sha256(installed).hexdigest(), candidate_builder.SOURCE_SHA256['ua_new_car_bot.py'])
        photo = (ROOT / 'cloud/crm_photo_card_001/photo_card.py').read_bytes()
        self.assertEqual(hashlib.sha256(photo).hexdigest(), candidate_builder.DEPENDENCY_SHA256['photo_card.py'])
        fast = (ROOT / 'cloud/task_059_ai_fast_schema/ai_fast_schema.py').read_bytes()
        self.assertEqual(hashlib.sha256(fast).hexdigest(), candidate_builder.DEPENDENCY_SHA256['ai_fast_schema.py'])

    def test_refuses_drift(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'ua_new_car_bot.py': b'x'}, {})


if __name__ == '__main__':
    unittest.main()
