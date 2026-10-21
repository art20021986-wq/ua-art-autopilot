"""Isolated async-handler checks; no production imports or network/DB writes.

Run with BASELINE_CARS_UI pointing to the independently verified private source.
The actual hash-bound patched handler is compiled and exercised with stubs.
"""
import asyncio
import hashlib
import html
import importlib.util
import logging
import os
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from build_list_patch import END, SOURCE_SHA256, START, build_candidate
from ua_crm_resilient_list import stable_catalog_ids


class HandlerStop(Exception):
    pass


class Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class FakeCatalog:
    def __init__(self, source='valid', changed=False, missing=False):
        self.source = source
        self.changed = changed
        self.missing = missing
        self.stats = 0

    def stat(self):
        if self.missing:
            raise FileNotFoundError('catalog unavailable')
        self.stats += 1
        return SimpleNamespace(st_dev=1, st_ino=2, st_size=10,
                               st_mtime_ns=4 + int(self.changed and self.stats > 1),
                               st_ctime_ns=5)

    def read_text(self, encoding):
        return self.source


class DBReadsOnly:
    def __init__(self, cards, authorized=True):
        self.cards = cards
        self.authorized = authorized
        self.reads = []

    def get_staff(self, actor):
        self.reads.append(('get_staff', actor))
        return {'role': 'owner'} if self.authorized else None

    def list_cards(self, table, limit):
        self.reads.append(('list_cards', table, limit))
        return self.cards

    def __getattr__(self, name):
        raise AssertionError('Unexpected DB operation: ' + name)


class ResilientListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = os.environ.get('BASELINE_CARS_UI')
        if not source_path:
            raise RuntimeError('Set BASELINE_CARS_UI to the verified private cars_ui.py')
        cls.source = Path(source_path).read_bytes()
        cls.candidate = build_candidate(cls.source)
        start = cls.candidate.index(START)
        end = cls.candidate.index(END, start) + len(END)
        cls.block = compile(cls.candidate[start:end], '<actual-patched-folder-block>', 'exec')
        cls.real_catalog = None
        catalog_path = os.environ.get('BASELINE_CATALOG_MODULE')
        if catalog_path:
            catalog_path = Path(catalog_path)
            catalog_sha = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
            if catalog_sha != '63cfe41b4ce4d6e5c1f5615235da8cad50c40fde3278a799a82dfae410daf7b0':
                raise RuntimeError('Real catalog parser baseline hash mismatch')
            spec = importlib.util.spec_from_file_location('ua002_verified_catalog_parser', catalog_path)
            cls.real_catalog = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.real_catalog)

    def setUp(self):
        self.cards = [dict(id=1, auto_number='UA-0001', brand='Kia', model='K5'),
                      dict(id=3, auto_number='UA-0003', brand='Toyota', model='Aqua')]
        self.db = DBReadsOnly(self.cards)
        self.catalog_ids = {'UA-0001', 'UA-0002'}  # UA-0002 is an orphan; never create it.
        self.messages = []
        self.acks = 0
        self.base_register_calls = []

        async def ack(query):
            self.acks += 1

        def parser(source):
            if source != 'valid':
                raise ValueError('Incomplete or malformed catalog')
            return self.catalog_ids

        parser_module = ModuleType('ua_crm_catalog_folders')
        parser_module.parse_catalog = parser
        logger = logging.getLogger('isolated-list-test')
        logger.disabled = True
        self.ns = dict(
            Update=object,
            ContextTypes=SimpleNamespace(DEFAULT_TYPE=object),
            ApplicationHandlerStop=HandlerStop,
            InlineKeyboardButton=Button,
            InlineKeyboardMarkup=Markup,
            CallbackQueryHandler=lambda callback, pattern: SimpleNamespace(
                callback=callback, pattern=pattern),
            card_kb=lambda card, staff: Markup([[Button('Back', 'cards_cars')]]),
            register=lambda app: self.base_register_calls.append(app),
            db=self.db,
            _v168_ack=ack,
            drop_wait=lambda context: context.user_data.pop('wait', None),
            card_of=lambda cid: next((c for c in self.cards if c['id'] == cid), None),
            S=SimpleNamespace(missing_required=lambda card: [],
                              status_label=lambda status: status),
            _ua082_title_html=lambda card: html.escape(card['auto_number']),
            _ua082_title_button=lambda card: card['auto_number'],
            log=logger,
        )
        with patch.dict(sys.modules, {'ua_crm_catalog_folders': parser_module}):
            exec(self.block, self.ns)
        self.ns['_UA122_CATALOG'] = FakeCatalog()

    def run_handler(self, callback='cards_cars'):
        self.messages.clear()

        async def reply(text, **kwargs):
            self.messages.append((text, kwargs))

        context = SimpleNamespace(user_data={
            'wait': 1, 'car_last': 1, 'car_voice_active': 1, 'voice_undo': 1})
        update = SimpleNamespace(callback_query=SimpleNamespace(
            data=callback, from_user=SimpleNamespace(id=777),
            message=SimpleNamespace(reply_text=reply)))
        with self.assertRaises(HandlerStop):
            asyncio.run(self.ns['cars_list'](update, context))
        self.assertEqual(len(self.messages), 1)
        return self.messages[0], context

    def callbacks(self):
        markup = self.messages[-1][1].get('reply_markup')
        return [b.callback_data for row in markup.inline_keyboard for b in row] if markup else []

    def open_ids(self):
        return [int(cb.split(':')[1]) for cb in self.callbacks() if cb.startswith('car_open:')]

    def test_hash_binding_and_unchanged_surrounding_code(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), SOURCE_SHA256)
        start = self.source.index(START)
        source_end = self.source.index(END) + len(END)
        candidate_end = self.candidate.index(END) + len(END)
        self.assertEqual(self.source[:start], self.candidate[:start])
        self.assertEqual(self.source[source_end:], self.candidate[candidate_end:])
        with self.assertRaisesRegex(ValueError, 'Source hash mismatch'):
            build_candidate(self.source + b'\n')
        with self.assertRaisesRegex(ValueError, 'Source hash mismatch'):
            build_candidate(self.candidate)

    def test_orphan_catalog_does_not_block_or_create_crm_car(self):
        (text, kwargs), context = self.run_handler()
        self.assertIn('Выберите папку', text)
        labels = [b.text for row in kwargs['reply_markup'].inline_keyboard for b in row]
        self.assertIn('В каталоге · 1', labels)
        self.assertIn('Не опубликованные · 1', labels)
        self.assertEqual(context.user_data, {})
        self.run_handler('ua122_cars:catalog:0')
        self.assertEqual(self.open_ids(), [1])
        self.run_handler('ua122_cars:unpublished:0')
        self.assertEqual(self.open_ids(), [3])
        self.assertEqual([card['id'] for card in self.db.cards], [1, 3])
        self.assertTrue(all(read[0] in ('get_staff', 'list_cards') for read in self.db.reads))

    def test_missing_malformed_and_raced_catalog_show_all_crm_as_unknown(self):
        for scenario in ('missing', 'malformed', 'raced'):
            for callback in ('cards_cars', 'cars_cards', 'ua122_cars:catalog:0',
                             'ua122_cars:unpublished:0'):
                with self.subTest(scenario=scenario, callback=callback):
                    self.ns['_UA122_CATALOG'] = FakeCatalog(
                        source='bad' if scenario == 'malformed' else 'valid',
                        missing=scenario == 'missing', changed=scenario == 'raced')
                    (text, _), _context = self.run_handler(callback)
                    self.assertIn('Статус на сайте неизвестен', text)
                    self.assertIn('Все автомобили CRM · 2', text)
                    self.assertNotIn('Не опубликованные', text)
                    self.assertEqual(self.open_ids(), [1, 3])
                    self.assertIn('cards_cars', self.callbacks())
                    self.assertIn('menu', self.callbacks())

    def test_all_crm_pagination_remains_usable_through_failure(self):
        self.cards[:] = [dict(id=i, auto_number='UA-%04d' % i) for i in range(1, 46)]
        self.ns['_UA122_CATALOG'] = FakeCatalog(missing=True)
        self.run_handler()
        self.assertEqual(self.open_ids(), list(range(1, 21)))
        self.assertIn('ua122_cars:all:1', self.callbacks())
        self.run_handler('ua122_cars:all:1')
        self.assertEqual(self.open_ids(), list(range(21, 41)))
        self.run_handler('ua122_cars:all:999999999')
        self.assertEqual(self.open_ids(), list(range(41, 46)))
        self.assertIn('ua122_cars:all:1', self.callbacks())
        self.run_handler('ua122_cars:unpublished:4')
        self.assertEqual(self.open_ids(), list(range(1, 21)))

    def test_healthy_folders_return_after_catalog_recovers(self):
        self.ns['_UA122_CATALOG'] = FakeCatalog(missing=True)
        self.run_handler()
        self.ns['_UA122_CATALOG'] = FakeCatalog()
        (text, _), _context = self.run_handler()
        self.assertIn('Выберите папку', text)
        self.assertNotIn('неизвестен', text)
        self.assertIn('ua122_cars:catalog:0', self.callbacks())
        self.run_handler('ua122_cars:all:0')
        self.assertEqual(self.open_ids(), [1, 3])

    def test_single_card_enrichment_error_retains_other_cards_and_own_open_button(self):
        def fail_one(cid):
            if cid == 1:
                raise RuntimeError('one corrupt card')
            return self.cards[1]
        self.ns['card_of'] = fail_one
        self.ns['_UA122_CATALOG'] = FakeCatalog(missing=True)
        (text, _), _context = self.run_handler()
        self.assertIn('Карточка #1', text)
        self.assertIn('UA-0003', text)
        self.assertEqual(self.open_ids(), [1, 3])

    def test_single_title_render_error_does_not_block_healthy_folder(self):
        self.catalog_ids.add('UA-0003')
        def title(card):
            if card['id'] == 1:
                raise ValueError('bad title')
            return card['auto_number']
        self.ns['_ua082_title_html'] = title
        (text, _), _context = self.run_handler('ua122_cars:catalog:0')
        self.assertEqual(self.open_ids(), [1, 3])
        self.assertIn('Карточка #1', text)

    def test_malformed_row_cannot_suppress_valid_rows(self):
        self.cards.append({'auto_number': 'BAD', 'id': None})
        self.ns['_UA122_CATALOG'] = FakeCatalog(missing=True)
        (text, _), _context = self.run_handler()
        self.assertEqual(self.open_ids(), [1, 3])
        self.assertIn('некорректным идентификатором', text)

    def test_unauthorized_actor_cannot_read_list(self):
        self.db.authorized = False
        (text, _), context = self.run_handler()
        self.assertEqual(text, 'Доступ только для сотрудников.')
        self.assertEqual(self.db.reads, [('get_staff', 777)])
        self.assertEqual(self.acks, 1)
        self.assertIn('wait', context.user_data)

    def test_invalid_callback_never_exposes_or_opens_rows(self):
        for callback in ('ua122_cars:all:-1', 'ua122_cars:all:١',
                         'ua122_cars:all:9999999999', 'ua122_cars:bad:0'):
            with self.subTest(callback=callback):
                (text, _), _context = self.run_handler(callback)
                self.assertIn('Не удалось прочитать список CRM', text)
                self.assertEqual(self.open_ids(), [])

    def test_database_failure_is_not_claimed_to_be_an_empty_list(self):
        def fail(*args, **kwargs):
            raise RuntimeError('database unavailable')
        self.db.list_cards = fail
        (text, _), _context = self.run_handler()
        self.assertIn('Не удалось прочитать список CRM', text)
        self.assertNotIn('Автомобилей пока нет', text)

    def test_empty_crm_with_orphan_catalog_stays_empty(self):
        self.cards[:] = []
        self.run_handler('ua122_cars:catalog:0')
        self.assertEqual(self.open_ids(), [])
        self.assertIn('пока нет автомобилей', self.messages[0][0])

    def test_registered_pagination_preserves_existing_register_and_group(self):
        handlers = []
        app = SimpleNamespace(add_handler=lambda handler, group: handlers.append((handler, group)))
        self.ns['register'](app)
        self.assertEqual(self.base_register_calls, [app])
        self.assertEqual(len(handlers), 1)
        handler, group = handlers[0]
        self.assertIs(handler.callback, self.ns['cars_list'])
        self.assertEqual(group, -1)
        for callback in ('ua122_cars:catalog:0', 'ua122_cars:unpublished:9', 'ua122_cars:all:12'):
            self.assertIsNotNone(re.fullmatch(handler.pattern, callback))
        self.assertIsNone(re.fullmatch(handler.pattern, 'ua122_cars:all:-1'))

    def test_card_navigation_returns_to_folders_or_root_if_unknown(self):
        card = self.cards[0]
        markup = self.ns['card_kb'](card, {})
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, 'ua122_cars:catalog:0')
        self.ns['_UA122_CATALOG'] = FakeCatalog(missing=True)
        markup = self.ns['card_kb'](card, {})
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, 'cards_cars')

    def test_extreme_fields_fit_message_limit_and_escape_stage_html(self):
        self.cards[:] = [dict(id=i, auto_number='UA-%04d' % i, status='&<b>' * 1000)
                        for i in range(1, 21)]
        self.ns['_UA122_CATALOG'] = FakeCatalog(missing=True)
        self.ns['_ua082_title_html'] = lambda card: 'X' * 5000
        self.ns['_ua082_title_button'] = lambda card: '&' * 64
        (text, _), _context = self.run_handler()
        self.assertLess(len(text), 4096)
        self.assertNotIn('&<b>', text)
        self.assertEqual(self.open_ids(), list(range(1, 21)))

    def test_catalog_reader_rejects_invalid_identity_collection(self):
        for value in ('UA-0001', {'UA-0001': True}, [None], ['']):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    stable_catalog_ids(FakeCatalog(), lambda source: value)

    def use_real_parser(self, source):
        if self.real_catalog is None:
            self.skipTest('Set BASELINE_CATALOG_MODULE to run exact production parser tests')
        self.ns['_ua122_parse_catalog'] = self.real_catalog.parse_catalog
        self.ns['_UA122_CATALOG'] = FakeCatalog(source=source)

    def test_real_parser_orphan_regression_and_healthy_navigation(self):
        source = ('<!doctype html><html><head><title>UA ART — Каталог</title></head><body>'
                  '<article data-ua-card="UA-0001">CRM car</article>'
                  '<article data-ua-card="UA-0002">Residual site entry</article></body></html>')
        self.use_real_parser(source)
        with self.assertRaisesRegex(self.real_catalog.CatalogSnapshotError, 'absent from the CRM'):
            self.real_catalog.partition_by_catalog(self.cards, self.real_catalog.parse_catalog(source))
        (text, kwargs), _context = self.run_handler()
        self.assertIn('Выберите папку', text)
        labels = [button.text for row in kwargs['reply_markup'].inline_keyboard for button in row]
        self.assertIn('В каталоге · 1', labels)
        self.assertIn('Не опубликованные · 1', labels)
        self.run_handler('ua122_cars:catalog:0')
        self.assertEqual(self.open_ids(), [1])
        self.run_handler('ua122_cars:unpublished:0')
        self.assertEqual(self.open_ids(), [3])

    def test_real_parser_incomplete_duplicate_and_wrong_brand_fall_back(self):
        for source in (
            '<html><head><title>UA ART</title></head><body>',
            '<html><head><title>UA ART</title></head><body>'
            '<i data-ua-card="UA-0001"></i><i data-ua-card="UA-0001"></i></body></html>',
            '<html><head><title>Temporary error</title></head><body></body></html>',
        ):
            with self.subTest(source=source):
                self.use_real_parser(source)
                (text, _), _context = self.run_handler('ua122_cars:unpublished:0')
                self.assertIn('Статус на сайте неизвестен', text)
                self.assertNotIn('Не опубликованные', text)
                self.assertEqual(self.open_ids(), [1, 3])

    def test_real_parser_verified_empty_catalog_is_distinct_from_failure(self):
        self.use_real_parser('<html><head><title>UA ART</title></head><body></body></html>')
        (text, kwargs), _context = self.run_handler()
        self.assertNotIn('неизвестен', text)
        labels = [button.text for row in kwargs['reply_markup'].inline_keyboard for button in row]
        self.assertIn('В каталоге · 0', labels)
        self.assertIn('Не опубликованные · 2', labels)


if __name__ == '__main__':
    unittest.main(verbosity=2)
