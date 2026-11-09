#!/usr/bin/env python3
"""Release-specific checks: exact inputs, the appended cars_ui hook, the preview smoke."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import build_cars_ui
import candidate_builder
import deployment_remote as remote

SOURCE = (b'import db\nlog = None\n\ndef card_kb(card, staff):\n    return ("base", card, staff)\n\n'
          b'def register(app):\n    app.append("base")\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_built():
    """The built cars_ui.py as a module (a temporary file, imported like the bot imports it)."""
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'cars_ui_built.py'
        path.write_bytes(build_cars_ui.build(SOURCE, expected=sha(SOURCE)))
        spec = importlib.util.spec_from_file_location('cars_ui_built', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class BuildTests(unittest.TestCase):
    def test_appends_hook_and_keeps_source(self):
        out = build_cars_ui.build(SOURCE, expected=sha(SOURCE))
        self.assertTrue(out.startswith(SOURCE.rstrip(b'\n')))
        names = [n.name for n in ast.parse(out).body if isinstance(n, ast.FunctionDef)]
        self.assertEqual(names, ['card_kb', 'register', 'card_kb', 'register'])

    def test_hook_wraps_previous_card_kb_and_register(self):
        calls = []
        bot = types.SimpleNamespace(with_button=lambda markup, card, staff: ('button', markup),
                                    register=lambda app: app.append('stage'))
        with patch.dict(sys.modules, {'db': types.ModuleType('db'), 'ua_home_stage_bot': bot}):
            built = load_built()
            self.assertEqual(built.card_kb('car', 'owner'), ('button', ('base', 'car', 'owner')))
            built.register(calls)
        self.assertEqual(calls, ['base', 'stage'])

    def test_hook_failure_keeps_the_card(self):
        class Log:
            warnings = []
            def warning(self, *args):
                self.warnings.append(args)
        broken = types.SimpleNamespace(with_button=lambda *a: 1 / 0, register=lambda app: 1 / 0)
        with patch.dict(sys.modules, {'db': types.ModuleType('db'), 'ua_home_stage_bot': broken}):
            built = load_built()
            built.log = Log()
            self.assertEqual(built.card_kb('car', 'owner'), ('base', 'car', 'owner'))
            apps = []
            built.register(apps)
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
                         '32eb47b07378ecd3213f0d85e877a0aa779338764c5738a15ae77bb8771cdd6d')
        self.assertEqual(set(candidate_builder.DEPENDENCY_SHA256), {'db.py', 'master_card.py', 'publication_fence.py'})
        with self.assertRaises(ValueError):
            candidate_builder.build({'cars_ui.py': b'other'}, {})


class SmokeTests(unittest.TestCase):
    TILE = '{"edit_ok": %s, "others_kept": %s}'

    def run_smoke(self, stdout, returncode=0):
        result = types.SimpleNamespace(stdout=stdout, stderr='Traceback: boom', returncode=returncode)
        with patch.object(remote.subprocess, 'run', return_value=result) as run:
            value = remote.smoke(remote.Path('/tmp/x'))
        self.assertEqual(run.call_args.args[0][:3], ['python3.10', '-B', '-c'])
        return value

    def test_accepts_edit_of_every_tile(self):
        value = self.run_smoke('noise\n{"tiles": {"kiev": %s}}\n' % (self.TILE % ('true', 'true')))
        self.assertTrue(value['tiles']['kiev']['edit_ok'])

    def test_rejects_failure_or_bad_edit(self):
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE:Traceback: boom'):
            self.run_smoke('', 1)
        for flags in (('false', 'true'), ('true', 'false')):
            with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
                self.run_smoke('{"tiles": {"kiev": %s}}' % (self.TILE % flags))

    def test_smoke_reads_only(self):
        self.assertIn("sys.modules['db'] = fake_db", remote.SMOKE)
        self.assertIn('mode=ro', remote.SMOKE)
        self.assertNotIn('publish(', remote.SMOKE)
        self.assertNotIn('open(root + \'/video/index.html\', \'w', remote.SMOKE)


if __name__ == '__main__':
    unittest.main()
