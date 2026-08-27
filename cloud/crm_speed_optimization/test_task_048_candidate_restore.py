"""test_task_048_candidate_restore.py (corrected under TASK 053)

Compact focused tests for candidate_transforms.py. Corrections applied in
this revision versus the original TASK 048 test file:

- The module-level compatibility name list no longer asserts hasattr for
  CrossProcessLock / SingletonGuard / RebuildQueue directly on the
  `candidate_transforms` module -- those classes are not top-level names
  of this module; they only exist inside the generated runtime support
  source string and must be proven by executing
  generate_runtime_support_source() (see TestGeneratedRuntimeSupport).
- The brittle substring assertion that mistook `def gen():` for a call to
  `gen()` is replaced by an AST walk that proves no direct ast.Call to the
  generator survives outside its own function definition.
- New class-definition-time test cases (class-body assignment, method
  annotation/default/decorator, nested class surface) are added for the
  TASK 053 launcher fail-open repair, plus a confirming ordinary
  method-body-reference OK case and an application-import-relocation
  check.

Assumes sqlite_ownership.py already exists unchanged in this same package
directory (delivered by an earlier task); this file does not modify or
redeliver it.

No network, no PythonAnywhere, no Production/CRM access. All lock paths
used here are temporary directories created by the test itself.
"""
from __future__ import annotations

import ast
import os
import signal
import sys
import tempfile
import types
import unittest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import candidate_transforms as ct  # noqa: E402


def _assert_no_surviving_generator_call(candidate_source, generator_name):
    """AST-based proof (not a text substring check) that no ast.Call to
    `generator_name` survives anywhere outside that generator's own
    function definition."""
    tree = ast.parse(candidate_source)
    generator_node = next(
        (
            n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == generator_name
        ),
        None,
    )

    def _walk_excluding(node, excluded):
        for child in ast.iter_child_nodes(node):
            if child is excluded:
                continue
            yield child
            yield from _walk_excluding(child, excluded)

    for node in _walk_excluding(tree, generator_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == generator_name:
            raise AssertionError(
                f"generator call to {generator_name!r} survived outside its own definition"
            )


class TestCompatibilityNames(unittest.TestCase):
    def test_required_names_exist(self):
        names = [
            "_ok", "_blocked", "generate_runtime_support_source", "transform_usercustomize",
            "transform_launcher_singleton", "transform_avtoperedacha_rebuild",
            "transform_sqlite_short_ownership", "check_db_closed_before_slow_work_candidate",
        ]
        for n in names:
            self.assertTrue(hasattr(ct, n), f"missing required name: {n}")

    def test_result_schema_compatible(self):
        ok = ct._ok("candidate-src", ["r1"], {"k": 1})
        for key in ("status", "candidate", "reasons", "metadata"):
            self.assertIn(key, ok)
        self.assertEqual(ok["status"], "OK")
        self.assertEqual(ok["candidate"], "candidate-src")

        blocked = ct._blocked(["why"], {"a": 1})
        for key in ("status", "candidate", "reasons", "metadata"):
            self.assertIn(key, blocked)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertIsNone(blocked["candidate"])


class TestGeneratedRuntimeSupport(unittest.TestCase):
    def test_generated_runtime_defines_expected_classes(self):
        src = ct.generate_runtime_support_source()
        ns = {}
        exec(compile(src, "<runtime>", "exec"), ns)
        for name in ("CrossProcessLock", "SingletonGuard", "RebuildQueue"):
            self.assertIn(name, ns)
            self.assertTrue(isinstance(ns[name], type), f"{name} is not a class in generated runtime")


class TestRebuildTransformPositives(unittest.TestCase):
    def test_expr_trigger_positive(self):
        src = (
            "def gen():\n"
            "    return 1\n\n"
            "def start():\n"
            "    gen()\n\n"
            "import subprocess\n\n"
            "def spawn_related():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK", result["reasons"])
        compile(result["candidate"], "<t>", "exec")
        self.assertIn("_queue = RebuildQueue(gen", result["candidate"])
        self.assertIn("_queue.enqueue()", result["candidate"])
        _assert_no_surviving_generator_call(result["candidate"], "gen")

    def test_return_trigger_positive(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def trigger():\n"
            "    return gen()\n\n"
            "def spawner():\n"
            "    return subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK", result["reasons"])
        compile(result["candidate"], "<t>", "exec")
        self.assertIn("return _queue.enqueue()", result["candidate"])
        _assert_no_surviving_generator_call(result["candidate"], "gen")

    def test_aliased_subprocess_positive(self):
        src = (
            "import subprocess as sp\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def start():\n"
            "    gen()\n\n"
            "def spawner():\n"
            "    sp.Popen(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "OK", result["reasons"])
        _assert_no_surviving_generator_call(result["candidate"], "gen")


class TestRebuildTransformNegatives(unittest.TestCase):
    def test_unrelated_spawn_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def start():\n"
            "    gen()\n\n"
            "def other():\n"
            "    subprocess.run(['ffmpeg', '-i', 'a.mp4'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_direct_call_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_nonzero_args_generator_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen(x):\n"
            "    return x\n\n"
            "def start():\n"
            "    gen(1)\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_module_level_direct_call_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "gen()\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_assignment_context_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen():\n"
            "    return 1\n\n"
            "def start():\n"
            "    x = gen()\n"
            "    return x\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")

    def test_ambiguous_two_full_candidates_blocks(self):
        src = (
            "import subprocess\n\n"
            "def gen_a():\n"
            "    return 1\n\n"
            "def gen_b():\n"
            "    return 2\n\n"
            "def start():\n"
            "    gen_a()\n"
            "    gen_b()\n\n"
            "def spawner():\n"
            "    subprocess.run(['python3', 'stranica.py', 'gen_a'])\n"
            "    subprocess.run(['python3', 'stranica.py', 'gen_b'])\n"
        )
        result = ct.transform_avtoperedacha_rebuild(src)
        self.assertEqual(result["status"], "BLOCKED")


class TestLauncherTransform(unittest.TestCase):
    LAUNCHER_SRC = (
        '"""Launcher module docstring."""\n'
        "from __future__ import annotations\n\n"
        "import fake_app_module\n\n\n"
        "def main():\n"
        "    fake_app_module.run()\n\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

    def _build_fake_runtime_module(self, install_return, events):
        mod = types.ModuleType(ct.RUNTIME_MODULE_NAME)

        class FakeSingletonGuard:
            def __init__(self, path):
                self.path = path

            def install(self):
                events.append("install")
                return install_return

            def cleanup(self):
                events.append("cleanup")

        mod.SingletonGuard = FakeSingletonGuard
        return mod

    def test_future_import_preserved_and_compiles(self):
        result = ct.transform_launcher_singleton(self.LAUNCHER_SRC, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "OK", result["reasons"])
        self.assertIn("from __future__ import annotations", result["candidate"])
        compile(result["candidate"], "<launcher>", "exec")

    def test_import_as_module_no_lock_no_app_import(self):
        result = ct.transform_launcher_singleton(self.LAUNCHER_SRC, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "OK")
        events = []
        fake_runtime = self._build_fake_runtime_module(True, events)
        fake_app = types.ModuleType("fake_app_module")
        fake_app.RAN = []
        fake_app.run = lambda: fake_app.RAN.append("app_ran")
        sys.modules[ct.RUNTIME_MODULE_NAME] = fake_runtime
        sys.modules["fake_app_module"] = fake_app
        try:
            ns = {"__name__": "not_main"}
            exec(compile(result["candidate"], "<launcher>", "exec"), ns)
            self.assertEqual(events, [])
            self.assertEqual(fake_app.RAN, [])
        finally:
            sys.modules.pop(ct.RUNTIME_MODULE_NAME, None)
            sys.modules.pop("fake_app_module", None)

    def test_main_path_acquires_guard_before_app_import(self):
        result = ct.transform_launcher_singleton(self.LAUNCHER_SRC, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "OK")
        events = []
        fake_runtime = self._build_fake_runtime_module(True, events)
        fake_app = types.ModuleType("fake_app_module")
        fake_app.run = lambda: events.append("app_ran")
        sys.modules[ct.RUNTIME_MODULE_NAME] = fake_runtime
        sys.modules["fake_app_module"] = fake_app
        try:
            ns = {"__name__": "__main__"}
            exec(compile(result["candidate"], "<launcher>", "exec"), ns)
            self.assertIn("install", events)
            self.assertIn("app_ran", events)
            self.assertLess(events.index("install"), events.index("app_ran"))
        finally:
            sys.modules.pop(ct.RUNTIME_MODULE_NAME, None)
            sys.modules.pop("fake_app_module", None)

    def test_duplicate_start_exits_78_before_app_import(self):
        result = ct.transform_launcher_singleton(self.LAUNCHER_SRC, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "OK")
        events = []
        fake_runtime = self._build_fake_runtime_module(False, events)
        fake_app = types.ModuleType("fake_app_module")
        fake_app.run = lambda: events.append("app_ran")
        sys.modules[ct.RUNTIME_MODULE_NAME] = fake_runtime
        sys.modules["fake_app_module"] = fake_app
        try:
            ns = {"__name__": "__main__"}
            with self.assertRaises(SystemExit) as cm:
                exec(compile(result["candidate"], "<launcher>", "exec"), ns)
            self.assertEqual(cm.exception.code, 78)
            self.assertNotIn("app_ran", events)
        finally:
            sys.modules.pop(ct.RUNTIME_MODULE_NAME, None)
            sys.modules.pop("fake_app_module", None)

    def test_definition_time_moved_alias_ambiguity_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "import fake_dep\n\n\n"
            "@fake_dep.register\n"
            "def helper():\n"
            "    pass\n\n\n"
            "if __name__ == '__main__':\n"
            "    helper()\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")

    def test_relative_import_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "from . import sibling\n\n\n"
            "if __name__ == '__main__':\n"
            "    sibling.run()\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")

    # --- TASK 053: class definition-time closure cases ---

    def test_class_body_assignment_moved_alias_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "import fake_dep\n\n\n"
            "class Holder:\n"
            "    VALUE = fake_dep.CONSTANT\n\n\n"
            "if __name__ == '__main__':\n"
            "    pass\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")

    def test_class_body_annassign_moved_alias_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "import fake_dep\n\n\n"
            "class Holder:\n"
            "    VALUE: fake_dep.Type = None\n\n\n"
            "if __name__ == '__main__':\n"
            "    pass\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")

    def test_method_annotation_in_class_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "import fake_dep\n\n\n"
            "class Holder:\n"
            "    def method(self, x: fake_dep.Type) -> None:\n"
            "        pass\n\n\n"
            "if __name__ == '__main__':\n"
            "    pass\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")

    def test_method_default_in_class_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "import fake_dep\n\n\n"
            "class Holder:\n"
            "    def method(self, x=fake_dep.DEFAULT):\n"
            "        pass\n\n\n"
            "if __name__ == '__main__':\n"
            "    pass\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")

    def test_method_decorator_in_class_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "import fake_dep\n\n\n"
            "class Holder:\n"
            "    @fake_dep.register\n"
            "    def method(self):\n"
            "        pass\n\n\n"
            "if __name__ == '__main__':\n"
            "    pass\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")

    def test_nested_class_definition_time_surface_blocks(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "import fake_dep\n\n\n"
            "class Outer:\n"
            "    class Inner:\n"
            "        VALUE = fake_dep.CONSTANT\n\n\n"
            "if __name__ == '__main__':\n"
            "    pass\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "BLOCKED")

    def test_ordinary_method_body_reference_ok_and_import_relocated(self):
        src = (
            '"""Doc."""\n'
            "from __future__ import annotations\n\n"
            "import fake_dep\n\n\n"
            "class Holder:\n"
            "    def method(self):\n"
            "        return fake_dep.run()\n\n\n"
            "if __name__ == '__main__':\n"
            "    Holder().method()\n"
        )
        result = ct.transform_launcher_singleton(src, "/tmp/x/launcher.lock")
        self.assertEqual(result["status"], "OK", result["reasons"])
        compile(result["candidate"], "<launcher>", "exec")
        module_tree = ast.parse(result["candidate"])
        top_level_import_names = set()
        for n in module_tree.body:
            if isinstance(n, ast.Import):
                for a in n.names:
                    top_level_import_names.add(a.asname or a.name)
        self.assertNotIn("fake_dep", top_level_import_names)
        self.assertIn("import fake_dep", result["candidate"])


class TestRuntimeSignalCleanup(unittest.TestCase):
    def test_cleanup_restores_fake_handlers_idempotently(self):
        src = ct.generate_runtime_support_source()
        ns = {}
        exec(compile(src, "<runtime>", "exec"), ns)
        SingletonGuard = ns["SingletonGuard"]

        fake_prev_term = lambda signum, frame: None  # noqa: E731
        fake_prev_int = lambda signum, frame: None  # noqa: E731
        orig_getsignal = signal.getsignal
        orig_signal = signal.signal
        installed = {}

        def fake_getsignal(sig):
            if sig == signal.SIGTERM:
                return fake_prev_term
            if sig == signal.SIGINT:
                return fake_prev_int
            return orig_getsignal(sig)

        def fake_signal(sig, handler):
            installed[sig] = handler
            return None

        with tempfile.TemporaryDirectory() as d:
            lock_path = os.path.join(d, "test.lock")
            guard = SingletonGuard(lock_path)
            signal.getsignal = fake_getsignal
            signal.signal = fake_signal
            try:
                ok = guard.install()
                self.assertTrue(ok)
                self.assertIn(signal.SIGTERM, installed)
                self.assertIn(signal.SIGINT, installed)
                guard.cleanup()
                self.assertEqual(installed[signal.SIGTERM], fake_prev_term)
                self.assertEqual(installed[signal.SIGINT], fake_prev_int)
                # idempotent: second cleanup must not raise or re-restore
                guard.cleanup()
            finally:
                signal.getsignal = orig_getsignal
                signal.signal = orig_signal


if __name__ == "__main__":
    unittest.main()
