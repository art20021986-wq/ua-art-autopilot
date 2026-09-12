"""Offline contracts for an inert package and the server gate's I/O boundaries."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load('isolated_server_gate_test', HERE/'server_gate.py')
packager = load('isolated_server_packager_test', HERE/'package_server_gate.py')


class ServerGateTests(unittest.TestCase):
    def test_seven_source_snapshot_is_read_only_and_never_imports_application(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            expected = {}
            for name in gate.SOURCE_NAMES:
                data = ("raise RuntimeError('PRODUCTION_APPLICATION_MUST_NOT_EXECUTE')\n# "+name+'\n').encode()
                (root/name).write_bytes(data)
                expected[name] = hashlib.sha256(data).hexdigest()
            before = {name: ((root/name).read_bytes(), (root/name).stat().st_mtime_ns) for name in gate.SOURCE_NAMES}
            snapshot, copies = gate.read_source_snapshot(root, expected)
            self.assertEqual(set(snapshot), set(gate.SOURCE_NAMES))
            self.assertEqual({name: copies[name] for name in copies}, {name: before[name][0] for name in before})
            self.assertEqual(before, {name: ((root/name).read_bytes(), (root/name).stat().st_mtime_ns) for name in gate.SOURCE_NAMES})
            (root/'cars_ui.py').write_text('changed source')
            with self.assertRaisesRegex(gate.GateError, 'PRODUCTION_SOURCE_HASH_MISMATCH:cars_ui.py'):
                gate.read_source_snapshot(root, expected)
            failure = gate.failure_details(OSError(22, 'untrusted detail', '/private/source.py'), 'candidate_compile')
            self.assertEqual(failure['failure_errno'], 22)
            self.assertEqual(failure['failure_phase'], 'candidate_compile')
            self.assertNotIn('/private', json.dumps(failure))
            self.assertNotIn('untrusted detail', json.dumps(failure))

    def test_stage_validation_refuses_wrong_cwd_and_unreviewed_runner_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage = root/'isolated-stage'
            (stage/'cloud/spec_auto10_restore').mkdir(parents=True)
            script = stage/'cloud/spec_auto10_restore/server_gate.py'
            script.write_text('# fixture')
            with patch.object(gate, 'STAGE', stage):
                gate.validate_stage(stage, script, stage)
                with self.assertRaisesRegex(gate.GateError, 'CWD_MUST_BE_EXACT'):
                    gate.validate_stage(stage, script, root)
                with self.assertRaisesRegex(gate.GateError, 'RUNNER_MUST_BE_INSIDE'):
                    gate.validate_stage(stage, root/'different.py', stage)
            private_tmp = root/'tmp'
            private_tmp.mkdir(mode=0o700)
            with patch.object(gate, 'TMP_PARENT', private_tmp):
                owned = gate.create_owned_temp()
                self.assertEqual(owned.parent, private_tmp)
                self.assertTrue(owned.name.startswith(gate.TMP_PREFIX))
                self.assertEqual(owned.stat().st_mode & 0o077, 0)
                with self.assertRaises(gate.GateError):
                    gate.validate_owned_temp(private_tmp)
                owned.chmod(0o755)
                with self.assertRaises(gate.GateError):
                    gate.validate_owned_temp(owned)

    def test_io_guard_blocks_production_writes_imports_database_and_network(self):
        with tempfile.TemporaryDirectory() as folder:
            server = Path(folder)
            stage = server/'stage'
            stage.mkdir()
            temp_parent = server/'tmp'
            temp_parent.mkdir(mode=0o700)
            with patch.object(gate, 'TMP_PARENT', temp_parent):
                owned = gate.create_owned_temp()
                guard, counters = gate.make_audit_guard(stage, server, owned_temp=owned)
            guard('open', (str(stage/'temporary.db'), 'w', os.O_WRONLY | os.O_CREAT))
            guard('open', (str(owned/'temporary.db'), 'w', os.O_WRONLY | os.O_CREAT))
            guard('os.rename', (str(owned/'before'), str(owned/'after'), -1, -1))
            guard('open', (str(server/'cars_ui.py'), 'r', os.O_RDONLY))
            for event, args in (
                ('open', (str(server/'cars_ui.py'), 'w', os.O_WRONLY)),
                ('open', (str(server/'crm.db'), 'r', os.O_RDONLY)),
                ('sqlite3.connect', (str(server/'crm.db'),)),
                ('import', ('cars_ui', str(server/'cars_ui.py'))),
                ('compile', (b'pass', str(server/'cars_ui.py'))),
                ('socket.connect', (None, ('example.invalid', 443))),
                ('subprocess.Popen', ('python', [], None, None)),
                ('os.rename', (str(stage/'before.html'), str(server/'video/UA-0016.html'), -1, -1)),
                ('open', (str(temp_parent/'unowned.db'), 'w', os.O_WRONLY | os.O_CREAT)),
                ('os.mkdir', (str(temp_parent/'another-scratch'), 0o700, -1)),
            ):
                with self.subTest(event=event), self.assertRaises(gate.GateError):
                    guard(event, args)
            self.assertEqual(counters['blocked_network_or_process_actions'], 2)
            self.assertGreaterEqual(counters['blocked_outside_stage_writes'], 3)
            approved = [sys.executable, '-I', '-B', '-c', gate.LOCK_PROBE_SCRIPT, str(stage/'lock')]
            guard('subprocess.Popen', (sys.executable, approved, None, None))
            self.assertEqual(counters['isolated_lock_probe_processes'], 1)
            guard('subprocess.Popen', (sys.executable, approved[:-1]+[str(owned/'lock')], None, None))
            self.assertEqual(counters['isolated_lock_probe_processes'], 2)
            for command in (approved[:-1]+[str(server/'lock')], approved[:-1]+[str(temp_parent/'lock')],
                            approved[:4]+['print(1)', approved[-1]]):
                with self.assertRaises(gate.GateError):
                    guard('subprocess.Popen', (sys.executable, command, None, None))
            (owned/'escape').symlink_to(server/'crm.db')
            with self.assertRaises(gate.GateError):
                guard('open', (str(owned/'escape'), 'w', os.O_WRONLY))

    def test_io_guard_resolves_relative_directory_descriptors(self):
        with tempfile.TemporaryDirectory() as folder:
            server = Path(folder)
            stage = server/'stage'
            stage.mkdir()
            guard, counters = gate.make_audit_guard(stage, server)
            server_fd = os.open(server, os.O_RDONLY | os.O_DIRECTORY)
            stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
            try:
                guard('os.link', ('src', 'dst', stage_fd, stage_fd))
                guard('os.mkdir', ('candidate', 0o700, stage_fd))
                guard('os.remove', ('owned', stage_fd))
                for event, args in (
                    ('os.link', ('src', 'dst', stage_fd, server_fd)),
                    ('os.mkdir', ('candidate', 0o700, server_fd)),
                    ('os.remove', ('existing', server_fd)),
                    ('os.rename', ('owned', 'existing', stage_fd, server_fd)),
                ):
                    with self.subTest(event=event), self.assertRaises(gate.GateError):
                        guard(event, args)
                self.assertEqual(counters['blocked_outside_stage_writes'], 4)
            finally:
                os.close(stage_fd)
                os.close(server_fd)

    def test_package_has_complete_manifest_expected_sources_legacy_fixtures_and_no_databases(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'gate.zip'
            report = packager.build(output)
            self.assertFalse(report['server_executed'])
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertTrue(set(packager.LEGACY_FIXTURES) <= names)
                self.assertIn('cloud/spec_auto10_restore/server_gate.py', names)
                self.assertIn('cloud/spec_auto10_restore/tests/test_server_gate.py', names)
                self.assertFalse(any(name.endswith(('.db', '.pyc')) for name in names))
                self.assertEqual({name for name in names if name.endswith('.html')},
                                 {'cloud/spec_auto10_restore/tests/fixtures/reviewed_shell_assets.html'})
                manifest = json.loads(archive.read('server-gate-manifest.json'))
                self.assertIn('cloud/spec_auto10_restore/tests/fixtures/reviewed_shell_assets.html', archive.namelist())
                self.assertEqual(set(manifest['files']) | {'server-gate-manifest.json'}, names)
                for name, info in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), info['sha256'])
                expected = json.loads(archive.read('server-expected-sources.json'))
                self.assertEqual(set(expected['source_byte_hashes']), set(gate.SOURCE_NAMES))
            before = output.read_bytes()
            with self.assertRaisesRegex(ValueError, 'OUTPUT_ALREADY_EXISTS'):
                packager.build(output)
            self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
