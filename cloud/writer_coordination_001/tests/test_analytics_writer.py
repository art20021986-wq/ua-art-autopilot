"""Run with UAART_ANALITIKA_SOURCE pointing at the private verified capture.

Only the actual patched function AST is executed with synthetic roots. No
production module imports, private source copies, external services or uploads.
"""
from __future__ import annotations

import ast
import errno
import fcntl
import hashlib
import importlib.util
import io
import multiprocessing
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[1] / "patch_analytics_writer.py"
spec = importlib.util.spec_from_file_location("analytics_patch", MODULE)
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


def hold_lock(path, ready, release):
    with open(path, "r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        ready.set()
        release.wait(5)


class AnalyticsWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = os.environ.get("UAART_ANALITIKA_SOURCE")
        if not source_path:
            raise RuntimeError("UAART_ANALITIKA_SOURCE is required; source-backed test must not silently skip")
        cls.source = Path(source_path).read_bytes()
        cls.patched = patcher.patch(cls.source)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for dirname in ("video", "site"):
            (self.root / dirname).mkdir()
        self.lock = self.root / ".ua_art_publish_transaction.lock"
        self.lock.touch()
        self.page = self.root / "video" / "UA-0001.html"
        self.original = '<html><body><p>VIN X123</p><section data-spec="manual">АКПП 6 ступеней</section></body></html>'
        self.page.write_text(self.original)
        self.env = {"os": os, "io": io, "time": time, "DOM": str(self.root),
                    "VIDEO": str(self.root / "video"), "SITE": str(self.root / "site"),
                    "_FON": [0], "STROKA": "<script src='/ua/a.js?v=1' defer></script><!--UA-ANALIT-V1-->"}
        tree = ast.parse(self.patched)
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_storozh"]
        exec(compile(ast.Module(body=functions, type_ignores=[]), "actual_patched_analytics_function", "exec"), self.env)
        self.net = mock.patch.object(socket, "socket", side_effect=AssertionError("NETWORK_FORBIDDEN"))
        self.net.start()
        self.addCleanup(self.net.stop)

    def run_pass(self):
        self.env["_storozh"]()

    def assert_unchanged(self):
        self.assertEqual(self.page.read_text(), self.original)
        self.assertFalse(Path(str(self.page) + ".ana_tmp").exists())

    def test_actual_source_hash_and_unrelated_ast_unchanged(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), patcher.SOURCE_SHA256)
        def outside(blob):
            tree = ast.parse(blob)
            tree.body = [n for n in tree.body if not isinstance(n, ast.FunctionDef) or n.name != "_storozh"]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(outside(self.source), outside(self.patched))

    def test_manual_spec_and_shell_preserved_exactly(self):
        self.run_pass()
        expected = self.original.replace("</body>", self.env["STROKA"] + "</body>", 1)
        self.assertEqual(self.page.read_text(), expected)
        self.env["_FON"][0] = 0
        self.run_pass()
        self.assertEqual(self.page.read_text(), expected)

    def test_competing_process_defers_then_resumes(self):
        ctx = multiprocessing.get_context("fork")
        ready, release = ctx.Event(), ctx.Event()
        process = ctx.Process(target=hold_lock, args=(str(self.lock), ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(2))
            started = time.monotonic()
            self.run_pass()
            self.assertLess(time.monotonic() - started, 0.5)
            self.assert_unchanged()
            self.assertEqual(self.env["_FON"][0], 0)
        finally:
            release.set()
            process.join(3)
            if process.is_alive():
                process.terminate()
                process.join()
        self.assertEqual(process.exitcode, 0)
        self.run_pass()
        self.assertIn("UA-ANALIT-V1", self.page.read_text())

    def test_existing_stop_prevents_write(self):
        (self.root / "analitika_stop.txt").touch()
        self.run_pass()
        self.assert_unchanged()

    def test_stop_rechecked_after_lock(self):
        original = fcntl.flock
        def stopped(fd, operation):
            result = original(fd, operation)
            (self.root / "analitika_stop.txt").touch()
            return result
        with mock.patch.object(fcntl, "flock", side_effect=stopped):
            self.run_pass()
        self.assert_unchanged()

    def test_durable_intent_denies_even_failed_or_invalid_receipt(self):
        control = self.root / ".uaart_writer_coordination"
        control.mkdir()
        intent = control / "active-intent.json"
        for body in ('{"state":"HELD"}', '{"state":"RELEASED"}', 'not-json'):
            intent.write_text(body)
            self.run_pass()
            self.assert_unchanged()
            self.assertEqual(self.env["_FON"][0], 0)

    def test_missing_lock_is_not_recreated(self):
        self.lock.unlink()
        self.run_pass()
        self.assert_unchanged()
        self.assertFalse(self.lock.exists())

    def test_intent_lookup_failure_defers(self):
        original = os.lstat
        for code in (errno.EACCES, errno.EIO):
            def denied(path, *args, **kwargs):
                if os.fspath(path).endswith("active-intent.json"):
                    raise OSError(code, "synthetic lookup failure")
                return original(path, *args, **kwargs)
            with mock.patch.object(os, "lstat", side_effect=denied):
                self.run_pass()
            self.assert_unchanged()
            self.assertEqual(self.env["_FON"][0], 0)

    def test_fifo_lock_is_refused_without_wait(self):
        self.lock.unlink()
        os.mkfifo(self.lock)
        started = time.monotonic()
        self.run_pass()
        self.assertLess(time.monotonic() - started, 0.5)
        self.assert_unchanged()

    def test_symlink_lock_is_refused(self):
        target = self.root / "another"
        target.touch()
        self.lock.unlink()
        self.lock.symlink_to(target)
        self.run_pass()
        self.assert_unchanged()

    def test_replaced_inode_after_acquisition_is_refused(self):
        original = fcntl.flock
        def replaced(fd, operation):
            result = original(fd, operation)
            self.lock.unlink()
            self.lock.touch()
            return result
        with mock.patch.object(fcntl, "flock", side_effect=replaced):
            self.run_pass()
        self.assert_unchanged()

    def test_existing_marker_is_byte_identical(self):
        self.original = self.original.replace("</body>", self.env["STROKA"] + "</body>")
        self.page.write_text(self.original)
        self.run_pass()
        self.assert_unchanged()

    def test_source_drift_refuses_patch(self):
        with self.assertRaisesRegex(ValueError, "ANALYTICS_SOURCE_DRIFT"):
            patcher.patch(self.source + b"\n")


if __name__ == "__main__":
    unittest.main()
