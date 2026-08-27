"""
TASK 050 discover module.

- safe_read_file: verified read (identity, not-a-symlink, size, mtime, full
  sha256). Keeps the verified raw bytes available for downstream structural
  analysis instead of discarding them before analysis (fixes TASK 047 defect).
- discover_registry: builds a full occurrence inventory across given file
  paths (HTML text/attrs via transform.py, Python string literals via ast,
  never importing/executing target code).
- read_crm_verified: strict SQLite read-only (mode=ro, query_only,
  quick_check) contract with explicit table/id-column allowlists, exact
  parameterized UA-0001..UA-0009 IDs, exactly-one-row enforcement, and
  before/after full-SHA identity verification of the database file.
- run_discovery: aggregates everything into one receipt with an overall
  OK / BLOCKED status. BLOCKED on any required source blocked, CRM blocked,
  or any AMBIGUOUS occurrence among required targets. Optional missing files
  remain explicit MISSING and do not block by themselves. The final
  serialized receipt is scanned for secrets before being returned.

KNOWN LIMITATION: this module operates on whatever paths/DB are passed to
it (intended for temporary fixtures and future real registries supplied by
the owner/Codex). It does not itself locate or touch real UA ART production
files or the live CRM database.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import transform as _transform


# ---------------------------------------------------------------------------
# Verified file read
# ---------------------------------------------------------------------------

@dataclass
class VerifiedFile:
    path: str
    exists: bool
    is_symlink: bool
    size: int
    mtime: float
    sha256: str
    raw_bytes: Optional[bytes] = field(default=None, repr=False)


def safe_read_file(path: str) -> VerifiedFile:
    """Verify identity (does not follow symlinks) and read full bytes,
    keeping them available for structural analysis instead of discarding
    them after a preliminary check."""
    if not os.path.exists(path) and not os.path.islink(path):
        return VerifiedFile(path=path, exists=False, is_symlink=False, size=0, mtime=0.0, sha256="")
    is_symlink = os.path.islink(path)
    if is_symlink:
        st = os.lstat(path)
        return VerifiedFile(path=path, exists=True, is_symlink=True, size=st.st_size,
                             mtime=st.st_mtime, sha256="", raw_bytes=None)
    if not os.path.exists(path):
        return VerifiedFile(path=path, exists=False, is_symlink=False, size=0, mtime=0.0, sha256="")
    st = os.lstat(path)
    with open(path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    return VerifiedFile(path=path, exists=True, is_symlink=False, size=len(raw),
                         mtime=st.st_mtime, sha256=sha, raw_bytes=raw)


# ---------------------------------------------------------------------------
# Python literal inventory (parse/tokenize only, never import/execute)
# ---------------------------------------------------------------------------

def _classify_py_literal(name_hint: str) -> str:
    hint = (name_hint or "").upper()
    if "ALIAS" in hint:
        return "LEGACY_INPUT_ALIAS"
    if any(k in hint for k in ("LABEL", "TEXT", "TEMPLATE", "RENDER")):
        return "USER_FACING"
    return "AMBIGUOUS"


def inventory_python_literals(source: str, path: str, sha256: str) -> List[_transform.Occurrence]:
    occurrences: List[_transform.Occurrence] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return occurrences

    targets = ("В море", "Море")

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.assign_stack: List[str] = []

        def visit_Assign(self, node: ast.Assign) -> None:
            name_hint = ""
            for t in node.targets:
                if isinstance(t, ast.Name):
                    name_hint = t.id
            self.assign_stack.append(name_hint)
            self.generic_visit(node)
            self.assign_stack.pop()

        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, str) and any(t in node.value for t in targets):
                hint = self.assign_stack[-1] if self.assign_stack else ""
                classification = _classify_py_literal(hint)
                occurrences.append(_transform.Occurrence(
                    path=path, sha256=sha256, language="n/a", form="python_literal",
                    classification=classification, before=node.value, after=node.value,
                    anchor=(f"assign:{hint}" if hint else "literal"),
                    context=node.value[:80],
                    action="PRESERVE",
                ))

    _Visitor().visit(tree)
    return occurrences


# ---------------------------------------------------------------------------
# Discovery registry
# ---------------------------------------------------------------------------

def discover_registry(paths: List[str]) -> Dict[str, Any]:
    files_report: List[Dict[str, Any]] = []
    all_occurrences: List[Dict[str, Any]] = []
    blocked = False

    for path in paths:
        vf = safe_read_file(path)
        if not vf.exists:
            files_report.append({"path": path, "status": "MISSING"})
            continue
        if vf.is_symlink:
            files_report.append({"path": path, "status": "BLOCKED", "reason": "symlink_not_followed"})
            blocked = True
            continue

        occurrences: List[_transform.Occurrence] = []
        try:
            text = vf.raw_bytes.decode("utf-8", errors="strict") if vf.raw_bytes is not None else ""
        except UnicodeDecodeError:
            files_report.append({"path": path, "status": "BLOCKED", "reason": "undecodable_utf8"})
            blocked = True
            continue

        if path.endswith((".html", ".htm")):
            _new_text, occurrences = _transform.transform_html(text, path, vf.sha256)
        elif path.endswith(".py"):
            occurrences = inventory_python_literals(text, path, vf.sha256)

        files_report.append({
            "path": path,
            "status": "OK",
            "sha256": vf.sha256,
            "size": vf.size,
            "occurrence_count": len(occurrences),
        })
        all_occurrences.extend(asdict(o) for o in occurrences)

    return {"files": files_report, "occurrences": all_occurrences, "blocked": blocked}


# ---------------------------------------------------------------------------
# CRM (SQLite) verified read-only inspection
# ---------------------------------------------------------------------------

TABLE_ALLOWLIST = ("cards", "ua_cards", "orders")
ID_COLUMN_ALLOWLIST = ("id", "card_id", "order_id")
ALLOWED_FIELDS = ("status", "route", "note", "stage")
VALID_IDS = tuple(f"UA-{i:04d}" for i in range(1, 10))  # UA-0001..UA-0009


def _verify_identity(path: str) -> Dict[str, Any]:
    if os.path.islink(path):
        return {"exists": True, "blocked": True, "reason": "symlink_not_followed"}
    if not os.path.exists(path):
        return {"exists": False}
    st = os.lstat(path)
    with open(path, "rb") as f:
        raw = f.read()
    return {
        "exists": True,
        "blocked": False,
        "size": st.st_size,
        "mtime": st.st_mtime,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def read_crm_verified(db_path: str, ids: List[str]) -> Dict[str, Any]:
    """Read CRM rows for exact allowlisted IDs via a strict read-only,
    nofollow, allowlisted contract. Blocks on any ambiguity, missing/
    duplicate rows, or corrupted/unreadable database."""
    before = _verify_identity(db_path)
    if not before.get("exists"):
        return {"status": "MISSING", "reason": "db_not_found"}
    if before.get("blocked"):
        return {"status": "BLOCKED", "reason": before["reason"]}

    for i in ids:
        if i not in VALID_IDS:
            return {"status": "BLOCKED", "reason": f"id_not_allowlisted:{i}"}

    uri = f"file:{db_path}?mode=ro"
    conn = None
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only = 1;")
        quick = conn.execute("PRAGMA quick_check;").fetchall()
        if not quick or quick[0][0] != "ok":
            return {"status": "BLOCKED", "reason": "quick_check_failed"}

        placeholders = ",".join("?" for _ in TABLE_ALLOWLIST)
        cur = conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name IN ({placeholders})",
            TABLE_ALLOWLIST,
        )
        tables = [r[0] for r in cur.fetchall()]
        if len(tables) != 1:
            return {"status": "BLOCKED", "reason": f"table_ambiguous:{tables}"}
        table = tables[0]

        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        id_cols = [c for c in cols if c in ID_COLUMN_ALLOWLIST]
        if len(id_cols) != 1:
            return {"status": "BLOCKED", "reason": f"id_column_ambiguous:{id_cols}"}
        id_col = id_cols[0]

        fields = [c for c in cols if c in ALLOWED_FIELDS]
        select_cols = [id_col] + fields

        rows_out: List[Dict[str, Any]] = []
        for target_id in ids:
            cur = conn.execute(
                f"SELECT {', '.join(select_cols)} FROM {table} WHERE {id_col} = ?",
                (target_id,),
            )
            rows = cur.fetchall()
            if len(rows) == 0:
                return {"status": "BLOCKED", "reason": f"missing_row:{target_id}"}
            if len(rows) > 1:
                return {"status": "BLOCKED", "reason": f"duplicate_row:{target_id}"}
            row = rows[0]
            rows_out.append({col: val for col, val in zip(select_cols, row)})
    except sqlite3.Error as exc:
        return {"status": "BLOCKED", "reason": f"sqlite_error:{exc}"}
    finally:
        if conn is not None:
            conn.close()

    after = _verify_identity(db_path)
    if after.get("sha256") != before.get("sha256"):
        return {"status": "BLOCKED", "reason": "identity_changed_during_read"}

    return {
        "status": "OK",
        "rows": rows_out,
        "table": table,
        "id_column": id_col,
        "sha256_before": before["sha256"],
        "sha256_after": after["sha256"],
    }


# ---------------------------------------------------------------------------
# Aggregate run
# ---------------------------------------------------------------------------

def run_discovery(html_paths: List[str], py_paths: List[str],
                   crm_db_path: Optional[str] = None,
                   crm_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    registry = discover_registry(list(html_paths) + list(py_paths))

    crm_result = None
    if crm_db_path is not None:
        crm_result = read_crm_verified(crm_db_path, crm_ids or [])

    ambiguous = [o for o in registry["occurrences"] if o["classification"] == "AMBIGUOUS"]
    required_blocked = registry["blocked"] or any(f["status"] == "BLOCKED" for f in registry["files"])

    overall = "OK"
    if required_blocked:
        overall = "BLOCKED"
    elif crm_result is not None and crm_result.get("status") not in ("OK", None):
        overall = "BLOCKED"
    elif ambiguous:
        overall = "BLOCKED"

    receipt: Dict[str, Any] = {
        "overall": overall,
        "files": registry["files"],
        "occurrences": registry["occurrences"],
        "ambiguous_count": len(ambiguous),
        "crm": crm_result,
        "PRODUCTION_TOUCHED": "NO",
        "CRM_TOUCHED": "NO" if crm_db_path is None else "READ_ONLY",
        "CRM_DB_WRITTEN": "NO",
        "GATE_B_EXECUTED": "NO",
        "UA_0009_PUBLISHED": "NO",
    }

    serialized = repr(receipt)
    if _transform.scan_for_secrets(serialized):
        serialized = _transform.redact_secrets(serialized)
        receipt["_secret_redaction_applied"] = True

    receipt["_serialized_receipt"] = serialized
    return receipt
