#!/usr/bin/env python3
"""The three new modules without the server: framing geometry, the page edit and write, the dialogue.

OpenCV, numpy, Pillow and python-telegram-bot exist on the server, not in CI;
where missing they are replaced by small stand-ins. The real detector runs in the
preview on the server (deployment_remote.smoke) on the live home photo.
"""
import asyncio
import importlib
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


def stand_in(name, **attributes):
    try:
        importlib.import_module(name)
    except ImportError:
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        sys.modules[name] = module


class Stop(Exception):
    pass


class Filter:
    def __and__(self, other):
        return self

    def __invert__(self):
        return self


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = tuple(tuple(row) for row in rows)


stand_in('cv2')
stand_in('numpy')
stand_in('PIL', Image=types.SimpleNamespace(), ImageOps=types.SimpleNamespace())
stand_in('telegram', InlineKeyboardButton=Button, InlineKeyboardMarkup=Markup, Update=object)
stand_in('telegram.ext', ApplicationHandlerStop=Stop, CallbackQueryHandler=object, MessageHandler=object,
         ContextTypes=types.SimpleNamespace(DEFAULT_TYPE=object), filters=types.SimpleNamespace(ALL=Filter(), COMMAND=Filter()))
db = types.ModuleType('db')
db.ROLE_OWNER = 'owner'
db.get_staff = lambda user_id: {'active': 1, 'role': 'owner' if user_id == 1 else 'manager'}
sys.modules['db'] = db

import ua_home_photo_bot as bot  # noqa: E402
import ua_home_photo_crop as crop  # noqa: E402
import ua_home_photo_site as site  # noqa: E402
from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: E402
from telegram.ext import ApplicationHandlerStop  # noqa: E402

# The live first screen observed by HOME-PHOTO-PROBE-20261028 (shortened copy text).
HOME = ('<html><head><style id="home-ge-typography">a{}</style>'
        '<style id="ua-home-audi-001">.ua-order-first>picture img{object-fit:contain;object-position:center}'
        '@media (max-width:700px){.ua-order-first>picture{aspect-ratio:1756/1190}}</style></head><body>'
        '<section class="hero ua-order-first"><picture><img src="/video/order/audi_owner.jpg" alt="Audi — UA ART COMPANY,'
        ' Київ" width="1756" height="1190" fetchpriority="high" decoding="async"></picture>'
        '<div class="ua-order-shade"></div><nav><img src="order/flags/korea.svg" width="54" height="36" alt=""></nav>'
        '</section><section class="steps"><picture><img src="x.webp"></picture></section></body></html>')


class FrameTests(unittest.TestCase):
    def test_car_centred_with_margin_exact_ratio(self):
        left, top, right, bottom = crop.frame((1000, 900, 2000, 1500), 4000, 3000)
        self.assertEqual((right - left) * 2, (bottom - top) * 3)
        self.assertLessEqual(left, 1000 - 40)
        self.assertGreaterEqual(right, 2000 + 40)
        self.assertLessEqual(abs((left + right) / 2 - 1500), 1)
        self.assertLessEqual(abs((top + bottom) / 2 - 1200), 1)

    def test_tall_car_sets_the_height(self):
        left, top, right, bottom = crop.frame((1000, 500, 1600, 1500), 4000, 3000)
        self.assertLessEqual(top, 500)
        self.assertGreaterEqual(bottom, 1500)
        self.assertEqual((right - left) * 2, (bottom - top) * 3)

    def test_frame_stays_inside_the_photo(self):
        for box in ((0, 0, 700, 400), (3300, 2600, 4000, 3000), (0, 0, 4000, 3000), (100, 0, 3900, 600)):
            left, top, right, bottom = crop.frame(box, 4000, 3000)
            self.assertGreaterEqual(min(left, top), 0)
            self.assertLessEqual(right, 4000)
            self.assertLessEqual(bottom, 3000)
            self.assertEqual((right - left) * 2, (bottom - top) * 3)

    def test_tight_photo_gives_largest_frame(self):
        self.assertEqual(crop.frame((0, 0, 640, 480), 640, 480), (0, 27, 639, 453))


class HomeEditTests(unittest.TestCase):
    def test_only_first_screen_photo_and_css_change(self):
        out = site.edit_home(HOME, '/video/order/home-abc.jpg', 1800, 1200)
        self.assertIn('<img src="/video/order/home-abc.jpg" alt="Авто під замовлення — UA ART COMPANY, Київ" '
                      'width="1800" height="1200"', out)
        self.assertIn('aspect-ratio:1800/1200', out)
        self.assertNotIn('ua-home-audi-001', out)
        self.assertNotIn('audi_owner.jpg', out)
        for kept in ('<style id="home-ge-typography">a{}</style>', '<img src="x.webp">', 'order/flags/korea.svg',
                     '<div class="ua-order-shade"></div>'):
            self.assertIn(kept, out)
        again = site.edit_home(out, '/video/order/home-def.jpg', 1200, 800)
        self.assertEqual(again.count('<style id="ua-home-photo-001">'), 1)
        self.assertEqual(site.edit_home(again, '/video/order/home-abc.jpg', 1800, 1200), out)

    def test_unexpected_page_is_refused(self):
        for page in (HOME.replace('hero ua-order-first', 'hero'), HOME.replace('</section>', '</section>' * 0, 1),
                     HOME.replace('<section class="hero', '<section class="hero ua-order-first"></section><section class="hero', 1)):
            with self.assertRaises(site.SiteError):
                site.edit_home(page, '/x.jpg', 3, 2)


class PublishTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / 'video/order').mkdir(parents=True)
        (root / 'video/index.html').write_text(HOME, encoding='utf-8')
        os.chmod(root / 'video/index.html', 0o600)
        self.root = root
        for name, value in (('HOME', str(root / 'video/index.html')), ('ORDER', str(root / 'video/order')),
                            ('BACKUP', str(root / 'backup'))):
            patcher = patch.object(site, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        opened = types.SimpleNamespace(open=lambda data: types.SimpleNamespace(size=(1800, 1200)))
        patcher = patch.object(site, 'Image', opened)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_writes_photo_and_page_with_backup(self):
        self.assertEqual(site.publish(b'jpeg'), site.SITE)
        photos = list((self.root / 'video/order').glob('home-*.jpg'))
        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0].read_bytes(), b'jpeg')
        page = (self.root / 'video/index.html').read_text(encoding='utf-8')
        self.assertIn('/video/order/' + photos[0].name, page)
        self.assertEqual(oct((self.root / 'video/index.html').stat().st_mode & 0o777), oct(0o600))
        self.assertEqual([p.read_text(encoding='utf-8') for p in (self.root / 'backup').iterdir()], [HOME])
        self.assertEqual(list(self.root.rglob('*.tmp')), [])

    def test_same_photo_twice_changes_nothing_more(self):
        site.publish(b'jpeg')
        site.publish(b'jpeg')
        self.assertEqual(len(list((self.root / 'backup').iterdir())), 1)

    def test_page_changed_meanwhile_is_not_overwritten(self):
        original = site.shutil.copy2

        def edit_during_backup(source, target):
            original(source, target)
            Path(source).write_text(HOME + '<!-- other release -->', encoding='utf-8')
        with patch.object(site.shutil, 'copy2', side_effect=edit_during_backup):
            with self.assertRaisesRegex(site.SiteError, 'HOME_CHANGED_MEANWHILE'):
                site.publish(b'jpeg')
        self.assertTrue((self.root / 'video/index.html').read_text(encoding='utf-8').endswith('<!-- other release -->'))


class Message:
    def __init__(self, photo=(), document=None, group=None):
        self.photo, self.document, self.media_group_id = list(photo), document, group
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)

    async def reply_photo(self, photo, **kwargs):
        self.replies.append(('photo', photo, kwargs))


class Image:
    file_size = 1000

    async def get_file(self):
        async def download():
            return bytearray(b'raw')
        return types.SimpleNamespace(download_as_bytearray=download)


def update(message, user=1):
    return types.SimpleNamespace(effective_message=message, effective_user=types.SimpleNamespace(id=user))


class DialogueTests(unittest.TestCase):
    def setUp(self):
        self.context = types.SimpleNamespace(user_data={})
        self.framed = []
        fake_crop = types.SimpleNamespace(PhotoError=crop.PhotoError, make_home_photo=self.frame_photo)
        patcher = patch.dict(sys.modules, {'ua_home_photo_crop': fake_crop})
        patcher.start()
        self.addCleanup(patcher.stop)

    def frame_photo(self, data):
        self.framed.append(data)
        if data == b'nocar':
            raise crop.PhotoError('NO_CAR')
        return b'framed'

    def receive(self, message, user=1):
        return asyncio.run(bot.receive(update(message, user), self.context))

    def test_messages_without_the_button_go_on_to_the_crm(self):
        with patch.object(db, 'get_staff', side_effect=AssertionError('no lookup')):
            self.assertIsNone(self.receive(Message(photo=[Image()])))
        self.assertEqual(self.framed, [])

    def test_photo_after_button_is_framed_and_shown(self):
        self.context.user_data[bot.WAIT] = bot.time.monotonic()
        message = Message(photo=[Image()])
        with self.assertRaises(ApplicationHandlerStop):
            self.receive(message)
        self.assertEqual(self.framed, [b'raw'])
        self.assertEqual(self.context.user_data[bot.READY], b'framed')
        self.assertEqual(message.replies[-1][:2], ('photo', b'framed'))
        self.assertNotIn(bot.WAIT, self.context.user_data)

    def test_image_file_is_accepted_other_documents_are_not(self):
        self.assertIs(bot._image(Message(document=types.SimpleNamespace(mime_type='image/jpeg'))).mime_type, 'image/jpeg')
        self.assertIsNone(bot._image(Message(document=types.SimpleNamespace(mime_type='application/pdf'))))

    def test_other_message_ends_the_wait_and_goes_on(self):
        self.context.user_data[bot.WAIT] = bot.time.monotonic()
        message = Message()
        self.assertIsNone(self.receive(message))
        self.assertNotIn(bot.WAIT, self.context.user_data)
        self.assertIn('отменена', message.replies[0])

    def test_expired_wait_and_other_staff_are_ignored(self):
        self.context.user_data[bot.WAIT] = bot.time.monotonic() - bot.WAIT_SECONDS - 1
        self.assertIsNone(self.receive(Message(photo=[Image()])))
        self.context.user_data[bot.WAIT] = bot.time.monotonic()
        self.assertIsNone(self.receive(Message(photo=[Image()]), user=2))
        self.assertEqual(self.framed, [])

    def test_no_car_keeps_waiting(self):
        class NoCar(Image):
            async def get_file(self):
                async def download():
                    return bytearray(b'nocar')
                return types.SimpleNamespace(download_as_bytearray=download)
        self.context.user_data[bot.WAIT] = bot.time.monotonic()
        message = Message(photo=[NoCar()])
        with self.assertRaises(ApplicationHandlerStop):
            self.receive(message)
        self.assertEqual(message.replies[-1], bot.ERRORS['NO_CAR'])
        self.assertIn(bot.WAIT, self.context.user_data)

    def test_rest_of_album_does_not_become_a_car(self):
        self.context.user_data[bot.WAIT] = bot.time.monotonic()
        with self.assertRaises(ApplicationHandlerStop):
            self.receive(Message(photo=[Image()], group='g1'))
        with self.assertRaises(ApplicationHandlerStop):
            self.receive(Message(photo=[Image()], group='g1'))
        self.assertEqual(len(self.framed), 1)
        self.assertIsNone(self.receive(Message(photo=[Image()], group='g2')))

    def query(self, user=1):
        message = Message()

        async def answer():
            return None
        return types.SimpleNamespace(callback_query=types.SimpleNamespace(
            answer=answer, message=message, from_user=types.SimpleNamespace(id=user))), message

    def test_confirm_publishes_once(self):
        self.context.user_data[bot.READY] = b'framed'
        call, message = self.query()
        with patch.object(site, 'publish', return_value=site.SITE) as publish:
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(bot.confirm(call, self.context))
            publish.assert_called_once_with(b'framed')
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(bot.confirm(call, self.context))
            publish.assert_called_once()
        self.assertTrue(message.replies[0].startswith('Готово'))

    def test_failed_publish_says_page_unchanged(self):
        self.context.user_data[bot.READY] = b'framed'
        call, message = self.query()
        with patch.object(site, 'publish', side_effect=site.SiteError('HOME_HERO:0')):
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(bot.confirm(call, self.context))
        self.assertIn('не изменена', message.replies[0])

    def test_button_only_for_the_owner_and_only_owner_can_start(self):
        owner = InlineKeyboardMarkup([[InlineKeyboardButton('Авто', callback_data='cards_cars')],
                                      [InlineKeyboardButton('Сотрудники', callback_data='staff_list')]])
        filtered = InlineKeyboardMarkup([[InlineKeyboardButton('Авто', callback_data='cards_cars')]])
        menu = bot.with_button(owner, filtered)
        self.assertEqual([b.callback_data for row in menu.inline_keyboard for b in row], ['cards_cars', 'home_photo'])
        self.assertIs(bot.with_button(filtered, filtered), filtered)
        call, message = self.query(user=2)
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(bot.start(call, self.context))
        self.assertNotIn(bot.WAIT, self.context.user_data)


if __name__ == '__main__':
    unittest.main()
