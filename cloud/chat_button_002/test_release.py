#!/usr/bin/env python3
"""CHAT-BUTTON-002: the candidate on the sources as CHAT-BUTTON-001 left them (pages with the 001 block, the Korea page
without it) and the page lifecycle (install, a CRM rewrite with the new block, rollback that puts the old block back)."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
OLD = HERE.parent / 'chat_button_001' / 'ua_chat_button.py'
CARD = HERE.parent / 'crm_site_pages_20261012_r3' / 'UA-0018.html'
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_remote as remote  # noqa: E402
import ua_chat_button  # noqa: E402


def _module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


old = _module(OLD, 'ua_chat_button_001')


def live_sources():
    """The live files after CHAT-BUTTON-001 (installed 2026-11-11)."""
    catalog = old.apply((FIXTURES / 'katalog.html').read_text('utf-8')).encode('utf-8')
    metadata = (FIXTURES / 'ua_seo_metadata.txt').read_bytes()
    metadata = candidate_builder.REVISION.sub("SEO_REVISION = 'CHAT-BUTTON-001'", metadata.decode()).encode()
    return {'ua_chat_button.py': OLD.read_bytes(), 'ua_seo_metadata.py': metadata,
            'catalog_design_golden.html': catalog, 'video/katalog.html': catalog,
            'video/index.html': old.apply('<html><body><main>x</main></body></html>').encode('utf-8'),
            'video/korea.html': (FIXTURES / 'korea_live.html').read_bytes()}


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = live_sources()
        cls.result = candidate_builder.build(cls.source, {})

    def test_files(self):
        self.assertEqual(sorted(self.result), sorted(self.source))
        self.assertEqual(self.result['ua_chat_button.py'], (HERE / 'ua_chat_button.py').read_bytes())
        self.assertIn("SEO_REVISION = 'CHAT-BUTTON-002'", self.result['ua_seo_metadata.py'].decode())
        compile(self.result['ua_chat_button.py'], 'ua_chat_button.py', 'exec')

    def test_every_page_has_the_new_block_once(self):
        for name in ('video/index.html', 'video/katalog.html', 'catalog_design_golden.html', 'video/korea.html'):
            page = self.result[name].decode()
            self.assertEqual(page.count(ua_chat_button.MARK), 1, name)
            self.assertEqual(page.count(ua_chat_button.HTML), 1, name)
            self.assertNotIn(old.HTML, page, name)

    def test_only_the_block_changes(self):
        for name in ('video/index.html', 'video/katalog.html'):
            self.assertEqual(self.result[name].decode().replace(ua_chat_button.HTML, old.HTML),
                             self.source[name].decode(), name)
        self.assertEqual(self.result['video/korea.html'].decode().replace(ua_chat_button.HTML, ''),
                         self.source['video/korea.html'].decode())

    def test_catalogue_guard(self):
        guard = _module(FIXTURES / 'catalog_design_guard.txt', 'live_guard')
        self.assertEqual(guard.shell_audit(self.result['video/katalog.html'].decode())['status'], 'PASS')
        self.assertEqual(guard.shell_fingerprint(self.result['video/katalog.html'].decode()),
                         guard.shell_fingerprint(self.result['catalog_design_golden.html'].decode()))

    def test_second_build_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'CHAT2_ALREADY_APPLIED'):
            candidate_builder.build(dict(self.source, **{'ua_chat_button.py': self.result['ua_chat_button.py']}), {})
        with self.assertRaisesRegex(ValueError, 'CHAT2_ALREADY_APPLIED'):
            candidate_builder.edit('ua_seo_metadata.py', self.result['ua_seo_metadata.py'])


class StyleTests(unittest.TestCase):
    def test_desktop_look_unchanged_phone_rules_added(self):
        self.assertTrue(ua_chat_button.CSS.startswith(old.CSS))
        phone = ua_chat_button.CSS[len(old.CSS):]
        self.assertTrue(phone.startswith('@media (max-width:767px){') and phone.endswith('}}'))
        for part in ('left:50%!important', 'right:auto!important', 'transform:translateX(-50%)!important',
                     'bottom:calc(16px + env(safe-area-inset-bottom,0px))!important', 'font-size:16px!important',
                     'width:22px!important'):
            self.assertIn(part, phone)

    def test_apply_replaces_in_place_and_is_stable(self):
        card = CARD.read_text('utf-8')
        with_old = old.apply(card)
        new = ua_chat_button.apply(with_old)
        self.assertEqual(new, ua_chat_button.apply(card))
        self.assertEqual(ua_chat_button.apply(new), new)
        self.assertEqual(new.replace(ua_chat_button.HTML, ''), card)
        self.assertEqual(ua_chat_button.apply('google-site-verification: x'), 'google-site-verification: x')


class PageLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        patcher = patch.object(remote, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.backup = self.root / 'backup'
        (self.root / 'video').mkdir()
        self.plan = {'files': {}, 'protected': {}}
        self.pages = {}
        for name, page in (('video/index.html', old.apply('<html><body><footer>f</footer></body></html>')),
                           ('video/korea.html', '<html><body><footer>k</footer></body></html>')):
            before, after = page.encode(), ua_chat_button.apply(page).encode()
            for prefix, value in (('before', before), ('after', after)):
                (self.backup / prefix / 'video').mkdir(parents=True, exist_ok=True)
                (self.backup / prefix / name).write_bytes(value)
            (self.root / name).write_bytes(after)
            self.plan['files'][name] = {'before': remote.sha(before), 'after': remote.sha(after), 'mode': 0o644, 'page': True}
            self.pages[name] = (before, after)

    def test_rewrite_is_accepted_and_rollback_puts_the_old_block_back(self):
        for name, (before, after) in self.pages.items():
            (self.root / name).write_bytes(after.replace(b'<footer>', b'<p>new price</p><footer>'))
        remote.verify_files(self.plan, True)
        remote.restore(self.backup, self.plan)
        index = (self.root / 'video/index.html').read_text()
        self.assertEqual(index, old.apply('<html><body><p>new price</p><footer>f</footer></body></html>'))
        self.assertEqual((self.root / 'video/korea.html').read_text(),
                         '<html><body><p>new price</p><footer>k</footer></body></html>')

    def test_unchanged_install_rolls_back_to_the_backup(self):
        remote.restore(self.backup, self.plan)
        for name, (before, after) in self.pages.items():
            self.assertEqual((self.root / name).read_bytes(), before)

    def test_rewrite_without_block_is_refused(self):
        (self.root / 'video/index.html').write_bytes(b'<html><body>other</body></html>')
        with self.assertRaisesRegex(remote.DeploymentError, 'FILE_CHANGED'):
            remote.verify_files(self.plan, True)
        with self.assertRaisesRegex(remote.DeploymentError, 'ROLLBACK_CONCURRENT_CHANGE'):
            remote.restore(self.backup, self.plan)


if __name__ == '__main__':
    unittest.main()
