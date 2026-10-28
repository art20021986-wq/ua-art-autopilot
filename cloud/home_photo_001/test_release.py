#!/usr/bin/env python3
"""Release-specific checks: exact inputs, the appended cars_ui hook, the pinned model."""
import ast
import hashlib
from io import BytesIO
import sys
import types
import unittest
from unittest.mock import patch

import build_cars_ui
import candidate_builder
import deployment_remote as remote
import release_constants

SOURCE = (b'import db\nlog = None\n\ndef with_stats_button(markup):\n    return ("filtered", markup)\n\n'
          b'def register(app):\n    app.append("base")\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class BuildTests(unittest.TestCase):
    def test_appends_hook_and_keeps_source(self):
        out = build_cars_ui.build(SOURCE, expected=sha(SOURCE))
        self.assertTrue(out.startswith(SOURCE.rstrip(b'\n')))
        names = [n.name for n in ast.parse(out).body if isinstance(n, ast.FunctionDef)]
        self.assertEqual(names, ['with_stats_button', 'register', 'with_stats_button', 'register'])

    def test_hook_wraps_previous_menu_and_register(self):
        calls = []
        bot = types.SimpleNamespace(with_button=lambda original, menu: ('button', original, menu),
                                    register=lambda app: app.append('photo'))
        namespace = {}
        with patch.dict(sys.modules, {'db': types.ModuleType('db'), 'ua_home_photo_bot': bot}):
            exec(build_cars_ui.build(SOURCE, expected=sha(SOURCE)), namespace)
            self.assertEqual(namespace['with_stats_button']('menu'), ('button', 'menu', ('filtered', 'menu')))
            namespace['register'](calls)
        self.assertEqual(calls, ['base', 'photo'])

    def test_hook_failure_keeps_the_crm_menu(self):
        class Log:
            warnings = []
            def warning(self, *args):
                self.warnings.append(args)
        broken = types.SimpleNamespace(with_button=lambda *a: 1 / 0, register=lambda app: 1 / 0)
        namespace = {}
        with patch.dict(sys.modules, {'db': types.ModuleType('db'), 'ua_home_photo_bot': broken}):
            exec(build_cars_ui.build(SOURCE, expected=sha(SOURCE)), namespace)
            namespace['log'] = Log()
            self.assertEqual(namespace['with_stats_button']('menu'), ('filtered', 'menu'))
            apps = []
            namespace['register'](apps)
        self.assertEqual(apps, ['base'])
        self.assertEqual(len(Log.warnings), 2)

    def test_refuses_other_source_repeat_or_missing_hooks(self):
        with self.assertRaises(build_cars_ui.BuildError):
            build_cars_ui.build(SOURCE)
        once = build_cars_ui.build(SOURCE, expected=sha(SOURCE))
        with self.assertRaises(build_cars_ui.BuildError):
            build_cars_ui.build(once, expected=sha(once))
        bare = b'def register(app):\n    pass\n'
        with self.assertRaises(build_cars_ui.BuildError):
            build_cars_ui.build(bare, expected=sha(bare))

    def test_builder_pins_inputs(self):
        self.assertEqual(candidate_builder.SOURCE_SHA256['cars_ui.py'],
                         '19adbff34be18402897ca4b54889c9361bcdd261f329218e147b72f8031f9ad6')
        with self.assertRaises(ValueError):
            candidate_builder.build({'cars_ui.py': b'other'}, {})


class ModelTests(unittest.TestCase):
    def fetch(self, payload):
        response = BytesIO(payload)
        with patch.object(remote.urllib.request, 'urlopen', return_value=response) as opened:
            value = remote.fetch_model()
        self.assertEqual(opened.call_args.args[0].full_url, release_constants.MODEL_URL)
        return value

    def test_model_is_pinned_to_commit_and_hash(self):
        self.assertIn('/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/', release_constants.MODEL_URL)
        self.assertRegex(release_constants.MODEL_SHA256, '^[0-9a-f]{64}$')

    def test_other_bytes_stop_the_release(self):
        for payload in (b'', b'x' * release_constants.MODEL_BYTES):
            with self.assertRaisesRegex(remote.DeploymentError, 'MODEL_HASH'):
                self.fetch(payload)

    def test_pinned_bytes_are_returned(self):
        payload = b'model'
        with patch.object(remote, 'MODEL_BYTES', len(payload)), patch.object(remote, 'MODEL_SHA256', sha(payload)):
            self.assertEqual(self.fetch(payload), payload)


class SmokeTests(unittest.TestCase):
    def run_smoke(self, stdout, returncode=0):
        result = types.SimpleNamespace(stdout=stdout, stderr='Traceback: boom', returncode=returncode)
        with patch.object(remote.subprocess, 'run', return_value=result) as run:
            value = remote.smoke(remote.Path('/tmp/x'))
        self.assertEqual(run.call_args.args[0][:3], ['python3.10', '-B', '-c'])
        return value

    def test_accepts_exact_frame_and_home_edit(self):
        value = self.run_smoke('noise\n{"framed_size": [1800, 1200], "home_edit_ok": true}\n')
        self.assertEqual(value['framed_size'], [1800, 1200])

    def test_rejects_failure_wrong_ratio_or_home_edit(self):
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE:Traceback: boom'):
            self.run_smoke('', 1)
        for bad in ('{"framed_size": [1800, 1199], "home_edit_ok": true}',
                    '{"framed_size": [1800, 1200], "home_edit_ok": false}'):
            with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
                self.run_smoke(bad)

    def test_smoke_never_imports_the_crm_database(self):
        self.assertIn("sys.modules['db'] = types.ModuleType('db')", remote.SMOKE)
        self.assertNotIn('crm.db', remote.SMOKE)


if __name__ == '__main__':
    unittest.main()
