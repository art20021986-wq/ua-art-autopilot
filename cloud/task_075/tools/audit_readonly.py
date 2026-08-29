"""TASK 075 — GET-only / read-only audit helpers.

Safety rules enforced by this module:
- crm.db is only ever opened with mode=ro and PRAGMA query_only=1.
- PythonAnywhere API access is GET-only (no other HTTP verb is implemented).
- Every input file is SHA256+size fixated BEFORE any transform is applied.
- No function in this module writes to any external system.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class InputFixation:
    path: str
    sha256: str
    size_bytes: int


def fixate_inputs(paths: Iterable[str]) -> List[InputFixation]:
    """Compute SHA256 and byte size for each given path before any transform.

    Read-only: opens each file in binary read mode only.
    """
    results: List[InputFixation] = []
    for p in paths:
        fp = Path(p)
        data = fp.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        results.append(InputFixation(path=str(fp), sha256=digest, size_bytes=len(data)))
    return results


def open_crm_readonly(db_path: str) -> sqlite3.Connection:
    """Open crm.db strictly read-only. Any write attempt on this connection
    will raise sqlite3.OperationalError because of query_only=1.
    """
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = 1;")
    return conn


def fetch_all_statuses(conn: sqlite3.Connection, table: str = "leads") -> List[Dict[str, Any]]:
    """Read-only SELECT of id/status/photo/transition fields.

    Column names are placeholders; the real schema must be confirmed by the
    controller with actual access before running this against production data.
    """
    cur = conn.execute(
        f"SELECT id, status, photo_count, transition_at FROM {table};"
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def pa_api_get(url: str, timeout: int = 10) -> Dict[str, Any]:
    """GET-only fetch against a PythonAnywhere API endpoint. Raises if a
    non-GET verb is ever requested (there is no parameter for that; this
    function structurally cannot issue anything but GET).
    """
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))
