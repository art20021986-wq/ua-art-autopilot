#!/usr/bin/env python3
"""CRM-VOICE-STAGE-001: stage phrases, the voice reply, exact cars_ui.py edits and the stage buttons.

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

    def test_apply_saves_through_the_crm_and_answers(self):
        calls, replies = [], []

        async def save_stage(card_id, code, actor):
            calls.append((card_id, code, actor))
            return {'id': card_id, 'auto_number': 'UA-0024'}, None, 'Этап сохранён в CRM. Обновление сайта поставлено в очередь.'

        class Thinking:
            async def edit_text(self, text, reply_markup=None):
                replies.append((text, reply_markup))

        done = asyncio.run(self.voice.apply(Thinking(), {'id': 24}, 'Автомобиль находится в Киеве', 7, save_stage,
                                            lambda code: {'ua_arrived': 'В Киеве'}[code]))
        self.assertTrue(done)
        self.assertEqual(calls, [(24, 'ua_arrived', 7)])
        self.assertTrue(replies[0][0].startswith('✅ UA-0024: этап «В Киеве» сохранён\nЭтап сохранён в CRM.'))
        self.assertEqual([row[0].callback_data for row in replies[0][1].rows], ['car_stage:24', 'car_open:24'])

    def test_apply_leaves_other_text_to_the_field_parser(self):
        async def save_stage(*args):
            raise AssertionError('must not save')
        self.assertFalse(asyncio.run(self.voice.apply(None, {'id': 1}, 'пробег 120 тысяч', 7, save_stage, str)))


class CandidateTests(unittest.TestCase):
    def test_exact_edits_once(self):
        source = live_source()
        built = candidate.cars_ui(source)
        self.assertEqual(built.count(candidate.MARKER), 3)  # gearbox, save_stage, voice hook
        self.assertNotIn('"transmission": r"кпп', built)
        hook = built.index('        if card and voice_object:\n')
        self.assertLess(built.index('voice_stage.apply(', hook), built.index('schema_allowed = set(', hook))
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
