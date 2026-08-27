"""
Preflight policy checks for UA Cards Unified Gate A package.

Design goal (TASK 021 mandatory fix over the rejected TASK 018 package):

- This module NEVER scans the runner's own source text for banned
  field-name substrings (e.g. "api_url"). It only ever inspects
  *discovered data identifiers* explicitly supplied by the caller.
- It distinguishes real production identifiers (UA-0001..UA-0009) from
  synthetic/demo placeholder identifiers, and NEVER treats the real
  identifiers as banned.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from . import common

SYNTHETIC_DEMO_PATTERNS = [
    re.compile(r"^DEMO-", re.IGNORECASE),
    re.compile(r"^TEST-", re.IGNORECASE),
    re.compile(r"^FAKE-", re.IGNORECASE),
    re.compile(r"^SAMPLE-", re.IGNORECASE),
    re.compile(r"^SYNTH-", re.IGNORECASE),
    re.compile(r"^PLACEHOLDER", re.IGNORECASE),
]

# Names of this package's own source files. Used only to refuse
# self-scanning; never used to scan data.
THIS_PACKAGE_FILES = {
    "runner.py", "preflight.py", "manifest_builder.py", "launcher.py",
    "verifier.py", "common.py",
}


def is_real_card_code(code: str) -> bool:
    """UA-0001..UA-0009 are real production identifiers. Never banned."""
    return code in common.ALL_CODES


def is_synthetic_placeholder(identifier: str) -> bool:
    """Detect synthetic/demo placeholders in *discovered data*, never in
    the package's own source code and never in the real UA-0001..UA-0009
    identifiers."""
    if is_real_card_code(identifier):
        return False
    for pattern in SYNTHETIC_DEMO_PATTERNS:
        if pattern.search(identifier):
            return True
    return False


def reject_if_package_self_scan(path: Path) -> None:
    """Guard used by tests to prove the preflight never scans its own
    module files for banned substrings. If a caller mistakenly passes
    one of this package's own files, refuse to run pattern scanning on
    it and raise, instead of producing a false positive."""
    if path.name in THIS_PACKAGE_FILES:
        raise common.GateAError(
            f"Refusing to preflight-scan the package's own source file: {path}"
        )


def scan_discovered_identifiers(identifiers: Iterable[str]) -> list[str]:
    """Return the subset of *discovered data identifiers* flagged as
    synthetic placeholders. Real UA-0001..UA-0009 codes are always
    excluded from this result. This function never receives or scans
    this package's own source code."""
    return [i for i in identifiers if is_synthetic_placeholder(i)]


def validate_required_real_codes(discovered_codes: Iterable[str]) -> list[str]:
    """Return the list of required real codes UA-0001..UA-0008 that are
    missing from discovered_codes. UA-0009 has a separate readiness
    gate and is not required here."""
    discovered = set(discovered_codes)
    return [c for c in common.REAL_CODES if c not in discovered]
