"""No-argument launcher: discovers and runs every test under tests/.

Usage: python3 run_tests.py
Exit code 0 on full pass, 1 otherwise. Standard library only.
"""

import os
import sys
import unittest


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.join(here, "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
