#!/usr/bin/env python3
"""Dependency-free TASK 080 test runner used locally and in Actions."""
from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    passed = failed = 0
    failures = []
    for index, path in enumerate(sorted((root / "tests").glob("test_*.py"))):
        name = "task080_test_%d" % index
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        for test_name, function in sorted(inspect.getmembers(module, inspect.isfunction)):
            if not test_name.startswith("test_"):
                continue
            try:
                function()
                passed += 1
            except Exception as exc:
                failed += 1
                failures.append(
                    "%s::%s %s: %s"
                    % (path.name, test_name, type(exc).__name__, exc)
                )
    for failure in failures:
        print("FAIL", failure)
    print("TASK080_TEST_RESULT %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
