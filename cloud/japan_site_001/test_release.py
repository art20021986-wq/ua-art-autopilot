#!/usr/bin/env python3
"""Release-specific checks: pinned inputs and the preview smoke (JAPAN-STOCK-001 step 2)."""
import json
import types
import unittest
from unittest.mock import patch

import candidate_builder
import deployment_remote as remote

GOOD = {'audit': 'PASS', 'audit_errors': [], 'counts': {'all': 18, 'kiev': 4, 'georgia': 4, 'sea': 6, 'korea': 4},
        'live_counts': {'all': 18, 'kiev': 4, 'georgia': 4, 'sea': 6, 'korea': 4}, 'cards': 18,
        'cards_same_as_live': 18, 'countries': 18, 'row': 1, 'korea_button': ['Выкуплены · 4'],
        'sync_changes_live': [], 'sync_changes_built': []}


class BuildTests(unittest.TestCase):
    def test_builder_pins_step_one_modules(self):
        self.assertEqual(set(candidate_builder.DEPENDENCY_SHA256), {'ua_car_country.py', 'ua_delivery_status.py'})
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({}, {'ua_car_country.py': b'other', 'ua_delivery_status.py': b'x'})
        self.assertNotIn('video/index.html', candidate_builder.SOURCE_FILES)
        self.assertIn('catalog_design_golden.html', candidate_builder.SOURCE_FILES)


class SmokeTests(unittest.TestCase):
    def run_smoke(self, stdout, returncode=0):
        result = types.SimpleNamespace(stdout=stdout, stderr='Traceback: boom', returncode=returncode)
        with patch.object(remote.subprocess, 'run', return_value=result) as run:
            value = remote.smoke(remote.Path('/tmp/x'))
        self.assertEqual(run.call_args.args[0][:3], ['python3.10', '-B', '-c'])
        return value

    def test_accepts_expected_result(self):
        self.assertEqual(self.run_smoke('noise\n' + json.dumps(GOOD))['row'], 1)

    def test_rejects_failure_or_wrong_result(self):
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE:Traceback: boom'):
            self.run_smoke('', 1)
        for key, value in (('audit', 'FAIL'), ('row', 0), ('countries', 17), ('korea_button', ['В Корее · 4']),
                           ('sync_changes_live', ['UA-0001']), ('counts', {**GOOD['counts'], 'korea': 3})):
            with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
                self.run_smoke(json.dumps({**GOOD, key: value}))

    def test_smoke_reads_live_only(self):
        self.assertIn("sys.modules['db'] = fake", remote.SMOKE)
        self.assertIn('mode=ro', remote.SMOKE)
        self.assertNotIn('write', remote.SMOKE.replace('patch_catalog_stages', ''))


if __name__ == '__main__':
    unittest.main()
