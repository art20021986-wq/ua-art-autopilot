#!/usr/bin/env python3
"""Private isolated unittest runner used only by gate.py."""
import argparse
import importlib
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("tests", nargs="+")
    args = parser.parse_args()
    folder = args.directory.resolve(strict=True)
    sys.path.insert(0, str(folder))
    suite = unittest.TestSuite()
    for filename in args.tests:
        if Path(filename).name != filename or not filename.startswith("test_") or not filename.endswith(".py"):
            raise ValueError("PRICE_TEST_FILE_SCOPE")
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(filename[:-3])))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    evidence = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                    skipped=len(result.skipped), expected_failures=len(result.expectedFailures),
                    unexpected_successes=len(result.unexpectedSuccesses))
    with args.result.open("x") as stream:
        json.dump(evidence, stream, sort_keys=True)
    return 0 if result.wasSuccessful() and result.testsRun and not result.skipped and not result.expectedFailures else 1


if __name__ == "__main__":
    raise SystemExit(main())
