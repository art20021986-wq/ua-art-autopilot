#!/usr/bin/env python3
"""Dependency-free TASK 080 test runner used locally and in Actions."""
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    passed = failed = 0
    failures = []
    for index, path in enumerate(sorted((root / "tests").glob("test_*.py"))):
        name = "task080_test_%d" % index
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            failed += 1
            failures.append(
                "%s::<module> %s: %s" % (path.name, type(exc).__name__, exc)
            )
            continue
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
    evidence = root / "evidence" / "test_run.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "task_id": "task_080",
        "status": "PASS" if failed == 0 else "FAIL",
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "failures": failures,
        "production_write": False,
        "database_write": False,
        "finished_at_utc": datetime.now(timezone.utc).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z"),
    }
    temporary = evidence.with_name("." + evidence.name + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(evidence)
    print("TASK080_TEST_RESULT %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
