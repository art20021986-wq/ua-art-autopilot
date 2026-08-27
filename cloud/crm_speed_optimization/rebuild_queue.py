"""Thin re-export of the canonical RebuildQueue implementation.

This module contains no logic of its own; it exists only so historical
imports keep resolving to the exact same object used by the launcher and
orchestrator.
"""
from canonical_modules import RebuildQueue

__all__ = ["RebuildQueue"]
