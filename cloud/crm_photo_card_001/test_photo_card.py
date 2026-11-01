#!/usr/bin/env python3
"""CRM-PHOTO-AUTOFILL-001: screenshot fields, VIN brand, exact source edits and the owner's three rules.

The CRM modules are the exact installed ones: ai_filter.py from probe CRM-PHOTO-PROBE-20261101-R2,
ai_fast_schema.py from task_059 and local_ocr.py rebuilt as installed (task_061 + task_089); each is
checked against the hash read on the server.
"""
import asyncio
import hashlib
import importlib.util
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
import candidate  # noqa: E402
import candidate_builder  # noqa: E402
import screen_fields  # noqa: E402
import vin_brand  # noqa: E402

PROBE = HERE.parent / 'crm_photo_autofill_001' / 'probe_20261101-R2.json'
# Tesseract text of the owner's AUTO.RIA screenshot (2026-11-01) read with the candidate local_ocr.
OCR_TEXT = '11:29 № «п\'єте\n\nW245 (FL)\n\nДвигун\n\nБензин, 1.7 л, (116 к.с. / 85 кВт)\nЕкологічний стандарт\n\nЄвро-5\n\nКоробка передач\n\nАвтомат\n\nПривід\nПередній\n\nКолір\n\nЧорний металік\n\nЛакофарбове покриття\n\nЯк нове\n\nТехнічний стан\nПовністю непошкоджене\n\nПродавець готовий до перевірки на СТО\n\nба Замовити перевірку\n\nДивитись всі опції\n\nПеревірено AUTO.RIA по МІМ-коду\n\nба WDD2452322J660244 Vm)\n\nДії з оголошенням\n\nосо ер @\n\nГоловна Обране Продати Чат Меню\n\nat! < БЕ)\n\nт ©\n\nмісць\n\nодифікація\n\n85 кВт)\n\n11:29 NX\n\nPe ‘EK " одверей * о МІСЦЬ\nliu. ..ІННЯ, комплектащя, модифік:\n\nW245 (FL)\n\nДвигун\nБензин, 1.7 л, (116 к.с. / 85 кВт\n\nЕкологічний стандарт\n\nЄвро-5\n\nКоробка передач\n\nАвтомат\n\nOo\n\nЕкологічний стандарт\n\nЄвро-5\n\nКоробка передач\n\nАвтомат\n\nПривід\nПередній\n\nКолір\nЧорний металік\n\nЛакофарбове покриття\n\nЯк нове\n\nТехнічний стан\n\nе\nтеревірки на СТО\n\nтись всі опції\n\nА мал ЗИМЕ пи\n\nморний металік\nЛакофарбове покриття\nЯк нове\n\nГехнічний стан\nПовністю непошкоджене\n\nПродавець готовий до перевір\n\n#4 Замовити перевірку\n\nДивитись вс\n\nrlanapinaiun ЛИТА DIA nn\n\nтись всі опції\n\nНА по МІМ-коду\n\nЖе\n\nголошенням\n\nоо о\n\nПродати Чат Меню\n\n| Дивитись вс\n\nПеревірено AUTO.RIA по\n\nКа WDD2452322J660244 Ful!\n\nДії з oronows\n\nсо 0 о\n\nГоловна Обране Продати\n\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def installed_local_ocr():
    repair = load('task089_repair', ROOT / 'cloud/task_089_crm_voice_photo_repair/repair_installer.py')
    source = repair.build_ocr((ROOT / 'cloud/task_061/local_ocr.py').read_text())
    assert sha(source.encode()) == candidate_builder.SOURCE_SHA256['local_ocr.py']
    return source


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.rows = rows


def crm_modules(temp):
    """Import photo_card with the exact installed ai_filter/ai_fast_schema/local_ocr; telegram and db are stubs."""
    telegram = types.ModuleType('telegram')
    telegram.InlineKeyboardButton, telegram.InlineKeyboardMarkup, telegram.Update = Button, Markup, object
    ext = types.ModuleType('telegram.ext')
    ext.ApplicationHandlerStop = type('ApplicationHandlerStop', (Exception,), {})
    ext.CallbackQueryHandler = object
    ext.ContextTypes = type('ContextTypes', (), {'DEFAULT_TYPE': object})
    schema = types.ModuleType('cars_schema')
    schema.num = lambda value, unit='': '%s%s' % (value, unit)
    stubs = {'telegram': telegram, 'telegram.ext': ext, 'cars_schema': schema, 'db': types.ModuleType('db')}
    sources = {name: item['source'] for name, item in json.loads(PROBE.read_text())['files'].items()}
    files = {'ai_filter.py': sources['ai_filter.py'] + '\n',
             'ai_fast_schema.py': (ROOT / 'cloud/task_059_ai_fast_schema/ai_fast_schema.py').read_text(),
             'local_ocr.py': candidate.local_ocr(installed_local_ocr())}
    for name in ('ai_filter.py', 'ai_fast_schema.py'):
        assert sha(files[name].encode()) == candidate_builder.DEPENDENCY_SHA256[name], name
    for name, text in files.items():
        (temp / name).write_text(text)
    patcher = patch.dict(sys.modules, stubs)
    patcher.start()
    for name in files:
        load(name[:-3], temp / name)
    return patcher, load('photo_card', HERE / 'photo_card.py')


class ScreenFieldsTests(unittest.TestCase):
    def test_label_value_lines(self):
        self.assertEqual(screen_fields.join_labels(OCR_TEXT).splitlines(), [
            'двигатель: Бензин, 1.7 л, (116 к.с. / 85 кВт)', 'коробка передач: Автомат', 'привод: Передній',
            'цвет: Чорний металік', 'состояние: Повністю непошкоджене'])

    def test_first_value_wins_and_fragments_are_skipped(self):
        text = 'Технічний стан\nе\nКолір\nСірий\nТехнічний стан\nПотребує ремонту\nКолір\nБілий'
        self.assertEqual(screen_fields.join_labels(text), 'цвет: Сірий\nсостояние: Потребує ремонту')

    def test_label_after_label_is_not_a_value(self):
        self.assertEqual(screen_fields.join_labels('Привід\nКолір\nЧорний'), 'цвет: Чорний')


class VinBrandTests(unittest.TestCase):
    def test_known_and_unknown(self):
        self.assertEqual(vin_brand.brand('WDD2452322J660244'), 'Mercedes-Benz')
        self.assertEqual(vin_brand.brand('kna12345678901234'), 'Kia')
        for value in ('ZZZ2452322J660244', '', None):
            self.assertIsNone(vin_brand.brand(value))

    def test_every_wmi_is_three_characters_and_unique(self):
        codes = [code for codes in vin_brand.WMI.values() for code in codes]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(len(code) == 3 for code in codes))


class CandidateTests(unittest.TestCase):
    def test_local_ocr_exact_edits(self):
        source = installed_local_ocr()
        built = candidate.local_ocr(source)
        changed = [(a, b) for a, b in zip(source.splitlines(), built.splitlines()) if a != b]
        self.assertEqual(len(changed), 2)
        self.assertIn('min(1.45, remaining)', changed[0][0])
        self.assertIn('deadline, 4)', changed[1][1])
        compile(built, 'local_ocr.py', 'exec')
        with self.assertRaisesRegex(candidate.CandidateError, 'ALREADY_APPLIED'):
            candidate.local_ocr(built)

    def test_team_bot_photo_branch_only(self):
        source = json.loads(PROBE.read_text())['files']['team_bot.py']['source'] + '\n'
        built = candidate.team_bot(source)
        self.assertEqual(built.count('photo_card.handle(update, context, inbox_id, file_id, text)'), 1)
        self.assertNotIn('local_ocr.fields_from_image', built)
        self.assertEqual(len(source) - len(candidate.TEAM_OLD), len(built) - len(candidate.TEAM_NEW))
        with self.assertRaisesRegex(candidate.CandidateError, 'ANCHOR'):
            candidate.team_bot(source.replace(candidate.TEAM_OLD, ''))

    def test_builder_refuses_drifted_sources(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'local_ocr.py': b'x', 'team_bot.py': b'y'}, {})


class PhotoCardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher, self.card = crm_modules(Path(self.temp.name))
        self.addCleanup(patcher.stop)
        self.ai_filter = sys.modules['ai_filter']

    def test_owner_screenshot_fields(self):
        self.assertEqual(self.card.extract(OCR_TEXT), {
            'brand': 'Mercedes-Benz', 'vin': 'WDD2452322J660244', 'fuel': 'бензин', 'engine_cc': 1700,
            'gearbox': 'автомат', 'drive': 'передний', 'color': 'Чорний металік',
            'condition_text': 'Повністю непошкоджене'})

    def test_visible_brand_is_kept(self):
        data = self.card.extract('Toyota Prius 2016\nVIN WDD2452322J660244')
        self.assertEqual((data['brand'], data['model'], data['year']), ('Toyota', 'PRIUS', 2016))

    def test_rule_new_vin_creates_unpublished_card(self):
        data = self.card.extract(OCR_TEXT)
        with patch.object(self.ai_filter, 'find_by_vin', return_value=None), \
             patch.object(self.ai_filter, 'store', return_value=(42, 'UA-0042', True)) as store:
            message, rows, card_id = self.card.create_card(data, 7, 99)
        store.assert_called_once_with(data, 7, 99)
        self.assertEqual(card_id, 42)
        self.assertIn('UA-0042', message)
        self.assertIn('на сайте не опубликована', message)
        self.assertIn('WDD2452322J660244', message)
        self.assertEqual(rows[0][0].callback_data, 'car_open:42')

    def test_rule_existing_vin_creates_nothing(self):
        with patch.object(self.ai_filter, 'find_by_vin', return_value={'id': 5, 'auto_number': 'UA-0005'}), \
             patch.object(self.ai_filter, 'store') as store:
            message, rows, card_id = self.card.create_card({'vin': 'WDD2452322J660244'}, 7, 99)
        store.assert_not_called()
        self.assertIsNone(card_id)
        self.assertIn('Карточка с таким VIN-кодом уже существует', message)
        self.assertIn('UA-0005', message)
        self.assertEqual(rows[0][0].callback_data, 'car_open:5')

    def test_rule_no_vin_creates_nothing(self):
        with patch.object(self.ai_filter, 'find_by_vin') as find, patch.object(self.ai_filter, 'store') as store:
            message, rows, card_id = self.card.create_card({'gearbox': 'автомат'}, 7, 99)
        find.assert_not_called()
        store.assert_not_called()
        self.assertEqual((rows, card_id), ([], None))
        self.assertIn('VIN на фото не найден', message)

    def test_handle_answers_even_when_ocr_fails(self):
        replies = []

        class Thinking:
            async def edit_text(self, text, **kwargs):
                replies.append((text, kwargs))

        class Message:
            async def reply_text(self, text):
                return Thinking()

        class Bot:
            async def get_file(self, file_id):
                raise TimeoutError

        update = types.SimpleNamespace(message=Message(), effective_user=types.SimpleNamespace(id=1))
        context = types.SimpleNamespace(bot=Bot(), user_data={})
        sys.modules['db'].get_staff = lambda user_id: {'user_id': 7}
        with patch.object(self.ai_filter, 'store') as store:
            asyncio.run(self.card.handle(update, context, 99, 'file', ''))
        store.assert_not_called()
        self.assertIn('VIN на фото не найден', replies[0][0])
        self.assertEqual(context.user_data, {})


if __name__ == '__main__':
    unittest.main()
