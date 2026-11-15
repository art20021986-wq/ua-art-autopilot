"""The home photo is found on the live page (photo in its own block since 2026-11-10) and in the old layout;
only the photo and its CSS block change; the Korea home module leaves the result as it is (CRM rewrites keep it)."""
import importlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

try:
    importlib.import_module('PIL')
except ImportError:  # Pillow exists on the server, not in CI
    sys.modules['PIL'] = types.ModuleType('PIL')
    sys.modules['PIL'].Image = types.SimpleNamespace()

import candidate_builder  # noqa: E402
import ua_home_photo_site as site  # noqa: E402

FIXTURES = Path(__file__).resolve().parent/'fixtures'
LIVE = (FIXTURES/'index_live.html').read_text(encoding='utf-8')  # www.uaart.com.ua 2026-11-15, the failing page
URL = '/video/order/home-abc.jpg'


def korea_home():
    loader = importlib.machinery.SourceFileLoader('ua_korea_home', str(FIXTURES/'ua_korea_home.txt'))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('ua_korea_home', loader))
    loader.exec_module(module)
    return module


KOREA = korea_home()


def photo(text):
    return site.PICTURE.findall(text)


def css(text):
    import re
    return re.findall(r'<style id="ua-home-photo-001">.*?</style>', text, re.S)


class LivePageTests(unittest.TestCase):
    def test_live_page_photo_is_its_own_block(self):
        self.assertIn(KOREA.PHOTO, LIVE)
        self.assertEqual(len(photo(LIVE)), 1)
        block = LIVE[LIVE.index(KOREA.PHOTO):LIVE.index(KOREA.PHOTO_END)]
        self.assertIn(photo(LIVE)[0], block)

    def test_only_photo_and_css_change(self):
        after = site.edit_home(LIVE, URL, 1800, 1200)
        self.assertEqual(photo(after), [site.PICTURE_HTML % (URL, 1800, 1200)])
        self.assertEqual(css(after), [site.CSS % (site.MARK, 1800, 1200)])
        back = after.replace(photo(after)[0], photo(LIVE)[0]).replace(css(after)[0], css(LIVE)[0])
        self.assertEqual(back, LIVE)

    def test_photo_stays_in_its_block(self):
        after = site.edit_home(LIVE, URL, 1800, 1200)
        block = after[after.index(KOREA.PHOTO):after.index(KOREA.PHOTO_END)]
        self.assertIn(URL, block)

    def test_crm_rewrite_keeps_the_new_photo(self):
        after = site.edit_home(LIVE, URL, 1800, 1200)
        self.assertEqual(KOREA.apply(after), after)

    def test_old_layout_photo_in_first_screen_still_works(self):
        old = KOREA._photo_back(LIVE)
        self.assertNotIn(KOREA.PHOTO, old)
        after = site.edit_home(old, URL, 1800, 1200)
        hero = after.index(KOREA.HERO) + len(KOREA.HERO)
        self.assertTrue(after.startswith(site.PICTURE_HTML % (URL, 1800, 1200), hero))

    def test_same_photo_again_changes_nothing(self):
        after = site.edit_home(LIVE, URL, 1800, 1200)
        self.assertEqual(site.edit_home(after, URL, 1800, 1200), after)
        self.assertEqual(site.edit_home(site.edit_home(after, '/video/order/home-def.jpg', 1200, 800), URL, 1800, 1200),
                         after)

    def test_no_photo_or_two_photos_is_refused(self):
        one = photo(LIVE)[0]
        for page in (LIVE.replace(one, ''), LIVE.replace(one, one + one),
                     LIVE.replace(one, one.replace('fetchpriority="high"', 'loading="lazy"'))):
            with self.assertRaisesRegex(site.SiteError, 'HOME_PICTURE'):
                site.edit_home(page, URL, 3, 2)

    def test_other_pictures_are_not_touched(self):
        after = site.edit_home(LIVE, URL, 1800, 1200)
        self.assertEqual(after.count('<picture class="stage-picture"'), LIVE.count('<picture class="stage-picture"'))


class PublishTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root/'video/order').mkdir(parents=True)
        (root/'video/index.html').write_text(LIVE, encoding='utf-8')
        os.chmod(root/'video/index.html', 0o644)
        self.root = root
        for name, value in (('HOME', str(root/'video/index.html')), ('ORDER', str(root/'video/order')),
                            ('BACKUP', str(root/'backup'))):
            patcher = patch.object(site, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        opened = types.SimpleNamespace(open=lambda data: types.SimpleNamespace(size=(1800, 1200)))
        patcher = patch.object(site, 'Image', opened)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_live_page_publish_writes_photo_page_and_backup(self):
        self.assertEqual(site.publish(b'jpeg'), site.SITE)
        photos = list((self.root/'video/order').glob('home-*.jpg'))
        self.assertEqual(len(photos), 1)
        page = (self.root/'video/index.html').read_text(encoding='utf-8')
        self.assertIn('/video/order/' + photos[0].name, page)
        self.assertEqual([p.read_text(encoding='utf-8') for p in (self.root/'backup').iterdir()], [LIVE])
        self.assertEqual(list(self.root.rglob('*.tmp')), [])

    def test_refused_page_is_not_written(self):
        broken = LIVE.replace(photo(LIVE)[0], '')
        (self.root/'video/index.html').write_text(broken, encoding='utf-8')
        with self.assertRaises(site.SiteError):
            site.publish(b'jpeg')
        self.assertEqual((self.root/'video/index.html').read_text(encoding='utf-8'), broken)
        self.assertFalse((self.root/'backup').exists())


class BuildTests(unittest.TestCase):
    def test_candidate_is_the_packaged_module_on_the_installed_source(self):
        installed = b'installed'
        with patch.dict(candidate_builder.SOURCE_SHA256, {'ua_home_photo_site.py': candidate_builder.hashlib.sha256(
                installed).hexdigest()}):
            self.assertEqual(candidate_builder.build({'ua_home_photo_site.py': installed}, {}),
                             {'ua_home_photo_site.py': (Path(__file__).resolve().parent/'ua_home_photo_site.py').read_bytes()})

    def test_other_installed_source_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'ua_home_photo_site.py': b'other'}, {})


if __name__ == '__main__':
    unittest.main()
