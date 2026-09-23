"""Targeted guard and pure relocation failures; no application imports."""
import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rehearsal = load("full_publisher_rehearsal")
master = load("repair_master_shell")
contract = load("repair_public_contract")


class RehearsalGuardTests(unittest.TestCase):
    def test_literals_only_relocation_preserves_other_tokens(self):
        source = '# unchanged /home/Carix comment\nROOT = "/home/Carix"\nURL = "https://example.invalid"\n'
        output, changes = rehearsal.relocated(source, Path("/isolated/runtime"))
        self.assertEqual(output, source.replace('"/home/Carix"', "'/isolated/runtime'"))
        self.assertEqual(len(changes), 1)

    def test_unhandled_fstring_relocation_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "RELOCATION_AST_SCOPE"):
            rehearsal.relocated('x = f"/home/Carix/{name}"\n', Path("/isolated/runtime"))

    def test_network_process_and_outside_file_database_denied(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guard, counters = rehearsal.make_guard(root, [])
            samples = [('socket.connect', (None, ("example.invalid", 443))),
                       ('subprocess.Popen', ('python', [], None, None)),
                       ('open', ('/home/Carix/crm.db', 'r', os.O_RDONLY)),
                       ('open', ('/home/Carix/video/UA-0001.html', 'w', os.O_WRONLY)),
                       ('sqlite3.connect', ('file:/home/Carix/crm.db?mode=ro',))]
            for event, args in samples:
                with self.subTest(event=event), self.assertRaises(PermissionError):
                    guard(event, args)
            self.assertTrue(all(counters.values()))

    def test_fd_and_symlink_cannot_escape_write_root(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as other:
            root, outside = Path(temp), Path(other)
            guard, counters = rehearsal.make_guard(root, [])
            (root / "escape").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(PermissionError):
                guard('open', (str(root / 'escape/data'), 'w', os.O_WRONLY))
            fd = os.open(outside, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(PermissionError):
                    guard('os.mkdir', ('escape', 0o700, fd))
            finally:
                os.close(fd)
            self.assertEqual(counters['outside_write'], 2)

    def test_owned_io_and_stdlib_read_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guard, counters = rehearsal.make_guard(root, [Path('/usr/lib')])
            guard('open', (str(root / 'crm.db'), 'w', os.O_WRONLY))
            guard('sqlite3.connect', ('file:' + str(root / 'crm.db') + '?mode=ro',))
            guard('open', ('/usr/lib/example.py', 'r', os.O_RDONLY))
            self.assertFalse(any(counters.values()))

    def test_sqlite_audit_bytes_paths_remain_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guard, counters = rehearsal.make_guard(root, [])
            for value in [os.fsencode(root / 'crm.db'), os.fsencode('file:' + str(root / 'crm.db') + '?mode=ro'), b':memory:']:
                guard('sqlite3.connect', (value,))
            for value in [b'/home/Carix/crm.db', b'file:/home/Carix/crm.db?mode=ro', b'file:%2fhome%2fCarix%2fcrm.db?mode=ro']:
                with self.subTest(value=value), self.assertRaises(PermissionError):
                    guard('sqlite3.connect', (value,))
            self.assertEqual(counters['outside_write'], 3)

    def test_patchers_refuse_unknown_source_without_execution(self):
        source = 'raise RuntimeError("must never execute")\n'
        for patcher in (master.patch_master_shell, contract.patch_public_contract):
            with self.subTest(patcher=patcher.__name__), self.assertRaisesRegex(ValueError, 'SOURCE_SHA_MISMATCH'):
                patcher(source)

    def test_existing_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sentinel').write_text('preserve')
            with self.assertRaisesRegex(RuntimeError, 'OUTPUT_MUST_BE_NEW'):
                rehearsal.prepare(root, root, root / 'golden', root)
            self.assertEqual((root / 'sentinel').read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
