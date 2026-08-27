"""Thin re-export of the canonical CrossProcessLock implementation.

This module contains no logic. Historical callers/tests that import from
here receive the exact same class objects as canonical_modules. Do not
add logic to this file.
"""
from canonical_modules import CrossProcessLock, LockEvidence, SingletonGuard

__all__ = ["CrossProcessLock", "LockEvidence", "SingletonGuard"]
