#!/usr/bin/env python3
"""TASK099: fresh GET-only audit of the 16-card CRM and public site."""
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

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "cloud/task_099_site_crm_repair/evidence"
SUMMARY = OUT / "live_audit.json"
BUNDLE = OUT / "source_bundle.json"
REMOTE_ROOT = "/home/Carix"
API_BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
PUBLIC = "https://www.uaart.com.ua"
IDS = tuple(f"UA-{number:04d}" for number in range(1, 17))
FILES = (
    "cars_ui.py", "db.py", "cars_schema.py", "publikaciya.py", "master_card.py",
    "stranica.py", "yadro.py", "team_bot.py", "card_render.py", "konteyner.py",
)
FUNCTION_NAME = re.compile(
    r"(?:card|car|kartoch|sobrat|html|menu|publish|spec|render|build|open|toggle|field|schema|status|stage|diag|diagnost|container|cta|opis|otpravit|additional|accordion)",
    re.I,
)
MAX_BYTES = 15_000_000


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ReadOnly:
    def __init__(self) -> None:
        token = (os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
        self.headers = {"Authorization": "Token " + token, "User-Agent": "ua-art-task099-audit/1"}
        self.methods: list[str] = []

    def get(self, url: str, authenticated: bool, limit: int = MAX_BYTES) -> tuple[int, bytes, str]:
        headers = self.headers if authenticated else {"User-Agent": "ua-art-task099-public-audit/1"}
        request = urllib.request.Request(url, headers=headers, method="GET")
        self.methods.append("GET")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read(limit + 1)
                status = int(response.status)
                final_url = response.geturl()
        except urllib.error.HTTPError as exc:
            body = exc.read(limit + 1)
            status = int(exc.code)
            final_url = exc.geturl()
        if len(body) > limit:
            raise RuntimeError("GET_TOO_LARGE")
        return status, body, final_url

    def file(self, name: str) -> bytes:
        if "/" in name or name not in FILES + ("crm.db",):
            raise RuntimeError("FILE_OUTSIDE_ALLOWLIST")
        url = API_BASE + "files/path" + urllib.parse.quote(REMOTE_ROOT + "/" + name, safe="/")
        status, body, _ = self.get(url, True)
        if status != 200:
            raise RuntimeError(f"LIVE_FILE_HTTP_{status}:{name}")
        return body


def redact(source: str) -> str:
    source = re.sub(r"bot\d+:[A-Za-z0-9_-]{20,}", "bot<TOKEN>", source)
    source = re.sub(r"(?i)(api[_-]?key|token|secret|password)(\s*[=:]\s*)['\"][^'\"]+['\"]", r"\1\2'<REDACTED>'", source)
    return source


def source_facts(name: str, data: bytes) -> tuple[dict, dict]:
    source = data.decode("utf-8")
    compile(source, name, "exec")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    inventory = []
    selected = []
    selected_bytes = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.end_lineno is None:
            continue
        block = "".join(lines[node.lineno - 1:node.end_lineno])
        record = {
            "name": node.name,
            "kind": type(node).__name__,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "sha256": sha(block.encode("utf-8")),
        }
        inventory.append(record)
        if FUNCTION_NAME.search(node.name) and selected_bytes < 180_000:
            safe = redact(block)
            selected.append({**record, "source": safe})
            selected_bytes += len(safe.encode("utf-8"))
    summary = {
        "bytes": len(data), "sha256": sha(data), "compiled": True,
        "function_count": len(inventory), "functions": inventory,
        "markers": {
            "additional_specification": source.count("additional_specification"),
            "Дополнительная спецификация": source.count("Дополнительная спецификация"),
            "complex_diagnostics": source.count("Комплексная диагностика"),
            "sea_transit": source.count("sea_transit"),
            "sea_loaded": source.count("sea_loaded"),
        },
    }
    return summary, {"path": name, "selected_functions": selected}


def text_meta(value: object) -> dict:
    raw = "" if value is None else str(value)
    return {"present": bool(raw.strip()), "bytes": len(raw.encode("utf-8")), "sha256": sha(raw.encode("utf-8"))}


def database_facts(data: bytes) -> dict:
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
        conn = sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        tables = [str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        schemas = {}
        for table in tables:
            if table == "cars" or "additional_spec" in table or "enrichment" in table or "primary_field" in table:
                schemas[table] = [str(row[1]) for row in conn.execute('PRAGMA table_info("' + table.replace('"', '""') + '")')]
        columns = set(schemas.get("cars") or [])
        rows = conn.execute("SELECT * FROM cars ORDER BY auto_number").fetchall()
        safe_fields = (
            "id", "auto_number", "brand", "model", "year", "engine_cc", "fuel", "gearbox", "drive",
            "mileage_km", "status", "stage", "published", "publish_pending", "review_status",
            "sea_date_out", "eta_manual", "days_to_kyiv",
        )
        cards = []
        for row in rows:
            item = {key: row[key] for key in safe_fields if key in columns}
            vin = re.sub(r"[^A-Za-z0-9]", "", str(row["vin"] or "").upper()) if "vin" in columns else ""
            item["vin_hint"] = {"length": len(vin), "wmi": vin[:3], "last4": vin[-4:]} if vin else None
            for key in ("photos", "videos", "condition_photos", "condition_videos", "description", "diag_text", "diag_report"):
                if key in columns:
                    item[key] = text_meta(row[key])
            cards.append(item)
        extra_counts = {}
        for table in schemas:
            if table != "cars":
                extra_counts[table] = int(conn.execute('SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0])
        conn.close()
    finally:
        path.unlink(missing_ok=True)
    identifiers = [str(item.get("auto_number") or "") for item in cards]
    published = [str(item.get("auto_number")) for item in cards if int(item.get("published") or 0) == 1]
    safe_hash = sha(json.dumps(cards, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return {
        "quick_check": quick, "query_only": True, "connection_total_changes": 0,
        "row_count": len(cards), "ids": identifiers, "published_ids": published,
        "schemas": schemas, "additional_table_counts": extra_counts, "cards": cards,
        "safe_projection_sha256": safe_hash, "database_bytes": len(data), "database_sha256": sha(data),
    }


def public_record(api: ReadOnly, path: str) -> dict:
    status, body, final_url = api.get(PUBLIC + path, False, 6_000_000)
    text = body.decode("utf-8", "replace")
    hrefs = re.findall(r"href=['\"](?:[^'\"]*/)?(UA-[0-9]{4,})\.html(?:[?#][^'\"]*)?['\"]", text, re.I)
    counts: dict[str, int] = {}
    for identifier in hrefs:
        identifier = identifier.upper()
        counts[identifier] = counts.get(identifier, 0) + 1
    identity = re.search(r"/(UA-[0-9]{4,})(?:-diag)?\.html$", path, re.I)
    expected = identity.group(1).upper() if identity else None
    return {
        "status": status, "bytes": len(body), "sha256": sha(body), "final_url": final_url,
        "redirected": final_url.rstrip("/") != (PUBLIC + path).rstrip("/"),
        "expected_identity": expected,
        "exact_identity": bool(expected and expected in text.upper() and expected in final_url.upper()),
        "href_counts": counts,
        "additional_specification_count": text.count("Дополнительная спецификация"),
        "complex_diagnostics_count": text.count("Комплексная диагностика"),
        "description_heading_count": len(re.findall(r">\s*Описание\s*<", text, re.I)),
        "old_sea_wording": bool(re.search(r"\b(?:В море|в море)\b", text)),
    }


def main() -> int:
    started = now()
    api = ReadOnly()
    errors = []
    file_summary = {}
    bundle = {"task_id": "task_099", "generated_at_utc": started, "files": {}}
    try:
        for name in FILES:
            data = api.file(name)
            facts, selected = source_facts(name, data)
            file_summary[name] = facts
            bundle["files"][name] = selected
        database = database_facts(api.file("crm.db"))
        public = {
            "/video/index.html": public_record(api, "/video/index.html"),
            "/video/katalog.html": public_record(api, "/video/katalog.html"),
        }
        for identifier in IDS:
            public[f"/video/{identifier}.html"] = public_record(api, f"/video/{identifier}.html")
            public[f"/video/{identifier}-diag.html"] = public_record(api, f"/video/{identifier}-diag.html")
    except Exception as exc:
        database = locals().get("database", {})
        public = locals().get("public", {})
        errors.append(type(exc).__name__ + ":" + str(exc))

    catalog_counts = (public.get("/video/katalog.html") or {}).get("href_counts") or {}
    published = database.get("published_ids") or []
    gap = {
        "published_ids": published,
        "missing_from_catalog": [identifier for identifier in published if catalog_counts.get(identifier, 0) == 0],
        "duplicates_in_catalog": [identifier for identifier in published if catalog_counts.get(identifier, 0) > 1],
        "catalog_unique_ids": sorted(catalog_counts),
        "catalog_count": len(catalog_counts),
    }
    if database.get("quick_check") != "ok":
        errors.append("CRM_QUICK_CHECK_FAIL")
    if database.get("ids") != list(IDS):
        errors.append("CRM_16_CARD_REGISTRY_MISMATCH")
    value = {
        "task_id": "task_099", "contract_id": "UA-ART-16-SITE-CRM-COMPLETION-099-V1",
        "status": "PASS_READ_ONLY" if not errors else "FAIL_INCOMPLETE", "mode": "GET_ONLY",
        "started_at_utc": started, "finished_at_utc": now(), "http_methods": sorted(set(api.methods)),
        "production_touched": False, "crm_write": False, "site_write": False, "media_write": False,
        "files": file_summary, "database": database, "public": public, "publication_gap": gap,
        "errors": errors,
    }
    atomic_json(SUMMARY, value)
    atomic_json(BUNDLE, bundle)
    print(json.dumps({"status": value["status"], "row_count": database.get("row_count"), "gap": gap, "errors": errors}, ensure_ascii=False))
    return 0 if value["status"] == "PASS_READ_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
