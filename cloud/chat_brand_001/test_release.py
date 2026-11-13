#!/usr/bin/env python3
"""CHAT-BRAND-001: the candidate on the sources as CHAT-BUTTON-001 left them (pages with the 001 button block, the Korea
page without it), the two style modules, and the page lifecycle (install, a CRM rewrite with the new blocks, rollback
that puts the old blocks back)."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
OLD_PACKAGE = HERE.parent / 'chat_button_001'
OLD = OLD_PACKAGE / 'ua_chat_button.py'
CARD = HERE.parent / 'crm_site_pages_20261012_r3' / 'UA-0018.html'
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_remote as remote  # noqa: E402
import ua_brand_home  # noqa: E402
import ua_chat_button  # noqa: E402


def _module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


old = _module(OLD, 'ua_chat_button_001')
old_builder = _module(OLD_PACKAGE / 'candidate_builder.py', 'chat_button_001_builder')
HOME_HEAD = '<html lang="uk"><head><link rel="canonical" href="https://www.uaart.com.ua/video/index.html"></head>'
HEADER = ('<a href="index.html" class="brand"><span class="brand-mark">UA</span><span class="brand-copy">'
          '<b>UA ART COMPANY</b><small>АВТОМОБІЛІ З РІЗНИХ КРАЇН</small></span></a>')


def live_sources():
    """The live files after CHAT-BUTTON-001 (installed 2026-11-11)."""
    catalog = old.apply((FIXTURES / 'katalog.html').read_text('utf-8')).encode('utf-8')
    metadata = (FIXTURES / 'ua_seo_metadata.txt').read_bytes()
    metadata = candidate_builder.REVISION.sub("SEO_REVISION = 'CHAT-BUTTON-001'", metadata.decode()).encode()
    index = (OLD_PACKAGE / 'fixtures' / 'ua_seo_index.txt').read_text('utf-8')  # before SOCIAL-LINKS-001
    index = index.replace('import ua_own_counter  # UA-OWN-COUNTER-001\n',
                          'import ua_own_counter  # UA-OWN-COUNTER-001\nimport ua_social_links  # SOCIAL-LINKS-001\n')
    index = index.replace('ua_own_counter.apply(ua_google_tag.apply(html))',
                          'ua_social_links.apply(ua_own_counter.apply(ua_google_tag.apply(html)))')
    after_001 = {'site_ge_inject.py': old_builder.edit('site_ge_inject.py',
                                                       (OLD_PACKAGE / 'fixtures' / 'site_ge_inject.txt').read_bytes()),
                 'ua_seo_index.py': old_builder.edit('ua_seo_index.py', index.encode('utf-8'))}
    return {'ua_chat_button.py': OLD.read_bytes(), 'ua_seo_metadata.py': metadata, **after_001,
            'catalog_design_golden.html': catalog, 'video/katalog.html': catalog,
            'video/index.html': old.apply(HOME_HEAD + '<body>' + HEADER + '<main>x</main></body></html>').encode('utf-8'),
            'video/korea.html': (FIXTURES / 'korea_live.html').read_bytes()}


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = live_sources()
        cls.result = candidate_builder.build(cls.source, {})

    def test_files(self):
        self.assertEqual(sorted(self.result), sorted(list(self.source) + ['ua_brand_home.py']))
        for name in ('ua_chat_button.py', 'ua_brand_home.py'):
            self.assertEqual(self.result[name], (HERE / name).read_bytes())
        self.assertIn("SEO_REVISION = 'CHAT-BRAND-001'", self.result['ua_seo_metadata.py'].decode())
        for name, value in self.result.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')

    def test_writers_add_both_blocks(self):
        inject = self.result['site_ge_inject.py'].decode()
        self.assertTrue(inject.endswith(candidate_builder.INJECT_TAIL))
        self.assertLess(inject.index('_ua_chat_base_inject = inject_html'), inject.index('_ua_brand_base_inject = inject_html'))
        index = self.result['ua_seo_index.py'].decode()
        self.assertIn('import ua_brand_home  # CHAT-BRAND-001\n', index)
        self.assertEqual(index.count('ua_brand_home.apply(' + candidate_builder.CHAIN + ')'), 1)

    def test_every_page_has_both_blocks_once(self):
        for name in ('video/index.html', 'video/katalog.html', 'catalog_design_golden.html', 'video/korea.html'):
            page = self.result[name].decode()
            self.assertEqual(page.count(ua_chat_button.HTML), 1, name)
            self.assertEqual(page.count(ua_brand_home.MARK), 1, name)
            self.assertNotIn(old.HTML, page, name)
            self.assertLess(page.index(ua_chat_button.MARK), page.index(ua_brand_home.MARK), name)

    def test_home_page_has_the_ring_but_no_caption(self):
        self.assertIn(ua_brand_home.block(home=True), self.result['video/index.html'].decode())
        self.assertIn(ua_brand_home.block(home=False), self.result['video/korea.html'].decode())

    def test_only_the_blocks_change(self):
        for name in ('video/index.html', 'video/katalog.html'):
            page = self.result[name].decode().replace(ua_chat_button.HTML, old.HTML)
            for home in (True, False):
                page = page.replace(ua_brand_home.block(home), '')
            self.assertEqual(page, self.source[name].decode(), name)
        page = self.result['video/korea.html'].decode().replace(ua_chat_button.HTML, '')
        self.assertEqual(page.replace(ua_brand_home.block(), ''), self.source['video/korea.html'].decode())

    def test_catalogue_guard(self):
        guard = _module(FIXTURES / 'catalog_design_guard.txt', 'live_guard')
        self.assertEqual(guard.shell_audit(self.result['video/katalog.html'].decode())['status'], 'PASS')
        self.assertEqual(guard.shell_fingerprint(self.result['video/katalog.html'].decode()),
                         guard.shell_fingerprint(self.result['catalog_design_golden.html'].decode()))

    def test_second_build_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'CHAT_BRAND_ALREADY_APPLIED'):
            candidate_builder.build(dict(self.source, **{'ua_chat_button.py': self.result['ua_chat_button.py']}), {})
        for name in ('ua_seo_metadata.py', 'site_ge_inject.py', 'ua_seo_index.py'):
            with self.assertRaisesRegex(ValueError, 'CHAT_BRAND_ALREADY_APPLIED'):
                candidate_builder.edit(name, self.result[name])

    def test_unexpected_live_writer_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'CHAT_BRAND_EDIT'):
            candidate_builder.edit('ua_seo_index.py', b'import ua_chat_button  # CHAT-BUTTON-001\nother chain\n')


class ButtonStyleTests(unittest.TestCase):
    def test_one_size_everywhere_and_phone_rules(self):
        base, phone = ua_chat_button.CSS.split('@media (max-width:767px){')
        for part in ('min-height:0!important', 'margin:0!important', 'box-sizing:border-box!important',
                     'transform:none!important', 'animation:none!important', 'font-family:'):
            self.assertIn(part, base)
        self.assertTrue(phone.endswith('}}'))
        for part in ('left:50%!important', 'right:auto!important', 'transform:translateX(-50%)!important',
                     'bottom:calc(16px + env(safe-area-inset-bottom,0px))!important', 'font-size:16px!important',
                     'width:22px!important'):
            self.assertIn(part, phone)

    def test_label_link_and_colours_kept(self):
        for part in ('Зв’язатися з менеджером', 'Связаться с менеджером', 'მენეჯერთან დაკავშირება',
                     'rgba(11,21,36,.55)', 'rgba(232,200,125,.45)', 'a.mcf-chat[href*="wa.me"]'):
            self.assertIn(part, ua_chat_button.CSS)

    def test_apply_replaces_in_place_and_is_stable(self):
        card = CARD.read_text('utf-8')
        new = ua_chat_button.apply(old.apply(card))
        self.assertEqual(new, ua_chat_button.apply(card))
        self.assertEqual(ua_chat_button.apply(new), new)
        self.assertEqual(new.replace(ua_chat_button.HTML, ''), card)
        self.assertEqual(ua_chat_button.apply('google-site-verification: x'), 'google-site-verification: x')


class BrandStyleTests(unittest.TestCase):
    def test_both_header_kinds_and_languages(self):
        css = ua_brand_home.block()
        for part in ('a.brand .brand-mark', '.shapka .logo .znak', 'a.brand .brand-copy::after',
                     '.shapka .logo > div:not(.znak)::after', 'outline:1.5px solid #e8c87d',
                     '\\2190\\00a0На головну', '\\2190\\00a0На главную', 'html[lang^="ru"] a.brand .brand-copy::after,',
                     'html[lang^="ka"]'):
            self.assertIn(part, css)
        self.assertNotIn('::after', ua_brand_home.block(home=True))
        self.assertIn('outline:1.5px', ua_brand_home.block(home=True))

    def test_home_detection(self):
        self.assertTrue(ua_brand_home.is_home(HOME_HEAD))
        self.assertTrue(ua_brand_home.is_home('<link rel="canonical" href="https://www.uaart.com.ua/video/">'))
        for other in ('<link rel="canonical" href="https://www.uaart.com.ua/video/korea.html">',
                      '<link rel="canonical" href="https://www.uaart.com.ua/video/ua/UA-0007.html">', '<html></html>'):
            self.assertFalse(ua_brand_home.is_home(other), other)

    def test_apply_replaces_in_place_and_is_stable(self):
        card = CARD.read_text('utf-8')
        new = ua_brand_home.apply(card)
        self.assertEqual(new.count(ua_brand_home.MARK), 1)
        self.assertEqual(ua_brand_home.apply(new), new)
        self.assertEqual(new.replace(ua_brand_home.block(), ''), card)
        stale = card.replace('</body>', ua_brand_home.MARK + '<style>old</style>' + ua_brand_home.END + '</body>')
        self.assertEqual(ua_brand_home.apply(stale), new)
        self.assertEqual(ua_brand_home.apply('google-site-verification: x'), 'google-site-verification: x')


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
            before, after = page.encode(), candidate_builder.page(page).encode()
            for prefix, value in (('before', before), ('after', after)):
                (self.backup / prefix / 'video').mkdir(parents=True, exist_ok=True)
                (self.backup / prefix / name).write_bytes(value)
            (self.root / name).write_bytes(after)
            self.plan['files'][name] = {'before': remote.sha(before), 'after': remote.sha(after), 'mode': 0o644, 'page': True}
            self.pages[name] = (before, after)

    def test_rewrite_is_accepted_and_rollback_puts_the_old_blocks_back(self):
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

    def test_rewrite_without_both_blocks_is_refused(self):
        only_button = ua_chat_button.apply('<html><body>other</body></html>').encode()
        (self.root / 'video/index.html').write_bytes(only_button)
        with self.assertRaisesRegex(remote.DeploymentError, 'FILE_CHANGED'):
            remote.verify_files(self.plan, True)
        with self.assertRaisesRegex(remote.DeploymentError, 'ROLLBACK_CONCURRENT_CHANGE'):
            remote.restore(self.backup, self.plan)


if __name__ == '__main__':
    unittest.main()
