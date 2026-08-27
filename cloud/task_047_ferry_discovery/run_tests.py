"""run_tests.py -- offline test runner for TASK 052 ferry discovery package.

Runs the full suite twice (determinism check) and works from any cwd,
since it resolves paths relative to its own file location.

Usage: python3 run_tests.py
"""
import sys
import unittest
from pathlib import Path


def main():
    base = Path(__file__).resolve().parent
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))

    loader = unittest.TestLoader()
    total_failures = 0
    last_ran = 0

    for run_index in (1, 2):
        suite = loader.discover(str(base / "tests"), pattern="test_*.py")
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        last_ran = result.testsRun
        total_failures += len(result.failures) + len(result.errors)
        print(f"RUN {run_index}: ran={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}")

    if total_failures:
        print("RESULT: FAIL")
        return 1

    print(f"RESULT: PASS total_tests_per_run={last_ran}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
