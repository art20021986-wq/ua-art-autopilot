#!/usr/bin/env python3
"""Release-specific checks: exact inputs, modules shipped as is, worker republish via revision."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_public_sync  # noqa: E402
import candidate_builder  # noqa: E402
import deployment_remote as remote  # noqa: E402
from release_constants import NEW_MODULES, REPLACED_MODULES  # noqa: E402
from test_seo_growth import installed  # noqa: E402

DIAG = HERE.parent / 'crm_diag_media_publish_001'
R5 = HERE.parent / 'crm_video_probe_20261012_r5' / 'sanitized_sources.txt'


class ReleaseTests(unittest.TestCase):
    def sources(self):
        spec = importlib.util.spec_from_file_location('diag_build', DIAG / 'build_public_sync.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text = R5.read_text(encoding='utf-8').split('# ===== ua_crm_public_sync.py =====\n', 1)[1]
        text = text.split('\n# ===== ua_publish_requests.py =====\n', 1)[0].rstrip('\n') + '\n'
        sync = module.build(text.encode())
        return {'ua_seo_metadata.py': installed('ua_seo_metadata.py').encode(),
                'ua_seo_sitemap.py': installed('ua_seo_sitemap.py').encode(),
                'publish_transaction_guard.py': installed('publish_transaction_guard.py').encode(),
                'ua_crm_public_sync.py': sync}

    def test_builder_on_exact_installed_sources(self):
        source = self.sources()
        for name, value in source.items():
            self.assertEqual(hashlib.sha256(value).hexdigest(), candidate_builder.SOURCE_SHA256[name], name)
        candidate = candidate_builder.build(source, {})
        self.assertEqual(set(candidate), set(NEW_MODULES) | set(REPLACED_MODULES)
                         | {'publish_transaction_guard.py', 'ua_crm_public_sync.py'})
        for name in NEW_MODULES + REPLACED_MODULES:
            self.assertEqual(candidate[name], (HERE / name).read_bytes())
        for name, value in candidate.items():
            compile(value, name, 'exec')
        sync = candidate['ua_crm_public_sync.py'].decode()
        self.assertEqual(sync.count('_seo_revision=SEO_REVISION'), 1)
        self.assertEqual(sync.replace(build_public_sync.NEW, build_public_sync.OLD)
                         .replace(build_public_sync.IMPORT_NEW, build_public_sync.IMPORT_OLD),
                         source['ua_crm_public_sync.py'].decode())

    def test_builder_refuses_unexpected_inputs(self):
        source = self.sources()
        for name in source:
            with self.assertRaises(ValueError):
                candidate_builder.build(dict(source, **{name: source[name] + b'\n'}), {})

    def test_revision_changes_for_every_card_once(self):
        sync = candidate_builder.build(self.sources(), {})['ua_crm_public_sync.py'].decode()
        snapshot = sync.split('def snapshot():', 1)[1].split('\ndef ', 1)[0]
        self.assertIn('from ua_seo_metadata import SEO_REVISION', snapshot)
        self.assertLess(snapshot.index('_diag_files=diag_files'), snapshot.index('_seo_revision'))
        self.assertLess(snapshot.index('_seo_revision'), snapshot.index('raw = json.dumps(source'))

    def test_import_check_on_candidate_modules(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for name in NEW_MODULES + REPLACED_MODULES:
                (folder / name).write_bytes((HERE / name).read_bytes())
            remote.import_check(folder)
            (folder / 'ua_seo_schema.py').write_text('raise ImportError("broken")\n')
            with self.assertRaisesRegex(remote.DeploymentError, 'CANDIDATE_IMPORT'):
                remote.import_check(folder)

    def test_no_catalog_repair_mode(self):
        self.assertFalse(hasattr(remote, 'repair_catalog'))


if __name__ == '__main__':
    unittest.main()
