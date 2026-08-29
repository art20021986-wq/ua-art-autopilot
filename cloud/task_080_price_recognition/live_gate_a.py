#!/usr/bin/env python3
"""TASK 080: bounded GET-only audit of the live CRM price path.

Remote HTTP is GET-only. The script downloads source files and a disposable
SQLite snapshot, analyses them locally, and writes sanitized evidence.
It never sends a write request to PythonAnywhere and never reloads a process.
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


API = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
REMOTE_ROOT = "/home/Carix"
HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence" / "live_gate_a.json"
REPORT = HERE / "LIVE_GATE_A_REPORT.md"
MAX_SOURCE = 4_000_000
MAX_DB = 120_000_000
SOURCES = {
    "cars_ui.py": {
        "_v167_voice_explicit_fields",
        "_v168_cas_write",
        "_v168_empty",
        "_v168_is_correction",
        "_v168_named_fields",
        "catch_message",
        "auto_catch",
        "apply_value",
        "set_field",
        "remember_price",
        "voice_change_plan",
    },
    "local_ocr.py": {"fields_from_text"},
    "ai_fast_schema.py": {
        "car_fields",
        "labeled_text_data",
        "fast_text_data",
        "clean_car",
    },
    "ai_filter.py": {"clean"},
    "db.py": {
        "Soedinenie",
        "_ua_lock3_connect",
        "connect",
        "get_card",
        "update_card_field",
        "log_action",
        "now",
    },
    "trace_zhurnal.py": {"_ua_connect", "_Obertka"},
}
PRICE_NEEDLES = (
    "price_uah",
    "price_history",
    "цена",
    "стоимость",
    "ціна",
    "вартість",
    "remember_price",
    "update_card_field",
    "audit",
)


def now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def remote_get(path: str, limit: int, *, optional: bool = False) -> bytes | None:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
    request = urllib.request.Request(
        API + urllib.parse.quote(path, safe="/"),
        method="GET",
        headers={
            "Authorization": "Token " + token,
            "User-Agent": "ua-art-task080-price-gate-a/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if optional and exc.code == 404:
            return None
        raise RuntimeError(
            "GET_HTTP_%d:%s" % (exc.code, pathlib.PurePosixPath(path).name)
        ) from exc
    if len(data) > limit:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + pathlib.PurePosixPath(path).name)
    return data


def redact(text: str) -> str:
    replacements = (
        (
            r"(?i)((?:token|api[_-]?key|secret|password)\s*=\s*)"
            r"(\"[^\"]*\"|'[^']*')",
            r'\1"<redacted>"',
        ),
        (r"(?i)(bearer\s+)[A-Za-z0-9._:-]{16,}", r"\1<redacted>"),
        (r"\b\d{7,12}:[A-Za-z0-9_-]{20,}\b", "<redacted-telegram-token>"),
        (r"\bsk-[A-Za-z0-9_-]{16,}\b", "<redacted-api-key>"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines(keepends=True)
    end = getattr(node, "end_lineno", node.lineno)
    return "".join(lines[node.lineno - 1 : end])


def analyse_source(name: str, payload: bytes) -> dict:
    source = payload.decode("utf-8")
    compile(source, name, "exec")
    tree = ast.parse(source, filename=name)
    definitions = []
    assignments = []
    wanted = SOURCES[name]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name not in wanted:
                continue
            value = segment(source, node)
            definitions.append(
                {
                    "kind": type(node).__name__,
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": node.end_lineno,
                    "sha256": sha(value.encode("utf-8")),
                    "source": redact(value)[:100_000],
                    "truncated": len(value) > 100_000,
                }
            )
        elif name == "ai_filter.py" and isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "ALLOWED" for target in targets):
                value = segment(source, node)
                assignments.append(
                    {
                        "name": "ALLOWED",
                        "line": node.lineno,
                        "end_line": node.end_lineno,
                        "sha256": sha(value.encode("utf-8")),
                        "source": redact(value)[:100_000],
                        "truncated": len(value) > 100_000,
                    }
                )
    snippets = []
    lines = source.splitlines()
    used = set()
    for index, line in enumerate(lines):
        if not any(needle.casefold() in line.casefold() for needle in PRICE_NEEDLES):
            continue
        start, end = max(0, index - 8), min(len(lines), index + 9)
        if any(abs(start - previous) < 5 for previous in used):
            continue
        used.add(start)
        snippets.append(
            {
                "line": index + 1,
                "source": redact("\n".join(lines[start:end]))[:20_000],
            }
        )
        if len(snippets) >= 24:
            break
    definitions.sort(key=lambda item: (item["line"], item["name"]))
    return {
        "sha256": sha(payload),
        "bytes": len(payload),
        "compiled": True,
        "definitions": definitions,
        "assignments": assignments,
        "price_snippets": snippets,
    }


def _snapshot_once(directory: pathlib.Path) -> dict:
    db_path = directory / "crm.db"
    db_path.write_bytes(remote_get(REMOTE_ROOT + "/crm.db", MAX_DB))
    for suffix in ("-wal", "-shm"):
        data = remote_get(REMOTE_ROOT + "/crm.db" + suffix, MAX_DB, optional=True)
        if data:
            (directory / ("crm.db" + suffix)).write_bytes(data)
    uri = "file:" + urllib.parse.quote(str(db_path), safe="/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        if quick != "ok":
            raise RuntimeError("LOCAL_COPY_QUICK_CHECK:" + str(quick))
        columns = [row["name"] for row in con.execute("PRAGMA table_info(cars)")]
        required = {"id", "auto_number", "price_uah"}
        if not required.issubset(columns):
            raise RuntimeError("PRICE_COLUMNS_MISSING:" + ",".join(sorted(required - set(columns))))
        history_expr = "price_history" if "price_history" in columns else "NULL"
        rows = con.execute(
            "SELECT id,auto_number,price_uah,typeof(price_uah) AS price_type,"
            "length(COALESCE(%s,'')) AS price_history_length "
            "FROM cars ORDER BY id" % history_expr
        ).fetchall()
        cards = []
        missing = non_positive = non_numeric = 0
        for row in rows:
            value = row["price_uah"]
            kind = row["price_type"]
            if value is None or str(value).strip() == "":
                missing += 1
            elif kind not in ("integer", "real"):
                try:
                    number = float(str(value).replace(" ", "").replace(",", "."))
                except ValueError:
                    non_numeric += 1
                else:
                    if number <= 0:
                        non_positive += 1
            elif float(value) <= 0:
                non_positive += 1
            cards.append(
                {
                    "id": row["id"],
                    "auto_number": row["auto_number"],
                    "price_uah": value,
                    "price_type": kind,
                    "price_history_length": row["price_history_length"],
                }
            )
        duplicates = [
            dict(row)
            for row in con.execute(
                "SELECT auto_number,count(*) AS count FROM cars "
                "GROUP BY auto_number HAVING count(*)>1 ORDER BY auto_number"
            )
        ]
        audit_columns = [
            dict(row) for row in con.execute("PRAGMA table_info(audit)").fetchall()
        ]
        if not audit_columns:
            raise RuntimeError("AUDIT_TABLE_MISSING")
        audit_indexes = [
            dict(row) for row in con.execute("PRAGMA index_list(audit)").fetchall()
        ]
        audit_create_row = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='audit'"
        ).fetchone()
        return {
            "sha256": sha(db_path.read_bytes()),
            "bytes": db_path.stat().st_size,
            "quick_check": quick,
            "cars_count": len(cards),
            "columns": columns,
            "audit_columns": audit_columns,
            "audit_indexes": audit_indexes,
            "audit_create_sql": audit_create_row["sql"] if audit_create_row else None,
            "audit_count": con.execute("SELECT count(*) FROM audit").fetchone()[0],
            "cards": cards,
            "duplicates": duplicates,
            "price_audit": {
                "missing_or_empty": missing,
                "non_positive": non_positive,
                "non_numeric": non_numeric,
            },
        }
    finally:
        con.close()


def database_snapshot() -> dict:
    last_error = None
    for attempt in range(1, 4):
        try:
            with tempfile.TemporaryDirectory(prefix="task080-price-gate-a-") as temp:
                return _snapshot_once(pathlib.Path(temp))
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2)
    raise RuntimeError("CRM_DB_LOCAL_COPY_FAILED:" + repr(last_error))


def definition_map(source_result: dict) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for item in source_result["definitions"]:
        found.setdefault(item["name"], []).append(item["source"])
    return found


def writer_findings(sources: dict) -> dict:
    cars = definition_map(sources["cars_ui.py"])
    db = definition_map(sources["db.py"])
    apply_value = "\n".join(cars.get("apply_value", []))
    catch_message = "\n".join(cars.get("catch_message", []))
    auto_catch = "\n".join(cars.get("auto_catch", []))
    remember = "\n".join(cars.get("remember_price", []))
    update = "\n".join(db.get("update_card_field", []))
    combined = "\n".join((apply_value, catch_message, auto_catch, remember, update))
    legacy = (
        "remember_price(" in combined
        and ("set_field(" in apply_value or "update_card_field(" in combined)
    )
    # Fail closed: source text containing all logical terms is evidence of a
    # candidate only, not proof that they share one transaction/commit.
    atomic_terms_present = all(
        term in combined for term in ("price_uah", "price_history", "audit")
    )
    return {
        "legacy_separate_remember_price_path_present": legacy,
        "atomic_terms_present_in_relevant_sources": atomic_terms_present,
        "active_atomic_price_writer_verified": False,
        "reason": (
            "LEGACY_MULTI_STEP_PRICE_PATH_PRESENT"
            if legacy
            else "ATOMICITY_NOT_PROVEN_BY_GET_ONLY_STATIC_SOURCE"
        ),
    }


def atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    result = {
        "task_id": "task_080",
        "contract_id": "CRM-PRICE-RECOGNITION-006-v1.0",
        "status": "FAIL",
        "mode": "LIVE_GET_ONLY",
        "http_methods": ["GET"],
        "production_touched": False,
        "crm_write": False,
        "site_write": False,
        "process_restart": False,
        "started_at_utc": now(),
        "sources": {},
        "errors": [],
    }
    try:
        blobs = {
            name: remote_get(REMOTE_ROOT + "/" + name, MAX_SOURCE)
            for name in SOURCES
        }
        result["sources"] = {
            name: analyse_source(name, blobs[name]) for name in SOURCES
        }
        for name, wanted in SOURCES.items():
            actual = {
                item["name"] for item in result["sources"][name]["definitions"]
            }
            missing = wanted - actual
            if missing:
                raise RuntimeError(
                    "REQUIRED_DEFINITION_MISSING:%s:%s"
                    % (name, ",".join(sorted(missing)))
                )
        if not result["sources"]["ai_filter.py"]["assignments"]:
            raise RuntimeError("AI_FILTER_ALLOWED_ASSIGNMENT_MISSING")
        result["database"] = database_snapshot()
        result["writer"] = writer_findings(result["sources"])
        result["release_blocker"] = (
            None
            if result["writer"]["active_atomic_price_writer_verified"]
            else result["writer"]["reason"]
        )
        result["status"] = "PASS_LIVE_GET_AUDIT"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    result["finished_at_utc"] = now()
    atomic_write(
        EVIDENCE,
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    report = [
        "# CRM-PRICE-RECOGNITION-006 — live Gate A",
        "",
        "STATUS: **%s**" % result["status"],
        "",
        "- Remote HTTP methods: **GET only**",
        "- Production / CRM / site writes: **NO**",
        "- Process restart: **NO**",
    ]
    if result["status"] == "PASS_LIVE_GET_AUDIT":
        report.extend(
            [
                "- Live source hashes/functions: **CAPTURED**",
                "- Local CRM snapshot quick_check: **%s**"
                % result["database"]["quick_check"],
                "- Current cards audited: **%d**" % result["database"]["cars_count"],
                "- Duplicate auto_number values: **%d**"
                % len(result["database"]["duplicates"]),
                "- Missing/empty sale prices: **%d**"
                % result["database"]["price_audit"]["missing_or_empty"],
                "- Atomic active price writer verified: **%s**"
                % (
                    "YES"
                    if result["writer"]["active_atomic_price_writer_verified"]
                    else "NO"
                ),
                "- Release blocker: **%s**" % (result["release_blocker"] or "NONE"),
            ]
        )
    else:
        report.append("- Errors: `%s`" % "; ".join(result["errors"]))
    atomic_write(REPORT, "\n".join(report) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "errors": result["errors"],
                "production_touched": False,
                "release_blocker": result.get("release_blocker"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["status"] == "PASS_LIVE_GET_AUDIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
