import ast
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import compose_release as release


class ReleaseCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = release.publication_builder()
        cls.original = (Path(cls.builder.__file__).parents[1] / 'crm_performance_001/fixtures/worker_before.py').read_bytes()
        cls.publication = cls.builder.patch_worker(cls.original.decode()).encode()
        cls.candidate = release.compose_file('ua_crm_public_sync.py', cls.original, cls.publication)

    def test_worker_matches_reviewed_publication_intermediate(self):
        self.assertEqual(hashlib.sha256(self.publication).hexdigest(),
                         release.PUBLICATION_CANDIDATE_SHA256['ua_crm_public_sync.py'])
        before = ast.parse(self.publication)
        after = ast.parse(self.candidate)
        def remaining(tree):
            return [ast.dump(n) for n in tree.body if not isinstance(n, ast.FunctionDef) or n.name != 'snapshot']
        self.assertEqual(remaining(before), remaining(after))

    def test_changed_runtime_or_publication_candidate_is_rejected(self):
        for original, publication in [(self.original + b'\n', self.publication),
                                      (self.original, self.publication + b'\n')]:
            with self.subTest(original_changed=original != self.original), self.assertRaises(ValueError):
                release.compose_file('ua_crm_public_sync.py', original, publication)

    def test_other_publication_outputs_cannot_be_silently_omitted(self):
        with self.assertRaisesRegex(ValueError, 'PUBLICATION_CANDIDATE_SET'):
            release.combine({}, {'ua_crm_public_sync.py': self.publication})

    def test_media_revision_change_is_published_through_composed_worker(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root/'worker.py'; path.write_bytes(self.candidate)
            spec = importlib.util.spec_from_file_location('combined_worker_fixture', path)
            worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
            worker.ROOT = root
            worker.STATE = root/'state.json'; worker.LOCK = root/'worker.lock'
            old = {'1': {'code': 'UA-0001', 'sha256': 'old-media', 'delivery_status': 'korea'}}
            new = {'1': {**old['1'], 'sha256': 'changed-media-ledger'}}
            worker.save_state({'version': 1, 'revisions': old, 'retry': {}, 'last_success': None})
            published, verified = [], []
            revision = types.SimpleNamespace(snapshot=lambda received: new if received == root else None)
            requests = types.SimpleNamespace(pending=lambda received: {}, finish=lambda *args: None)
            freshness = types.SimpleNamespace(verify_public=lambda code: verified.append(code))
            with patch.dict('sys.modules', {'crm_revision': revision, 'ua_publish_requests': requests,
                                           'ua_public_freshness': freshness}):
                def publish(code):
                    published.append(code)
                    return True, 'ok'
                self.assertEqual(worker.reconcile_once(publish=publish, clock=lambda: 100), 'published')
                self.assertEqual(worker.reconcile_once(publish=publish, clock=lambda: 101), 'idle')
            self.assertEqual(published, ['UA-0001'])
            self.assertEqual(verified, ['UA-0001'])


if __name__ == '__main__':
    unittest.main()
