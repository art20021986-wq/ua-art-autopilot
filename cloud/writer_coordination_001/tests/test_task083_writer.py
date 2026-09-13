import argparse
import ast
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("task083_patcher", ROOT / "patch_task083_writer.py")
patcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(patcher)
DEFAULT_SOURCE = Path("/workspace/scratch/2d59224df460/private-runtime/publisher-inputs-20260909T074529Z/autopilot_inbox/cloud/task_083_catalog_dedup/installer.py")
SOURCE = Path(os.environ.get("UA_ART_TASK083_SOURCE", str(DEFAULT_SOURCE)))


class Task083Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_bytes()
        cls.patched = patcher.patch(cls.source)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.names = [".ua_art_publish_transaction.lock", ".task082_catalog_stage_repair.lock",
                      ".task082_catalog_stage_guard.lock", ".task083_catalog_dedup.lock"]
        for name in self.names:
            (self.base / name).touch()
        self.writes = []
        self.ns = {"__name__": "isolated_ast_only", "Any": Any, "os": os, "fcntl": fcntl,
                   "ROOT": self.base, "argparse": argparse, "json": json, "pathlib": __import__("pathlib"),
                   "CONTRACT": "isolated", "REMOTE_ROOT": self.base / "remote",
                   "TASK082_INSTALL_LOCK": self.base / self.names[1],
                   "TASK082_RUNTIME_LOCK": self.base / self.names[2], "LOCK_PATH": self.base / self.names[3],
                   "SOURCE_PATHS": [], "CATALOG_PATHS": [], "CORE_PATH": self.base / "core",
                   "BACKUP_PARENT": self.base / "backups",
                   "RECEIPTS": {mode: self.base / (mode + ".json") for mode in ("shadow", "install", "rollback")}}
        tree = ast.parse(self.patched)
        names = {"Blocked", "run_install", "run_rollback", "main", "_ua083_check_intent", "_ua083_identity", "_ua083_guard"}
        nodes = [n for n in tree.body if
                 isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names or
                 isinstance(n, ast.Import) and any(a.asname and a.asname.startswith("_ua083_") for a in n.names) or
                 isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_ua083_local" for t in n.targets)]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "isolated-task083-entrypoints", "exec"), self.ns)
        snapshot = {"stage_guard": {"installed": False}, "database": {}, "protected_pages": {}, "catalogs": {}}
        self.ns.update(inspect_base=lambda: snapshot, backup=lambda _: self.base / "backups" / "one",
                       atomic_json=lambda path, value: self.writes.append((path, value)), run_shadow=lambda: {"status": "PASS", "mode": "SHADOW"},
                       restore=lambda *_: self.writes.append("restore") or [])
        self.ns["RECEIPTS"]["install"].write_text(json.dumps({"backup_root": str(self.base / "backups" / "one"),
                                                             "managed_paths": [str(self.base / "core")]}))

    def invoke(self, name, mode="install"):
        with mock.patch("sys.argv", ["installer.py", mode]), contextlib.redirect_stdout(io.StringIO()):
            return self.ns[name]()

    def test_exact_sha_and_only_admission_ast_changes(self):
        self.assertEqual(patcher.SOURCE_SHA256, hashlib.sha256(self.source).hexdigest())
        self.assertEqual(self.patched, patcher.patch(self.source))
        self.assertEqual(1, self.patched.count(patcher.MARKER.encode()))
        # Patcher itself strips only decorators/helpers and known touch loop,
        # then compares the full remaining original AST before returning bytes.

    def test_unknown_source_or_repeat_patch_refused(self):
        for data in (self.source + b"\n", self.patched):
            with self.assertRaisesRegex(ValueError, "SOURCE_DRIFT"):
                patcher.patch(data)

    def test_busy_common_lock_blocks_main_and_direct_entrypoints(self):
        with (self.base / self.names[0]).open("r+") as fd:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for name, mode in (("main", "install"), ("main", "rollback"), ("run_install", "install"), ("run_rollback", "rollback")):
                with self.subTest(name=name, mode=mode), self.assertRaisesRegex(self.ns["Blocked"], "DEFERRED_WRITER_COORDINATION"):
                    self.invoke(name, mode)
        self.assertEqual([], self.writes)
        self.assertFalse(self.ns["REMOTE_ROOT"].exists())

    def test_any_durable_intent_blocks_every_entrypoint_and_stale_pass_untouched(self):
        control = self.base / ".uaart_writer_coordination"; control.mkdir()
        receipt = self.ns["RECEIPTS"]["install"]; receipt.write_text('{"status":"PASS","old":true}')
        for contents in ('{"state":"HELD"}', '{"state":"RELEASED"}', "broken"):
            (control / "active-intent.json").write_text(contents)
            for name, mode in (("main", "install"), ("main", "rollback"), ("run_install", "install"), ("run_rollback", "rollback")):
                with self.subTest(name=name, contents=contents), self.assertRaisesRegex(self.ns["Blocked"], "DURABLE_WRITER_INTENT"):
                    self.invoke(name, mode)
        self.assertEqual([], self.writes)
        self.assertEqual('{"status":"PASS","old":true}', receipt.read_text())

    def test_missing_lock_never_recreated(self):
        for name in self.names:
            path = self.base / name; path.unlink()
            with self.subTest(name=name), self.assertRaises(self.ns["Blocked"]):
                self.invoke("main")
            self.assertFalse(path.exists()); path.touch()
        self.assertEqual([], self.writes)

    def test_symlink_or_hardlink_lock_refused(self):
        path = self.base / self.names[0]; path.unlink()
        target = self.base / "target"; target.touch()
        path.symlink_to(target)
        with self.assertRaises(self.ns["Blocked"]): self.invoke("main")
        path.unlink(); os.link(target, path)
        with self.assertRaises(self.ns["Blocked"]): self.invoke("main")
        self.assertEqual([], self.writes)

    def test_main_preserves_existing_three_lock_order_and_reentrant_install(self):
        order = []
        by_inode = {p.stat().st_ino: p.name for p in (self.base / n for n in self.names)}
        original = fcntl.flock
        def record(fd, operation):
            order.append(by_inode[os.fstat(fd if type(fd) is int else fd.fileno()).st_ino])
            return original(fd, operation)
        before = {name: (self.base / name).stat() for name in self.names}
        with mock.patch.object(fcntl, "flock", side_effect=record):
            self.assertEqual(0, self.invoke("main"))
        self.assertEqual(self.names, order)
        self.assertEqual("PASS", self.writes[-1][1]["status"])
        for name in self.names:
            after = (self.base / name).stat()
            self.assertEqual((before[name].st_ino, before[name].st_mtime_ns), (after.st_ino, after.st_mtime_ns))

    def test_direct_install_and_rollback_hold_common_lock_during_payload(self):
        observed = []
        def locked():
            with (self.base / self.names[0]).open("r+") as fd:
                with self.assertRaises(BlockingIOError): fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            observed.append(True)
        original = self.ns["inspect_base"]
        self.ns["inspect_base"] = lambda: (locked(), original())[1]
        self.assertEqual("PASS", self.invoke("run_install")["status"])
        self.ns["restore"] = lambda *_: locked() or []
        self.assertEqual("PASS", self.invoke("run_rollback")["status"])
        self.assertEqual(3, len(observed))

    def test_intent_io_error_defers(self):
        with mock.patch.object(os, "lstat", side_effect=PermissionError("denied")):
            with self.assertRaises(self.ns["Blocked"]): self.invoke("main")
        self.assertEqual([], self.writes)

    def test_inherited_thread_local_admission_refused(self):
        self.ns["_ua083_local"].held = (1, [], os.getpid() + 1)
        with self.assertRaisesRegex(self.ns["Blocked"], "INHERITED_ADMISSION"):
            self.invoke("run_install")
        self.assertEqual([], self.writes)

    def test_payload_errno_preserved_and_lock_released(self):
        self.ns["inspect_base"] = mock.Mock(side_effect=OSError(22, "synthetic"))
        with self.assertRaises(OSError) as raised: self.invoke("run_install")
        self.assertEqual(22, raised.exception.errno)
        with (self.base / self.names[0]).open("r+") as fd:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


if __name__ == "__main__": unittest.main()
