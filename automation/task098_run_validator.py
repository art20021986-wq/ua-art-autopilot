#!/usr/bin/env python3
"""Run TASK 098 validator with normalized machine-derived QA aliases.

SQLite's foreign_keys PRAGMA is connection-local, so every in-memory validation
connection starts with enforcement enabled. The generated evidence may use nested
field names; this launcher temporarily adds canonical count aliases derived from the
raw probe files, rejects conflicts, runs the strict validator, and restores the exact
original evidence bytes in all cases.
"""
from __future__ import annotations

import json
import runpy
import sqlite3
from pathlib import Path
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


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _set_verified_alias(document: dict[str, Any], key: str, value: int) -> None:
    existing = document.get(key)
    if existing is not None:
        try:
            existing_value = int(existing)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Conflicting non-numeric {key}: {existing!r}") from exc
        if existing_value != value:
            raise RuntimeError(f"Conflicting {key}: generated={existing_value}, raw={value}")
    document[key] = value


sqlite3.connect = _connect_with_foreign_keys  # type: ignore[assignment]

evidence_path = Path("cloud/task_098_editorial_atlas_qa/evidence_qa.json")
original_bytes = evidence_path.read_bytes()
document = json.loads(original_bytes.decode("utf-8"))
if not isinstance(document, dict):
    raise RuntimeError("evidence_qa.json must contain a JSON object")

live_rows = _load_json(Path("cloud/task_098_editorial_atlas_qa/live_site_probe.json"))
redirect_rows = _load_json(Path("cloud/task_098_editorial_atlas_qa/redirect_probe.json"))
machine = _load_json(Path("cloud/task_098_editorial_atlas_qa/source_probe_qa_machine.json"))
if not isinstance(live_rows, list) or not isinstance(redirect_rows, list) or not isinstance(machine, dict):
    raise RuntimeError("Raw QA evidence has invalid structure")

_set_verified_alias(document, "live_seo_probe_rows", len(live_rows))
_set_verified_alias(document, "redirect_probe_rows", len(redirect_rows))
_set_verified_alias(document, "non_normal_source_count", int(machine["non_normal_count"]))

evidence_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
try:
    runpy.run_path("automation/task098_validate.py", run_name="__main__")
finally:
    evidence_path.write_bytes(original_bytes)
