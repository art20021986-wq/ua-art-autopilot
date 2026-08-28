#!/usr/bin/env python3
"""Read-only live audit for CRM-CONTAINER-KYIV-DAYS-001."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request


API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
ROOT = "/home/Carix"
REMOTE = {
    "cars_ui.py": ROOT + "/cars_ui.py",
    "konteyner.py": ROOT + "/konteyner.py",
    "db.py": ROOT + "/db.py",
}
CRM_PATH = ROOT + "/crm.db"
OUT = pathlib.Path("cloud/task_069/evidence/current.json")
MAX_FILE = 3_000_000
MAX_DB = 128_000_000
TERMS = (
    "container", "konteyner", "контейн", "sea_container", "cont_",
    "eta_days", "eta_manual", "days_to_kyiv", "дней до", "дни до",
    "киев", "київ", "car_wait", "register",
)
WANTED = {
    "cars_ui.py": {
        "drop_wait", "set_field", "edit_ask", "apply_value", "stage_menu",
        "catch_message", "register", "eta_of",
    },
    "db.py": {"connect", "update_card_field", "now"},
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(text: str) -> str:
    text = re.sub(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b", "<redacted-token>", text)
    text = re.sub(
        r"(?i)((?:token|api[_-]?key|password)\s*=\s*)['\"][^'\"]{12,}['\"]",
        r"\1'<redacted-secret>'",
        text,
    )
    return text


def read_remote(path: str) -> bytes:
    request = urllib.request.Request(
        API + "files/path" + urllib.parse.quote(path, safe="/"),
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task069-container-readonly/1",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        limit = MAX_DB if path == CRM_PATH else MAX_FILE
        data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + pathlib.PurePosixPath(path).name)
    return data


def segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def inspect_python(name: str, path: str) -> dict:
    data = read_remote(path)
    source = data.decode("utf-8")
    tree = ast.parse(source, path)
    definitions = []
    inventory = []
    assignments = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = segment(source, node)
            relevant = name == "konteyner.py" or node.name in WANTED.get(name, set())
            relevant = relevant or any(term in body.casefold() for term in TERMS)
            inventory.append({
                "name": node.name,
                "kind": type(node).__name__,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "sha256": sha256(body.encode()),
                "relevant": relevant,
            })
            if relevant:
                definitions.append({
                    "name": node.name,
                    "kind": type(node).__name__,
                    "line": node.lineno,
                    "end_line": node.end_lineno,
                    "sha256": sha256(body.encode()),
                    "source": redact(body[:160_000]),
                })
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            body = segment(source, node)
            if any(term in body.casefold() for term in TERMS):
                assignments.append({"line": node.lineno, "source": redact(body[:40_000])})

    buttons = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else ""
        )
        if called not in {"InlineKeyboardButton", "KeyboardButton"}:
            continue
        rendered = ast.get_source_segment(source, node) or ""
        if any(term in rendered.casefold() for term in TERMS):
            buttons.append({"line": node.lineno, "source": redact(rendered)})

    return {
        "path": path,
        "size": len(data),
        "sha256": sha256(data),
        "definitions": definitions,
        "definition_inventory": inventory,
        "assignments": assignments,
        "buttons": buttons,
    }


def inspect_db() -> dict:
    data = read_remote(CRM_PATH)
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
        connection = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(cars)")]
            safe = [
                field for field in (
                    "id", "auto_number", "code", "status", "sea_container",
                    "sea_date_out", "eta_manual", "eta_days", "days_to_kyiv",
                ) if field in columns
            ]
            identity = "auto_number" if "auto_number" in columns else (
                "code" if "code" in columns else None
            )
            target = None
            container_owners = []
            if identity:
                row = connection.execute(
                    "SELECT %s FROM cars WHERE %s=?" % (",".join(safe), identity),
                    ("UA-0011",),
                ).fetchone()
                target = dict(row) if row else None
                if "sea_container" in columns:
                    container_owners = [dict(row) for row in connection.execute(
                        "SELECT id,%s,sea_container FROM cars "
                        "WHERE UPPER(TRIM(COALESCE(sea_container,'')))=? ORDER BY id" % identity,
                        ("ONEYSELGF1046602",),
                    )]
            card_ids = []
            if identity:
                card_ids = [str(row[0]) for row in connection.execute(
                    "SELECT %s FROM cars WHERE %s GLOB 'UA-[0-9][0-9][0-9][0-9]' ORDER BY %s"
                    % (identity, identity, identity)
                )]
        finally:
            connection.close()
    finally:
        path.unlink(missing_ok=True)
    return {
        "sha256": sha256(data),
        "size": len(data),
        "quick_check": quick,
        "columns": columns,
        "ua_0011": target,
        "target_container_owners": container_owners,
        "card_ids": card_ids,
    }


def main() -> None:
    evidence = {
        "task_id": "CRM-CONTAINER-KYIV-DAYS-001-V1.0",
        "mode": "READ_ONLY_LIVE_AUDIT",
        "production_touched": False,
        "crm_db_write": False,
        "files": {},
        "db": {},
        "errors": [],
    }
    for name, path in REMOTE.items():
        evidence["files"][name] = inspect_python(name, path)
    evidence["db"] = inspect_db()
    if evidence["db"]["quick_check"] != "ok":
        evidence["errors"].append("sqlite_quick_check_failed")
    if not evidence["files"]["konteyner.py"]["definitions"]:
        evidence["errors"].append("container_handlers_not_found")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("TASK069_READ_ONLY_PASS errors=%d" % len(evidence["errors"]))


if __name__ == "__main__":
    main()
