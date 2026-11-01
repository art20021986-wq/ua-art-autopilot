#!/usr/bin/env python3
"""SPEED-001: Telegram script placement, photo copies and the exact edits; nothing else changes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import candidate_builder as builder
import ua_photo_copies as copies
import ua_tg_script as tg

TAG = "<script src='https://telegram.org/js/telegram-web-app.js'></script>"
USER = "<script>\n var tg = window.Telegram && window.Telegram.WebApp;\n</script>"
PAGE = ("<!doctype html><html><head><meta charset='utf-8'>" + TAG + "<title>T</title>"
        '<script src="order/a.js" defer></script></head><body><h1>Car</h1>'
        "<script>var other = 1;</script><p>text</p>" + USER + "</body></html>")


class TelegramScriptTests(unittest.TestCase):
    def test_moves_before_first_user_only(self):
        moved = tg.place(PAGE)
        self.assertLess(moved.index('<body'), moved.index(TAG))
        self.assertEqual(moved.index(TAG) + len(TAG), moved.index(USER))
        self.assertEqual(moved.replace(TAG, ''), PAGE.replace(TAG, ''))
        self.assertEqual(tg.place(moved), moved)

    def test_unchanged_when_unsafe_or_unneeded(self):
        in_head = PAGE.replace('<title>T</title>', '<title>T</title>' + USER)
        no_user = PAGE.replace(USER, '')
        two_tags = PAGE.replace('<title>', TAG + '<title>')
        for page in (in_head, no_user, two_tags, '<p>fragment</p>', None):
            self.assertEqual(tg.place(page), page)


class PhotoCopyTests(unittest.TestCase):
    def test_existing_copies_only(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder)
            for name in ('foto/UA-0013/s/001.jpg', 'foto/UA-0013/m/001.jpg', 'foto/UA-0014/m/001.jpg'):
                (video/name).parent.mkdir(parents=True, exist_ok=True)
                (video/name).write_bytes(b'x')
            with patch.object(copies, 'VIDEO', video):
                self.assertEqual(copies.copy('foto/UA-0013/m/001.jpg', 's'), 'foto/UA-0013/s/001.jpg')
                self.assertEqual(copies.copy('/video/foto/UA-0013/001.jpg', 'm'), '/video/foto/UA-0013/m/001.jpg')
                self.assertIsNone(copies.copy('/video/foto/UA-0014/001.jpg', 's'))
                self.assertIsNone(copies.copy('/video/stage/UA-0013.webp', 's'))
                self.assertIsNone(copies.copy('foto/UA-0013/001.jpg', 'x'))
                self.assertEqual(copies.srcset('/video/foto/UA-0013/001.jpg'),
                                 '/video/foto/UA-0013/s/001.jpg 440w, /video/foto/UA-0013/m/001.jpg 1000w')
                self.assertEqual(copies.srcset('/video/foto/UA-0014/001.jpg'), '')
                self.assertEqual(copies.srcset('https://www.uaart.com.ua/video/foto/UA-0013/001.jpg'),
                                 'https://www.uaart.com.ua/video/foto/UA-0013/s/001.jpg 440w, '
                                 'https://www.uaart.com.ua/video/foto/UA-0013/m/001.jpg 1000w')
                self.assertIsNone(copies.copy('https://other.example/video/foto/UA-0013/001.jpg', 's'))


class BuildTests(unittest.TestCase):
    def sources(self):
        return {name: ('# head\n' + ''.join(old + '\n# between\n' for old, _ in edits)).encode()
                for name, edits in builder.EDITS.items()}

    def test_exact_edits_and_new_modules(self):
        source = self.sources()
        source['video/podbor.html'] = PAGE.encode()
        result = builder.build(source, {})
        self.assertEqual(set(result), set(source) | set(builder.NEW_MODULES))
        for name, edits in builder.EDITS.items():
            text = result[name].decode()
            for old, new in edits:
                self.assertIn(new, text)
        self.assertEqual(result['video/podbor.html'].decode(), tg.place(PAGE))
        self.assertIn("SEO_REVISION = 'SPEED-001'", result['ua_seo_metadata.py'].decode())

    def test_refuses_missing_duplicate_or_applied(self):
        for change in ('missing', 'duplicate', 'applied'):
            source = self.sources()
            text = source['ua_media_gallery.py'].decode()
            old = builder.EDITS['ua_media_gallery.py'][0][0]
            text = {'missing': text.replace(old, ''), 'duplicate': text + old,
                    'applied': text + '# SPEED-001\n'}[change]
            source['ua_media_gallery.py'] = text.encode()
            with self.assertRaises(ValueError, msg=change):
                builder.build(source, {})
        with self.assertRaisesRegex(ValueError, 'SPEED_PAGE_UNCHANGED'):
            builder.build({'video/podbor.html': tg.place(PAGE).encode()}, {})

    def test_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'video').mkdir()
            (root/'video/podbor.html').write_text(PAGE)
            self.assertEqual(builder.targets(root), tuple(builder.EDITS) + ('video/podbor.html',))


if __name__ == '__main__':
    unittest.main()
