#!/usr/bin/env python3
"""PHOTO-ORDER-001: photos in a card keep the order they were sent in (Telegram message number), per sender.

Runs the live photo intake code (fixtures/cars_ui_photos.py, the installed version after PHOTO-ADD-001) before and
after the edits, with the bot's own handler and queue worker over a stand-in card store.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_cars_ui  # noqa: E402
from edits import replace_once  # noqa: E402

INTAKE = (HERE / 'fixtures/cars_ui_photos.py').read_text(encoding='utf-8')
CARD = 18
OWNER, MANAGER = 1, 2


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Stop(Exception):
    pass


class Message:
    def __init__(self, file_id, message_id):
        media = types.SimpleNamespace(file_id=file_id, file_unique_id='U-' + file_id)
        self.photo, self.video, self.video_note, self.document = [media], None, None, None
        self.message_id, self.chat_id, self.text, self.replies = message_id, 1, None, []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class Bot:
    def __init__(self, folder, fixed, photos=()):
        text = replace_once(INTAKE, edit_cars_ui.PAIRS, 'cars_ui') if fixed else INTAKE
        guard = types.ModuleType('crm_online_guard')
        guard.media_receipt_key = lambda card_id, target, unique_id: '%s:%s:%s' % (card_id, target, unique_id)
        guard.media_saved_file = lambda key: None
        guard.media_mark = lambda *args: None
        sys.modules['crm_online_guard'] = guard
        (folder / 'intake.py').write_text(text, encoding='utf-8')
        ns = load(folder / 'intake.py', 'photo_order_intake')
        self.cards = {CARD: {'id': CARD, 'photos': json.dumps(list(photos))}}
        ns.S = types.SimpleNamespace(PHOTO_LIMIT=100, CONDITION_PHOTO_LIMIT=100)
        ns.card_of = lambda cid: dict(self.cards[cid]) if cid in self.cards else None
        ns.jload = lambda value, default=None: json.loads(value) if value else (default or [])
        ns.jdump = json.dumps
        ns.set_field = self.set_field
        ns.save_media = self.save_media
        ns.log = types.SimpleNamespace(warning=lambda *args: None)
        ns.ApplicationHandlerStop, ns.asyncio = Stop, asyncio
        ns._orient = lambda video: 'video_h'
        ns._v165_schedule_progress = lambda *args, **kwargs: None
        ns._V165_SPOOL = str(folder / 'spool.jsonl')
        ns._V165_SPOOL_LOCK = str(folder / 'spool.lock')
        ns._V165_DRAIN_LOCK = str(folder / 'drain.lock')
        self.ns = ns

    def set_field(self, card_id, field, value, actor_id):
        self.cards[card_id][field] = value

    def save_media(self, card, target, file_id, actor_id, tag=''):
        items = json.loads(self.cards[card['id']][target])
        items.append({'file_id': file_id, 'tag': tag})
        self.cards[card['id']][target] = json.dumps(items)
        return 'Сохранено.'

    def send(self, file_id, message_id, actor=OWNER):
        """One photo message through the live handler (queued, not yet saved)."""
        context = types.SimpleNamespace(user_data={'car_media_wait': {'card_id': CARD, 'target': 'photos'}})
        try:
            asyncio.run(self.ns.media_wait(None, context, Message(file_id, message_id), actor))
        except Stop:
            pass

    def drain(self):
        self.ns._v165_spool_drain(100)

    def photos(self):
        return [item['file_id'] for item in json.loads(self.cards[CARD]['photos'])]


class OrderTests(unittest.TestCase):
    def mixed_albums(self, fixed):
        """Two albums of one upload arrive mixed (as UA-0011 on 19.11): message numbers 1-3 and 4-6."""
        with tempfile.TemporaryDirectory() as temp:
            bot = Bot(Path(temp), fixed)
            for number in (4, 1, 5, 2, 6, 3):
                bot.send('P%d' % number, number)
            bot.drain()
            return bot.photos()

    def test_bug_reproduced_on_the_live_code(self):
        self.assertEqual(self.mixed_albums(False), ['P4', 'P1', 'P5', 'P2', 'P6', 'P3'])

    def test_sent_order_kept(self):
        self.assertEqual(self.mixed_albums(True), ['P1', 'P2', 'P3', 'P4', 'P5', 'P6'])

    def test_late_photo_of_an_earlier_message_takes_its_place(self):
        with tempfile.TemporaryDirectory() as temp:
            bot = Bot(Path(temp), True)
            bot.send('P2', 2)
            bot.send('P3', 3)
            bot.drain()
            bot.send('P1', 1)
            bot.drain()
            self.assertEqual(bot.photos(), ['P1', 'P2', 'P3'])

    def test_older_photos_keep_their_places(self):
        with tempfile.TemporaryDirectory() as temp:
            old = [{'file_id': 'OLD1', 'tag': ''}, {'file_id': 'OLD2', 'tag': ''}]
            bot = Bot(Path(temp), True, old)
            bot.send('P8', 8)
            bot.send('P7', 7)
            bot.drain()
            self.assertEqual(bot.photos(), ['OLD1', 'OLD2', 'P7', 'P8'])

    def test_each_sender_ordered_in_own_places(self):
        """Message numbers of two chats are not comparable: owner and manager are ordered separately."""
        with tempfile.TemporaryDirectory() as temp:
            bot = Bot(Path(temp), True)
            bot.send('O2', 20, OWNER)
            bot.send('M1', 5, MANAGER)
            bot.send('O1', 10, OWNER)
            bot.drain()
            self.assertEqual(bot.photos(), ['O1', 'M1', 'O2'])

    def test_first_photo_is_the_main(self):
        self.assertEqual(self.mixed_albums(True)[0], 'P1')


class EditTests(unittest.TestCase):
    def test_builds_on_the_installed_excerpt_and_refuses_twice(self):
        built = candidate_builder.build({'cars_ui.py': INTAKE.encode()}, {})
        self.assertEqual(sorted(built), ['cars_ui.py'])
        with self.assertRaises(ValueError):
            edit_cars_ui.build(built['cars_ui.py'])

    def test_refuses_unexpected_file(self):
        with self.assertRaisesRegex(ValueError, 'EDIT_ANCHOR'):
            edit_cars_ui.build(b'def other(): pass\n')


if __name__ == '__main__':
    unittest.main()
