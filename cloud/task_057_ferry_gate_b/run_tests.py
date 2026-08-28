#!/usr/bin/env python3
"""Standard-library test runner for task_057 Gate B package.

Runs entirely against temporary fixtures. Never touches production paths.
"""
import sys
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG_DIR))


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(str(PKG_DIR / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
