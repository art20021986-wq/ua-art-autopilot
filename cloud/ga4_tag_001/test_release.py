#!/usr/bin/env python3
"""Release-specific checks: exact installed inputs, planned files and the catalog hook."""
import base64
import hashlib
import json
from pathlib import Path
import importlib.util
import tempfile
import unittest

import candidate_builder
import ua_google_tag

HERE = Path(__file__).resolve().parent
# Where each replaced module was last released.
PREVIOUS = {'ua_seo_metadata.py': 'seo_growth_001', 'ua_seo_index.py': 'gsc_growth_001'}
# A stand-in for the private publish_transaction_guard.py with the names the block uses.
GUARD = b'''import pathlib
ROOTS = ()
LOG = []
class PublishError(RuntimeError):
    pass
def _read(path):
    return path.read_bytes()
def _atomic(path, data, mode=None):
    path.write_bytes(data)
def _sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()
def _append_log(message):
    LOG.append(message)
def _install_catalog(source, target):
    for root in ROOTS:
        (root / 'katalog.html').write_bytes(source.encode())
    return {'installed': {str(root / 'katalog.html'): {'sha256': 'old'} for root in ROOTS}}
'''


def load(source, folder):
    path = Path(folder) / 'guard_under_test.py'
    path.write_bytes(source)
    spec = importlib.util.spec_from_file_location('guard_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def installed():
    value = {name: (HERE.parent / folder / name).read_bytes() for name, folder in PREVIOUS.items()}
    return {**value, 'publish_transaction_guard.py': GUARD}


class ReleaseTests(unittest.TestCase):
    def test_pins_match_the_installed_releases(self):
        for name, folder in PREVIOUS.items():
            plan = json.loads((HERE.parent / folder / 'deployment_plan.json').read_text())['files']
            self.assertEqual(plan[name]['after'], candidate_builder.SOURCE_SHA256[name])

    def test_builder_refuses_unexpected_inputs(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH:ua_seo_index.py'):
            candidate_builder.build({**installed(), 'ua_seo_index.py': b'other'}, {})

    def build(self, source, pages):
        pins = {name: hashlib.sha256(value).hexdigest() for name, value in source.items()}
        original = candidate_builder.SOURCE_SHA256
        candidate_builder.SOURCE_SHA256 = pins
        try:
            return candidate_builder.build(source, pages)
        finally:
            candidate_builder.SOURCE_SHA256 = original

    def test_planned_files_and_pages(self):
        pages = {'video/index.html': b'<html><head><title>x</title></head><body></body></html>',
                 'video/UA-0018.html': ('<html><head>' + ua_google_tag.SNIPPET + '</head></html>').encode()}
        result = self.build(installed(), pages)
        self.assertEqual(sorted(result), ['publish_transaction_guard.py', 'ua_google_tag.py', 'ua_seo_index.py',
                                          'ua_seo_metadata.py', 'video/index.html'])
        for name, value in result.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')
        self.assertIn(b'G-6SRBQK6GY4', result['video/index.html'])

    def test_patch_needs_its_anchors_and_runs_once(self):
        with self.assertRaisesRegex(ValueError, 'PATCH_ANCHOR'):
            self.build({**installed(), 'publish_transaction_guard.py': GUARD.replace(b'def _append_log', b'def log')}, {})
        patched = self.build(installed(), {})['publish_transaction_guard.py']
        with self.assertRaisesRegex(ValueError, 'ALREADY_PATCHED'):
            self.build({**installed(), 'publish_transaction_guard.py': patched}, {})

    def test_catalog_block_tags_every_root(self):
        patched = self.build(installed(), {})['publish_transaction_guard.py']
        with tempfile.TemporaryDirectory() as temp:
            roots = (Path(temp) / 'video', Path(temp) / 'site')
            for root in roots:
                root.mkdir()
            module = load(patched, temp)
            module.ROOTS = roots
            result = module._install_catalog('<html><head></head><body>cars</body></html>', None)
            for root in roots:
                data = (root / 'katalog.html').read_bytes()
                self.assertEqual(data.count(b'G-6SRBQK6GY4'), 2)
                self.assertEqual(result['installed'][str(root / 'katalog.html')]['sha256'], hashlib.sha256(data).hexdigest())

    def test_catalog_block_never_blocks_the_sale(self):
        patched = self.build(installed(), {})['publish_transaction_guard.py']
        with tempfile.TemporaryDirectory() as temp:
            module = load(patched, temp)
            module.ROOTS = (Path(temp),)
            (Path(temp) / 'katalog.html').write_bytes(b'')
            module._UA_GA4_TAG_BASE_INSTALL = lambda source, target: {}
            (Path(temp) / 'katalog.html').write_bytes(b'\xff not utf-8')
            self.assertEqual(module._install_catalog('', None), {})
            self.assertEqual((Path(temp) / 'katalog.html').read_bytes(), b'\xff not utf-8')
            self.assertTrue(module.LOG[0].startswith('GA4_TAG_SKIPPED'))

    def test_real_pages_get_one_tag_in_head(self):
        home = json.loads((HERE.parent / 'home_layout_001/live_home.json').read_text())['files']
        order = json.loads((HERE.parent / 'podbor_probe_20261025/live_podbor_r3.json').read_text())['files']
        for raw in (home['https://www.uaart.com.ua/video/index.html']['b64'],
                    order['https://www.uaart.com.ua/video/podbor.html?strana=korea&lang=uk']['b64']):
            page = base64.b64decode(raw).decode()
            tagged = ua_google_tag.apply(page)
            self.assertEqual(tagged.count(ua_google_tag.MARK), 1)
            self.assertLess(tagged.index(ua_google_tag.MARK), tagged.index('</head>'))
            self.assertEqual(tagged.replace(ua_google_tag.SNIPPET, ''), page)
            self.assertEqual(ua_google_tag.apply(tagged), tagged)


if __name__ == '__main__':
    unittest.main()
