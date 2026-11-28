#!/usr/bin/env python3
"""Release-specific checks: pinned input and the preview smoke (SEO-PRICE-001)."""
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

import candidate_builder
import deployment_remote as remote
import metadata_tail

HERE = Path(__file__).resolve().parent
CARD = {'price': 19900, 'title_before_block': True, 'title_live': True, 'ld_before_block': True, 'same_canonical': True}


class BuildTests(unittest.TestCase):
    def test_builder_pins_the_live_module(self):
        self.assertEqual(candidate_builder.SOURCE_FILES, ('ua_seo_metadata.py',))
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'ua_seo_metadata.py': b'other'}, {})

    def test_tail_on_the_live_source_compiles(self):
        source = (HERE / 'fixtures/ua_seo_metadata.txt').read_bytes()
        result = metadata_tail.build(source)
        compile(result, 'ua_seo_metadata.py', 'exec')
        self.assertEqual(result[:len(source.rstrip(b'\n'))], source.rstrip(b'\n'))
        self.assertEqual(result.count(b'def card_facts('), 2)


class SmokeTests(unittest.TestCase):
    def run_smoke(self, stdout, returncode=0):
        result = types.SimpleNamespace(stdout=stdout, stderr='Traceback: boom', returncode=returncode)
        with patch.object(remote.subprocess, 'run', return_value=result) as run:
            value = remote.smoke(remote.Path('/tmp/x'))
        self.assertEqual(run.call_args.args[0][:3], ['python3.10', '-B', '-c'])
        return value

    def test_accepts_expected_result(self):
        value = self.run_smoke('noise\n' + json.dumps({'cards': {'UA-0017': CARD, 'UA-0002': {'price': None}}}))
        self.assertEqual(value['summary'], {'cards': 2, 'priced': 1, 'title_before_block': 1, 'title_live': 1,
                                            'ld_before_block': 1, 'same_canonical': 1})

    def test_rejects_failure_or_wrong_result(self):
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE:Traceback: boom'):
            self.run_smoke('', 1)
        for key in ('title_before_block', 'title_live', 'ld_before_block', 'same_canonical'):
            with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
                self.run_smoke(json.dumps({'cards': {'UA-0017': {**CARD, key: False}}}))
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
            self.run_smoke(json.dumps({'cards': {}}))

    def test_smoke_reads_live_only(self):
        self.assertIn('RLIMIT_FSIZE, (0, 0)', remote.SMOKE)
        self.assertIn('mode=ro', remote.SMOKE)
        self.assertNotIn('write', remote.SMOKE)


if __name__ == '__main__':
    unittest.main()
