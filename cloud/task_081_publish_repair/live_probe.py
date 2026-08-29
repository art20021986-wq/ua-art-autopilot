#!/usr/bin/env python3
"""GET-only live audit probe for TASK 081 (UA-0013-PUBLISH-REPAIR-001).

This script performs ONLY HTTP GET requests against the PythonAnywhere API and
public site. It never writes to production, never restarts anything, and never
posts/patches/deletes anything.

Required environment variables (read from CI secrets, never hardcoded):
  PYANYWHERE_API_TOKEN   - PythonAnywhere API token
  PYANYWHERE_USERNAME    - PythonAnywhere account/username
  PYANYWHERE_HOST        - optional, default 'www.pythonanywhere.com'
  UA_SITE_BASE_URL       - optional, default 'https://<username>.pythonanywhere.com'

Outputs a sanitized JSON+Markdown report under ./evidence/ (relative to CWD).
No secrets, no raw DB blobs, no base64 payloads are ever written to the report.
"""
import ast
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

FILES_TO_FETCH = [
    "cars_ui.py",
    "publikaciya.py",
    "stranica.py",
    "master_card.py",
    "yadro.py",
    "cars_schema.py",
    "db.py",
]

CATALOG_PATHS = [
    "/video/katalog.html",
    "/site/katalog.html",
]

FUNCTIONS_OF_INTEREST = {
    "cars_ui.py": ["toggle_publish"],
    "publikaciya.py": ["opublikovat", "sobrat_kartochku"],
    "stranica.py": ["_ua_seo068_normalize", "sobrat_kartochku"],
    "master_card.py": ["sobrat_kartochku"],
}

UA_ID = "UA-0013"
UA_RE = re.compile(r"UA-[0-9]{4,}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(
            f"BLOCKED: required environment variable {name} is not set. "
            "No live GET audit can be performed without it. No production access "
            "was attempted."
        )
    return val


def pa_get_file(session, host, username, token, path):
    """GET a file's content via the PythonAnywhere Files API (read-only)."""
    url = f"https://{host}/api/v0/user/{username}/files/path{path}"
    resp = session.get(url, headers={"Authorization": f"Token {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.content


def extract_ast_functions(source: str, names):
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            seg = ast.get_source_segment(source, node)
            if seg is None:
                continue
            found[node.name] = {
                "sha256": sha256_bytes(seg.encode("utf-8")),
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", None),
                "length_chars": len(seg),
            }
    return found


def extract_ua0013_row(db_path: Path):
    """Return sanitized field:value dict for auto_number='UA-0013'. No blobs."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    table = None
    for t in tables:
        try:
            cur.execute(f"PRAGMA table_info({t})")
            cols = [c[1] for c in cur.fetchall()]
        except sqlite3.Error:
            continue
        if "auto_number" in cols:
            table = t
            break
    if not table:
        conn.close()
        return {"error": "no table with auto_number column found", "tables_seen": tables}
    cur.execute(f"SELECT * FROM {table} WHERE auto_number = ?", (UA_ID,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return {"error": f"no row for {UA_ID}", "table": table}
    if len(rows) > 1:
        return {"error": f"more than one row for {UA_ID}", "count": len(rows), "table": table}
    row = rows[0]
    out = {}
    for k in row.keys():
        v = row[k]
        if isinstance(v, bytes):
            out[k] = f"<binary:{len(v)}bytes:redacted>"
        else:
            out[k] = v
    out["_table"] = table
    return out


def count_occurrences(html: str, ua_id: str) -> int:
    return len(re.findall(re.escape(ua_id), html))


def main():
    evidence_dir = Path("cloud/task_081_publish_repair/evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    if requests is None:
        raise SystemExit("BLOCKED: 'requests' package is not installed. No GET performed.")

    token = require_env("PYANYWHERE_API_TOKEN")
    username = require_env("PYANYWHERE_USERNAME")
    host = os.environ.get("PYANYWHERE_HOST", "www.pythonanywhere.com")
    site_base = os.environ.get("UA_SITE_BASE_URL", f"https://{username}.pythonanywhere.com")

    session = requests.Session()
    report = {"files": {}, "functions": {}, "catalogs": {}, "db_row": None, "errors": []}

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for fname in FILES_TO_FETCH:
            try:
                content = pa_get_file(session, host, username, token, f"/{fname}")
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"fetch {fname} failed: {exc}")
                continue
            local = tmpdir / fname
            local.write_bytes(content)
            report["files"][fname] = {"sha256": sha256_bytes(content), "bytes": len(content)}
            names = FUNCTIONS_OF_INTEREST.get(fname, [])
            if names:
                try:
                    report["functions"][fname] = extract_ast_functions(
                        content.decode("utf-8", errors="replace"), names
                    )
                except SyntaxError as exc:
                    report["errors"].append(f"AST parse failed for {fname}: {exc}")

        try:
            db_content = pa_get_file(session, host, username, token, "/crm.db")
            db_path = tmpdir / "crm.db"
            db_path.write_bytes(db_content)
            report["db_row"] = extract_ua0013_row(db_path)
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"fetch/read crm.db failed: {exc}")

    for cat_path in CATALOG_PATHS:
        try:
            resp = session.get(site_base + cat_path, timeout=30)
            html = resp.text
            report["catalogs"][cat_path] = {
                "http_status": resp.status_code,
                "ua0013_occurrences": count_occurrences(html, UA_ID),
                "bytes": len(html),
            }
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"GET {cat_path} failed: {exc}")

    for path in [f"/video/{UA_ID}.html", f"/video/{UA_ID}-diag.html", f"/site/{UA_ID}.html", f"/site/{UA_ID}-diag.html"]:
        try:
            resp = session.get(site_base + path, timeout=30)
            report.setdefault("pages", {})[path] = {"http_status": resp.status_code, "bytes": len(resp.text)}
        except Exception as exc:  # noqa: BLE001
            report.setdefault("pages", {})[path] = {"error": str(exc)}

    report["production_touched"] = False
    report["note"] = "GET-only probe. No writes, no restarts were performed."

    out_json = evidence_dir / "live_audit_report.json"
    out_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    out_md = evidence_dir / "live_audit_report.md"
    lines = ["# Live GET-only audit report (TASK 081)", "", f"Errors: {len(report['errors'])}"]
    for e in report["errors"]:
        lines.append(f"- {e}")
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"status": "probe_complete", "errors": report["errors"]}))


if __name__ == "__main__":
    main()
