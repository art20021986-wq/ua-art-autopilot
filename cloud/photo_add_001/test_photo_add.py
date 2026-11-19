#!/usr/bin/env python3
"""PHOTO-ADD-001: a photo removed from a card can be sent again; a photo still in the card stays a duplicate.

Runs the live photo intake code (excerpts in fixtures/, from PHOTO-ADD-PROBE-20261119) before and after the edits.
"""
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
import edit_crm_online_guard  # noqa: E402
from edits import replace_once  # noqa: E402

GUARD = (HERE / 'fixtures/crm_online_guard_media.py').read_text(encoding='utf-8')
INTAKE = (HERE / 'fixtures/cars_ui_intake.py').read_text(encoding='utf-8')
CARD = 18


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Bot:
    """The live intake and drain code over a stand-in card store, ledger and queue in a temporary folder."""

    def __init__(self, folder, fixed):
        guard_text = replace_once(GUARD, edit_crm_online_guard.PAIRS, 'guard') if fixed else GUARD
        intake_text = replace_once(INTAKE, edit_cars_ui.PAIRS, 'cars_ui') if fixed else INTAKE
        (folder / 'crm_online_guard.py').write_text(
            'from __future__ import annotations\nimport fcntl, hashlib, json, os, time\n' + guard_text, encoding='utf-8')
        (folder / 'intake.py').write_text(intake_text, encoding='utf-8')
        guard = load(folder / 'crm_online_guard.py', 'crm_online_guard')
        guard.MEDIA_LEDGER_PATH = folder / 'receipts.jsonl'
        guard.MEDIA_LEDGER_LOCK = folder / 'receipts.lock'
        self.guard = guard
        self.cards = {CARD: {'id': CARD, 'photos': '[]'}}
        ns = load(folder / 'intake.py', 'photo_add_intake')
        ns.S = types.SimpleNamespace(PHOTO_LIMIT=100, CONDITION_PHOTO_LIMIT=100)
        ns.card_of = lambda cid: dict(self.cards[cid]) if cid in self.cards else None
        ns.jload = lambda value, default=None: json.loads(value) if value else (default or [])
        ns.save_media = self.save_media
        ns._V165_SPOOL = str(folder / 'spool.jsonl')
        ns._V165_SPOOL_LOCK = str(folder / 'spool.lock')
        ns._V165_DRAIN_LOCK = str(folder / 'drain.lock')
        self.ns = ns

    def save_media(self, card, target, file_id, actor_id, tag=''):
        items = json.loads(self.cards[card['id']][target])
        if any(item['file_id'] == file_id for item in items):
            return None
        items.append({'file_id': file_id, 'tag': tag})
        self.cards[card['id']][target] = json.dumps(items)
        return 'Сохранено.'

    def send(self, unique_id, file_id):
        """One photo message, then the queue worker, as the bot runs them."""
        state = self.ns._v165_spool_enqueue(CARD, 'photos', file_id, 1, unique_id=unique_id)['state']
        self.ns._v165_spool_drain(100)
        return state

    def photos(self):
        return [item['file_id'] for item in json.loads(self.cards[CARD]['photos'])]

    def remove_all(self):
        self.cards[CARD]['photos'] = '[]'


class OwnerCase(unittest.TestCase):
    def run_case(self, fixed):
        with tempfile.TemporaryDirectory() as temp:
            bot = Bot(Path(temp), fixed)
            first = bot.send('U1', 'F1')
            again_in_card = bot.send('U1', 'F1b')
            bot.remove_all()
            after_removal = bot.send('U1', 'F1c')
            return first, again_in_card, after_removal, bot.photos()

    def test_bug_reproduced_on_the_live_code(self):
        self.assertEqual(self.run_case(False), ('accepted', 'duplicate_saved', 'duplicate_saved', []))

    def test_removed_photo_can_be_sent_again(self):
        self.assertEqual(self.run_case(True), ('accepted', 'duplicate_saved', 'accepted', ['F1c']))

    def test_receipt_before_the_release_does_not_block(self):
        with tempfile.TemporaryDirectory() as temp:
            bot = Bot(Path(temp), True)
            key = bot.ns._v165_key(CARD, 'photos', 'U2')
            (Path(temp) / 'receipts.jsonl').write_text(json.dumps(
                {'key': key, 'card_id': CARD, 'target': 'photos', 'saved_at': 1}) + '\n', encoding='utf-8')
            self.assertEqual(bot.guard.media_saved_file(key), '')
            self.assertEqual(bot.send('U2', 'F2'), 'accepted')
            self.assertEqual((bot.photos(), bot.guard.media_saved_file(key)), (['F2'], 'F2'))

    def test_same_photo_twice_in_one_album_saved_once(self):
        with tempfile.TemporaryDirectory() as temp:
            bot = Bot(Path(temp), True)
            states = [bot.send('U3', 'F3'), bot.send('U3', 'F3')]
        self.assertEqual(states, ['accepted', 'duplicate_saved'])

    def test_mark_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            bot = Bot(Path(temp), True)
            for _ in range(3):
                bot.guard.media_mark('k', CARD, 'photos', 'F')
            bot.guard.media_mark('k', CARD, 'photos')
            lines = (Path(temp) / 'receipts.jsonl').read_text().splitlines()
        self.assertEqual(len(lines), 2)


class EditTests(unittest.TestCase):
    def test_builds_on_the_live_excerpts_and_refuses_twice(self):
        built = candidate_builder.build({'cars_ui.py': INTAKE.encode(), 'crm_online_guard.py': GUARD.encode()}, {})
        self.assertEqual(sorted(built), ['cars_ui.py', 'crm_online_guard.py'])
        for edit in candidate_builder.EDITS:
            with self.assertRaises(ValueError):
                edit.build(built[edit.NAME])

    def test_refuses_unexpected_file(self):
        with self.assertRaisesRegex(ValueError, 'EDIT_ANCHOR'):
            edit_cars_ui.build(b'def other(): pass\n')
        with self.assertRaisesRegex(ValueError, 'EDIT_ANCHOR'):
            edit_crm_online_guard.build(b'def other(): pass\n')


if __name__ == '__main__':
    unittest.main()
