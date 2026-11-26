#!/usr/bin/env python3
"""Release-specific checks: exact inputs and the preview smoke (JAPAN-STOCK-001 step 1)."""
import hashlib
import json
import types
import unittest
from unittest.mock import patch

import candidate_builder
import deployment_remote as remote

GOOD = {'rows': remote.EXPECTED_ROWS, 'labels': remote.EXPECTED_LABELS, 'stored': remote.EXPECTED_STORED,
        'saved': {'before': 'korea', 'changed': [False, True, False], 'after': 'japan', 'japan_ids': [7],
                  'journal': [[1, 'card_edit', 'cars', 7, 'country', 'korea', 'japan']]},
        'live': {'stage_counts': {'korea': 4}, 'car_country_table': False}}


class BuildTests(unittest.TestCase):
    def test_builder_pins_inputs(self):
        self.assertEqual(set(candidate_builder.SOURCE_SHA256), {'ua_delivery_status.py', 'cars_ui.py', 'konteyner.py'})
        self.assertEqual(set(candidate_builder.DEPENDENCY_SHA256), {'db.py', 'cars_schema.py'})
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'cars_ui.py': b'other'}, {})

    def test_build_with_matching_inputs(self):
        source = {e.NAME: (candidate_builder.HERE / 'fixtures' / e.NAME.replace('.py', '.txt')).read_bytes()
                  for e in candidate_builder.EDITS}
        expected = {name: hashlib.sha256(value).hexdigest() for name, value in source.items()}
        deps = {'db.py': b'db', 'cars_schema.py': b'schema'}
        pins = {name: hashlib.sha256(value).hexdigest() for name, value in deps.items()}
        with patch.dict(candidate_builder.DEPENDENCY_SHA256, pins), \
             patch.object(candidate_builder.edit_cars_ui, 'compile', create=True), \
             patch.object(candidate_builder.edit_konteyner, 'compile', create=True):
            result = candidate_builder.build(source, deps, expected=expected)
        self.assertEqual(set(result), {'ua_delivery_status.py', 'cars_ui.py', 'konteyner.py', 'ua_car_country.py'})


class SmokeTests(unittest.TestCase):
    def run_smoke(self, stdout, returncode=0):
        result = types.SimpleNamespace(stdout=stdout, stderr='Traceback: boom', returncode=returncode)
        with patch.object(remote.subprocess, 'run', return_value=result) as run:
            value = remote.smoke(remote.Path('/tmp/x'))
        self.assertEqual(run.call_args.args[0][:3], ['python3.10', '-B', '-c'])
        return value

    def test_accepts_expected_result(self):
        self.assertEqual(self.run_smoke('noise\n' + json.dumps(GOOD))['saved']['after'], 'japan')

    def test_rejects_failure_or_wrong_result(self):
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE:Traceback: boom'):
            self.run_smoke('', 1)
        for key, value in (('rows', [['На пароме']]), ('live', {'stage_counts': {}, 'car_country_table': True})):
            with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
                self.run_smoke(json.dumps({**GOOD, key: value}))

    def test_smoke_reads_live_only(self):
        self.assertIn("sys.modules['db'] = fake", remote.SMOKE)
        self.assertIn('mode=ro', remote.SMOKE)
        self.assertIn("temp + '/crm.db'", remote.SMOKE)


if __name__ == '__main__':
    unittest.main()
