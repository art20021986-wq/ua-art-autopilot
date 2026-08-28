#!/usr/bin/env python3
"""Compile every task_058 source file, then run the full offline test suite
10 consecutive times. Fails loudly (non-zero exit) on the first failing run
or any compile error. Does not touch anything outside this package."""
import py_compile
import sys
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
RUNS = 10


def compile_all():
    py_files = list(PKG_DIR.glob("*.py")) + list((PKG_DIR / "tests").glob("*.py"))
    for f in py_files:
        py_compile.compile(str(f), doraise=True)


def run_suite_once():
    loader = unittest.TestLoader()
    suite = loader.discover(str(PKG_DIR / "tests"), pattern="test_*.py", top_level_dir=str(PKG_DIR))
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    return result.wasSuccessful(), len(result.errors), len(result.failures), result.testsRun


def main():
    sys.path.insert(0, str(PKG_DIR))
    print("Compiling all task_058 sources...")
    compile_all()
    print("Compilation OK.")

    total_runs_ok = 0
    for i in range(1, RUNS + 1):
        ok, errs, fails, tests_run = run_suite_once()
        print(f"RUN {i}/{RUNS}: tests_run={tests_run} errors={errs} failures={fails} ok={ok}")
        if not ok:
            print(f"FAILED on run {i}")
            return 1
        total_runs_ok += 1

    print(f"ALL {total_runs_ok} RUNS PASSED CONSECUTIVELY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
