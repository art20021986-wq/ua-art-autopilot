#!/usr/bin/env python3
"""Release-specific checks: pinned inputs and the preview smoke (BOUGHT-WORD-001)."""
import json
import types
import unittest
from unittest.mock import patch

import candidate_builder
import deployment_remote as remote

COUNTS = {'all': 18, 'kiev': 4, 'georgia': 4, 'sea': 6, 'korea': 4}
GOOD = {'audit': 'PASS', 'audit_errors': [], 'counts': COUNTS, 'live_counts': COUNTS, 'cards': 18,
        'cards_same_as_live_except_word': 18, 'checked_word': 0, 'stage1_status': [], 'sync_changes_built': [],
        'japan_label': ['В Японии · выкуплен', 'У Японії · викуплений']}


class BuildTests(unittest.TestCase):
    def test_builder_pins_inputs(self):
        self.assertEqual(set(candidate_builder.SOURCE_FILES), {'catalog_design_guard.py', 'ua_country_site.py'})
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'catalog_design_guard.py': b'x', 'ua_country_site.py': b'y'}, {})


class SmokeTests(unittest.TestCase):
    def run_smoke(self, stdout, returncode=0):
        result = types.SimpleNamespace(stdout=stdout, stderr='Traceback: boom', returncode=returncode)
        with patch.object(remote.subprocess, 'run', return_value=result):
            return remote.smoke(remote.Path('/tmp/x'))

    def test_accepts_and_rejects(self):
        self.assertEqual(self.run_smoke(json.dumps(GOOD))['cards'], 18)
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE:Traceback: boom'):
            self.run_smoke('', 1)
        for key, value in (('audit', 'FAIL'), ('checked_word', 2), ('counts', {**COUNTS, 'korea': 3}),
                           ('sync_changes_built', ['UA-0003'])):
            with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
                self.run_smoke(json.dumps({**GOOD, key: value}))


if __name__ == '__main__':
    unittest.main()
