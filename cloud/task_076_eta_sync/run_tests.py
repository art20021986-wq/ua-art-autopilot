"""Offline test runner. No network, no CRM, no PythonAnywhere access.

Usage: python3 run_tests.py

Exit code 0 on full pass, 1 otherwise.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "fixtures"))
sys.path.insert(0, os.path.join(HERE, "tests"))

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(HERE, "tests"))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
