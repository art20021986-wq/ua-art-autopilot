#!/usr/bin/env python3
"""
Deterministic offline test runner for TASK 050 (corrects TASK 047 runner
defect: unittest discovery previously failed with
"Start directory is not importable" because tests/ was not a package on the
top_level_dir used by discovery).

This runner:
  1. Works from any current working directory (uses its own absolute path).
  2. Compiles every .py file in this package (fails loudly on any syntax
     error) instead of relying on unittest discovery's import machinery.
  3. Explicitly loads every tests/test_*.py module via importlib and runs
     all TestCase classes found in them.
  4. Runs the whole suite twice to check determinism/idempotence.
  5. Exits with a non-zero status on any compile failure, test failure, or
     non-deterministic result.
"""
from __future__ import annotations

import compileall
import importlib.util
import os
import sys
import unittest

PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def _compile_all() -> bool:
    return bool(compileall.compile_dir(PKG_DIR, quiet=1, force=True))


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_suite() -> unittest.TestSuite:
    if PKG_DIR not in sys.path:
        sys.path.insert(0, PKG_DIR)
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    tests_dir = os.path.join(PKG_DIR, "tests")
    for fname in sorted(os.listdir(tests_dir)):
        if fname.startswith("test_") and fname.endswith(".py"):
            mod_name = f"task050_tests_{fname[:-3]}"
            mod = _load_module(mod_name, os.path.join(tests_dir, fname))
            suite.addTests(loader.loadTestsFromModule(mod))
    return suite


def main() -> int:
    if not _compile_all():
        print("COMPILE FAILED")
        return 1

    suite = _build_suite()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1

    suite2 = _build_suite()
    result2 = unittest.TextTestRunner(verbosity=0).run(suite2)
    if result2.testsRun != result.testsRun or not result2.wasSuccessful():
        print("NON-DETERMINISTIC TEST RESULT")
        return 1

    print(f"ALL TESTS PASSED: {result.testsRun} tests (verified twice for determinism)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
