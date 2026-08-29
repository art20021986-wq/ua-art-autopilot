"""Offline test runner for TASK 073 tooling.

Run with: python3 cloud/task_073/tests/run_all_tests.py
Exits non-zero on any failure so CI/manual runs fail closed.
"""

import os
import sys
import unittest


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    loader = unittest.TestLoader()
    suite = loader.discover(here, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
