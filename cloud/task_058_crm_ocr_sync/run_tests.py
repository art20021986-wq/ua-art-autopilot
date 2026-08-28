#!/usr/bin/env python3
"""Compile TASK 058 and require ten consecutive clean offline runs."""
from __future__ import annotations

import pathlib
import py_compile
import sys
import unittest


PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
RUNS = 10


def compile_all() -> None:
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        if "__pycache__" not in path.parts:
            py_compile.compile(str(path), doraise=True)


def run_once() -> unittest.result.TestResult:
    suite = unittest.defaultTestLoader.discover(
        str(PACKAGE_DIR / "tests"), pattern="test_*.py", top_level_dir=str(PACKAGE_DIR)
    )
    return unittest.TextTestRunner(verbosity=1).run(suite)


def main() -> int:
    sys.path.insert(0, str(PACKAGE_DIR))
    compile_all()
    for run in range(1, RUNS + 1):
        result = run_once()
        print(
            f"TASK058 RUN {run}/{RUNS}: tests={result.testsRun} "
            f"errors={len(result.errors)} failures={len(result.failures)}"
        )
        if not result.wasSuccessful():
            return 1
    print("TASK058: 10/10 CONSECUTIVE RUNS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
