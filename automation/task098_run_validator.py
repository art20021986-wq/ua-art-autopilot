#!/usr/bin/env python3
"""Run TASK 098 validator with SQLite foreign keys enabled per connection.

SQLite's foreign_keys PRAGMA is connection-local. This launcher changes only the
validator process: every sqlite3 connection it opens starts with foreign-key
enforcement enabled. The validator still executes the generated schema in :memory:
and keeps all existing fail-closed checks.
"""
from __future__ import annotations

import runpy
import sqlite3
from typing import Any

_real_connect = sqlite3.connect


def _connect_with_foreign_keys(*args: Any, **kwargs: Any) -> sqlite3.Connection:
    connection = _real_connect(*args, **kwargs)
    connection.execute("PRAGMA foreign_keys = ON")
    enabled = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
    if enabled != 1:
        connection.close()
        raise RuntimeError("Could not enable SQLite foreign-key enforcement")
    return connection


sqlite3.connect = _connect_with_foreign_keys  # type: ignore[assignment]
runpy.run_path("automation/task098_validate.py", run_name="__main__")
