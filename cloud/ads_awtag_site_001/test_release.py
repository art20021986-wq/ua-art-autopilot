#!/usr/bin/env python3
"""ADS-AWTAG-SITE: the site Google tag block V1 -> V2 on copies of live pages (LOGO-001 fixtures and a fresh card of
2026-11-28, the Japan and Korea pages of 2026-11-27/28). The installed V1 module is the GA4-TAG-001 copy, pinned by hash;
the catalogue design guard is the JAPAN-SITE-001 copy of the installed one."""
import hashlib
import importlib.util
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as cb  # noqa: E402

CLOUD = HERE.parent
PAGES = {'video/index.html': CLOUD/'logo_site_001/fixtures/index.html',
         'video/katalog.html': CLOUD/'logo_site_001/fixtures/katalog.html',
         'video/podbor.html': CLOUD/'logo_site_001/fixtures/podbor.html',
         'video/ua/UA-0023.html': CLOUD/'logo_site_001/fixtures/card.html',
         'video/seo/ua/landing.html': CLOUD/'logo_site_001/fixtures/landing.html',
         'site/UA-0001.html': CLOUD/'logo_card_001/card_no_switch_UA-0001.html',
         'video/japan.html': CLOUD/'share_lots_001/fixtures/japan_live.html',
         'video/korea.html': CLOUD/'japan_lhd_001/fixtures/korea_live.html'}
GUARD = CLOUD/'japan_site_001/fixtures/catalog_design_guard.txt'
OLD, NEW = cb.OLD, cb.NEW


def sha(value):
    return hashlib.sha256(value).hexdigest()


def text(name):
    return PAGES[name].read_text(encoding='utf-8')


class ModuleTests(unittest.TestCase):
    def test_old_copy_is_the_installed_module(self):
        self.assertEqual(sha((HERE/cb.OLD_COPY).read_bytes()), cb.MODULE_SHA256)
        self.assertEqual((HERE/cb.OLD_COPY).read_bytes(), (CLOUD/'ga4_tag_001/ua_google_tag.py').read_bytes())

    def test_v2_is_v1_plus_the_ads_lines_only(self):
        self.assertEqual(NEW.SNIPPET, OLD.SNIPPET.replace(OLD.EVENTS, NEW.ADS + OLD.EVENTS))
        self.assertEqual((NEW.MARK, NEW.END, NEW.MEASUREMENT_ID, NEW.EVENTS), (OLD.MARK, OLD.END, OLD.MEASUREMENT_ID, OLD.EVENTS))
        self.assertEqual(NEW.SNIPPET.count("gtag('config','G-6SRBQK6GY4');"), 1)
        self.assertEqual(NEW.SNIPPET.count("gtag('config','AW-18537441937');"), 1)
        self.assertEqual(NEW.SNIPPET.count("send_to:'AW-18537441937/fvkWCIT9vsAdEJHVq4dF'"), 1)
        self.assertEqual(NEW.SNIPPET.count(NEW.END), 1)

    def test_no_user_data_and_no_new_host(self):
        for word in ('user_data', 'enhanced', 'email', 'phone_number', 'sha256', 'allow_', 'transaction_id'):
            self.assertNotIn(word, NEW.SNIPPET.lower())
        hosts = lambda value: set(re.findall(r'//([A-Za-z0-9.-]+)', value))
        self.assertEqual(hosts(NEW.SNIPPET), hosts(OLD.SNIPPET))


class PageTests(unittest.TestCase):
    def test_every_fixture_carries_the_v1_block(self):
        for name in PAGES:
            self.assertTrue(cb.is_old(text(name)), name)

    def test_v1_to_v2_is_byte_local(self):
        for name in PAGES:
            old = text(name)
            new = cb.swap(old)
            at = old.index(OLD.EVENTS, old.index(OLD.MARK))
            self.assertEqual(new, old[:at] + NEW.ADS + old[at:], name)
            self.assertEqual(cb.undo(new), old, name)
            self.assertTrue(cb.is_new(new), name)

    def test_writers_write_the_same_and_reapplying_is_a_no_op(self):
        for name in PAGES:
            old = text(name)
            new = cb.swap(old)
            self.assertEqual(NEW.apply(old), new, name)
            self.assertEqual(NEW.apply(new), new, name)
            self.assertEqual(OLD.apply(new), new, name)  # a writer still on V1 adds no second block

    def test_fresh_page_gets_v2_where_v1_went(self):
        for name in PAGES:
            bare = text(name).replace(OLD.SNIPPET, '')
            self.assertEqual(NEW.apply(bare), OLD.apply(bare).replace(OLD.SNIPPET, NEW.SNIPPET), name)
        self.assertEqual(NEW.apply('<p>no head</p>'), '<p>no head</p>')
        self.assertIs(NEW.apply(None), None)

    def test_unexpected_blocks_are_left_alone(self):
        old = text('video/index.html')
        twice = old.replace(OLD.SNIPPET, OLD.SNIPPET + OLD.SNIPPET)
        self.assertEqual(NEW.apply(twice), twice)
        with self.assertRaisesRegex(ValueError, 'AWTAG_PAGE_UNEXPECTED'):
            cb.swap(twice)
        broken = old.replace(OLD.END, '')
        self.assertEqual(NEW.apply(broken), broken)

    def test_catalogue_guard_sees_the_same_shell(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = Path(folder)/'catalog_design_guard.py'
        path.write_bytes(GUARD.read_bytes())
        spec = importlib.util.spec_from_file_location('awtag_test_guard', path)
        guard = importlib.util.module_from_spec(spec)
        sys.modules['awtag_test_guard'] = guard  # its dataclasses look the module up
        self.addCleanup(sys.modules.pop, 'awtag_test_guard', None)
        spec.loader.exec_module(guard)
        old = text('video/katalog.html')
        self.assertEqual(guard.shell_fingerprint(cb.swap(old)), guard.shell_fingerprint(old))


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        (self.root/cb.MODULE).write_bytes((HERE/cb.OLD_COPY).read_bytes())
        for name, path in PAGES.items():
            (self.root/name).parent.mkdir(parents=True, exist_ok=True)
            (self.root/name).write_bytes(path.read_bytes())
        (self.root/'video/privacy_plain.html').write_text('<html><head></head><body>no tag</body></html>')
        (self.root/'other').mkdir()
        (self.root/'other/x.html').write_bytes(PAGES['video/index.html'].read_bytes())

    def source(self):
        return {name: (self.root/name).read_bytes() for name in cb.targets(self.root)}

    def test_targets_find_only_tagged_public_pages(self):
        self.assertEqual(cb.targets(self.root), (cb.MODULE,) + tuple(sorted(PAGES)))

    def test_build_swaps_the_block_and_nothing_else(self):
        source = self.source()
        result = cb.build(source, {})
        self.assertEqual(set(result), set(source))
        self.assertEqual(result[cb.MODULE], (HERE/cb.MODULE).read_bytes())
        for name in PAGES:
            self.assertEqual(result[name].decode('utf-8').replace(NEW.SNIPPET, OLD.SNIPPET), text(name))

    def test_second_build_is_refused(self):
        for name, value in cb.build(self.source(), {}).items():
            (self.root/name).write_bytes(value)
        with self.assertRaisesRegex(ValueError, 'AWTAG_LIVE_MODULE_UNEXPECTED'):
            cb.build(self.source(), {})

    def test_unexpected_page_is_refused(self):
        source = self.source()
        source['video/index.html'] = source['video/index.html'].replace(b'G-6SRBQK6GY4', b'G-OTHER', 1)
        with self.assertRaisesRegex(ValueError, 'AWTAG_PAGE_UNEXPECTED:video/index.html'):
            cb.build(source, {})

    def test_landing_already_v2_is_kept_and_the_rest_swapped(self):
        source = self.source()
        name = 'video/seo/ua/landing.html'
        source[name] = source[name].replace(OLD.SNIPPET.encode(), NEW.SNIPPET.encode())
        result = cb.build(source, {})
        self.assertEqual(result[name], source[name])
        self.assertTrue(cb.is_new(result['video/index.html'].decode('utf-8')))


if __name__ == '__main__':
    unittest.main()
