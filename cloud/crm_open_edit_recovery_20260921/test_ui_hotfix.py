import ast
import asyncio
import copy
import hashlib
import html
from html.parser import HTMLParser
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest

from build_ui_hotfix import build, SOURCE_SHA256

BASELINE = Path(__file__).resolve().parents[1] / 'current' / 'cars_ui.py'


class Stop(Exception):
    pass


class BadRequest(Exception):
    pass


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class TelegramHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in {'b', 'i', 'a'}:
            raise BadRequest("Can't parse entities: unsupported start tag")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise BadRequest("Can't parse entities: mismatched tag")

    def handle_data(self, data):
        self.text.append(data)


class Message:
    def __init__(self):
        self.sent = []
        self.attempts = []
        self.fail = None

    async def reply_text(self, text, **kwargs):
        self.attempts.append((text, kwargs))
        if self.fail is not None:
            raise self.fail
        rendered = text
        if kwargs.get('parse_mode') == 'HTML':
            parser = TelegramHTML()
            parser.feed(text)
            if parser.stack:
                raise BadRequest("Can't parse entities: unclosed tag")
            rendered = ''.join(parser.text)
        if len(rendered.encode('utf-16-le')) // 2 > 4096:
            raise BadRequest('Message is too long')
        self.sent.append((text, kwargs, rendered))
        return SimpleNamespace()


class Application:
    def __init__(self):
        self.running = True
        self.tasks = []
        self.coroutines = []

    def create_task(self, coro, update=None):
        self.coroutines.append(coro)
        async def wrapper():
            return await coro
        task = asyncio.create_task(wrapper())
        self.tasks.append(task)
        return task


class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.source = BASELINE.read_bytes()
        self.candidate = build(self.source)
        self.card = {'id': 5, 'auto_number': 'UA-0005', 'brand': 'Kia',
                     'model': 'K5', 'condition_text': 'Original description'}
        self.message = Message()
        self.application = Application()
        self.context = SimpleNamespace(application=self.application, user_data={})
        self.query = SimpleNamespace(data='car_open:5', from_user=SimpleNamespace(id=700),
                                     message=self.message)
        self.update = SimpleNamespace(callback_query=self.query)
        self.media_gate = asyncio.Event()
        self.media_started = []
        self.active_media = 0
        self.max_active_media = 0
        self.staff_calls = []

        async def ack(*args, **kwargs):
            pass

        async def photos(message, card):
            self.media_started.append(card['id'])
            self.active_media += 1
            self.max_active_media = max(self.max_active_media, self.active_media)
            try:
                await self.media_gate.wait()
            finally:
                self.active_media -= 1

        async def videos(message, card):
            pass

        def get_staff(user_id):
            self.staff_calls.append(user_id)
            return {'role': 'owner'}

        def drop_wait(context):
            context.user_data.pop('car_wait', None)
            context.user_data.pop('car_media_wait', None)

        self.ns = {
            '_ua_ui_asyncio': asyncio, '_ua_ui_html': html, '_ua_ui_BadRequest': BadRequest,
            'InlineKeyboardButton': Button, 'InlineKeyboardMarkup': Markup,
            'Update': object, 'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
            'ApplicationHandlerStop': Stop, 'log': logging.getLogger('ui-hotfix-tests'),
            '_v168_ack': ack, 'drop_wait': drop_wait,
            'db': SimpleNamespace(get_staff=get_staff, card_title=lambda *args: 'Kia K5'),
            'card_of': lambda cid: copy.deepcopy(self.card),
            'card_kb': lambda card, staff: Markup([[Button('Edit', 'car_edit:5')]]),
            'render': lambda card, staff: '<b>Card</b>',
            'CR': SimpleNamespace(send_photos=photos, send_videos=videos),
            'EDITABLE': [('condition_text', 'Описание'), ('price_uah', 'Цена Украины'),
                         ('price_georgia', 'Цена Грузии')],
            '_ua_ui_media_slots': {},
        }
        tree = ast.parse(self.candidate)
        selected = [n for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and (n.name.startswith('_ua_ui_')
                         or n.name in {'open_card', 'edit_menu', 'edit_ask'})]
        exec(compile(ast.Module(body=selected, type_ignores=[]), '<candidate-extracted>', 'exec'), self.ns)

    async def asyncTearDown(self):
        for slot in list(self.ns['_ua_ui_media_slots'].values()):
            slot['pending'] = None
            slot['task'].cancel()
        await asyncio.gather(*self.application.tasks, return_exceptions=True)
        await asyncio.sleep(0)

    async def invoke(self, name, data=None):
        if data is not None:
            self.query.data = data
        with self.assertRaises(Stop):
            await asyncio.wait_for(self.ns[name](self.update, self.context), timeout=0.2)

    def test_source_binding_and_unchanged_other_functions(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), SOURCE_SHA256)
        with self.assertRaisesRegex(ValueError, 'Source hash mismatch'):
            build(self.source + b'\n')
        old = ast.parse(self.source)
        new = ast.parse(self.candidate)
        def unchanged(tree):
            return [ast.dump(n, include_attributes=False) for n in tree.body
                    if not (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and (n.name in {'open_card', 'edit_menu', 'edit_ask'}
                                 or n.name.startswith('_ua_ui_')))
                    and not (isinstance(n, ast.Import)
                             and any(x.asname in {'_ua_ui_asyncio', '_ua_ui_html'} for x in n.names))
                    and not (isinstance(n, ast.ImportFrom) and n.module == 'telegram.error')
                    and not (isinstance(n, ast.Assign)
                             and any(isinstance(t, ast.Name) and t.id == '_ua_ui_media_slots'
                                     for t in n.targets))]
        self.assertEqual(unchanged(old), unchanged(new))
        ast.parse(self.candidate, feature_version=(3, 10))

    async def test_open_returns_before_slow_media_and_preserves_staff_lookup(self):
        await self.invoke('open_card')
        self.assertFalse(self.media_gate.is_set())
        self.assertEqual(self.context.user_data['car_last'], 5)
        self.assertEqual(self.staff_calls, [700])
        self.assertEqual(len(self.message.sent), 1)
        await asyncio.sleep(0)
        self.assertEqual(self.media_started, [5])

    async def test_original_handler_waits_for_the_same_slow_media(self):
        node = next(n for n in ast.parse(self.source).body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == 'open_card')
        ns = dict(self.ns)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline-extracted>', 'exec'), ns)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ns['open_card'](self.update, self.context), timeout=0.02)
        self.assertEqual(len(self.message.sent), 1)

    async def test_html_rejection_falls_back_with_edit_keyboard(self):
        self.ns['render'] = lambda *args: '<broken>operator text'
        await self.invoke('open_card')
        self.assertEqual(len(self.message.attempts), 2)
        self.assertIsNone(self.message.sent[0][1]['parse_mode'])
        self.assertEqual(self.message.sent[0][1]['reply_markup'].inline_keyboard[0][0].callback_data,
                         'car_edit:5')

    async def test_long_or_broken_renderer_still_opens(self):
        for renderer in (lambda *a: '😀' * 4000,
                         lambda *a: (_ for _ in ()).throw(ValueError('bad render'))):
            self.message.sent.clear()
            self.ns['render'] = renderer
            await self.invoke('open_card')
            self.assertEqual(len(self.message.sent), 1)
            self.assertIn('Редактировать данные', self.message.sent[0][0])

    async def test_broken_keyboard_retains_minimal_edit_and_media_buttons(self):
        self.ns['card_kb'] = lambda *a: (_ for _ in ()).throw(ValueError('catalog unavailable'))
        await self.invoke('open_card')
        callbacks = [b.callback_data for row in self.message.sent[0][1]['reply_markup'].inline_keyboard
                     for b in row]
        self.assertEqual(callbacks, ['car_edit:5', 'car_media:5', 'cards_cars'])

    async def test_missing_card_never_opens_editor_or_starts_media(self):
        self.ns['card_of'] = lambda cid: None
        for name, data in [('open_card', 'car_open:5'), ('edit_menu', 'car_edit:5'),
                           ('edit_ask', 'car_setf:5:condition_text')]:
            self.context.user_data['car_wait'] = {'card_id': 5, 'field': 'price_uah'}
            await self.invoke(name, data)
            self.assertNotIn('car_wait', self.context.user_data)
            self.assertIn('не найдена', self.message.sent[-1][0])
        self.assertEqual(self.application.tasks, [])

    async def test_database_failure_produces_retry_not_empty_or_success(self):
        self.ns['card_of'] = lambda cid: (_ for _ in ()).throw(RuntimeError('database locked'))
        for name, data in [('open_card', 'car_open:5'), ('edit_menu', 'car_edit:5'),
                           ('edit_ask', 'car_setf:5:price_georgia')]:
            await self.invoke(name, data)
            self.assertIn('Не удалось прочитать', self.message.sent[-1][0])
        self.assertEqual(self.application.tasks, [])

    async def test_current_value_is_escaped_and_bounded_without_data_changes(self):
        original = '<broken>& 😀 ' * 2000
        self.card['condition_text'] = original
        await self.invoke('edit_ask', 'car_setf:5:condition_text')
        text, _, rendered = self.message.sent[-1]
        self.assertIn('&lt;broken&gt;&amp;', text)
        self.assertLessEqual(len(rendered.encode('utf-16-le')) // 2, 4096)
        self.assertEqual(self.card['condition_text'], original)
        self.assertEqual(self.context.user_data['car_wait'], {'card_id': 5, 'field': 'condition_text'})

    async def test_ua_and_ge_editor_identity_and_usd_hint_are_preserved(self):
        for field in ('price_uah', 'price_georgia'):
            await self.invoke('edit_ask', 'car_setf:5:' + field)
            self.assertEqual(self.context.user_data['car_wait']['field'], field)
            self.assertIn('в долларах', self.message.sent[-1][2])
        self.assertEqual(self.staff_calls, [])  # Existing edit authorization model is unchanged.

    async def test_prompt_transport_failure_does_not_activate_invisible_edit(self):
        self.context.user_data.update(car_wait={'card_id': 9, 'field': 'price_uah'},
                                      car_last=9, car_voice_active=9)
        self.message.fail = RuntimeError('transport timeout')
        self.query.data = 'car_setf:5:price_georgia'
        with self.assertRaisesRegex(RuntimeError, 'transport timeout'):
            await self.ns['edit_ask'](self.update, self.context)
        self.assertNotIn('car_wait', self.context.user_data)
        self.assertNotIn('car_last', self.context.user_data)
        self.assertNotIn('car_voice_active', self.context.user_data)

    async def test_network_failure_is_not_retried_as_html_failure(self):
        self.message.fail = RuntimeError('transport timeout')
        with self.assertRaisesRegex(RuntimeError, 'transport timeout'):
            await self.ns['open_card'](self.update, self.context)
        self.assertEqual(len(self.message.attempts), 1)
        self.assertEqual(self.application.tasks, [])

    async def test_repeated_media_requests_keep_one_task_and_latest_slot(self):
        schedule = self.ns['_ua_ui_schedule_media']
        schedule(self.context, self.update, self.message, {'id': 1}, 700)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        for cid in range(2, 102):
            schedule(self.context, self.update, self.message, {'id': cid}, 700)
        self.assertEqual(len(self.application.tasks), 1)
        self.assertEqual(self.ns['_ua_ui_media_slots'][700]['pending'][3]['id'], 101)
        for _ in range(8):
            await asyncio.sleep(0)
        self.assertLessEqual(len(self.application.tasks), 2)
        self.assertEqual(self.max_active_media, 1)
        self.assertEqual(self.media_started[-1], 101)

    async def test_edit_cancels_current_media_and_pending_replacement(self):
        schedule = self.ns['_ua_ui_schedule_media']
        schedule(self.context, self.update, self.message, {'id': 1}, 700)
        await asyncio.sleep(0)
        schedule(self.context, self.update, self.message, {'id': 2}, 700)
        await self.invoke('edit_menu', 'car_edit:5')
        for _ in range(6):
            await asyncio.sleep(0)
        self.assertNotIn(700, self.ns['_ua_ui_media_slots'])
        self.assertEqual(len(self.application.tasks), 1)
        self.assertIn('Что меняем', self.message.sent[-1][0])

    async def test_media_task_creation_failure_does_not_break_open_card(self):
        self.application.create_task = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('stopping'))
        await self.invoke('open_card')
        self.assertEqual(self.context.user_data['car_last'], 5)
        self.assertEqual(self.ns['_ua_ui_media_slots'], {})

    async def test_cancel_before_application_wrapper_starts_closes_coroutine(self):
        self.ns['_ua_ui_schedule_media'](self.context, self.update, self.message, {'id': 1}, 700)
        self.ns['_ua_ui_cancel_media'](700)
        for _ in range(4):
            await asyncio.sleep(0)
        self.assertTrue(self.application.tasks[0].cancelled())
        self.assertIsNone(self.application.coroutines[0].cr_frame)
        self.assertNotIn(700, self.ns['_ua_ui_media_slots'])

    async def test_successful_navigation_replaces_old_card_context_with_opened_card(self):
        for name, data in [('open_card', 'car_open:5'), ('edit_menu', 'car_edit:5'),
                           ('edit_ask', 'car_setf:5:condition_text')]:
            self.context.user_data.update(car_wait={'card_id': 9, 'field': 'price_uah'},
                                          car_last=9, car_voice_active=9)
            await self.invoke(name, data)
            self.assertEqual(self.context.user_data['car_last'], 5)
            self.assertEqual(self.context.user_data['car_voice_active'], 5)
            if name == 'edit_ask':
                self.assertEqual(self.context.user_data['car_wait']['card_id'], 5)
            else:
                self.assertNotIn('car_wait', self.context.user_data)

    async def test_failed_navigation_cannot_leave_prior_card_active(self):
        self.message.fail = RuntimeError('transport timeout')
        for name, data in [('open_card', 'car_open:5'), ('edit_menu', 'car_edit:5'),
                           ('edit_ask', 'car_setf:5:condition_text')]:
            self.context.user_data.update(car_wait={'card_id': 9, 'field': 'price_uah'},
                                          car_last=9, car_voice_active=9)
            self.query.data = data
            with self.assertRaisesRegex(RuntimeError, 'transport timeout'):
                await self.ns[name](self.update, self.context)
            for key in ('car_wait', 'car_last', 'car_voice_active'):
                self.assertNotIn(key, self.context.user_data)

    async def test_prior_context_is_cleared_before_first_await(self):
        async def inspect_ack(*args, **kwargs):
            for key in ('car_wait', 'car_last', 'car_voice_active'):
                self.assertNotIn(key, self.context.user_data)
        self.ns['_v168_ack'] = inspect_ack
        for name, data in [('open_card', 'car_open:5'), ('edit_menu', 'car_edit:5'),
                           ('edit_ask', 'car_setf:5:condition_text')]:
            self.context.user_data.update(car_wait={'card_id': 9, 'field': 'price_uah'},
                                          car_last=9, car_voice_active=9)
            await self.invoke(name, data)


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    unittest.main()
