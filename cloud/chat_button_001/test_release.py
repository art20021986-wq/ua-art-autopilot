#!/usr/bin/env python3
"""CHAT-BUTTON-001: the candidate on the live sources (SOCIAL-PROBE-20261108 fixtures with the installed SPEED-002 and
SOCIAL-LINKS-001 edits) and the page lifecycle (install, a CRM rewrite that keeps the style, rollback that removes only
the style)."""
import importlib.machinery
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
SPEED2 = HERE.parent / 'speed_002'
SOCIAL = HERE.parent / 'social_links_001'
CARD = HERE.parent / 'crm_site_pages_20261012_r3' / 'UA-0018.html'
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_remote as remote  # noqa: E402
import ua_chat_button  # noqa: E402


def _module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def live_sources():
    """The live modules as the probe read them, with SPEED-002 and SOCIAL-LINKS-001 (both installed 2026-11-10)."""
    speed2 = _module(SPEED2 / 'candidate_builder.py', 'speed2_builder')
    sys.path.insert(0, str(SOCIAL))
    try:
        social = _module(SOCIAL / 'candidate_builder.py', 'social_builder')
        social_links = _module(SOCIAL / 'ua_social_links.py', 'ua_social_links')
    finally:
        sys.path.remove(str(SOCIAL))
    source = {n: (FIXTURES / n.replace('.py', '.txt')).read_bytes() for n in candidate_builder.EDITS}
    for name in ('site_ge_inject.py', 'ua_seo_metadata.py'):
        source[name] = speed2.edit(name, source[name])
    source['ua_seo_metadata.py'] = source['ua_seo_metadata.py'].replace(b"SEO_REVISION = 'SPEED-001'",
                                                                        b"SEO_REVISION = 'SPEED-002'")
    for name in candidate_builder.EDITS:
        source[name] = social.edit(name, source[name])
    page = social_links.apply((FIXTURES / 'katalog.html').read_text('utf-8')).encode('utf-8')
    source.update({'catalog_design_golden.html': page, 'video/katalog.html': page,
                   'video/index.html': b'<html><body><main>x</main><footer>f</footer></body></html>',
                   'video/google609494476a22f741.html': b'google-site-verification: x'})
    return source


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = live_sources()
        cls.result = candidate_builder.build(cls.source, {})

    def test_files(self):
        self.assertEqual(sorted(self.result), sorted(['ua_chat_button.py', 'site_ge_inject.py', 'ua_seo_index.py',
                                                      'ua_seo_metadata.py', 'catalog_design_golden.html',
                                                      'video/katalog.html', 'video/index.html']))
        for name, value in self.result.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')

    def test_edits(self):
        inject = self.result['site_ge_inject.py'].decode()
        self.assertTrue(inject.rstrip().endswith('return ua_chat_button.apply(_ua_chat_base_inject(source))'))
        self.assertLess(inject.index('_ua_social_base_inject = inject_html'), inject.index('_ua_chat_base_inject = inject_html'))
        self.assertIn('ua_chat_button.apply(ua_social_links.apply(ua_own_counter.apply(ua_google_tag.apply(html))))',
                      self.result['ua_seo_index.py'].decode())
        self.assertIn('import ua_chat_button  # CHAT-BUTTON-001', self.result['ua_seo_index.py'].decode())
        self.assertIn("SEO_REVISION = 'CHAT-BUTTON-001'", self.result['ua_seo_metadata.py'].decode())
        for name in candidate_builder.EDITS:
            with self.assertRaisesRegex(ValueError, 'CHAT_ALREADY_APPLIED'):
                candidate_builder.edit(name, self.result[name])

    def test_inject_chain_adds_style_after_social_row(self):
        folder = Path(tempfile.mkdtemp())
        (folder / 'site_ge_inject.py').write_bytes(self.result['site_ge_inject.py'])
        (folder / 'ua_chat_button.py').write_bytes(self.result['ua_chat_button.py'])
        code = self.result['site_ge_inject.py'].decode()
        tail = code[code.index('# CHAT-BUTTON-001'):]
        # The appended chain over a stub base inject_html, loaded as a module (the execution contract denies exec).
        (folder / 'chain_probe.py').write_text('CALLS = []\n\ndef inject_html(source):\n    CALLS.append(source)\n'
                                               '    return source\n' + tail, 'utf-8')
        sys.path.insert(0, str(folder))
        try:
            probe = _module(folder / 'chain_probe.py', 'chain_probe')
            page = probe.inject_html('<html><body><a class="chat" href="https://wa.me/1">c</a></body></html>')
        finally:
            sys.path.remove(str(folder))
        self.assertEqual(len(probe.CALLS), 1)
        self.assertTrue(page.endswith(ua_chat_button.END + '</body></html>'))
        self.assertEqual(probe.inject_html(page), page)

    def test_pages_style_once_and_guard(self):
        for name in ('video/katalog.html', 'video/index.html', 'catalog_design_golden.html'):
            page = self.result[name].decode()
            self.assertEqual(page.count(ua_chat_button.MARK), 1, name)
            self.assertLess(page.index(ua_chat_button.END), page.rindex('</body>'), name)
        self.assertEqual(ua_chat_button.apply(self.result['video/index.html'].decode()), self.result['video/index.html'].decode())
        guard = _module(FIXTURES / 'catalog_design_guard.txt', 'live_guard')
        self.assertEqual(guard.shell_audit(self.result['video/katalog.html'].decode())['status'], 'PASS')
        self.assertEqual(guard.shell_fingerprint(self.result['video/katalog.html'].decode()),
                         guard.shell_fingerprint(self.result['catalog_design_golden.html'].decode()))

    def test_page_without_body(self):
        self.assertEqual(ua_chat_button.apply('google-site-verification: x'), 'google-site-verification: x')

    def test_card_link_unchanged_and_only_floating_button_styled(self):
        card = CARD.read_text('utf-8')
        after = ua_chat_button.apply(card)
        self.assertEqual(after.replace(ua_chat_button.HTML, ''), card)
        selectors = re.findall(r'a\.([a-z-]+)\[href\*="wa\.me"\]', ua_chat_button.CSS)
        self.assertEqual(set(selectors), {'mcf-chat', 'floating-chat', 'chat'})
        for other in ('wa', 'wa2', 'header-whatsapp', 'v171_punkt'):
            self.assertNotIn('a.%s[' % other, ua_chat_button.CSS)

    def test_labels_and_look(self):
        css = ua_chat_button.CSS
        self.assertIn('content:"Зв’язатися з менеджером"', css)
        self.assertIn('html[lang^="ru"] body a.chat[href*="wa.me"]::after{content:"Связаться с менеджером"', css)
        self.assertIn('html[lang^="ka"] body a.chat[href*="wa.me"]::after{content:"მენეჯერთან დაკავშირება"', css)
        for part in ('background:rgba(11,21,36,.55)!important', 'border:1px solid rgba(232,200,125,.45)!important',
                     'border-radius:999px!important', 'opacity:1!important'):
            self.assertIn(part, css)
        self.assertNotIn('<script', ua_chat_button.HTML)


class PageLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        patcher = patch.object(remote, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.backup = self.root / 'backup'
        before = b'<html><body><footer>f</footer></body></html>'
        after = ua_chat_button.apply(before.decode()).encode()
        for prefix, value in (('before', before), ('after', after)):
            (self.backup / prefix / 'video').mkdir(parents=True)
            (self.backup / prefix / 'video/index.html').write_bytes(value)
        (self.root / 'video').mkdir()
        self.page = self.root / 'video/index.html'
        self.page.write_bytes(after)
        self.before, self.after = before, after
        self.plan = {'files': {'video/index.html': {'before': remote.sha(before), 'after': remote.sha(after),
                                                    'mode': 0o644, 'page': True}}, 'protected': {}}

    def test_rewrite_with_style_is_installed_and_rollback_removes_only_the_style(self):
        newer = self.after.replace(b'<footer>f', b'<p>new price</p><footer>f')
        self.page.write_bytes(newer)
        remote.verify_files(self.plan, True)
        remote.restore(self.backup, self.plan)
        self.assertEqual(self.page.read_bytes(), b'<html><body><p>new price</p><footer>f</footer></body></html>')

    def test_rewrite_without_style_is_refused(self):
        self.page.write_bytes(b'<html><body>other</body></html>')
        with self.assertRaisesRegex(remote.DeploymentError, 'FILE_CHANGED'):
            remote.verify_files(self.plan, True)
        with self.assertRaisesRegex(remote.DeploymentError, 'ROLLBACK_CONCURRENT_CHANGE'):
            remote.restore(self.backup, self.plan)

    def test_unchanged_install_rolls_back_to_the_backup(self):
        remote.restore(self.backup, self.plan)
        self.assertEqual(self.page.read_bytes(), self.before)


if __name__ == '__main__':
    unittest.main()
