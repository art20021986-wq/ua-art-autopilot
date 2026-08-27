"""FERRY-PHASE1 — Bounded, fail-closed, read-only discovery.

No production write. No CRM write. No Gate A/B execution. Reads only,
from a fixed registry, under a single base directory. Missing files are
reported honestly, never fabricated.

The CLI root is fixed at /home/Carix. Tests can inject a temporary base only
through function parameters; environment variables cannot retarget the CLI.
"""

import ast
import hashlib
import io
import json
import os
import re
import sqlite3
import stat
import sys
import tokenize
from typing import Dict, List, Optional, Tuple

import transform

BASE_DIR = "/home/Carix"

MAX_SIZE = 20 * 1024 * 1024  # 20 MiB bound for a single file read
MAX_DB_SIZE = 512 * 1024 * 1024

UA_IDS = tuple("UA-%04d" % i for i in range(1, 10))

REGISTRY: Dict[str, List[str]] = {
    "video_pages": [
        "video/index.html", "video/katalog.html", "video/info.html", "video/podbor.html",
    ] + ["video/UA-%04d.html" % i for i in range(1, 10)],
    "site_pages": [
        "site/index.html", "site/katalog.html", "site/info.html", "site/podbor.html",
    ] + ["site/UA-%04d.html" % i for i in range(1, 10)],
    "diag_track_candidates": (
        ["video/UA-%04d-diag.html" % i for i in range(1, 10)]
        + ["video/UA-%04d-track.html" % i for i in range(1, 10)]
    ),
    "python_modules": [
        "stranica.py", "yadro.py", "master_card.py", "cars_ui.py", "team_bot.py",
        "avtoperedacha.py", "db.py", "run_all.py", "start_safe.py",
    ],
    "database": ["crm.db"],
}

PRIMARY_TABLE = "cars"
PRIMARY_ID_COLUMN = "auto_number"
ID_COLUMN_ALIASES = ("ua_id", "catalog_id", "id", "code")
PRIMARY_CONTAINER_COLUMN = "sea_container"
CONTAINER_COLUMN_ALIASES = ("container",)
SANITIZED_OUTPUT_COLUMNS = {
    "stage", "status", "sea_container", "container", "tracking",
    "diagnostics", "cta",
}

SECRET_RE = re.compile(
    r"(?i)([\"']?\b(?:secret|token|password|api[-_]?key|authorization|"
    r"private[-_]?key|credential)\b[\"']?\s*[:=]\s*[\"']?)"
    r"([^\"'\s,}]+)"
)


class _PathIssue(Exception):
    def __init__(self, kind: str, reason: str) -> None:
        self.kind = kind
        self.reason = reason
        super().__init__(reason)


def _resolve_contained_path(base_dir: str, rel_path: str) -> str:
    base_real = os.path.realpath(base_dir)
    rel_norm = os.path.normpath(rel_path)
    parts = rel_norm.split(os.sep)
    if os.path.isabs(rel_norm) or parts[0] == "..":
        raise _PathIssue("BLOCKED", "PATH_ESCAPE_RELATIVE")
    cur_path = base_dir
    for part in parts[:-1]:
        cur_path = os.path.join(cur_path, part)
        if os.path.islink(cur_path):
            raise _PathIssue("BLOCKED", "SYMLINK_PARENT")
        if not os.path.isdir(cur_path):
            raise _PathIssue("MISSING", "MISSING_PARENT_DIR")
    full = os.path.join(cur_path, parts[-1])
    full_real = os.path.realpath(full)
    try:
        common = os.path.commonpath([base_real, full_real])
    except ValueError:
        raise _PathIssue("BLOCKED", "PATH_ESCAPE_DIFFERENT_ROOT")
    if common != base_real:
        raise _PathIssue("BLOCKED", "PATH_ESCAPE")
    return full


def _safe_read_file_bytes(
    base_dir: str,
    rel_path: str,
    require_utf8: bool = True,
    max_size: Optional[int] = None,
) -> Tuple[dict, Optional[bytes]]:
    """Return verified metadata and the exact bytes from the verified fd.

    Raw bytes are internal-only. Public receipts use safe_read_file(), which
    returns metadata without ever serializing file content.
    """
    if max_size is None:
        max_size = MAX_SIZE
    try:
        full = _resolve_contained_path(base_dir, rel_path)
    except _PathIssue as exc:
        if exc.kind == "MISSING":
            return {"status": "MISSING", "path": rel_path}, None
        return {"status": "BLOCKED", "reason": exc.reason, "path": rel_path}, None

    try:
        st_l = os.lstat(full)
    except FileNotFoundError:
        return {"status": "MISSING", "path": rel_path}, None
    except OSError as exc:
        return {"status": "BLOCKED", "reason": "LSTAT_FAILED:%s" % exc, "path": rel_path}, None

    if stat.S_ISLNK(st_l.st_mode):
        return {"status": "BLOCKED", "reason": "SYMLINK_FINAL", "path": rel_path}, None
    if not stat.S_ISREG(st_l.st_mode):
        return {"status": "BLOCKED", "reason": "NOT_REGULAR_FILE", "path": rel_path}, None
    if st_l.st_nlink != 1:
        return {"status": "BLOCKED", "reason": "HARDLINK_DETECTED", "path": rel_path}, None

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(full, flags)
    except OSError as exc:
        return {"status": "BLOCKED", "reason": "OPEN_FAILED:%s" % exc, "path": rel_path}, None

    try:
        st_before = os.fstat(fd)
        identity_before = (
            st_before.st_dev, st_before.st_ino, st_before.st_size, st_before.st_mtime_ns,
        )
        identity_lstat = (st_l.st_dev, st_l.st_ino, st_l.st_size, st_l.st_mtime_ns)
        if identity_before != identity_lstat:
            return {"status": "BLOCKED", "reason": "TOCTOU_MISMATCH", "path": rel_path}, None
        if st_before.st_size > max_size:
            return {"status": "BLOCKED", "reason": "OVERSIZE", "path": rel_path}, None

        chunks: List[bytes] = []
        remaining = st_before.st_size
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                return {"status": "BLOCKED", "reason": "TRUNCATED_READ", "path": rel_path}, None
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            return {
                "status": "BLOCKED", "reason": "SIZE_CHANGED_DURING_READ", "path": rel_path,
            }, None

        st_after = os.fstat(fd)
        identity_after = (
            st_after.st_dev, st_after.st_ino, st_after.st_size, st_after.st_mtime_ns,
        )
        if identity_after != identity_before:
            return {"status": "BLOCKED", "reason": "TOCTOU_AFTER_READ", "path": rel_path}, None
    finally:
        os.close(fd)

    data = b"".join(chunks)
    if require_utf8:
        try:
            data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return {"status": "BLOCKED", "reason": "NON_UTF8", "path": rel_path}, None

    return {
        "status": "OK", "path": rel_path,
        "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
        "mtime_ns": st_after.st_mtime_ns, "dev": st_after.st_dev,
        "ino": st_after.st_ino,
    }, data


def safe_read_file(base_dir: str, rel_path: str) -> dict:
    metadata, _data = _safe_read_file_bytes(base_dir, rel_path)
    return metadata


def discover_registry(base_dir: str = BASE_DIR) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    for _cat, files in REGISTRY.items():
        for f in files:
            results[f] = safe_read_file(base_dir, f)
    return results


def crm_readonly_summary(path: str) -> dict:
    absolute = os.path.abspath(path)
    db_base = os.path.dirname(absolute) or "."
    db_rel = os.path.basename(absolute)
    before, _raw = _safe_read_file_bytes(
        db_base, db_rel, require_utf8=False, max_size=MAX_DB_SIZE,
    )
    if before["status"] == "MISSING":
        return {"status": "MISSING", "path": path}
    if before["status"] != "OK":
        return {"status": "BLOCKED", "reason": "DB_%s" % before.get("reason", "READ_FAILED")}

    outcome: dict
    conn = None
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % absolute, uri=True, timeout=2)
        conn.execute("PRAGMA query_only=ON")
        qc_row = conn.execute("PRAGMA quick_check").fetchone()
        quick_check_ok = bool(qc_row) and qc_row[0] == "ok"
        if not quick_check_ok:
            outcome = {"status": "BLOCKED", "reason": "QUICK_CHECK_FAILED", "quick_check": False}
        else:
            tables = [row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            table = next((name for name in tables if name.lower() == PRIMARY_TABLE), None)
            if table is None:
                outcome = {
                    "status": "BLOCKED", "reason": "AMBIGUOUS_SCHEMA_NO_TABLE",
                    "quick_check": True,
                }
            else:
                quoted_table = '"%s"' % table.replace('"', '""')
                columns = [row[1] for row in conn.execute(
                    "PRAGMA table_info(%s)" % quoted_table
                ).fetchall()]
                by_lower = {column.lower(): column for column in columns}

                id_col = by_lower.get(PRIMARY_ID_COLUMN)
                if id_col is None:
                    id_aliases = [by_lower[name] for name in ID_COLUMN_ALIASES if name in by_lower]
                    id_col = id_aliases[0] if len(id_aliases) == 1 else None

                container_col = by_lower.get(PRIMARY_CONTAINER_COLUMN)
                if container_col is None:
                    container_aliases = [
                        by_lower[name] for name in CONTAINER_COLUMN_ALIASES if name in by_lower
                    ]
                    container_col = container_aliases[0] if len(container_aliases) == 1 else None

                if id_col is None or container_col is None:
                    outcome = {
                        "status": "BLOCKED", "reason": "AMBIGUOUS_SCHEMA_NO_ID_COLUMN",
                        "quick_check": True,
                    }
                else:
                    output_cols = [container_col]
                    for lower_name, actual in sorted(by_lower.items()):
                        if lower_name in SANITIZED_OUTPUT_COLUMNS and actual not in output_cols:
                            output_cols.append(actual)
                    selected = [id_col] + output_cols
                    quoted_selected = ", ".join(
                        '"%s"' % column.replace('"', '""') for column in selected
                    )
                    quoted_id = '"%s"' % id_col.replace('"', '""')
                    placeholders = ",".join("?" for _ in UA_IDS)
                    rows = conn.execute(
                        "SELECT %s FROM %s WHERE %s IN (%s)" % (
                            quoted_selected, quoted_table, quoted_id, placeholders,
                        ),
                        UA_IDS,
                    ).fetchall()
                    grouped: Dict[str, List[tuple]] = {ua: [] for ua in UA_IDS}
                    for row in rows:
                        if row[0] in grouped:
                            grouped[row[0]].append(row)
                    missing = [ua for ua, found in grouped.items() if not found]
                    duplicate = [ua for ua, found in grouped.items() if len(found) != 1]
                    if missing:
                        outcome = {
                            "status": "BLOCKED", "reason": "MISSING_IDS",
                            "missing": missing, "quick_check": True,
                        }
                    elif duplicate:
                        outcome = {
                            "status": "BLOCKED", "reason": "DUPLICATE_IDS",
                            "duplicates": duplicate, "quick_check": True,
                        }
                    else:
                        results: Dict[str, Optional[dict]] = {}
                        for ua in UA_IDS:
                            row = grouped[ua][0]
                            results[ua] = dict(zip(output_cols, row[1:]))
                        outcome = {
                            "status": "OK", "quick_check": True, "table": table,
                            "id_column": id_col, "container_column": container_col,
                            "results": results,
                        }
    except sqlite3.Error as exc:
        outcome = {"status": "BLOCKED", "reason": "SQLITE_ERROR:%s" % exc}
    finally:
        if conn is not None:
            conn.close()

    after, _raw_after = _safe_read_file_bytes(
        db_base, db_rel, require_utf8=False, max_size=MAX_DB_SIZE,
    )
    if after.get("status") != "OK":
        return {"status": "BLOCKED", "reason": "DB_READ_AFTER_FAILED"}
    identity_keys = ("dev", "ino", "size", "mtime_ns", "sha256")
    if any(before.get(key) != after.get(key) for key in identity_keys):
        return {"status": "BLOCKED", "reason": "IDENTITY_CHANGED_AFTER_READ"}
    outcome["sha256"] = before["sha256"]
    return outcome


def _markers() -> dict:
    return {
        "PRODUCTION_TOUCHED": "NO", "CRM_TOUCHED": "NO",
        "CRM_DB_WRITTEN": "NO", "GATE_B_EXECUTED": "NO",
        "UA_0009_PUBLISHED": "NO",
    }


SAFE_AST_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
SAFE_AST_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
USER_FACING_ASSIGNMENTS = {
    "ETAP_KOROTKO", "ETAPY_GLAVNOY", "FILTRY", "SROKI", "POTOK",
}
USER_FACING_FUNCTIONS = {
    "etap_dlinno", "blok_pribytiya", "sobrat_kartochku", "sobrat_katalog",
    "sobrat_info",
}
PYTHON_TEXT_REPLACEMENTS = (
    ("В море · Корея → Грузия", "На пароме · Корея → Грузия"),
    ("У морі · Корея → Грузія", "На поромі · Корея → Грузія"),
    ("В море", "На пароме"),
    ("У морі", "На поромі"),
    ("Море", "Паром"),
)


class PythonTransformBlocked(RuntimeError):
    pass


def _safe_ast_name(value: object) -> str:
    return value if isinstance(value, str) and SAFE_AST_NAME_RE.fullmatch(value) else ""


def _safe_ast_key(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if SAFE_AST_KEY_RE.fullmatch(node.value) else ""
    return ""


def _target_hint(node: ast.AST) -> str:
    """Return identifiers only; never relay executable source or literal values."""
    if isinstance(node, ast.Name):
        return _safe_ast_name(node.id)
    if isinstance(node, ast.Attribute):
        left = _target_hint(node.value)
        right = _safe_ast_name(node.attr)
        return ".".join(part for part in (left, right) if part)
    if isinstance(node, ast.Subscript):
        left = _target_hint(node.value)
        key = _safe_ast_key(node.slice)
        return ".".join(part for part in (left, key) if part)
    if isinstance(node, (ast.Tuple, ast.List)):
        return ".".join(filter(None, (_target_hint(item) for item in node.elts)))
    return ""


def _call_hint(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return _safe_ast_name(node.id)
    if isinstance(node, ast.Attribute):
        left = _call_hint(node.value)
        right = _safe_ast_name(node.attr)
        return ".".join(part for part in (left, right) if part)
    return ""


def _inventory_python_literals(source: str, rel_path: str) -> List[dict]:
    occurrences: List[dict] = []
    tree = ast.parse(source)
    target_phrases = (
        "В море · Корея → Грузия", "У морі · Корея → Грузія",
        "В море", "У морі", "Море",
    )

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.hints: List[str] = []
            self.roles: List[str] = []
            self.dict_keys: List[str] = []
            self.calls: List[str] = []
            self.keywords: List[str] = []
            self.functions: List[str] = []
            self.classes: List[str] = []

        def _push_visit(self, stack: List[str], value: str, node: ast.AST) -> None:
            stack.append(value)
            self.visit(node)
            stack.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.classes.append(_safe_ast_name(node.name))
            self.generic_visit(node)
            self.classes.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.functions.append(_safe_ast_name(node.name))
            self.generic_visit(node)
            self.functions.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Assign(self, node: ast.Assign) -> None:
            hints = [_target_hint(target) for target in node.targets]
            self.hints.append(".".join(filter(None, hints)))
            self.visit(node.value)
            self.hints.pop()

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            hint = _target_hint(node.target)
            self.hints.append(hint)
            if node.value is not None:
                self.visit(node.value)
            self.hints.pop()

        def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
            self.hints.append(_target_hint(node.target))
            self.visit(node.value)
            self.hints.pop()

        def visit_Dict(self, node: ast.Dict) -> None:
            for key, value in zip(node.keys, node.values):
                key_hint = _safe_ast_key(key) if key is not None else ""
                if key is not None:
                    self._push_visit(self.roles, "DICT_KEY", key)
                self.dict_keys.append(key_hint)
                self._push_visit(self.roles, "DICT_VALUE", value)
                self.dict_keys.pop()

        def visit_Call(self, node: ast.Call) -> None:
            call = _call_hint(node.func)
            self.calls.append(call)
            for argument in node.args:
                self._push_visit(self.roles, "CALL_ARG", argument)
            for keyword in node.keywords:
                self.keywords.append(_safe_ast_name(keyword.arg))
                self._push_visit(self.roles, "CALL_KEYWORD", keyword.value)
                self.keywords.pop()
            self.calls.pop()

        def visit_Return(self, node: ast.Return) -> None:
            if node.value is not None:
                self._push_visit(self.roles, "RETURN", node.value)

        def _visit_collection(self, node: ast.AST) -> None:
            for item in node.elts:
                self._push_visit(self.roles, "COLLECTION_ITEM", item)

        visit_List = _visit_collection
        visit_Tuple = _visit_collection
        visit_Set = _visit_collection

        def visit_Compare(self, node: ast.Compare) -> None:
            self._push_visit(self.roles, "COMPARISON", node.left)
            for comparator in node.comparators:
                self._push_visit(self.roles, "COMPARISON", comparator)

        def visit_Constant(self, node: ast.Constant) -> None:
            if not isinstance(node.value, str):
                return
            matched = next((phrase for phrase in target_phrases if phrase in node.value), None)
            if matched is None:
                return
            hint = (self.hints[-1] if self.hints else "").upper()
            function = self.functions[-1] if self.functions else ""
            _preview, structural = transform.transform_document(node.value)
            structural_changes = sum(
                item.get("action") == "APPLIED" for item in structural
            )
            structural_ambiguous = sum(
                item.get("classification") == "AMBIGUOUS" for item in structural
            )
            if any(word in hint for word in ("ALIAS", "LEGACY", "INPUT_MAP")):
                classification = "LEGACY_INPUT_ALIAS"
            elif structural_changes and not structural_ambiguous:
                classification = "USER_FACING"
            elif hint in USER_FACING_ASSIGNMENTS or (
                function in USER_FACING_FUNCTIONS
                and (self.roles[-1] if self.roles else "OTHER")
                not in {"DICT_KEY", "COMPARISON"}
            ):
                classification = "USER_FACING"
            elif any(word in hint for word in ("LABEL", "TEXT", "STATUS", "STAGE", "HTML", "TEMPLATE")):
                classification = "USER_FACING"
            else:
                classification = "AMBIGUOUS"
            occurrences.append({
                "path": rel_path, "line": getattr(node, "lineno", None),
                "column": getattr(node, "col_offset", None),
                "end_line": getattr(node, "end_lineno", None),
                "end_column": getattr(node, "end_col_offset", None),
                "before": matched, "classification": classification,
                "action": "PRESERVE",
                "literal_sha256": hashlib.sha256(node.value.encode("utf-8")).hexdigest(),
                "literal_length": len(node.value),
                "assignment": self.hints[-1] if self.hints else "",
                "role": self.roles[-1] if self.roles else "OTHER",
                "dict_key": self.dict_keys[-1] if self.dict_keys else "",
                "call": self.calls[-1] if self.calls else "",
                "keyword": self.keywords[-1] if self.keywords else "",
                "function": self.functions[-1] if self.functions else "",
                "class": self.classes[-1] if self.classes else "",
                "structural_changes": structural_changes,
                "structural_ambiguous": structural_ambiguous,
                "structural_contexts": sorted({
                    str(item.get("context")) for item in structural if item.get("context")
                }),
            })

    Visitor().visit(tree)
    return occurrences


def _ast_byte_column_to_character(line: str, byte_column: int) -> int:
    if not isinstance(byte_column, int) or byte_column < 0:
        raise PythonTransformBlocked("invalid_ast_column")
    encoded = line.encode("utf-8")
    if byte_column > len(encoded):
        raise PythonTransformBlocked("ast_column_out_of_bounds")
    try:
        return len(encoded[:byte_column].decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise PythonTransformBlocked("ast_column_not_character_boundary") from exc


def _mapped_python_text(value: str) -> Tuple[str, int]:
    mapped = value
    changes = 0
    for before, after in PYTHON_TEXT_REPLACEMENTS:
        count = mapped.count(before)
        if count:
            mapped = mapped.replace(before, after)
            changes += count
    return mapped, changes


def transform_python_source(source: str, rel_path: str) -> Tuple[str, List[dict]]:
    """Patch only approved string tokens; preserve every other source character."""
    compile(source, rel_path, "exec")
    inventory = _inventory_python_literals(source, rel_path)
    ambiguous = [item for item in inventory if item["classification"] == "AMBIGUOUS"]
    if ambiguous:
        raise PythonTransformBlocked("ambiguous_python_literal")
    approved = [item for item in inventory if item["classification"] == "USER_FACING"]
    if not approved:
        return source, []

    lines = source.splitlines(keepends=True)
    logical_lines = source.splitlines()
    if source.endswith(("\n", "\r")):
        logical_lines.append("")
    starts = []
    cursor = 0
    for line in lines:
        starts.append(cursor)
        cursor += len(line)
    if not lines or (source and not source.endswith(("\n", "\r"))):
        if len(starts) < len(logical_lines):
            starts.append(cursor)

    tokens = [
        token for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.STRING
    ]
    replacements = []
    records = []
    seen_positions = set()
    seen_token_positions = set()
    for item in approved:
        line_number = item["line"]
        end_line = item["end_line"]
        if not 1 <= line_number <= len(logical_lines) or not 1 <= end_line <= len(logical_lines):
            raise PythonTransformBlocked("literal_line_out_of_bounds")
        start_character = _ast_byte_column_to_character(
            logical_lines[line_number - 1], item["column"]
        )
        end_character = _ast_byte_column_to_character(
            logical_lines[end_line - 1], item["end_column"]
        )
        position = (line_number, start_character, end_line, end_character)
        if position in seen_positions:
            raise PythonTransformBlocked("duplicate_literal_position")
        seen_positions.add(position)
        node_start = (line_number, start_character)
        node_end = (end_line, end_character)
        node_tokens = [
            token for token in tokens
            if node_start <= token.start and token.end <= node_end
        ]
        if not node_tokens:
            raise PythonTransformBlocked("literal_has_no_string_tokens:%s" % line_number)
        values = []
        for token in node_tokens:
            token_position = (token.start, token.end)
            if token_position in seen_token_positions:
                raise PythonTransformBlocked("overlapping_literal_tokens:%s" % line_number)
            try:
                value_part = ast.literal_eval(token.string)
            except (SyntaxError, ValueError) as exc:
                raise PythonTransformBlocked(
                    "literal_not_static_string_token:%s" % line_number
                ) from exc
            if not isinstance(value_part, str):
                raise PythonTransformBlocked("literal_not_text:%s" % line_number)
            values.append(value_part)
        value = "".join(values)
        if hashlib.sha256(value.encode("utf-8")).hexdigest() != item["literal_sha256"]:
            raise PythonTransformBlocked("literal_hash_mismatch:%s" % line_number)
        mapped, change_count = _mapped_python_text(value)
        if change_count < 1 or mapped == value:
            raise PythonTransformBlocked("approved_literal_not_changed:%s" % line_number)
        direct_changes = 0
        mapped_parts = []
        for token, value_part in zip(node_tokens, values):
            mapped_part, part_changes = _mapped_python_text(value_part)
            token_text = token.string
            mapped_token_text = token_text
            token_direct_changes = 0
            for before, after in PYTHON_TEXT_REPLACEMENTS:
                count = mapped_token_text.count(before)
                if count:
                    mapped_token_text = mapped_token_text.replace(before, after)
                    token_direct_changes += count
            if token_direct_changes != part_changes:
                raise PythonTransformBlocked(
                    "literal_requires_escape_rewrite:%s" % line_number
                )
            try:
                evaluated = ast.literal_eval(mapped_token_text)
            except (SyntaxError, ValueError) as exc:
                raise PythonTransformBlocked("mapped_literal_invalid:%s" % line_number) from exc
            if evaluated != mapped_part:
                raise PythonTransformBlocked(
                    "mapped_literal_value_mismatch:%s" % line_number
                )
            mapped_parts.append(mapped_part)
            direct_changes += token_direct_changes
            if token_direct_changes:
                start_offset = starts[token.start[0] - 1] + token.start[1]
                end_offset = starts[token.end[0] - 1] + token.end[1]
                if source[start_offset:end_offset] != token_text:
                    raise PythonTransformBlocked("token_offset_mismatch:%s" % line_number)
                replacements.append((start_offset, end_offset, mapped_token_text))
            seen_token_positions.add((token.start, token.end))
        if direct_changes != change_count:
            raise PythonTransformBlocked("literal_target_crosses_tokens:%s" % line_number)
        if "".join(mapped_parts) != mapped:
            raise PythonTransformBlocked("mapped_parts_value_mismatch:%s" % line_number)
        records.append({
            "line": line_number,
            "before": item["before"],
            "after": dict(PYTHON_TEXT_REPLACEMENTS)[item["before"]],
            "replacements": change_count,
            "literal_sha256_before": item["literal_sha256"],
            "literal_sha256_after": hashlib.sha256(mapped.encode("utf-8")).hexdigest(),
        })

    candidate = source
    for start_offset, end_offset, replacement in sorted(replacements, reverse=True):
        candidate = candidate[:start_offset] + replacement + candidate[end_offset:]
    compile(candidate, rel_path, "exec")
    remaining = _inventory_python_literals(candidate, rel_path)
    if any(item["classification"] in {"USER_FACING", "AMBIGUOUS"} for item in remaining):
        raise PythonTransformBlocked("target_remains_after_python_transform")
    return candidate, records


def run_discovery(base_dir: str = BASE_DIR) -> dict:
    if not os.path.isdir(base_dir):
        return {
            "status": "BLOCKED", "reasons": ["ROOT_MISSING"],
            "base_dir": base_dir, "markers": _markers(),
        }

    required_html = set(REGISTRY["video_pages"])
    html_paths = (
        REGISTRY["video_pages"] + REGISTRY["site_pages"]
        + REGISTRY["diag_track_candidates"]
    )
    html_results: Dict[str, dict] = {}
    missing_required: List[str] = []
    ambiguous_required: List[str] = []
    total_occurrences = 0

    for rel_path in html_paths:
        meta, raw = _safe_read_file_bytes(base_dir, rel_path)
        if meta["status"] != "OK":
            html_results[rel_path] = meta
            if rel_path in required_html:
                missing_required.append(rel_path)
            continue
        source = raw.decode("utf-8")
        _preview, occurrences = transform.transform_document(source)
        ambiguous = [item for item in occurrences if item.get("classification") == "AMBIGUOUS"]
        total_occurrences += len(occurrences)
        if rel_path in required_html and ambiguous:
            ambiguous_required.append(rel_path)
        html_results[rel_path] = {
            "status": "OK", "sha256": meta["sha256"], "size": meta["size"],
            "occurrences": len(occurrences), "ambiguous": len(ambiguous),
        }

    python_results: Dict[str, dict] = {}
    python_blocked: List[str] = []
    python_ambiguous: List[str] = []
    for rel_path in REGISTRY["python_modules"]:
        meta, raw = _safe_read_file_bytes(base_dir, rel_path)
        if meta["status"] != "OK":
            python_results[rel_path] = meta
            python_blocked.append(rel_path)
            continue
        try:
            source = raw.decode("utf-8")
            occurrences = _inventory_python_literals(source, rel_path)
        except (UnicodeDecodeError, SyntaxError):
            python_results[rel_path] = {"status": "BLOCKED", "reason": "PARSE_FAILED"}
            python_blocked.append(rel_path)
            continue
        ambiguous = [item for item in occurrences if item["classification"] == "AMBIGUOUS"]
        total_occurrences += len(occurrences)
        if ambiguous:
            python_ambiguous.append(rel_path)
        python_results[rel_path] = {
            "status": "OK", "sha256": meta["sha256"], "size": meta["size"],
            "occurrences": occurrences,
        }

    crm = crm_readonly_summary(os.path.join(base_dir, REGISTRY["database"][0]))
    reasons: List[str] = []
    if missing_required:
        reasons.append("MISSING_CORE_PAGES")
    if python_blocked:
        reasons.append("PYTHON_SOURCES_BLOCKED")
    if ambiguous_required or python_ambiguous:
        reasons.append("AMBIGUOUS_TARGET")
    if crm.get("status") != "OK":
        reasons.append("CRM_NOT_PASS")
    if total_occurrences == 0:
        reasons.append("ZERO_OCCURRENCES")

    return {
        "status": "BLOCKED" if reasons else "OK", "reasons": reasons,
        "base_dir": base_dir, "html": html_results, "python": python_results,
        "crm": crm, "total_source_occurrences": total_occurrences,
        "missing_required": missing_required,
        "ambiguous_targets": sorted(set(ambiguous_required + python_ambiguous)),
        "markers": _markers(),
    }


def discover_all(base_dir: str = BASE_DIR) -> dict:
    return run_discovery(base_dir)


def scan_for_secrets(serialized: str) -> bool:
    return any(match.group(2) != "[REDACTED]" for match in SECRET_RE.finditer(serialized))


def redact_secrets(serialized: str) -> str:
    return SECRET_RE.sub(lambda match: match.group(1) + "[REDACTED]", serialized)


def redact_obj(value):
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return [redact_obj(item) for item in value]
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {
                "secret", "token", "password", "api_key", "authorization",
                "private_key", "credential",
            }:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_obj(item)
        return redacted
    return value


def serialize_receipt(receipt: dict) -> str:
    serialized = json.dumps(redact_obj(receipt), ensure_ascii=False, sort_keys=True)
    if scan_for_secrets(serialized):
        return json.dumps(
            {"status": "BLOCKED", "reason": "SECRET_LEAK_DETECTED"},
            ensure_ascii=False, sort_keys=True,
        )
    return serialized


def main() -> int:
    try:
        receipt = run_discovery(BASE_DIR)
    except Exception as exc:  # noqa: BLE001 - fail closed, single JSON, no traceback
        receipt = {"status": "BLOCKED", "reason": "EXCEPTION:%s:%s" % (type(exc).__name__, exc)}
    sys.stdout.write(serialize_receipt(receipt) + "\n")
    return 0 if receipt.get("status") == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
