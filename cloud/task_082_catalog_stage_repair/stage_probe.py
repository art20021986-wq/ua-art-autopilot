#!/usr/bin/env python3
"""GET-only live stage regression probe for UA-0011."""
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
import urllib.error
import urllib.parse
import urllib.request


HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/stage_probe.json"
API = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
ROOT = "/home/Carix"
MAX = 80_000_000
FILES = (
    "start_safe.py", "cars_ui.py", "db.py", "publikaciya.py", "stranica.py",
    "master_card.py", "team_bot.py", "cars_schema.py", "bot.py",
)


def get(path: str, missing: bool = False, limit: int = MAX):
    req = urllib.request.Request(
        API + urllib.parse.quote(path, safe="/"), method="GET",
        headers={"Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
                 "User-Agent": "ua-art-task082-stage-probe/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=70) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if missing and exc.code == 404:
            return None
        raise
    if len(data) > limit:
        raise RuntimeError("TOO_LARGE:" + path)
    return data


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def row_from(db: bytes, wal: bytes | None):
    with tempfile.TemporaryDirectory(prefix="task082-probe-") as directory:
        path = pathlib.Path(directory) / "crm.db"
        path.write_bytes(db)
        if wal:
            pathlib.Path(str(path) + "-wal").write_bytes(wal)
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA query_only=ON")
            quick = con.execute("PRAGMA quick_check").fetchone()[0]
            row = con.execute("SELECT * FROM cars WHERE auto_number='UA-0011'").fetchone()
        finally:
            con.close()
    if quick != "ok" or row is None:
        raise RuntimeError("UA0011_ROW_MISSING_OR_DB_BAD")
    raw = dict(row)
    keep = {}
    for key, value in raw.items():
        if key in ("id", "auto_number", "published", "brand", "model", "year", "vin") or re.search(
            r"status|stage|container|days|eta|date|sea_|ge_|kyiv|kiev|publish", key, re.I
        ):
            keep[key] = value
    return keep


def source_evidence(name: str, data: bytes):
    text = data.decode("utf-8", "replace")
    result = {"sha256": sha(data), "bytes": len(data), "definitions": [], "snippets": []}
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        result["parse_error"] = str(exc)
        return result
    lines = text.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        source = "\n".join(lines[node.lineno - 1:end])
        folded = source.casefold()
        if ("status" in folded and any(token in folded for token in (
            "sea_loaded", "korea", "update", "execute", "container", "stage"
        ))) or "days_to_kyiv" in folded:
            result["definitions"].append({
                "name": node.name, "lineno": node.lineno, "end_lineno": end,
                "sha256": sha(source.encode()), "source": source[:12000],
            })
    pattern = re.compile(r"sea_loaded|UPDATE\s+cars\s+SET\s+status|update_card_field|days_to_kyiv|eta_manual", re.I)
    for index, line in enumerate(lines):
        if pattern.search(line):
            start, end = max(index - 3, 0), min(index + 4, len(lines))
            result["snippets"].append({
                "lineno": index + 1, "source": "\n".join(lines[start:end])[:4000],
            })
    return result


def main() -> int:
    evidence = {
        "task_id": "task_082", "mode": "GET_ONLY_STAGE_REGRESSION_PROBE",
        "status": "FAIL", "production_touched": False,
        "pythonanywhere_methods": ["GET"], "errors": [],
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    try:
        db = get(ROOT + "/crm.db")
        wal = get(ROOT + "/crm.db-wal", missing=True)
        evidence["database"] = {
            "sha256": sha(db), "wal_sha256": sha(wal) if wal else None,
            "ua0011": row_from(db, wal),
        }
        evidence["files"] = {}
        for name in FILES:
            data = get(ROOT + "/" + name, missing=True, limit=8_000_000)
            if data is not None:
                evidence["files"][name] = source_evidence(name, data)
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    evidence["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    row = (evidence.get("database") or {}).get("ua0011") or {}
    print(json.dumps({"status": evidence["status"], "ua0011": row,
                      "errors": evidence["errors"]}, ensure_ascii=False))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

