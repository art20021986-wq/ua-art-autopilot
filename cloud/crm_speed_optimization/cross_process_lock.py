"""Thin re-export of the canonical CrossProcessLock implementation.

This module contains no logic. Historical callers/tests that import from
here receive the exact same class object as canonical_modules and
crm_speed_gate_a. Do not add logic to this file.
"""
from canonical_modules import CrossProcessLock, LockEvidence, SingletonGuard

__all__ = ["CrossProcessLock", "LockEvidence", "SingletonGuard"]
