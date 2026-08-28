#!/usr/bin/env python3
"""Compile every .py file in this package and run the full offline test suite
10 consecutive times. Exits non-zero on the first failure/error/nondeterminism.
"""
from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
RUNS = 10


def compile_all() -> None:
    py_files = sorted(PACKAGE_ROOT.rglob("*.py"))
    for f in py_files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as exc:
            print(f"COMPILE_FAILED: {f}: {exc}", file=sys.stderr)
            sys.exit(1)
    print(f"COMPILE_OK: {len(py_files)} files")


def run_suite_once(run_index: int) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        cwd=str(PACKAGE_ROOT),
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        print(f"TEST_RUN_FAILED at iteration {run_index}", file=sys.stderr)
        sys.exit(result.returncode)


def main() -> int:
    compile_all()
    for i in range(1, RUNS + 1):
        print(f"--- run {i}/{RUNS} ---")
        run_suite_once(i)
    print(f"ALL_{RUNS}_RUNS_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
