"""
Verifier utilities for Gate A byte-identical repeat runs and protected
hash comparisons (TASK 021).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable


def compare_protected_hashes(before: dict, after: dict) -> int:
    unexpected = 0
    for name, b in before.items():
        a = after.get(name)
        if a != b:
            unexpected += 1
    return unexpected


def compare_output_bytes(path_a: Path, path_b: Path) -> bool:
    return path_a.read_bytes() == path_b.read_bytes()


def verify_deterministic_repeat(build_fn: Callable[[], bytes], times: int = 10) -> bool:
    """build_fn() -> bytes; verifies all runs are byte-identical."""
    if times < 2:
        raise ValueError("times must be >= 2 to prove determinism")
    first = build_fn()
    for _ in range(times - 1):
        nxt = build_fn()
        if nxt != first:
            return False
    return True
