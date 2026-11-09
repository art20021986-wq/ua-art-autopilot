#!/usr/bin/env python3
"""The two new modules without the server: the stage tile edit and write, the card button.

python-telegram-bot, master_card and publication_fence exist on the server, not
in CI; they are replaced by small stand-ins. The preview (deployment_remote.smoke)
edits the live index.html in memory on the server.
"""
import asyncio
import contextlib
import importlib
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PAGE = (HERE / 'fixtures' / 'stages.html').read_text(encoding='utf-8')   # live #stages section, 2026-11-08


def stand_in(name, **attributes):
    try:
        importlib.import_module(name)
    except ImportError:
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        sys.modules[name] = module


class Stop(Exception):
    pass


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = tuple(tuple(row) for row in rows)


stand_in('telegram', InlineKeyboardButton=Button, InlineKeyboardMarkup=Markup, Update=object)
stand_in('telegram.ext', ApplicationHandlerStop=Stop, CallbackQueryHandler=lambda *a, **k: (a, k),
         ContextTypes=types.SimpleNamespace(DEFAULT_TYPE=object))
db = types.ModuleType('db')
db.ROLE_OWNER = 'owner'
sys.modules['db'] = db

import ua_home_stage_bot as bot  # noqa: E402
import ua_home_stage_site as site  # noqa: E402

OWNER = {'active': 1, 'role': 'owner'}
CAR = {'id': 7, 'auto_number': 'UA-0009', 'published': 1, 'status': 'ua_ready'}


class EditTests(unittest.TestCase):
    def test_live_page_has_four_tiles(self):
        self.assertEqual({s: site.current(PAGE, s) for s in site.STAGES},
                         {'kiev': 'UA-0002', 'georgia': 'UA-0001', 'sea': 'UA-0005', 'korea': 'UA-0003'})

    def test_changes_only_the_src_of_one_tile(self):
        url = '/video/stage/UA-0009.webp?v=abcdef12'
        for stage in site.STAGES:
            edited = site.edit_home(PAGE, stage, url)
            self.assertEqual(site.current(edited, stage), 'UA-0009')
            for other in site.STAGES:
                if other != stage:
                    self.assertEqual(site.current(edited, other), site.current(PAGE, other))
            old = [line for line in PAGE.split('src="') if line not in edited.split('src="')]
            self.assertEqual(len(old), 1)
            self.assertEqual(len(edited) - len(PAGE), len(url) - len(old[0].split('"')[0]))

    def test_drops_phone_copies_of_the_previous_car(self):
        page = PAGE.replace('src="/video/stage/UA-0002.webp?v=034537"',
                            'src="/video/stage/UA-0002.webp?v=034537" srcset="/video/opt/s/UA-0002.webp 600w, '
                            '/video/stage/UA-0002.webp 880w" sizes="50vw"')
        edited = site.edit_home(page, 'kiev', '/video/stage/UA-0009.webp?v=1')
        self.assertNotIn('UA-0002', edited.split('data-stage="kiev"')[1].split('</a>')[0])
        self.assertIn('src="/video/stage/UA-0009.webp?v=1"', edited)
        self.assertEqual(site.current(edited, 'georgia'), 'UA-0001')

    def test_refuses_unknown_stage_or_broken_page(self):
        with self.assertRaises(site.SiteError):
            site.edit_home(PAGE, 'moon', '/x')
        with self.assertRaisesRegex(site.SiteError, 'HOME_TILE:kiev:0'):
            site.edit_home(PAGE.replace('data-stage="kiev"', 'data-stage="x"'), 'kiev', '/x')
        with self.assertRaisesRegex(site.SiteError, 'HOME_LIVE_PHOTO'):
            site.edit_home(PAGE.replace('class="stage-live"', 'class="other"'), 'kiev', '/x')


class PublishTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        (self.base / 'video' / 'stage').mkdir(parents=True)
        (self.base / 'video' / 'index.html').write_text(PAGE, encoding='utf-8')
        (self.base / 'video' / 'stage' / 'UA-0009.webp').write_bytes(b'webp')
        self.fenced = []
        fence = types.ModuleType('publication_fence')

        @contextlib.contextmanager
        def publication_fence(timeout):
            self.fenced.append('in')
            yield
            self.fenced.append('out')
        fence.publication_fence = publication_fence
        card = types.ModuleType('master_card')
        self.photo = ('/video/stage/UA-0009.webp', {'ok': True})
        card.podgotovit_vitrinu = lambda code: (self.fenced.append('photo') or self.photo)
        for name, value in (('BASE', str(self.base)), ('HOME', str(self.base / 'video' / 'index.html')),
                            ('BACKUP', str(self.base / 'backup'))):
            patcher = patch.object(site, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        modules = patch.dict(sys.modules, {'publication_fence': fence, 'master_card': card})
        modules.start()
        self.addCleanup(modules.stop)

    def page(self):
        return (self.base / 'video' / 'index.html').read_text(encoding='utf-8')

    def test_puts_photo_with_backup_inside_the_fence(self):
        site.publish('UA-0009', 'kiev')
        self.assertIn('src="/video/stage/UA-0009.webp?v=', self.page())
        self.assertEqual(site.current(self.page(), 'kiev'), 'UA-0009')
        self.assertEqual(self.fenced, ['in', 'photo', 'out'])
        backups = list((self.base / 'backup').iterdir())
        self.assertEqual([b.read_text(encoding='utf-8') for b in backups], [PAGE])
        self.assertEqual(oct(os.stat(self.base / 'video' / 'index.html').st_mode & 0o777),
                         oct(os.stat(backups[0]).st_mode & 0o777))

    def test_no_photo_leaves_page(self):
        self.photo = ('', {'ok': False, 'prichina': 'файла нет'})
        with self.assertRaisesRegex(site.SiteError, 'PHOTO'):
            site.publish('UA-0009', 'kiev')
        self.assertEqual(self.page(), PAGE)
        self.assertFalse((self.base / 'backup').exists())

    def test_bad_code_refused(self):
        with self.assertRaisesRegex(site.SiteError, 'CODE'):
            site.publish('../x', 'kiev')
        self.assertEqual(self.page(), PAGE)


class ButtonTests(unittest.TestCase):
    MENU = Markup([[Button('Редактировать данные', 'car_edit:7')], [Button('Разместить объявление', 'car_ad:7')],
                   [Button('Продано', 'car_sold:7')]])

    def test_stage_from_crm_status(self):
        self.assertEqual([bot.stage_of({'status': s}) for s in ('ua_ready', 'GE_port', 'sea_transit', 'kr_bought', 'sold', None)],
                         ['kiev', 'georgia', 'sea', 'korea', '', ''])

    def test_button_after_the_ad_button_for_owner_on_published_car(self):
        rows = bot.with_button(self.MENU, CAR, OWNER).inline_keyboard
        self.assertEqual([r[0].callback_data for r in rows], ['car_edit:7', 'car_ad:7', 'home_stage:7', 'car_sold:7'])
        self.assertEqual(rows[2][0].text, '🏠 Разместить на главную')

    def test_no_button_for_others(self):
        for card, staff in ((CAR, {'active': 1, 'role': 'manager'}), (CAR, {'active': 0, 'role': 'owner'}), (CAR, None),
                            ({**CAR, 'published': 0}, OWNER), ({**CAR, 'status': 'sold'}, OWNER)):
            self.assertIs(bot.with_button(self.MENU, card, staff), self.MENU)


class Query:
    def __init__(self, data, user_id):
        self.data, self.from_user, self.replies = data, types.SimpleNamespace(id=user_id), []
        self.message = types.SimpleNamespace(reply_text=self.reply)

    async def answer(self):
        pass

    async def reply(self, text, reply_markup=None):
        self.replies.append(text)


class PlaceTests(unittest.TestCase):
    def press(self, user_id=1, card=CAR, publish=lambda code, stage: None):
        query = Query('home_stage:7', user_id)
        staff = {1: OWNER}.get(user_id, {'active': 1, 'role': 'manager'})
        with patch.object(db, 'get_card', lambda table, cid: card, create=True), \
                patch.object(db, 'get_staff', lambda uid: staff, create=True), \
                patch.object(site, 'publish', publish):
            with self.assertRaises(Stop):
                asyncio.run(bot.place(types.SimpleNamespace(callback_query=query), None))
        return query.replies

    def test_owner_places_the_car(self):
        calls = []
        replies = self.press(publish=lambda code, stage: calls.append((code, stage)))
        self.assertEqual(calls, [('UA-0009', 'kiev')])
        self.assertEqual(replies, ['Готово: фото UA-0009 стоит на главной странице в блоке «У Києві».'])

    def test_refused_for_manager_and_unpublished(self):
        calls = []
        for user_id, card in ((2, CAR), (1, {**CAR, 'published': 0})):
            self.press(user_id, card, publish=lambda code, stage: calls.append(code))
        self.assertEqual(calls, [])

    def test_failure_is_reported(self):
        def fail(code, stage):
            raise site.SiteError('HOME_TILE:kiev:0')
        self.assertIn('Главная не изменена', self.press(publish=fail)[0])


if __name__ == '__main__':
    unittest.main()
