#!/usr/bin/env python3
"""DIAG-COUNTERS-001: the candidate (inject chain tail, diagnostics pages), the preview smoke on a temporary server
root and the page lifecycle (install, a CRM rewrite that keeps both counters, rollback)."""
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_remote as remote  # noqa: E402
import ua_google_tag  # noqa: E402
import ua_own_counter  # noqa: E402

DIAG_PAGE = ('<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8"><title>UA-0005 diag</title></head><body>'
             '<main>report</main><a class="chat" href="https://wa.me/380992222002">c</a></body></html>')


def _module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def dependencies():
    return {name: (HERE/name).read_bytes() for name in candidate_builder.DEPENDENCY_SHA256}


def source():
    both = candidate_builder.counted(DIAG_PAGE)
    return {'site_ge_inject.py': (HERE/'fixtures'/'site_ge_inject.txt').read_bytes(),
            'video/UA-0005-diag.html': DIAG_PAGE.encode(),
            'site/UA-0005-diag.html': DIAG_PAGE.encode(),
            'video/UA-0018-diag.html': both.encode()}


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = candidate_builder.build(source(), dependencies())

    def test_copies_match_installed_modules(self):
        for name, digest in candidate_builder.DEPENDENCY_SHA256.items():
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(), digest)

    def test_files(self):
        self.assertEqual(sorted(self.result), ['site/UA-0005-diag.html', 'site_ge_inject.py', 'video/UA-0005-diag.html'])
        compile(self.result['site_ge_inject.py'], 'site_ge_inject.py', 'exec')

    def test_pages_carry_both_once(self):
        for name in ('video/UA-0005-diag.html', 'site/UA-0005-diag.html'):
            page = self.result[name].decode()
            self.assertEqual(page.count(ua_google_tag.MARK), 1)
            self.assertEqual(page.count(ua_own_counter.MARK), 1)
            self.assertLess(page.index('<head>'), page.index(ua_google_tag.MARK))
            self.assertLess(page.index(ua_own_counter.MARK), page.rindex('</body>'))
            self.assertEqual(page.replace(ua_google_tag.SNIPPET, '').replace(ua_own_counter.LINE, ''), DIAG_PAGE)

    def test_inject_tail_is_last_and_only_appended(self):
        before = source()['site_ge_inject.py'].decode()
        after = self.result['site_ge_inject.py'].decode()
        self.assertTrue(after.startswith(before.rstrip('\n')))
        self.assertEqual(after[len(before.rstrip('\n')):], candidate_builder.INJECT_TAIL)
        with self.assertRaisesRegex(ValueError, 'DIAG_COUNTERS_ALREADY_APPLIED'):
            candidate_builder.edit_inject(self.result['site_ge_inject.py'])
        with self.assertRaisesRegex(ValueError, 'DIAG_COUNTERS_INJECT_MISSING'):
            candidate_builder.edit_inject(b'x = 1\n')

    def test_inject_chain_adds_both_once(self):
        code = self.result['site_ge_inject.py'].decode()
        tail = code[code.index('# DIAG-COUNTERS-001'):]
        folder = Path(tempfile.mkdtemp())
        (folder/'chain_probe.py').write_text('CALLS = []\n\ndef inject_html(source):\n    CALLS.append(source)\n'
                                             '    return source\n' + tail, 'utf-8')
        probe = _module(folder/'chain_probe.py', 'chain_probe')
        page = probe.inject_html(DIAG_PAGE)
        self.assertEqual(probe.CALLS, [DIAG_PAGE])
        self.assertTrue(candidate_builder.has_both(page))
        self.assertEqual(probe.inject_html(page), page)
        self.assertEqual(probe.inject_html('google-site-verification: x'), 'google-site-verification: x')

    def test_wrong_dependency_is_refused(self):
        changed = dict(dependencies(), **{'ua_google_tag.py': b'other'})
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_HASH:ua_google_tag.py'):
            candidate_builder.build(source(), changed)

    def test_page_that_cannot_take_both_is_refused(self):
        value = dict(source(), **{'video/UA-0007-diag.html': b'<html><head></head><p>no body end</p></html>'})
        with self.assertRaisesRegex(ValueError, 'DIAG_COUNTERS_PAGE:video/UA-0007-diag.html'):
            candidate_builder.build(value, dependencies())

    def test_page_names_only_diagnostics(self):
        root = Path(tempfile.mkdtemp())
        for name in ('video/UA-0005-diag.html', 'site/UA-0012-diag.html', 'video/UA-0005.html',
                     'video/UA-0005-diag.html.bak', 'video/ua/UA-0005-diag.html', 'video/UA-X-diag.html'):
            (root/name).parent.mkdir(parents=True, exist_ok=True)
            (root/name).write_text('x')
        self.assertEqual(candidate_builder.page_names(root), ('video/UA-0005-diag.html', 'site/UA-0012-diag.html'))


class SmokeTests(unittest.TestCase):
    def test_preview_on_temporary_root(self):
        root = Path(tempfile.mkdtemp()).resolve()
        for name, value in source().items():
            (root/name).parent.mkdir(parents=True, exist_ok=True)
            (root/name).write_bytes(value)
        for name, value in dependencies().items():
            (root/name).write_bytes(value)
        (root/'video/preview/x').mkdir(parents=True)
        (root/'video/preview/x/a.html').write_text('<!--UA-CHAT-GLASS-V1-->')
        protected = ('start_safe.py', 'run_all.py', 'team_bot.py', 'lead_bot.py', 'db.py', 'publication_fence.py',
                     'ua_public_freshness.py', 'ua_site_counters.py', 'catalog_design_guard.py', 'cars_schema.py',
                     'stranica.py', 'master_card.py', 'publish_transaction_guard.py')
        for name in protected:
            (root/name).write_text('# installed\n')
        with patch.object(remote, 'ROOT', root):
            plan = remote.prepare(root/'work')
            value = remote.smoke(root/'work')
        self.assertEqual(sorted(plan['files']), ['site/UA-0005-diag.html', 'site_ge_inject.py', 'video/UA-0005-diag.html'])
        self.assertIn('ua_google_tag.py', plan['protected'])
        self.assertEqual(value['pages_with_both_once'], 2)
        self.assertTrue(value['inject_tail_last'])
        self.assertEqual((value['diag_pages_total'], value['drafts_total'], value['drafts_with_chat_style']), (3, 1, 1))
        self.assertEqual(json.loads((root/'work/plan.json').read_bytes())['site_write'], True)


class PageLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        patcher = patch.object(remote, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.backup = self.root/'backup'
        self.before = DIAG_PAGE.encode()
        self.after = candidate_builder.counted(DIAG_PAGE).encode()
        for prefix, value in (('before', self.before), ('after', self.after)):
            (self.backup/prefix/'video').mkdir(parents=True)
            (self.backup/prefix/'video/UA-0005-diag.html').write_bytes(value)
        (self.root/'video').mkdir()
        self.page = self.root/'video/UA-0005-diag.html'
        self.page.write_bytes(self.after)
        self.plan = {'files': {'video/UA-0005-diag.html': {'before': remote.sha(self.before), 'after': remote.sha(self.after),
                                                           'mode': 0o644, 'page': True}}, 'protected': {}}

    def test_rewrite_with_counters_is_installed_and_kept_by_rollback(self):
        newer = self.after.replace(b'<main>report</main>', b'<main>new report</main>')
        self.page.write_bytes(newer)
        remote.verify_files(self.plan, True)
        remote.restore(self.backup, self.plan)
        self.assertEqual(self.page.read_bytes(), newer)

    def test_rewrite_without_counters_is_refused(self):
        self.page.write_bytes(b'<html><head></head><body>other</body></html>')
        with self.assertRaisesRegex(remote.DeploymentError, 'FILE_CHANGED'):
            remote.verify_files(self.plan, True)
        with self.assertRaisesRegex(remote.DeploymentError, 'ROLLBACK_CONCURRENT_CHANGE'):
            remote.restore(self.backup, self.plan)

    def test_unchanged_install_rolls_back_to_the_backup(self):
        remote.restore(self.backup, self.plan)
        self.assertEqual(self.page.read_bytes(), self.before)


if __name__ == '__main__':
    unittest.main()
