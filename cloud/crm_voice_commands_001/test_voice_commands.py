#!/usr/bin/env python3
"""CRM-VOICE-ALL-001: named fields, stage phrases, voice writes, exact cars_ui.py edits, stage buttons.

Functions are taken from the candidate built on the cars_ui.py source read on the server
(probe CRM-VOICE-PROBE-20261101, checked against its sha256).
"""
import asyncio
import datetime
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

PROBE = ROOT / 'cloud/crm_voice_probe_001/probe_20261101.json'
DELIVERY = ROOT / 'cloud/delivery_status_001/delivery_status.py'


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.rows = rows


class Stop(Exception):
    pass


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def stubs():
    telegram = types.ModuleType('telegram')
    telegram.InlineKeyboardButton, telegram.InlineKeyboardMarkup = Button, Markup
    assert hashlib.sha256(DELIVERY.read_bytes()).hexdigest() == candidate_builder.DEPENDENCY_SHA256['ua_delivery_status.py']
    patcher = patch.dict(sys.modules, {'telegram': telegram})
    patcher.start()
    load('ua_delivery_status', DELIVERY)
    return patcher


def live_source():
    item = json.loads(PROBE.read_text())['files']['cars_ui.py']
    assert item['sha256'] == candidate_builder.SOURCE_SHA256['cars_ui.py']
    return item['source'] + '\n'


def top_level(text, name):
    """Source of one top-level function of the (sanitized, so not importable) cars_ui.py."""
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith(('def %s(' % name, 'async def %s(' % name)))
    end = next(i for i in range(start + 1, len(lines)) if lines[i][:1] not in ('', ' ', '\n', '\t'))
    return ''.join(lines[start:end])


def functions(names, namespace):
    """Import the named cars_ui functions into a temporary module seeded with ``namespace``."""
    built = candidate.cars_ui(live_source())
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'cars_ui_part.py'
        path.write_text(''.join(top_level(built, name) + '\n\n' for name in names))
        spec = importlib.util.spec_from_file_location('cars_ui_part', path)
        module = importlib.util.module_from_spec(spec)
        module.__dict__.update(namespace)
        spec.loader.exec_module(module)
    return module


class StagePhraseTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(stubs().stop)
        self.voice = load('voice_stage', HERE / 'voice_stage.py')

    def test_owner_phrase_and_variants(self):
        cases = {'Автомобиль находится в Киеве': 'ua_arrived', 'Автомобиль находится в Киеве.': 'ua_arrived',
                 'Машина уже в Грузии': 'ge_waiting', 'Автомобіль знаходиться у Києві': 'ua_arrived',
                 'Прибыл в Киев': 'ua_arrived', 'В Корее': 'kr_bought', 'Этап: на пароме': 'sea_loaded',
                 'сейчас стоит в Батуми': 'ge_waiting', 'из Кореи в Грузию на пароме уже': 'sea_loaded'}
        for text, code in cases.items():
            self.assertEqual(self.voice.stage_code(text), code, text)

    def test_other_sentences_are_not_stages(self):
        for text in ('измени коробку на механику', 'доставка до Киева через 10 дней',
                     'растаможка в Киеве займёт три дня по документам', 'уже не в Корее, а в Грузии',
                     'пробег 120 тысяч', '', None):
            self.assertIsNone(self.voice.stage_code(text), text)

class FieldTests(unittest.TestCase):
    def setUp(self):
        self.fields = load('voice_fields', HERE / 'voice_fields.py')

    def test_named_fields(self):
        parse = self.fields.parse
        self.assertEqual(parse('Измени цену Грузии на 17 500 долларов'),
                         ([('car', 'price_georgia', '17 500 долларов')], 'Измени'))
        self.assertEqual(parse('ціна у Грузії 16000')[0], [('car', 'price_georgia', '16000')])
        self.assertEqual(parse('цена 18500, пробег 120 тысяч'), ([('car', 'price_uah', '18500')], 'пробег 120 тысяч'))
        self.assertEqual(parse('Описание: без ДТП, один владелец. Цена 19000')[0],
                         [('car', 'condition_text', 'без ДТП, один владелец'), ('car', 'price_uah', '19000')])
        self.assertEqual(parse('Покупатель Иван Петров, телефон 0501234567, предоплата 1000 долларов')[0],
                         [('client', 'name', 'Иван Петров'), ('client', 'phone', '0501234567'),
                          ('client', 'prepayment', '1000 долларов')])
        self.assertEqual(parse('контейнер MSCU1234567, машина в Киеве'),
                         ([('car', 'sea_container', 'MSCU1234567')], 'машина в Киеве'))
        self.assertEqual(parse('срок доставки 45 дней')[0], [('car', 'eta_days', '45 дней')])
        self.assertEqual(parse('описание диагностики: двигатель без замечаний')[0],
                         [('car', 'diag_text', 'двигатель без замечаний')])
        self.assertEqual(parse('номер авто UA-0030')[0], [('car', 'auto_number', 'UA-0030')])

    def test_unnamed_speech_is_left_alone(self):
        for text in ('бензин автомат', 'Автомобиль находится в Киеве', 'пробег 120 тысяч',
                     'клиент хочет забрать в пятницу', ''):
            self.assertEqual(self.fields.parse(text), ([], text))


class VoiceCommandTests(unittest.TestCase):
    """voice_commands writes through the CRM functions; cars_ui is a recording fake."""

    def setUp(self):
        self.addCleanup(stubs().stop)
        for name in ('voice_fields', 'voice_stage'):
            load(name, HERE / (name + '.py'))
        self.calls, self.client = [], None
        test = self

        class Crm(types.ModuleType):
            S = types.SimpleNamespace(status_label={'ua_arrived': 'В Киеве'}.get)

            def _task088_apply_selected_price(self, card_id, field, value, actor):
                test.calls.append(('price', field, value))
                return True, 'Цена Грузии сохранена: 17 500 USD.'

            def apply_value(self, card_id, field, value, actor):
                test.calls.append(('value', field, value))
                return True, 'Записано.'

            async def save_stage(self, card_id, code, actor):
                test.calls.append(('stage', code))
                return {'id': card_id}, None, 'Этап сохранён в CRM.'

            def card_of(self, card_id):
                return {'id': card_id, 'client_id': 5 if test.client else None}

            def client_of(self, card):
                return test.client if card.get('client_id') else None

            def set_field(self, card_id, field, value, actor):
                test.calls.append(('set', field, value))
                test.client = {'id': value}

        crm = Crm('cars_ui')
        crm.db = types.SimpleNamespace(
            create_card=lambda table, data, actor: test.calls.append(('create', table, data)) or 5,
            update_card_field=lambda table, row, field, value, actor: test.calls.append((table, row, field, value)))
        patcher = patch.dict(sys.modules, {'cars_ui': crm})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.commands = load('voice_commands', HERE / 'voice_commands.py')

    def run_note(self, text):
        sent = []

        class Out:
            async def edit_text(self, text, reply_markup=None):
                sent.append(('edit', text))

            async def reply_text(self, text, reply_markup=None):
                sent.append(('reply', text))

        result = asyncio.run(self.commands.apply(Out(), Out(), {'id': 24, 'auto_number': 'UA-0024'}, text, 7))
        return result, sent

    def test_owner_stage_note(self):
        result, sent = self.run_note('Автомобиль находится в Киеве')
        self.assertEqual(result, (True, ''))
        self.assertEqual(self.calls, [('stage', 'ua_arrived')])
        self.assertEqual(sent, [('edit', 'UA-0024\n• Этап — В Киеве\n  Этап сохранён в CRM.')])

    def test_price_buyer_and_vehicle_rest(self):
        result, sent = self.run_note('цена Грузии 17 500, покупатель Иван, пробег 120 тысяч')
        self.assertEqual(result, (False, 'пробег 120 тысяч'))
        self.assertEqual(self.calls, [('price', 'price_georgia', '17 500'), ('create', 'clients', {'car_interest': 'UA-0024'}),
                                      ('set', 'client_id', 5), ('clients', 5, 'name', 'Иван')])
        self.assertEqual(sent, [('reply', 'UA-0024\n• Цена Грузии сохранена: 17 500 USD.\n• Покупатель — Иван')])

    def test_description_shows_value(self):
        result, sent = self.run_note('описание без ДТП, один владелец')
        self.assertEqual(self.calls, [('value', 'condition_text', 'без ДТП, один владелец')])
        self.assertEqual(sent[0][1], 'UA-0024\n• Описание — без ДТП, один владелец')

    def test_plain_vehicle_speech_is_not_taken(self):
        self.assertEqual(self.run_note('бензин, автомат'), ((False, 'бензин, автомат'), []))
        self.assertEqual(self.calls, [])


class CandidateTests(unittest.TestCase):
    def test_exact_edits_once(self):
        source = live_source()
        built = candidate.cars_ui(source)
        self.assertEqual(built.count(candidate.MARKER), 3)  # gearbox, save_stage, voice hook
        self.assertNotIn('"transmission": r"кпп', built)
        hook = built.index('        if card and voice_object:\n')
        self.assertLess(built.index('voice_commands.apply(', hook), built.index('schema_allowed = set(', hook))
        with self.assertRaisesRegex(candidate.CandidateError, 'ALREADY_APPLIED'):
            candidate.cars_ui(built)
        with self.assertRaisesRegex(candidate.CandidateError, 'ANCHOR:2'):
            candidate.cars_ui(source.replace(candidate.STAGE_SET_OLD, ''))

    def test_builder_refuses_drift(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'cars_ui.py': b'x'}, {})

    def test_gearbox_is_named_in_voice_corrections(self):
        part = functions(['_v168_named_fields'], {})
        allowed = {'gearbox', 'fuel', 'drive', 'color'}
        self.assertEqual(part._v168_named_fields('измени коробку на механику', allowed), {'gearbox'})


class StageButtonTests(unittest.TestCase):
    """stage_set keeps its behaviour after the save moves into save_stage."""

    def run_button(self, cards, requested='georgia'):
        fields, sent = [], []

        def set_field(card_id, field, value, actor):
            fields.append((field, value))
            if field == 'status' and cards.get('saves', True):
                cards['card']['status'] = value

        async def sync(card):
            return 'синхронизация'

        async def ack(*args):
            return None

        class Message:
            async def reply_text(self, text, reply_markup=None):
                sent.append((text, reply_markup))

        status_label = {'ge_waiting': 'В Грузии', 'kr_bought': 'В Корее'}.get
        namespace = {'card_of': lambda cid: cards.get('card'), 'set_field': set_field, '_date': datetime.date,
                     'S': types.SimpleNamespace(status_label=status_label), '_ua004_sync_current_stage': sync,
                     '_v168_ack': ack, 'drop_wait': lambda context: None, 'eta_of': lambda card: (None, None),
                     'InlineKeyboardButton': Button, 'InlineKeyboardMarkup': Markup, 'ApplicationHandlerStop': Stop,
                     'Update': object, 'ContextTypes': types.SimpleNamespace(DEFAULT_TYPE=object)}
        with patch.dict(sys.modules, {'ua_delivery_status': load('ua_delivery_status', DELIVERY)}):
            part = functions(['save_stage', 'stage_set'], namespace)
            query = types.SimpleNamespace(data='car_setstage:24:' + requested, from_user=types.SimpleNamespace(id=7),
                                          message=Message())
            with self.assertRaises(Stop):
                asyncio.run(part.stage_set(types.SimpleNamespace(callback_query=query), None))
        return fields, sent

    def test_saved_stage(self):
        fields, sent = self.run_button({'card': {'id': 24, 'auto_number': 'UA-0024', 'status': 'kr_bought'}})
        self.assertEqual(fields[0], ('status', 'ge_waiting'))
        self.assertEqual(fields[1][0], 'ge_arrived')
        self.assertEqual(sent[0][0], 'UA-0024\nЭтап сохранён: В Грузии\nсинхронизация')

    def test_missing_card(self):
        fields, sent = self.run_button({})
        self.assertEqual((fields, sent[0][0], sent[0][1]), ([], 'Карточка не найдена.', None))

    def test_save_refused(self):
        fields, sent = self.run_button({'card': {'id': 24, 'status': 'kr_bought', 'ge_arrived': '2026-10-01'},
                                        'saves': False})
        self.assertEqual(fields, [('status', 'ge_waiting')])
        self.assertEqual(sent[0][0], 'Не удалось сохранить этап. Сейчас в карточке: В Корее')
        self.assertEqual(sent[0][1].rows[0][0].callback_data, 'car_open:24')


if __name__ == '__main__':
    unittest.main()
