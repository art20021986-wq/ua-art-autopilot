#!/usr/bin/env python3
"""TASK 081 fresh, secret-backed, GET-only production audit.

The script deliberately implements no remote write operation.  It downloads
the bounded live source set and crm.db through the PythonAnywhere Files API,
records exact source/function hashes, extracts one sanitized UA-0013 row, and
checks the public catalogs/pages.  Downloaded source copies are kept only in
the workflow artifact for exact patch construction; they are never installed.
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
import sys
import urllib.error
import urllib.parse
import urllib.request


TASK_ID = "UA-0013-PUBLISH-REPAIR-001"
USERNAME = "Carix"
REMOTE_ROOT = "/home/Carix"
API_BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
PUBLIC_ORIGIN = "https://www.uaart.com.ua"
HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE_DIR = HERE / "evidence" / "live_audit_v2"
SOURCE_DIR = EVIDENCE_DIR / "sources"

FILES = (
    "cars_ui.py",
    "publikaciya.py",
    "stranica.py",
    "master_card.py",
    "yadro.py",
    "cars_schema.py",
    "db.py",
)

FUNCTIONS = {
    "cars_ui.py": ("toggle_publish",),
    "publikaciya.py": ("opublikovat", "_otkat", "_master", "sobrat_kartochku"),
    "stranica.py": ("_ua_seo068_normalize", "sobrat_kartochku"),
    "master_card.py": ("_ua_seo068_normalize", "sobrat_kartochku"),
    "yadro.py": ("_ua_seo068_normalize", "sobrat_kartochku"),
    "cars_schema.py": ("status_label", "stage_of", "category_of"),
}

PUBLIC_PATHS = (
    "/video/katalog.html",
    "/katalog.html",
    "/video/UA-0011.html",
    "/video/UA-0011-diag.html",
    "/video/UA-0012.html",
    "/video/UA-0012-diag.html",
    "/video/UA-0013.html",
    "/UA-0013.html",
    "/video/UA-0013-diag.html",
    "/UA-0013-diag.html",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class ReadOnlyAPI:
    """PythonAnywhere transport with GET as the sole remote method."""

    def __init__(self, token: str):
        if not token:
            raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
        self.token = token
        self.methods: list[str] = []

    def get(self, url: str, *, authenticated: bool = False, limit: int = 12_000_000):
        headers = {"User-Agent": "ua-art-task081-live-audit-v2/1"}
        if authenticated:
            headers["Authorization"] = "Token " + self.token
        request = urllib.request.Request(url, headers=headers, method="GET")
        self.methods.append("GET")
        try:
            with urllib.request.urlopen(request, timeout=50) as response:
                data = response.read(limit + 1)
                status = int(response.status)
                final_url = response.geturl()
        except urllib.error.HTTPError as exc:
            data = exc.read(limit + 1)
            status = int(exc.code)
            final_url = exc.geturl()
        if len(data) > limit:
            raise RuntimeError("GET_TOO_LARGE:%s" % url)
        return status, data, final_url

    def live_file(self, name: str) -> bytes:
        remote_path = REMOTE_ROOT + "/" + name
        url = API_BASE + "files/path" + urllib.parse.quote(remote_path, safe="/")
        status, data, _ = self.get(url, authenticated=True)
        if status != 200:
            raise RuntimeError("LIVE_FILE_HTTP_%d:%s" % (status, name))
        return data


def function_records(source: str, wanted: tuple[str, ...]) -> list[dict]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    records = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in wanted or node.end_lineno is None:
            continue
        raw = "".join(lines[node.lineno - 1 : node.end_lineno])
        records.append(
            {
                "name": node.name,
                "kind": type(node).__name__,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "sha256": sha256_bytes(raw.encode("utf-8")),
                "sha256_rstrip": sha256_bytes(raw.rstrip("\r\n").encode("utf-8")),
                "source": raw,
            }
        )
    return records


def sanitized_ua0013(db_path: pathlib.Path) -> dict:
    conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM cars WHERE auto_number=? ORDER BY id", ("UA-0013",)
        ).fetchall()
        published_rows = conn.execute(
            "SELECT auto_number, status, published FROM cars "
            "WHERE published=1 ORDER BY auto_number"
        ).fetchall()
        columns = {row[1] for row in conn.execute("PRAGMA table_info(cars)")}
    finally:
        conn.close()
    if len(rows) != 1:
        return {
            "quick_check": quick,
            "row_count": len(rows),
            "published_rows": [dict(item) for item in published_rows],
            "error": "UA0013_NOT_UNIQUE",
        }
    row = rows[0]
    safe_fields = (
        "id",
        "auto_number",
        "brand",
        "model",
        "year",
        "status",
        "stage",
        "published",
        "publish_pending",
        "review_status",
        "sea_container",
        "sea_date_out",
        "eta_manual",
        "days_to_kyiv",
    )
    safe = {name: row[name] for name in safe_fields if name in columns}
    for name in ("photos", "videos", "condition_photos", "condition_videos"):
        if name in columns:
            value = row[name]
            if value is None:
                size = 0
            elif isinstance(value, bytes):
                size = len(value)
            else:
                size = len(str(value).encode("utf-8"))
            safe[name + "_bytes"] = size
    return {
        "quick_check": quick,
        "row_count": 1,
        "row": safe,
        "published_rows": [dict(item) for item in published_rows],
    }


def expected_stage(row: dict) -> dict:
    status = str(row.get("status") or "").strip()
    mapping = {
        "sea_loaded": {"owner_label": "На пароме", "catalog_category": "more"},
        "sea_transit": {"owner_label": "На пароме", "catalog_category": "more"},
        "kr_bought": {"owner_label": "В Корее", "catalog_category": "korea"},
        "ge_waiting": {"owner_label": "В Грузии", "catalog_category": "georgia"},
        "ua_arrived": {"owner_label": "В Киеве", "catalog_category": "kyiv"},
    }
    value = mapping.get(status)
    if value is None:
        return {"status": status, "error": "UNAPPROVED_STATUS_MAPPING"}
    return {"status": status, **value}


def public_record(api: ReadOnlyAPI, path: str) -> dict:
    status, body, final_url = api.get(PUBLIC_ORIGIN + path, authenticated=False, limit=5_000_000)
    text = body.decode("utf-8", "replace")
    href_ids = re.findall(
        r"href=[\"'](?:[^\"']*/)?(UA-[0-9]{4,})\.html(?:[?#][^\"']*)?[\"']",
        text,
        re.I,
    )
    href_counts = {}
    for identifier in href_ids:
        identifier = identifier.upper()
        href_counts[identifier] = href_counts.get(identifier, 0) + 1
    identity_match = re.search(r"(UA-[0-9]{4,})\.html$", path, re.I)
    expected_identity = identity_match.group(1).upper() if identity_match else None
    return {
        "status": status,
        "final_url": final_url,
        "bytes": len(body),
        "ua0013_text_count": text.upper().count("UA-0013"),
        "ua0013_href_count": len(
            re.findall(r"href=[\"'][^\"']*UA-0013\.html(?:[?#][^\"']*)?[\"']", text, re.I)
        ),
        "diag_href_count": len(
            re.findall(r"href=[\"'][^\"']*UA-0013-diag\.html(?:[?#][^\"']*)?[\"']", text, re.I)
        ),
        "contains_sea_loaded": "sea_loaded" in text,
        "contains_more_category": bool(re.search(r"(?:data-category|category)[^>]{0,80}more", text, re.I)),
        "ua_href_counts": href_counts,
        "expected_identity": expected_identity,
        "exact_identity": bool(expected_identity)
        and expected_identity in text.upper()
        and final_url.rstrip("/").endswith("/%s.html" % expected_identity),
    }


def main() -> int:
    report = {
        "task_id": TASK_ID,
        "mode": "FRESH_LIVE_GET_ONLY",
        "started_at_utc": utc_now(),
        "production_touched": False,
        "crm_write": False,
        "site_write": False,
        "process_restart": False,
        "files": {},
        "functions": {},
        "database": {},
        "derived_stage": {},
        "public": {},
        "publication_gap": {},
        "defects": {},
        "errors": [],
    }
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
    api = ReadOnlyAPI(token)

    try:
        for name in FILES:
            data = api.live_file(name)
            (SOURCE_DIR / name).write_bytes(data)
            source = data.decode("utf-8")
            compile(source, name, "exec")
            report["files"][name] = {"bytes": len(data), "sha256": sha256_bytes(data)}
            if name in FUNCTIONS:
                report["functions"][name] = function_records(source, FUNCTIONS[name])

        db_bytes = api.live_file("crm.db")
        db_path = EVIDENCE_DIR / "crm_snapshot.db"
        db_path.write_bytes(db_bytes)
        report["database"] = sanitized_ua0013(db_path)
        db_path.unlink(missing_ok=True)
        row = report["database"].get("row") or {}
        report["derived_stage"] = expected_stage(row)

        for path in PUBLIC_PATHS:
            report["public"][path] = public_record(api, path)

        catalog_counts = report["public"]["/video/katalog.html"].get("ua_href_counts") or {}
        published_rows = report["database"].get("published_rows") or []
        published_numbers = [
            str(item.get("auto_number") or "").upper()
            for item in published_rows
            if re.fullmatch(r"UA-[0-9]{4,}", str(item.get("auto_number") or "").upper())
        ]
        report["publication_gap"] = {
            "published_numbers": published_numbers,
            "catalog_href_counts": catalog_counts,
            "missing_published_numbers": [
                number for number in published_numbers if catalog_counts.get(number, 0) == 0
            ],
            "duplicate_href_numbers": [
                number for number in published_numbers if catalog_counts.get(number, 0) > 1
            ],
            "published_count": len(published_numbers),
            "catalog_unique_count": len(catalog_counts),
        }

        toggle = next(
            (r["source"] for r in report["functions"].get("cars_ui.py", []) if r["name"] == "toggle_publish"),
            "",
        )
        seo_sources = [
            r["source"]
            for name in ("stranica.py", "master_card.py", "yadro.py")
            for r in report["functions"].get(name, [])
            if r["name"] == "_ua_seo068_normalize"
        ]
        report["defects"] = {
            "toggle_ignores_publisher_result": "_ok_rem2" in toggle and "if _ok_rem2" not in toggle,
            "toggle_unconditional_success": "Машина видна клиентам в каталоге." in toggle,
            "seo_live_diag_precheck_modules": sum(
                "SEO068_DIAGNOSTIC_TARGET_MISSING" in source for source in seo_sources
            ),
            "seo_module_count": len(seo_sources),
        }

        if report["database"].get("quick_check") != "ok":
            report["errors"].append("CRM_QUICK_CHECK_FAILED")
        if report["database"].get("row_count") != 1:
            report["errors"].append("UA0013_ROW_NOT_UNIQUE")
        if report["derived_stage"].get("status") != "sea_loaded":
            report["errors"].append("UA0013_STAGE_NOT_SEA_LOADED")
        if "UA-0013" not in report["publication_gap"].get("missing_published_numbers", []):
            report["errors"].append("UA0013_PUBLICATION_GAP_NOT_REPRODUCED")
        if not report["defects"].get("toggle_ignores_publisher_result"):
            report["errors"].append("FALSE_SUCCESS_DEFECT_NOT_REPRODUCED")
        if report["defects"].get("seo_live_diag_precheck_modules") != 3:
            report["errors"].append("SEO068_DEFECT_NOT_IN_ALL_THREE_MODULES")
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(type(exc).__name__ + ":" + str(exc))

    report["http_methods"] = sorted(set(api.methods))
    report["finished_at_utc"] = utc_now()
    report["status"] = (
        "PASS_AUDIT_DEFECT_REPRODUCED" if not report["errors"] else "BLOCKED"
    )
    (EVIDENCE_DIR / "live_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS_AUDIT_DEFECT_REPRODUCED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
