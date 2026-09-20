"""Isolated regression tests; private runtime modules are never imported.

Only selected function ASTs execute, with temp-directory IO and controlled
render/DB stubs. The original publisher's foreign-page guard is exercised.
"""
import ast
import contextlib
import fcntl
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

import build_candidate as build
import publication_fence as fence

FIXTURE = Path(__file__).with_name("safe_function_fixtures.py")
FIXTURE_SHA256 = "b37ed59bc7a819210a97b98582e2605a451d1813b3ff10be4fe90ec554300f49"


def fixture_sources():
    raw = FIXTURE.read_bytes()
    if build.sha(raw) != FIXTURE_SHA256:
        raise RuntimeError("SAFE_FIXTURE_SHA256_MISMATCH")
    from safe_function_fixtures import FIXTURES
    document = FIXTURES
    sources = {}
    for name, entry in document["sources"].items():
        if entry["original_source_sha256"] != build.SOURCE_SHA256[name]:
            raise RuntimeError("FIXTURE_ORIGINAL_PROVENANCE_MISMATCH:" + name)
        parts = []
        for record in entry["functions"]:
            piece = record["source"]
            if build.sha(piece.encode()) != record["extracted_sha256"]:
                raise RuntimeError("EXTRACTED_FUNCTION_SHA256_MISMATCH")
            node = ast.parse(piece).body[0]
            if build.sha(ast.dump(node, include_attributes=False).encode()) != record["ast_sha256"]:
                raise RuntimeError("EXTRACTED_FUNCTION_AST_MISMATCH")
            parts.append(piece)
        sources[name] = "\n".join(parts)
        if name == "stranica.py":
            sources[name] += '\nif __name__ == "__main__":\n    main()\n'
    return sources


def selected(source, names, *, occurrence=0):
    tree = ast.parse(source)
    result = []
    for name in names:
        matches = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
        result.append(matches[occurrence])
    return ast.Module(body=result, type_ignores=[])


def module_namespace(**values):
    module = types.ModuleType("ua0022_isolated_test_module")
    module.__dict__.update(values)
    module.__dict__["_test_module"] = module
    return module.__dict__


def load_selected_module(source, namespace):
    """Import a temporary selected-source module through the standard loader.

    The persistent test module dictionary provides explicit stubs and lets
    reload/wrapper tests exercise normal Python module global semantics.
    """
    text = ast.unparse(source) if isinstance(source, ast.AST) else source
    module = namespace["_test_module"]
    with tempfile.TemporaryDirectory(prefix="ua0022-selected-") as folder:
        path = Path(folder) / "selected.py"
        path.write_text(text, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(module.__name__, path)
        spec.loader.exec_module(module)


class NarrowFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        private_source_dir = os.environ.get("UA0022_TEST_SOURCE_DIR")
        if private_source_dir:
            root = Path(private_source_dir)
            cls.sources = {name: (root / name).read_text() for name in build.SOURCE_SHA256}
            for name, source in cls.sources.items():
                if build.sha(source.encode()) != build.SOURCE_SHA256[name]:
                    raise RuntimeError("TEST_SOURCE_HASH_MISMATCH:" + name)
        else:
            cls.sources = fixture_sources()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lock = self.root / ".publication.lock"
        self.threads = []
        self.errors = []
        self.test_fence = lambda timeout=3.0: fence.PublicationFence(
            timeout=timeout, lock_path=self.lock, _test_only_path=True, poll_interval=0.01)
        self.module = types.ModuleType("publication_fence")
        self.module.publication_fence = self.test_fence
        self.module.require_publication_fence = lambda: fence.require_publication_fence(lock_path=self.lock)
        self.patch_module = mock.patch.dict(sys.modules, {"publication_fence": self.module})
        self.patch_module.start()
        for folder in (self.root / "video", self.root / "site"):
            folder.mkdir()
            for code in ("UA-0015", "UA-0016", "UA-0022"):
                for suffix in (".html", "-diag.html", "-1234abcd.html"):
                    (folder / (code + suffix)).write_text("OLD:" + code + suffix)
            (folder / "index.html").write_text("ORIGINAL HOME")
            (folder / "katalog.html").write_text("ORIGINAL CATALOG")

    def tearDown(self):
        for thread in self.threads:
            thread.join(4)
            self.assertFalse(thread.is_alive(), "worker did not terminate")
        self.patch_module.stop()
        self.tmp.cleanup()
        self.assertEqual(self.errors, [])

    def worker(self, target):
        def run():
            try:
                target()
            except BaseException as exc:
                self.errors.append(repr(exc))
        thread = threading.Thread(target=run, daemon=True)
        self.threads.append(thread)
        thread.start()
        return thread

    def namespace(self):
        ns = module_namespace(os=os, io=io, re=re, time=time, shutil=shutil, hashlib=hashlib)
        ns.update(BASE=str(self.root), VIDEO=str(self.root / "video"), SITE=str(self.root / "site"),
                  REZERV_KORE=str(self.root / "backups"), _zhurnal=lambda _lines: None)
        load_selected_module(selected(self.sources["publikaciya.py"], ["_sha", "_kartochki", "_otkat", "opublikovat"]), ns)
        ns["proverit"] = lambda _html, _code: []
        ns["_master"] = lambda code: ("NEW PRIMARY:" + code, "NEW DIAG:" + code, {"auto_number": code})
        def atomic(path, text):
            temporary = path + ".tmp"
            Path(temporary).write_text(text)
            os.replace(temporary, path)
        ns["_zapisat_atomarno"] = atomic
        return ns

    def guard(self, patched):
        ns = module_namespace(contextlib=contextlib, fcntl=fcntl, time=time, LOCK=self.lock,
                  WAIT_SECONDS=3, PublishError=RuntimeError)
        load_selected_module(selected(self.sources["publish_transaction_guard.py"], ["_exclusive_lock"]), ns)
        if patched:
            load_selected_module(build.GUARD_BLOCK, ns)
        return ns["_exclusive_lock"]

    def legacy_main(self, patched, started):
        # Execute the actual baseline full-site main with only its render/DB
        # helpers stubbed. Real file writes stay under this temporary root.
        ns = module_namespace(os=os, time=time, traceback=__import__("traceback"), print=lambda *a, **k: None,
                  PAPKA_VID=str(self.root / "video"), otklyuchit_staroe=lambda: [],
                  mashiny=lambda: [{"auto_number": "UA-0015"}, {"auto_number": "UA-0016"}],
                  nomer=lambda row: row["auto_number"], kadry_mashiny=lambda _row: [],
                  sobrat_kartochku=lambda row, *_: "REBUILT:" + row["auto_number"],
                  est_diagnostika=lambda _row: True,
                  sobrat_diagnostiku=lambda row: "REBUILT DIAG:" + row["auto_number"],
                  kadry_diagnostiki=lambda _row: ([], []), cena=lambda _row: "100 $",
                  etap_korotko=lambda _row: "stage", obnovit_etalon=lambda *_: 0,
                  sobrat_katalog=lambda *_: "REBUILT CATALOG", sobrat_glavnuyu=lambda *_: "REBUILT HOME",
                  sobrat_podbor=lambda: "PODBOR", sobrat_info=lambda: "INFO", sajt=lambda: "isolated")
        def write(stem, text):
            started.set()
            for folder in (self.root / "video", self.root / "site"):
                paths = {folder / (stem + ".html")}
                if not stem.endswith("-diag"):
                    paths.update(folder.glob(stem + "-1234abcd.html"))
                for path in paths:
                    path.write_text(text)
            return 2
        ns["zapisat"] = write
        load_selected_module(selected(self.sources["stranica.py"], ["main"]), ns)
        if patched:
            load_selected_module(build.STRANICA_BLOCK, ns)
        return ns["main"]

    def race(self, patched):
        ns = self.namespace()
        guard = self.guard(patched)
        render_started, release_render, rebuild_started = (threading.Event() for _ in range(3))
        render = ns["_master"]
        def pause_render(code):
            render_started.set()
            if not release_render.wait(3):
                raise RuntimeError("test render synchronization timeout")
            return render(code)
        ns["_master"] = pause_render
        result = []
        def publish():
            with guard():
                result.append(ns["opublikovat"]("UA-0022"))
        pub_thread = self.worker(publish)
        self.assertTrue(render_started.wait(2))
        rebuild_thread = self.worker(self.legacy_main(patched, rebuild_started))
        try:
            if patched:
                self.assertFalse(rebuild_started.wait(0.15), "candidate rebuilt during publication")
            else:
                self.assertTrue(rebuild_started.wait(2))
                rebuild_thread.join(2)
                self.assertFalse(rebuild_thread.is_alive())
        finally:
            release_render.set()
        pub_thread.join(3)
        rebuild_thread.join(3)
        self.assertEqual(len(result), 1)
        return result[0]

    def test_original_reproduces_foreign_card_failure(self):
        ok, message = self.race(False)
        self.assertFalse(ok)
        self.assertIn("изменились чужие карточки", message)
        self.assertIn("UA-0015", message)
        self.assertIn("UA-0016", message)
        self.assertEqual((self.root / "video/UA-0022.html").read_text(), "OLD:UA-0022.html")
        self.assertEqual((self.root / "video/UA-0015.html").read_text(), "REBUILT:UA-0015")

    def test_candidate_serializes_exact_same_rebuild(self):
        ok, message = self.race(True)
        self.assertTrue(ok, message)
        self.assertEqual((self.root / "video/UA-0022.html").read_text(), "NEW PRIMARY:UA-0022")

    def test_nested_guard_main_does_not_deadlock(self):
        seen = []
        ns = module_namespace(main=lambda: (self.module.require_publication_fence(), seen.append("main")))
        load_selected_module(build.STRANICA_BLOCK, ns)
        with self.guard(True)():
            ns["main"]()
        self.assertEqual(seen, ["main"])

    def test_reload_is_blocked_then_nested_main_runs(self):
        reload_started = threading.Event()
        page_ns = module_namespace(main=lambda: self.module.require_publication_fence())
        load_selected_module(build.STRANICA_BLOCK, page_ns)
        page_module = types.ModuleType("stranica")
        page_module.main = page_ns["main"]
        calls = []
        def reload_stub(module):
            self.module.require_publication_fence()
            reload_started.set()
            calls.append("reload")
            return module
        ns = module_namespace(log=types.SimpleNamespace(warning=lambda *a: None))
        load_selected_module(selected(self.sources["cars_ui.py"], ["_peresobrat_stranicy"]), ns)
        load_selected_module(build.CARS_BLOCK, ns)
        before_path = list(sys.path)
        try:
            with mock.patch.dict(sys.modules, {"stranica": page_module}), mock.patch("importlib.reload", reload_stub):
                with self.guard(True)():
                    result = []
                    thread = self.worker(lambda: result.append(ns["_peresobrat_stranicy"]()))
                    self.assertFalse(reload_started.wait(0.15))
                thread.join(3)
                self.assertEqual(result, [True])
        finally:
            sys.path[:] = before_path
        self.assertEqual(calls, ["reload"])

    def test_foreign_invariant_still_rejects_uncovered_writer(self):
        ns = self.namespace()
        render = ns["_master"]
        def corrupt(code):
            (self.root / "video/UA-0015.html").write_text("FOREIGN NEWER")
            return render(code)
        ns["_master"] = corrupt
        with self.guard(True)():
            ok, message = ns["opublikovat"]("UA-0022")
        self.assertFalse(ok)
        self.assertIn("изменились чужие карточки", message)
        self.assertEqual((self.root / "video/UA-0022.html").read_text(), "OLD:UA-0022.html")
        self.assertEqual((self.root / "video/UA-0015.html").read_text(), "FOREIGN NEWER")

    def test_legacy_exception_releases_fence(self):
        def fail():
            self.module.require_publication_fence()
            raise ValueError("legacy render failure")
        ns = module_namespace(main=fail)
        load_selected_module(build.STRANICA_BLOCK, ns)
        with self.assertRaisesRegex(ValueError, "legacy render failure"):
            ns["main"]()
        with self.guard(True)():
            self.module.require_publication_fence()

    def test_rebuild_fence_failure_returns_false_without_reload(self):
        calls = []
        ns = module_namespace(_peresobrat_stranicy=lambda: calls.append("reload"),
                              log=types.SimpleNamespace(warning=lambda *a: calls.append("logged")))
        load_selected_module(build.CARS_BLOCK, ns)
        def unavailable(**kwargs):
            self.assertEqual(kwargs["timeout"], 90.0)
            raise fence.FenceTimeout("PUBLICATION_FENCE_TIMEOUT")
        ns["_ua0022_publication_fence"] = unavailable
        self.assertFalse(ns["_peresobrat_stranicy"]())
        self.assertEqual(calls, ["logged"])

    def test_wrapper_capture_survives_reload_globals(self):
        ns = module_namespace(main=lambda: "before")
        load_selected_module(build.STRANICA_BLOCK, ns)
        prior = ns["main"]
        ns["main"] = lambda: "after"
        load_selected_module(build.STRANICA_BLOCK, ns)
        self.assertEqual(prior(), "before")
        self.assertEqual(ns["main"](), "after")

    def test_direct_main_keeps_final_validation_and_restore_inside_fence(self):
        path = self.root / "video/index.html"
        before = path.read_text()
        events = []
        def guarded_open(filename, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                self.module.require_publication_fence()
                events.append("write:" + Path(filename).name)
            return io.open(filename, mode, *args, **kwargs)
        def render():
            self.module.require_publication_fence()
            path.write_text("PARTIAL RENDER")
            return "render-result"
        def validate():
            self.module.require_publication_fence()
            events.append("validation")
            return False, "simulated legacy validation failure"
        ns = module_namespace(__name__="__main__", os=os, time=time,
              io=types.SimpleNamespace(open=guarded_open), print=lambda *a, **k: None,
              BAZA_DIR=str(self.root), _v135_snimok=lambda: {str(path): before},
              _v135_main_ishodnyy=render, _v135_proverka=validate)
        load_selected_module(selected(self.sources["stranica.py"], ["main"], occurrence=1), ns)
        ns["_v157_main_do"] = ns["main"]
        ns["_v157_net_fajlov"] = lambda: []
        load_selected_module(selected(self.sources["stranica.py"], ["main"], occurrence=2), ns)
        load_selected_module(build.STRANICA_BLOCK, ns)
        load_selected_module('if __name__ == "__main__":\n    main()', ns)
        self.assertEqual(path.read_text(), before)
        self.assertEqual(events, ["validation", "write:publikaciya_log.txt", "write:index.html"])

    def test_patched_source_preserves_original_bytes_and_main_order(self):
        for name in ("cars_ui.py", "stranica.py", "publish_transaction_guard.py"):
            after = build.transform(name, self.sources[name])
            if name == "stranica.py":
                self.assertEqual(after.replace(build.STRANICA_BLOCK + "\n", "", 1), self.sources[name])
                self.assertLess(after.index(build.MARKER), after.index('if __name__ == "__main__":'))
            else:
                self.assertTrue(after.startswith(self.sources[name]))
            compile(after, name, "exec")

    def test_source_drift_rejected_before_output(self):
        sources = self.root / "drift"
        sources.mkdir()
        for name, source in self.sources.items():
            (sources / name).write_text(source + ("\n# drift\n" if name == "cars_ui.py" else ""))
        output = self.root / "must-not-exist"
        expected = {name: build.sha(source.encode()) for name, source in self.sources.items()}
        with mock.patch.dict(build.SOURCE_SHA256, expected, clear=True):
            with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH:cars_ui.py"):
                build.build(sources, Path(fence.__file__), output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
