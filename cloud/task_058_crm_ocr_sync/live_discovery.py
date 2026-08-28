#!/usr/bin/env python3
"""TASK 058 read-only discovery for the UA ART CRM/OCR incident.

Python 3.10, standard library only. The script reads only explicitly
allowlisted production inputs. Its sole write is one JSON receipt in the
task-specific safe inbox. It never imports production modules, rebuilds the
site, opens SQLite for writing, or reloads a service.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import stat
import sys
import tempfile
from typing import Iterable


BASE_DIR = pathlib.Path("/home/Carix")
SAFE_INBOX_DIR = BASE_DIR / "autopilot_inbox" / "cloud" / "task_058_crm_ocr_sync"
ALLOWLIST_PATH = SAFE_INBOX_DIR / "allowlist.json"
RECEIPT_PATH = SAFE_INBOX_DIR / "task_058_live_discovery_receipt.json"
MAX_SOURCE_BYTES = 3_000_000
MAX_SITE_BYTES = 5_000_000
MAX_LOG_BYTES = 5_000_000
MAX_LOG_LINES = 4_000
MAX_ANCHORS_PER_FILE = 160
MAX_SNIPPET_CHARS = 360
MAX_EXCERPT_CHARS = 30_000
MAX_IMPORTS_PER_FILE = 120

TARGET_FUNCTIONS = {
    "ai.py": {"parse_image", "parse_message", "transcribe", "validate", "to_card_data"},
    "team_bot.py": {"detect_kind", "intake", "run_ai_draft", "ai_save"},
    "ai_filter.py": {"clean", "store", "render", "source_text", "autosave"},
    "db.py": {"connect", "create_card", "set_card_review"},
    "cars_ui.py": {"_peresobrat_stranicy", "photo_remove_all"},
    "avtoperedacha.py": {"sobrat", "sobrat_svoimi_rukami", "shag"},
    "stranica.py": {"main", "zapisat", "zapisat_atomarno"},
    "konteyner.py": {"_peresobrat", "_svezhiy_sborshchik"},
}

ERROR_FRAGMENTS = {
    "ocr_failure": "Изображение сохранено, но разобрать его не получилось",
    "rebuild_failure": "страницы сайта отстали от базы",
}

FEATURE_PATTERNS = {
    "telegram_media": re.compile(
        r"(?i)(photo(?:size)?|effective_attachment|\.document\b|get_file|"
        r"download_(?:to_drive|as_bytearray|to_memory)|mime_type)"
    ),
    "ocr_vision": re.compile(
        r"(?i)(ocr|vision|image_to_text|tesseract|paddleocr|easyocr|"
        r"openai|anthropic|gemini|base64|image_url)"
    ),
    "database_write": re.compile(
        r"(?i)(sqlite3|\.execute\s*\(|\.executemany\s*\(|\.commit\s*\(|"
        r"\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bREPLACE\b)"
    ),
    "rebuild_publish": re.compile(
        r"(?i)(rebuild|regenerat|peresob|пересоб|stranica|yadro|"
        r"os\.replace|subprocess|create_subprocess|published_revision)"
    ),
    "retry_timeout": re.compile(r"(?i)(retry|attempt|timeout|backoff|sleep)"),
    "lock_resource": re.compile(
        r"(?i)(database is locked|busy_timeout|journal_mode|blockingioerror|"
        r"resource temporarily unavailable|filelock|flock|lock)"
    ),
    "log_path": re.compile(
        r"(?i)(?:['\"])([^'\"]{1,180}\.(?:log|jsonl|txt))(?:['\"])"
    )
}

LOG_PATTERNS = {
    "database_is_locked": re.compile(r"database is locked", re.I),
    "resource_temporarily_unavailable": re.compile(
        r"Resource temporarily unavailable", re.I
    ),
    "ocr_failure": re.compile(re.escape(ERROR_FRAGMENTS["ocr_failure"]), re.I),
    "rebuild_failure": re.compile(re.escape(ERROR_FRAGMENTS["rebuild_failure"]), re.I),
}

SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]{10,}){1,2}"),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
GENERIC_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b"
    r"\s*[:=]\s*(['\"])([^'\"\r\n]{8,})\2"
)
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.I)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[ ()-]*)?(?:\d[ ()-]*){8,14}\d(?!\w)"
)


class DiscoveryError(RuntimeError):
    """Sanitized fail-closed discovery error."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact(text: str) -> str:
    result = GENERIC_SECRET_ASSIGNMENT_RE.sub(
        lambda match: match.group(1) + "=[REDACTED_SECRET]", text
    )
    for pattern in SECRET_VALUE_PATTERNS:
        result = pattern.sub("[REDACTED_SECRET]", result)
    result = VIN_RE.sub("[REDACTED_VIN]", result)
    result = EMAIL_RE.sub("[REDACTED_EMAIL]", result)
    result = PHONE_RE.sub("[REDACTED_PHONE]", result)
    return result


def regular_file(
    raw_path: str,
    *,
    allowed_paths: set[str],
    max_bytes: int,
    required: bool,
) -> pathlib.Path | None:
    if raw_path not in allowed_paths:
        raise DiscoveryError("PATH_NOT_IN_HARDCODED_ALLOWLIST")
    path = pathlib.Path(raw_path)
    try:
        lst = path.lstat()
    except FileNotFoundError:
        if required:
            raise DiscoveryError("REQUIRED_PATH_MISSING:" + raw_path)
        return None
    if stat.S_ISLNK(lst.st_mode):
        raise DiscoveryError("SYMLINK_REJECTED:" + raw_path)
    if not stat.S_ISREG(lst.st_mode):
        raise DiscoveryError("NON_REGULAR_REJECTED:" + raw_path)
    if lst.st_nlink != 1:
        raise DiscoveryError("HARDLINK_REJECTED:" + raw_path)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(BASE_DIR.resolve(strict=True))
    except ValueError as exc:
        raise DiscoveryError("PATH_ESCAPE_REJECTED:" + raw_path) from exc
    if lst.st_size > max_bytes:
        raise DiscoveryError("OVERSIZE_REJECTED:" + raw_path)
    return resolved


def _string_list(value: object, key: str, *, limit: int) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise DiscoveryError("ALLOWLIST_FIELD_INVALID:" + key)
    if any(not isinstance(item, str) or not item for item in value):
        raise DiscoveryError("ALLOWLIST_ENTRY_INVALID:" + key)
    if len(value) != len(set(value)):
        raise DiscoveryError("ALLOWLIST_DUPLICATE:" + key)
    return list(value)


def load_allowlist(path: pathlib.Path) -> dict:
    if path != ALLOWLIST_PATH:
        raise DiscoveryError("ALLOWLIST_PATH_INVALID")
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise DiscoveryError("ALLOWLIST_FILE_INVALID")
    if path.parent.resolve(strict=True) != SAFE_INBOX_DIR.resolve(strict=True):
        raise DiscoveryError("ALLOWLIST_PARENT_INVALID")
    if path.stat().st_size > 100_000:
        raise DiscoveryError("ALLOWLIST_OVERSIZE")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError("ALLOWLIST_JSON_INVALID") from exc
    if not isinstance(data, dict):
        raise DiscoveryError("ALLOWLIST_NOT_OBJECT")
    allowed_keys = {
        "task_id",
        "required_source_paths",
        "optional_source_paths",
        "db_path",
        "required_site_paths",
        "optional_site_paths",
        "log_paths",
    }
    if set(data) != allowed_keys or data.get("task_id") != "task_058":
        raise DiscoveryError("ALLOWLIST_SCHEMA_INVALID")
    required_sources = _string_list(
        data["required_source_paths"], "required_source_paths", limit=20
    )
    optional_sources = _string_list(
        data["optional_source_paths"], "optional_source_paths", limit=20
    )
    required_site = _string_list(
        data["required_site_paths"], "required_site_paths", limit=40
    )
    optional_site = _string_list(
        data["optional_site_paths"], "optional_site_paths", limit=40
    )
    logs = _string_list(data["log_paths"], "log_paths", limit=12)
    db_path = data["db_path"]
    if not isinstance(db_path, str) or not db_path:
        raise DiscoveryError("ALLOWLIST_DB_PATH_INVALID")
    all_entries = required_sources + optional_sources + required_site + optional_site + logs + [db_path]
    if len(all_entries) != len(set(all_entries)):
        raise DiscoveryError("ALLOWLIST_CROSS_FIELD_DUPLICATE")
    hardcoded = hardcoded_paths()
    if any(entry not in hardcoded for entry in all_entries):
        raise DiscoveryError("ALLOWLIST_CONTAINS_UNAPPROVED_PATH")
    return {
        "required_source_paths": required_sources,
        "optional_source_paths": optional_sources,
        "db_path": db_path,
        "required_site_paths": required_site,
        "optional_site_paths": optional_site,
        "log_paths": logs,
    }


def hardcoded_paths() -> set[str]:
    source_names = (
        "ai.py",
        "team_bot.py",
        "db.py",
        "cars_ui.py",
        "avtoperedacha.py",
        "run_all.py",
        "start_safe.py",
        "stranica.py",
        "yadro.py",
        "konteyner.py",
        "ai_filter.py",
        "lock4_zhurnal.py",
    )
    paths = {str(BASE_DIR / name) for name in source_names}
    paths.add(str(BASE_DIR / "crm.db"))
    for root_name in ("video", "site"):
        root = BASE_DIR / root_name
        paths.add(str(root / "index.html"))
        paths.add(str(root / "katalog.html"))
        for number in range(1, 11):
            paths.add(str(root / f"UA-{number:04d}.html"))
    # Log paths are deliberately empty until an exact path is proven from
    # source evidence in this round. No broad log-directory scan is allowed.
    return paths


def _function_ranges(tree: ast.AST) -> list[tuple[int, int, str]]:
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            ranges.append((node.lineno, end, node.name))
    return ranges


def _function_for_line(ranges: Iterable[tuple[int, int, str]], line: int) -> str | None:
    matches = [item for item in ranges if item[0] <= line <= item[1]]
    if not matches:
        return None
    return min(matches, key=lambda item: item[1] - item[0])[2]


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return (parent + "." if parent else "") + node.attr
    return None


def _imports(tree: ast.AST) -> list[dict]:
    result = []
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            entries = [(alias.name, None, alias.asname) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            entries = [(node.module or "", alias.name, alias.asname) for alias in node.names]
        else:
            continue
        for module, name, alias in entries:
            key = (module, name, alias)
            if key not in seen and len(result) < MAX_IMPORTS_PER_FILE:
                seen.add(key)
                result.append({"module": module, "name": name, "as": alias})
    return result


def _target_excerpts(
    tree: ast.AST, lines: list[str], filename: str
) -> list[dict]:
    wanted = TARGET_FUNCTIONS.get(filename, set())
    result = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in wanted:
            continue
        end = int(getattr(node, "end_lineno", node.lineno))
        source = redact("\n".join(lines[node.lineno - 1 : end]))[:MAX_EXCERPT_CHARS]
        calls = sorted(
            {
                name
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                for name in [_call_name(call.func)]
                if name
            }
        )[:200]
        result.append(
            {
                "name": node.name,
                "line": node.lineno,
                "end_line": end,
                "calls": calls,
                "source": source,
            }
        )
    return sorted(result, key=lambda item: (item["line"], item["name"]))


def scan_source(path: pathlib.Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    try:
        tree = ast.parse(raw, filename=str(path))
        ranges = _function_ranges(tree)
        syntax = "PASS"
    except SyntaxError:
        tree = None
        ranges = []
        syntax = "FAIL"
    anchors = []
    message_locations = []
    log_literals = []
    for index, line in enumerate(lines, 1):
        function = _function_for_line(ranges, index)
        for label, fragment in ERROR_FRAGMENTS.items():
            if fragment.casefold() in line.casefold():
                start = max(0, index - 3)
                end = min(len(lines), index + 2)
                snippet = redact("\n".join(lines[start:end]))[:MAX_SNIPPET_CHARS]
                message_locations.append(
                    {"kind": label, "line": index, "function": function, "snippet": snippet}
                )
        for category, pattern in FEATURE_PATTERNS.items():
            if category == "log_path":
                for match in pattern.finditer(line):
                    literal = match.group(1)
                    if literal not in log_literals:
                        log_literals.append(redact(literal)[:180])
                continue
            if pattern.search(line) and len(anchors) < MAX_ANCHORS_PER_FILE:
                anchors.append(
                    {
                        "category": category,
                        "line": index,
                        "function": function,
                        "snippet": redact(line.strip())[:240],
                    }
                )
    st = path.stat()
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "syntax": syntax,
        "anchors": anchors,
        "message_locations": message_locations,
        "log_path_literals": log_literals[:20],
        "imports": _imports(tree) if tree is not None else [],
        "function_excerpts": (
            _target_excerpts(tree, lines, path.name) if tree is not None else []
        ),
    }


def _db_sidecar_snapshot(db_path: pathlib.Path) -> dict:
    result = {}
    for suffix in ("-wal", "-shm", "-journal"):
        candidate = pathlib.Path(str(db_path) + suffix)
        if candidate.exists() and candidate.is_file() and not candidate.is_symlink():
            st = candidate.stat()
            result[suffix] = {
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "sha256": sha256_file(candidate) if st.st_size <= MAX_SOURCE_BYTES else None,
            }
        else:
            result[suffix] = None
    return result


def sqlite_probe(db_path: pathlib.Path) -> dict:
    before = sha256_file(db_path)
    sidecars_before = _db_sidecar_snapshot(db_path)
    uri = "file:" + str(db_path) + "?mode=ro"
    result = {
        "path": str(db_path),
        "open_uri_mode": "ro",
        "query_only_requested": True,
        "sha256_before": before,
        "sidecars_before": sidecars_before,
    }
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        connection.execute("PRAGMA query_only=ON")
        result["query_only_value"] = int(connection.execute("PRAGMA query_only").fetchone()[0])
        result["journal_mode"] = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
        result["busy_timeout_ms"] = int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
        result["quick_check"] = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 100"
        ).fetchall()
        tables = [str(row[0]) for row in table_rows]
        result["table_names"] = tables
        cars_table = next((name for name in tables if name.casefold() == "cars"), None)
        result["cars_table_found"] = cars_table is not None
        result["cars_total"] = None
        result["ua0009_row_count"] = None
        result["ua0009_published_count"] = None
        result["ua0010_row_count"] = None
        result["ua0010_published_count"] = None
        result["candidate_cards"] = {}
        result["cars_columns"] = []
        if cars_table is not None:
            safe_table = '"' + cars_table.replace('"', '""') + '"'
            columns = [
                str(row[1])
                for row in connection.execute("PRAGMA table_info(" + safe_table + ")").fetchall()
            ]
            result["cars_columns"] = columns
            result["cars_total"] = int(
                connection.execute("SELECT COUNT(*) FROM " + safe_table).fetchone()[0]
            )
            id_column = next(
                (
                    name
                    for name in columns
                    if name.casefold()
                    in {
                        "auto_number",
                        "number",
                        "code",
                        "card_id",
                        "inventory_number",
                        "car_number",
                        "slug",
                        "uid",
                    }
                ),
                None,
            )
            published_column = next(
                (name for name in columns if name.casefold() in {"published", "is_published"}),
                None,
            )
            if id_column:
                safe_id = '"' + id_column.replace('"', '""') + '"'
                safe_published = (
                    '"' + published_column.replace('"', '""') + '"'
                    if published_column
                    else None
                )
                for candidate in ("UA-0009", "UA-0010"):
                    row_count = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM " + safe_table + " WHERE " + safe_id + "=?",
                            (candidate,),
                        ).fetchone()[0]
                    )
                    published_count = None
                    if safe_published:
                        published_count = int(
                            connection.execute(
                                "SELECT COUNT(*) FROM "
                                + safe_table
                                + " WHERE "
                                + safe_id
                                + "=? AND CAST(COALESCE("
                                + safe_published
                                + ",0) AS TEXT) IN ('1','true','True')",
                                (candidate,),
                            ).fetchone()[0]
                        )
                    result["candidate_cards"][candidate] = {
                        "row_count": row_count,
                        "published_count": published_count,
                    }
                result["ua0009_row_count"] = result["candidate_cards"]["UA-0009"]["row_count"]
                result["ua0009_published_count"] = result["candidate_cards"]["UA-0009"]["published_count"]
                result["ua0010_row_count"] = result["candidate_cards"]["UA-0010"]["row_count"]
                result["ua0010_published_count"] = result["candidate_cards"]["UA-0010"]["published_count"]

        result["inbox_columns"] = []
        result["recent_image_candidates"] = []
        inbox_table = next((name for name in tables if name.casefold() == "inbox"), None)
        if inbox_table is not None:
            safe_inbox = '"' + inbox_table.replace('"', '""') + '"'
            inbox_columns = [
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(" + safe_inbox + ")"
                ).fetchall()
            ]
            result["inbox_columns"] = inbox_columns
            id_col = next((name for name in inbox_columns if name.casefold() == "id"), None)
            kind_col = next((name for name in inbox_columns if name.casefold() == "kind"), None)
            file_col = next(
                (
                    name
                    for name in inbox_columns
                    if name.casefold() in {"file_id", "telegram_file_id", "media_file_id"}
                ),
                None,
            )
            created_col = next(
                (
                    name
                    for name in inbox_columns
                    if name.casefold() in {"created_at", "received_at", "timestamp"}
                ),
                None,
            )
            if id_col and kind_col and file_col:
                quote = lambda name: '"' + name.replace('"', '""') + '"'
                selected = [quote(id_col), quote(kind_col), quote(file_col)]
                selected.append(quote(created_col) if created_col else "NULL")
                rows = connection.execute(
                    "SELECT "
                    + ",".join(selected)
                    + " FROM "
                    + safe_inbox
                    + " WHERE LOWER(CAST("
                    + quote(kind_col)
                    + " AS TEXT)) IN ('photo','document')"
                    + " AND "
                    + quote(file_col)
                    + " IS NOT NULL ORDER BY "
                    + quote(id_col)
                    + " DESC LIMIT 5"
                ).fetchall()
                for row_id, kind, file_id, created_at in rows:
                    file_text = str(file_id)
                    created_text = (
                        str(created_at).replace(" ", "T")[:40]
                        if created_at is not None
                        else None
                    )
                    if created_text and not re.fullmatch(r"[0-9T:Z+.-]{1,40}", created_text):
                        created_text = None
                    result["recent_image_candidates"].append(
                        {
                            "inbox_id": int(row_id),
                            "kind": str(kind).casefold()[:20],
                            "created_at": created_text,
                            "file_id_sha256": hashlib.sha256(
                                file_text.encode("utf-8")
                            ).hexdigest(),
                            "file_id_present": bool(file_text),
                        }
                    )
    finally:
        connection.close()
    result["sha256_after"] = sha256_file(db_path)
    result["sidecars_after"] = _db_sidecar_snapshot(db_path)
    result["identity_stable"] = (
        result["sha256_before"] == result["sha256_after"]
        and result["sidecars_before"] == result["sidecars_after"]
    )
    return result


def site_snapshot(
    required_paths: list[str], optional_paths: list[str], allowed: set[str]
) -> tuple[dict[str, dict | None], list[str]]:
    snapshot = {}
    errors = []
    required_set = set(required_paths)
    for raw_path in required_paths + optional_paths:
        try:
            path = regular_file(
                raw_path,
                allowed_paths=allowed,
                max_bytes=MAX_SITE_BYTES,
                required=raw_path in required_set,
            )
            if path is None:
                snapshot[raw_path] = None
                continue
            st = path.stat()
            snapshot[raw_path] = {
                "sha256": sha256_file(path),
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
            }
        except DiscoveryError as exc:
            snapshot[raw_path] = None
            errors.append(str(exc))
    return snapshot, errors


def log_counts(paths: list[str], allowed: set[str]) -> dict:
    counts = {name: 0 for name in LOG_PATTERNS}
    scanned = []
    errors = []
    for raw_path in paths:
        try:
            path = regular_file(
                raw_path,
                allowed_paths=allowed,
                max_bytes=MAX_LOG_BYTES,
                required=False,
            )
            if path is None:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[-MAX_LOG_LINES:]:
                for name, pattern in LOG_PATTERNS.items():
                    if pattern.search(line):
                        counts[name] += 1
            scanned.append(str(path))
        except DiscoveryError as exc:
            errors.append(str(exc))
    return {"paths_scanned": scanned, "counts": counts, "errors": errors}


def build_report(config: dict) -> dict:
    started = utc_now()
    allowed = hardcoded_paths()
    errors = []

    site_before, site_errors_before = site_snapshot(
        config["required_site_paths"], config["optional_site_paths"], allowed
    )
    errors.extend(site_errors_before)

    sources = []
    required_set = set(config["required_source_paths"])
    for raw_path in config["required_source_paths"] + config["optional_source_paths"]:
        try:
            path = regular_file(
                raw_path,
                allowed_paths=allowed,
                max_bytes=MAX_SOURCE_BYTES,
                required=raw_path in required_set,
            )
            if path is not None:
                sources.append(scan_source(path))
        except DiscoveryError as exc:
            errors.append(str(exc))

    db_result = None
    try:
        db_file = regular_file(
            config["db_path"],
            allowed_paths=allowed,
            max_bytes=25 * 1024 * 1024,
            required=True,
        )
        if db_file is not None:
            db_result = sqlite_probe(db_file)
    except (DiscoveryError, sqlite3.Error, OSError) as exc:
        errors.append("DATABASE_PROBE_FAILED:" + redact(str(exc))[:180])

    logs = log_counts(config["log_paths"], allowed)
    errors.extend(logs["errors"])

    source_hashes_after = {}
    for entry in sources:
        path = pathlib.Path(entry["path"])
        source_hashes_after[entry["path"]] = sha256_file(path)
    source_identity_stable = all(
        entry["sha256"] == source_hashes_after.get(entry["path"])
        for entry in sources
    )
    if not source_identity_stable:
        errors.append("SOURCE_CHANGED_DURING_AUDIT")

    site_after, site_errors_after = site_snapshot(
        config["required_site_paths"], config["optional_site_paths"], allowed
    )
    errors.extend(site_errors_after)
    site_identity_stable = site_before == site_after
    if not site_identity_stable:
        errors.append("SITE_CHANGED_DURING_AUDIT")
    if db_result is not None and not db_result.get("identity_stable"):
        errors.append("DATABASE_CHANGED_DURING_AUDIT")

    found_paths = {entry["path"] for entry in sources}
    required_sources_found = set(config["required_source_paths"]).issubset(found_paths)
    team_source = next(
        (entry for entry in sources if entry["path"] == str(BASE_DIR / "team_bot.py")),
        None,
    )
    required_team_functions = TARGET_FUNCTIONS["team_bot.py"]
    found_team_functions = {
        item["name"] for item in (team_source or {}).get("function_excerpts", [])
    }
    target_functions_found = required_team_functions.issubset(found_team_functions)
    required_site_found = all(site_before.get(path) is not None for path in config["required_site_paths"])
    database_ok = bool(
        db_result
        and db_result.get("query_only_value") == 1
        and db_result.get("quick_check") == "ok"
        and db_result.get("identity_stable") is True
    )
    if not required_sources_found:
        errors.append("REQUIRED_SOURCES_INCOMPLETE")
    if not target_functions_found:
        errors.append("TARGET_FUNCTION_EXCERPTS_INCOMPLETE")
    if not required_site_found:
        errors.append("REQUIRED_SITE_INVENTORY_INCOMPLETE")
    if not database_ok:
        errors.append("DATABASE_READONLY_EVIDENCE_INCOMPLETE")

    message_kinds = {
        location["kind"]
        for source in sources
        for location in source["message_locations"]
    }
    anchors_by_category = {}
    for source in sources:
        for anchor in source["anchors"]:
            anchors_by_category[anchor["category"]] = (
                anchors_by_category.get(anchor["category"], 0) + 1
            )
    ua9_video = site_before.get(str(BASE_DIR / "video" / "UA-0009.html"))
    ua9_site = site_before.get(str(BASE_DIR / "site" / "UA-0009.html"))
    ua9_db_rows = db_result.get("ua0009_row_count") if db_result else None
    ua9_published = db_result.get("ua0009_published_count") if db_result else None
    ua10_video = site_before.get(str(BASE_DIR / "video" / "UA-0010.html"))
    ua10_site = site_before.get(str(BASE_DIR / "site" / "UA-0010.html"))
    ua10_db_rows = db_result.get("ua0010_row_count") if db_result else None
    ua10_published = db_result.get("ua0010_published_count") if db_result else None
    ua9_status = "UNKNOWN"
    if ua9_db_rows == 0 and ua9_video is None and ua9_site is None:
        ua9_status = "NOT_SAFE_TO_PUBLISH"
    ua10_status = "UNKNOWN"
    if ua10_db_rows == 0 and ua10_video is None and ua10_site is None:
        ua10_status = "READY_FOR_DRAFT_CREATION_ONLY"

    report = {
        "task_id": "task_058",
        "mode": "READ_ONLY_LIVE_DISCOVERY",
        "status": "PASS" if not errors else "BLOCKED",
        "generated_at_utc": utc_now(),
        "started_at_utc": started,
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "site_rebuilt": False,
        "service_reloaded": False,
        "ocr_fix_installed": False,
        "gate_b_executed": False,
        "ua0009_published": False,
        "ua0010_published": False,
        "sources": sources,
        "source_hashes_after": source_hashes_after,
        "source_identity_stable": source_identity_stable,
        "database": db_result,
        "site_before": site_before,
        "site_after": site_after,
        "site_identity_stable": site_identity_stable,
        "logs": logs,
        "completeness": {
            "required_sources_found": required_sources_found,
            "target_functions_found": target_functions_found,
            "required_site_found": required_site_found,
            "database_readonly_verified": database_ok,
            "logs_scanned": bool(logs["paths_scanned"]),
            "ocr_failure_message_found": "ocr_failure" in message_kinds,
            "rebuild_failure_message_found": "rebuild_failure" in message_kinds,
            "anchor_counts": anchors_by_category,
            "root_cause_confirmed": False,
        },
        "ua0009_status": ua9_status,
        "ua0009_evidence": {
            "db_row_count": ua9_db_rows,
            "db_published_count": ua9_published,
            "video_page_present": ua9_video is not None,
            "site_page_present": ua9_site is not None,
        },
        "ua0010_status": ua10_status,
        "ua0010_evidence": {
            "db_row_count": ua10_db_rows,
            "db_published_count": ua10_published,
            "video_page_present": ua10_video is not None,
            "site_page_present": ua10_site is not None,
            "owner_authorized": True,
            "publication_executed": False,
        },
        "errors": sorted(set(errors)),
    }
    # Defense in depth: reject the whole receipt if a secret-shaped value
    # somehow escaped redaction.
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if any(pattern.search(serialized) for pattern in SECRET_VALUE_PATTERNS):
        raise DiscoveryError("SECRET_SHAPED_CONTENT_IN_RECEIPT")
    if VIN_RE.search(serialized) or EMAIL_RE.search(serialized):
        raise DiscoveryError("PII_SHAPED_CONTENT_IN_RECEIPT")
    return report


def _safe_receipt_target(path: pathlib.Path) -> pathlib.Path:
    if path != RECEIPT_PATH:
        raise DiscoveryError("RECEIPT_PATH_INVALID")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise DiscoveryError("RECEIPT_PARENT_INVALID")
    if parent.resolve(strict=True) != SAFE_INBOX_DIR.resolve(strict=True):
        raise DiscoveryError("RECEIPT_PARENT_ESCAPE")
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise DiscoveryError("RECEIPT_EXISTING_PATH_INVALID")
    return path


def write_receipt(report: dict, path: pathlib.Path) -> None:
    target = _safe_receipt_target(path)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=target.parent,
        prefix="." + target.name + ".",
        suffix=".tmp",
        delete=False,
    )
    temp_path = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowlist-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if pathlib.Path(args.allowlist_file) != ALLOWLIST_PATH:
            raise DiscoveryError("ALLOWLIST_ARGUMENT_INVALID")
        if pathlib.Path(args.output) != RECEIPT_PATH:
            raise DiscoveryError("OUTPUT_ARGUMENT_INVALID")
        config = load_allowlist(ALLOWLIST_PATH)
        report = build_report(config)
        write_receipt(report, RECEIPT_PATH)
        return 0
    except Exception as exc:
        # Only a sanitized failure receipt is attempted. If the output path
        # itself is unsafe, nothing is written anywhere.
        failure = {
            "task_id": "task_058",
            "mode": "READ_ONLY_LIVE_DISCOVERY",
            "status": "BLOCKED",
            "generated_at_utc": utc_now(),
            "production_write": False,
            "crm_write": False,
            "db_write": False,
            "site_rebuilt": False,
            "service_reloaded": False,
            "ocr_fix_installed": False,
            "gate_b_executed": False,
            "ua0009_published": False,
            "ua0010_published": False,
            "errors": [redact(str(exc))[:240]],
        }
        try:
            if pathlib.Path(args.output) == RECEIPT_PATH:
                write_receipt(failure, RECEIPT_PATH)
        except Exception:
            pass
        print("TASK058_DISCOVERY_BLOCKED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
