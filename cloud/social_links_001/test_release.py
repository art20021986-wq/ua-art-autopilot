#!/usr/bin/env python3
"""SOCIAL-LINKS-001: the candidate on the live sources (SOCIAL-PROBE-20261108, sanitized; SPEED-002 edits applied) and
the page lifecycle (install, a CRM rewrite that keeps the row, rollback that removes only the row)."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
SPEED2 = HERE.parent / 'speed_002'
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_remote as remote  # noqa: E402
import ua_social_links  # noqa: E402


def _module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def live_sources():
    """The live modules as the probe read them, with SPEED-002's later edits (installed 2026-11-10)."""
    speed2 = _module(SPEED2 / 'candidate_builder.py', 'speed2_builder')
    source = {n: (FIXTURES / n.replace('.py', '.txt')).read_bytes() for n in candidate_builder.EDITS}
    for name in ('site_ge_inject.py', 'ua_seo_metadata.py'):
        source[name] = speed2.edit(name, source[name])
    source['ua_seo_metadata.py'] = source['ua_seo_metadata.py'].replace(b"SEO_REVISION = 'SPEED-001'",
                                                                        b"SEO_REVISION = 'SPEED-002'")
    page = (FIXTURES / 'katalog.html').read_bytes()
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
        self.assertEqual(sorted(self.result), sorted(['ua_social_links.py', 'site_ge_inject.py', 'ua_seo_index.py',
                                                      'ua_seo_schema.py', 'ua_seo_metadata.py', 'catalog_design_golden.html',
                                                      'video/katalog.html', 'video/index.html']))
        for name, value in self.result.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')

    def test_edits(self):
        inject = self.result['site_ge_inject.py'].decode()
        self.assertTrue(inject.rstrip().endswith('return ua_social_links.apply(_ua_social_base_inject(source))'))
        self.assertIn('ua_social_links.apply(ua_own_counter.apply(ua_google_tag.apply(html)))',
                      self.result['ua_seo_index.py'].decode())
        self.assertIn("SEO_REVISION = 'SOCIAL-LINKS-001'", self.result['ua_seo_metadata.py'].decode())
        with self.assertRaisesRegex(ValueError, 'SOCIAL_ALREADY_APPLIED'):
            candidate_builder.edit('ua_seo_index.py', self.result['ua_seo_index.py'])

    def test_schema_same_as(self):
        folder = Path(tempfile.mkdtemp())
        (folder / 'ua_seo_schema.py').write_bytes(self.result['ua_seo_schema.py'])
        sys.path.insert(0, str(folder))
        sys.modules.pop('ua_seo_schema', None)
        try:
            dealer = importlib.import_module('ua_seo_schema').dealer('uk')
        finally:
            sys.path.remove(str(folder))
        self.assertEqual(dealer['sameAs'], ['https://www.instagram.com/ua_artcompany_llc/', 'https://t.me/uaart_auto',
                                            'https://www.youtube.com/@beetleua', 'https://www.tiktok.com/@llc_ua_art_company'])

    def test_pages_row_once_in_footer_and_guard(self):
        for name in ('video/katalog.html', 'video/index.html', 'catalog_design_golden.html'):
            page = self.result[name].decode()
            self.assertEqual(page.count(ua_social_links.MARK), 1, name)
            self.assertLess(page.index(ua_social_links.END), page.rindex('</footer>'), name)
        self.assertEqual(ua_social_links.apply(self.result['video/index.html'].decode()), self.result['video/index.html'].decode())
        guard = _module(FIXTURES / 'catalog_design_guard.txt', 'live_guard')
        self.assertEqual(guard.shell_audit(self.result['video/katalog.html'].decode())['status'], 'PASS')
        self.assertEqual(guard.shell_fingerprint(self.result['video/katalog.html'].decode()),
                         guard.shell_fingerprint(self.result['catalog_design_golden.html'].decode()))

    def test_page_without_body_or_footer(self):
        self.assertEqual(ua_social_links.apply('google-site-verification: x'), 'google-site-verification: x')
        page = ua_social_links.apply('<html><body><p>card</p><script>x</script></body></html>')
        self.assertTrue(page.endswith(ua_social_links.END + '</body></html>'))

    def test_icons_links_and_colours(self):
        html = ua_social_links.HTML
        self.assertEqual(html.count('target="_blank" rel="noopener"'), 4)
        for colour in ('#26A5E4', '#FF0000', '#25F4EE', '#FE2C55', 'url(#ua-ig)'):
            self.assertIn(colour, html)


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
        after = ua_social_links.apply(before.decode()).encode()
        for prefix, value in (('before', before), ('after', after)):
            (self.backup / prefix / 'video').mkdir(parents=True)
            (self.backup / prefix / 'video/index.html').write_bytes(value)
        (self.root / 'video').mkdir()
        self.page = self.root / 'video/index.html'
        self.page.write_bytes(after)
        self.before, self.after = before, after
        self.plan = {'files': {'video/index.html': {'before': remote.sha(before), 'after': remote.sha(after),
                                                    'mode': 0o644, 'page': True}}, 'protected': {}}

    def test_rewrite_with_row_is_installed_and_rollback_removes_only_the_row(self):
        newer = self.after.replace(b'<footer>f', b'<p>new price</p><footer>f')
        self.page.write_bytes(newer)
        remote.verify_files(self.plan, True)
        remote.restore(self.backup, self.plan)
        self.assertEqual(self.page.read_bytes(), b'<html><body><p>new price</p><footer>f</footer></body></html>')

    def test_rewrite_without_row_is_refused(self):
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
