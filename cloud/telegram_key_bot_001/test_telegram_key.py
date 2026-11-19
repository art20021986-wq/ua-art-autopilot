#!/usr/bin/env python3
"""TELEGRAM-KEY-BOT: the key message is handled first, stops further processing, is deleted, never logged."""
import asyncio
import logging
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class Stop(Exception):
    pass


class Handler:
    def __init__(self, filters, callback):
        self.filters, self.callback = filters, callback


class Filter:
    def __and__(self, other):
        return self

    def __invert__(self):
        return self


ext = types.ModuleType('telegram.ext')
ext.ApplicationHandlerStop = Stop
ext.MessageHandler = Handler
ext.filters = types.SimpleNamespace(TEXT=Filter(), COMMAND=Filter(), ChatType=types.SimpleNamespace(PRIVATE=Filter()))
sys.modules.setdefault('telegram', types.ModuleType('telegram'))
sys.modules['telegram.ext'] = ext
import ua_telegram_key as key  # noqa: E402

API_ID, API_HASH = '7654321', '0123456789abcdef0123456789ABCDEF'


class Message:
    def __init__(self, text):
        self.text, self.deleted = text, False

    async def delete(self):
        self.deleted = True


class KeyTests(unittest.TestCase):
    def handle(self, text, user=1, chat='private'):
        message, replies = Message(text), []

        async def send_message(**kwargs):
            replies.append(kwargs['text'])
        update = types.SimpleNamespace(effective_message=message, effective_chat=types.SimpleNamespace(id=5, type=chat),
                                       effective_user=types.SimpleNamespace(id=user))
        context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=send_message))
        try:
            asyncio.run(key.on_message(update, context))
            stopped = False
        except Stop:
            stopped = True
        return stopped, message.deleted, replies

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'telegram_api.txt'
        for patcher in (patch.object(key, 'KEY_PATH', self.path), patch.object(key, 'is_owner', lambda uid: uid == 1)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def test_space_and_line_break_saved_mode_600(self):
        for separator in (' ', '\n'):
            self.assertEqual(self.handle(API_ID + separator + API_HASH), (True, True, [key.SAVED]))
            self.assertEqual(self.path.read_text(), '%s\n%s\n' % (API_ID, API_HASH.lower()))
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_malformed_key_deleted_not_written(self):
        for text in (API_ID + ' ' + API_HASH[:31], API_ID + ' ' + 'z' * 32, API_ID + ' ' + API_HASH + 'ff'):
            self.assertEqual(self.handle(text), (True, True, [key.WRONG]))
        self.assertFalse(self.path.exists())

    def test_others_pass_through(self):
        self.assertEqual(self.handle(API_ID + ' ' + API_HASH, user=2), (False, False, []))
        self.assertEqual(self.handle(API_ID + ' ' + API_HASH, chat='group'), (False, False, []))
        self.assertEqual(self.handle('Нужна машина 2020 года, бюджет 15000'), (False, False, []))
        self.assertFalse(self.path.exists())

    def test_values_never_logged(self):
        with self.assertLogs(key.log, level=logging.WARNING) as logs:
            with patch.object(key, 'write_key', side_effect=OSError(API_HASH)):
                self.assertEqual(self.handle(API_ID + ' ' + API_HASH), (True, True, [key.FAILED]))
            key.log.warning('marker')
        text = '\n'.join(logs.output)
        self.assertNotIn(API_HASH, text)
        self.assertNotIn(API_ID, text)

    def test_handler_runs_before_all_others(self):
        added = []
        app = types.SimpleNamespace(add_handler=lambda handler, group=0: added.append((handler.callback, group)))
        key.register(app)
        self.assertEqual(added, [(key.on_message, key.KEY_GROUP)])
        self.assertLess(key.KEY_GROUP, -100)  # the lowest live group seen in cars_ui.py is -100


class EditTests(unittest.TestCase):
    def test_block_once_and_refusals(self):
        import edit_cars_ui
        source = b'import logging\nlog = logging.getLogger(1)\ndef register(app):\n    pass\n'
        result = edit_cars_ui.build(source)
        self.assertTrue(result.startswith(source.rstrip(b'\n')))
        self.assertEqual(result.count(b'# TELEGRAM-KEY-BOT'), 1)
        compile(result, 'cars_ui.py', 'exec')
        with self.assertRaisesRegex(ValueError, 'ALREADY'):
            edit_cars_ui.build(result)
        with self.assertRaisesRegex(ValueError, 'REGISTER_MISSING'):
            edit_cars_ui.build(b'x = 1\n')


if __name__ == '__main__':
    unittest.main()
