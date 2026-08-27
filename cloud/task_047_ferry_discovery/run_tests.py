#!/usr/bin/env python3
"""FERRY-PHASE1 test runner: compile, determinism and two full test runs."""

import os
import py_compile
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def compile_check():
    for name in (
        "transform.py", "discover.py", "gate_a_remote.py", "gate_a_controller.py",
    ):
        py_compile.compile(os.path.join(HERE, name), doraise=True)


def determinism_check():
    sys.path.insert(0, HERE)
    import transform  # noqa: E402

    sample = ('<div class="status-pill">В море</div>'
              '<div class="route-long">У морі · Корея → Грузія</div>'
              '<span class="stage-step" data-lang="ru">Море</span>')
    first, _ = transform.transform_document(sample)
    for _ in range(10):
        out, _ = transform.transform_document(sample)
        if out != first:
            raise SystemExit("DETERMINISM_FAILURE")
    twice, _ = transform.transform_document(first)
    if twice != first:
        raise SystemExit("IDEMPOTENCE_FAILURE")


def run_unit_tests():
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(HERE, "tests"), pattern="test_*.py", top_level_dir=HERE)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result


if __name__ == "__main__":
    compile_check()
    determinism_check()
    first = run_unit_tests()
    second = run_unit_tests()
    ok = first.wasSuccessful() and second.wasSuccessful()
    if ok and first.testsRun == second.testsRun:
        print("RESULT: PASS total_tests_per_run=%d" % first.testsRun)
    else:
        print(
            "RESULT: FAIL run1=%d failures=%d errors=%d run2=%d failures=%d errors=%d"
            % (
                first.testsRun, len(first.failures), len(first.errors),
                second.testsRun, len(second.failures), len(second.errors),
            )
        )
    sys.exit(0 if ok else 1)
