#!/usr/bin/env python3
"""Read-only, privacy-limited candidate inventory for specification restoration.

Usage: python runtime_probe.py --root /home/Carix --output /tmp/spec-snapshot.json
Optional repeated --spec-db arguments identify other explicit database candidates.

No application module is imported or executed. ``modules`` describes files and
static imports, never the modules bound to an existing process. Database exports
are ``databases[].cards / facts / metadata / jobs``; facts and metadata join on
``car_uid, field_key``. Raw VINs, contacts, prices, raw errors, environment values,
and arbitrary tables/columns are not exported. Source URLs are not exported.

SQLite uses mode=ro, immutable=1 and query_only. A nonempty WAL or journal prevents
structured extraction: silently ignoring pending changes would be misleading.
An inventory is not an atomic runtime snapshot; consistent_snapshot stays false.
Run against a server-side copy/backup for a consistent data export. Output must
be outside the inspected root and must not replace an existing file.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any


MODULE_NAMES = frozenset({
    "ua_additional_spec.py", "vin_spec_service.py", "source_policy.py",
    "profile_library.py", "cars_ui.py", "publikaciya.py", "master_card.py",
    "stranica.py", "yadro.py", "publish_transaction_guard.py",
})
DB_NAMES = ("crm.db", "vin_specs.db", "vin_specs_task111_v3.db")
SOURCE_DOMAINS = frozenset({
    "vpic.nhtsa.dot.gov", "auto.danawa.com", "carwiki.co.kr", "carisyou.com",
    "auto-data.net", "ultimatespecs.com", "automobile-catalog.com",
    "cars-data.com", "carfolio.com", "encycarpedia.com",
})
SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".cache"})
CARD_FIELDS = {
    "car_uid": ("auto_number", "car_uid", "uid", "code", "slug"),
    "vin": ("vin", "vin_code"),
    "published": ("published", "is_published", "opublikovano", "public"),
    "brand": ("brand", "make", "marka", "manufacturer"),
    "model": ("model", "vehicle_model"),
    "year": ("year", "model_year", "god", "production_year"),
    "fuel": ("fuel", "fuel_type", "toplivo"),
}
FACT_FIELDS = ("car_uid", "field_key", "field_value", "normalized_value", "source",
               "confidence", "is_price_field", "created_at")
META_FIELDS = ("car_uid", "field_key", "label_ru", "category", "unit", "evidence_count",
               "source_domains_json", "verification_status", "model_match_score",
               "is_manual", "is_visible", "created_at", "updated_at")
JOB_FIELDS = ("car_uid", "vin", "policy_version", "status", "attempts", "facts_count",
              "site_sync_status", "requested_at", "started_at", "finished_at")
TABLE_FIELDS = {
    "cars": tuple(dict.fromkeys(n for names in CARD_FIELDS.values() for n in names)),
    "additional_specification": FACT_FIELDS,
    "additional_specification_meta": META_FIELDS,
    "vin_spec_jobs": JOB_FIELDS,
}
MAX_ROWS = 20000
UID_RE = re.compile(r"^UA[-\u2011\u2013\u2014]?0*(\d{1,6})$", re.I)
BLOCKED_FIELD_RE = re.compile(
    r"(?:^|_)(?:vin|price|cost|contact|phone|email|token|password|secret|owner|client|customer)(?:$|_)", re.I
)
SENSITIVE_TEXT_RE = re.compile(
    r"https?://|[<>]|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"\b[A-HJ-NPR-Z0-9]{17}\b|\b(?:gh[pousr]_|sk-|github_pat_)\S+|"
    r"\b[A-Za-z0-9_/-]{32,}\b|(?:\+?\d[ ()-]*){10,}", re.I
)


def _uid(value: Any) -> str | None:
    match = UID_RE.fullmatch(str(value or "").strip())
    return f"UA-{int(match.group(1)):04d}" if match else None


def _vin_hash(value: Any) -> str | None:
    value = re.sub(r"\s+", "", str(value or "")).upper()
    return hashlib.sha256(value.encode()).hexdigest() if value else None


def _text(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    if len(value) > limit or SENSITIVE_TEXT_RE.search(value):
        return None
    return value


def _flag(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip().lower() in {"1", "true", "yes", "да", "так", "published"}:
            return True
        if value.strip().lower() in {"0", "false", "no", "нет", "ні", "", "draft"}:
            return False
        return None
    return bool(value)


def _number(value: Any) -> int | float | None:
    try:
        number = float(value)
        if abs(number) > 1e12 or number != number:
            return None
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError, OverflowError):
        return None


def _error(exc: BaseException) -> str:
    # Exception messages may contain database values, SQL, or credentials.
    return type(exc).__name__ + (f":errno={exc.errno}" if isinstance(exc, OSError) and exc.errno else "")


def _metadata(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path.absolute())}
    try:
        resolved = path.resolve(strict=True)
        before = resolved.stat()
        record.update(resolved_path=str(resolved), device=before.st_dev,
                      inode=before.st_ino, size=before.st_size, mtime_ns=before.st_mtime_ns)
        if not resolved.is_file():
            return {**record, "status": "NOT_REGULAR_FILE"}
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        after = resolved.stat()
        stable = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        record.update(status="OBSERVED" if stable else "CHANGED_DURING_HASH",
                      sha256=digest.hexdigest(), stable_during_hash=stable)
    except (OSError, RuntimeError) as exc:
        record.update(status="MISSING" if isinstance(exc, FileNotFoundError) else "INACCESSIBLE", reason=_error(exc))
    return record


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _rows(conn: sqlite3.Connection, table: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    info = list(conn.execute("PRAGMA table_info(" + _quoted(table) + ")"))
    if not info:
        return {"status": "MISSING"}, []
    columns = {str(row[1]).casefold(): str(row[1]) for row in info}
    selected = [name for name in TABLE_FIELDS[table] if name in columns]
    count = conn.execute("SELECT COUNT(*) FROM " + _quoted(table)).fetchone()[0]
    schema = {"status": "READ", "column_count": len(columns), "known_columns": selected,
              "row_count": count, "truncated": count > MAX_ROWS}
    if not selected:
        return schema, []
    query = "SELECT " + ",".join(_quoted(columns[n]) for n in selected) + " FROM " + _quoted(table) + " LIMIT ?"
    rows = [dict(zip(selected, row)) for row in conn.execute(query, (MAX_ROWS,))]
    return schema, rows


def _pick(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    return next((row[n] for n in names if n in row and row[n] is not None and str(row[n]).strip()), None)


def _card(row: dict[str, Any]) -> dict[str, Any] | None:
    uid = _uid(_pick(row, CARD_FIELDS["car_uid"]))
    if not uid:
        return None
    card = {"car_uid": uid, "vin_sha256": _vin_hash(_pick(row, CARD_FIELDS["vin"])),
            "published": _flag(_pick(row, CARD_FIELDS["published"]))}
    for name in ("brand", "model", "year", "fuel"):
        value = _text(_pick(row, CARD_FIELDS[name]), 120)
        if value is not None:
            card[name] = value
    return card


def _fact_or_meta(row: dict[str, Any], meta: bool) -> dict[str, Any] | None:
    uid, key = _uid(row.get("car_uid")), str(row.get("field_key") or "")
    if not uid or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key) or BLOCKED_FIELD_RE.search(key):
        return None
    if _flag(row.get("is_price_field")):
        return None
    result: dict[str, Any] = {"car_uid": uid, "field_key": key}
    for name, value in row.items():
        if name in {"car_uid", "field_key"}:
            continue
        if name == "source_domains_json":
            try:
                domains = json.loads(value or "[]")
                result["source_domains"] = sorted({n for n in domains if isinstance(n, str) and n in SOURCE_DOMAINS}) if isinstance(domains, list) else []
            except (ValueError, TypeError):
                result["source_domains"] = []
        elif name in {"is_manual", "is_visible", "is_price_field"}:
            result[name] = _flag(value)
        elif name in {"confidence", "model_match_score", "evidence_count"}:
            result[name] = _number(value)
        else:
            result[name] = _text(value)
    if not meta and not result.get("field_value"):
        return None
    return result


def _job(row: dict[str, Any]) -> dict[str, Any] | None:
    uid = _uid(row.get("car_uid"))
    if not uid:
        return None
    result: dict[str, Any] = {"car_uid": uid}
    for name, value in row.items():
        if name == "car_uid":
            continue
        if name == "vin":
            result["vin_sha256"] = _vin_hash(value)
        elif name in {"attempts", "facts_count"}:
            result[name] = _number(value)
        else:
            result[name] = _text(value, 120)
    return result


def probe_database(path: Path) -> dict[str, Any]:
    before = _metadata(path)
    report: dict[str, Any] = {**before, "consistent_snapshot": False, "schema": {}}
    if before.get("status") != "OBSERVED":
        return report
    resolved = Path(before["resolved_path"])
    auxiliaries = [Path(str(resolved) + suffix) for suffix in ("-wal", "-journal")]
    report["journals"] = [_metadata(p) for p in auxiliaries]
    if any(item.get("status") not in {"OBSERVED", "MISSING"} or item.get("size", 0) for item in report["journals"]):
        report["status"] = "JOURNAL_PRESENT_OR_INACCESSIBLE_READ_SKIPPED"
        return report
    try:
        uri = resolved.as_uri() + "?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True, timeout=1)
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA trusted_schema=OFF")
            conn.execute("BEGIN")
            for table, key, transform in (
                ("cars", "cards", _card),
                ("additional_specification", "facts", lambda row: _fact_or_meta(row, False)),
                ("additional_specification_meta", "metadata", lambda row: _fact_or_meta(row, True)),
                ("vin_spec_jobs", "jobs", _job),
            ):
                schema, rows = _rows(conn, table)
                report["schema"][table] = schema
                report[key] = [item for row in rows if (item := transform(row)) is not None]
                schema["exported_rows"] = len(report[key])
                schema["omitted_rows"] = len(rows) - len(report[key])
            report["query_only"] = conn.execute("PRAGMA query_only").fetchone()[0] == 1
            report["database_changes"] = conn.total_changes
        finally:
            conn.close()
        after = _metadata(resolved)
        journal_changed = any(p.exists() and p.stat().st_size for p in auxiliaries)
        unchanged = before.get("sha256") == after.get("sha256") and before.get("inode") == after.get("inode")
        if not unchanged or journal_changed:
            for key in ("cards", "facts", "metadata", "jobs", "schema"):
                report.pop(key, None)
            report["status"] = "CHANGED_DURING_READ_EXPORT_DISCARDED"
        else:
            report["status"] = "READ_OBSERVATION_NOT_ATOMIC_SNAPSHOT"
    except (sqlite3.Error, OSError, ValueError) as exc:
        for key in ("cards", "facts", "metadata", "jobs", "schema"):
            report.pop(key, None)
        report.update(status="READ_FAILED", reason=_error(exc))
    return report


class _SpecParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.block_count = 0
        self.row_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if attributes.get("data-ua-additional-spec") == "1" or "ua-additional-spec" in classes:
            self.block_count += 1
        if "ua-addspec-row" in classes:
            self.row_count += 1


def _module(path: Path) -> dict[str, Any]:
    report = _metadata(path)
    report["binding_evidence"] = "STATIC_CANDIDATE_ONLY_NOT_PROCESS_BOUND"
    if report.get("status") != "OBSERVED":
        return report
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        targets = {n.removesuffix(".py") for n in MODULE_NAMES}
        imports = set()
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            imports.update(name for name in names if name.split(".")[-1] in targets)
        report["relevant_static_imports"] = sorted(imports)
    except (OSError, UnicodeError, SyntaxError) as exc:
        report["parse_error"] = _error(exc)
    return report


def _compare_databases(databases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare observations without choosing a canonical DB or merging data."""
    cards: dict[str, dict[str, Any]] = {}
    for db in databases:
        if db.get("status") != "READ_OBSERVATION_NOT_ATOMIC_SNAPSHOT":
            continue
        uids = {row["car_uid"] for key in ("cards", "facts", "metadata") for row in db.get(key, [])}
        for uid in sorted(uids):
            comparison = cards.setdefault(uid, {"car_uid": uid, "observations": [], "values": {}})
            facts = [f for f in db.get("facts", []) if f["car_uid"] == uid]
            meta = [m for m in db.get("metadata", []) if m["car_uid"] == uid]
            identities = [c for c in db.get("cards", []) if c["car_uid"] == uid]
            comparison["observations"].append({
                "database": db["path"], "facts_count": len(facts),
                "manual_fields_count": sum(m.get("is_manual") is True for m in meta),
                "vin_sha256": sorted({c["vin_sha256"] for c in identities if c.get("vin_sha256")}),
                "published_flags": sorted({str(c.get("published")) for c in identities}),
            })
            for fact in facts:
                comparison["values"].setdefault(fact["field_key"], set()).add(fact["field_value"])
    results = []
    for comparison in cards.values():
        values = comparison.pop("values")
        comparison["conflicting_field_keys"] = sorted(key for key, vals in values.items() if len(vals) > 1)
        comparison["canonical_database_determined"] = False
        results.append(comparison)
    return sorted(results, key=lambda item: item["car_uid"])


def build_report(root: Path, spec_dbs: tuple[Path, ...] = ()) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("ROOT_MUST_BE_DIRECTORY")
    report: dict[str, Any] = {
        "schema_version": 1, "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "root": str(root), "read_only": True, "runtime_verified": False,
        "consistent_snapshot": False,
        "limits": {"max_rows_per_table": MAX_ROWS, "source_urls_exported": False,
                   "raw_vin_exported": False, "html_exported": False, "processes_inspected": False},
        "modules": [], "databases": [], "public_pages": [], "discovery_errors": [],
    }
    db_candidates = {root / name for name in DB_NAMES} | {p.absolute() for p in spec_dbs}
    def walk_error(exc: OSError) -> None:
        report["discovery_errors"].append({"path": str(exc.filename), "reason": _error(exc)})
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not Path(directory, d).is_symlink())
        for name in sorted(names):
            path = Path(directory, name)
            if name in MODULE_NAMES:
                report["modules"].append(_module(path))
            elif name in DB_NAMES:
                db_candidates.add(path)
            elif re.fullmatch(r"UA-\d{4,6}\.html", name, re.I):
                page = _metadata(path)
                page["car_uid"] = _uid(path.stem)
                if page.get("status") == "OBSERVED":
                    try:
                        parser = _SpecParser()
                        parser.feed(path.read_text(encoding="utf-8"))
                        page.update(specification_blocks=parser.block_count, specification_rows=parser.row_count)
                    except (OSError, UnicodeError) as exc:
                        page["parse_error"] = _error(exc)
                report["public_pages"].append(page)
    seen: dict[tuple[int, int], str] = {}
    for path in sorted(db_candidates):
        record = _metadata(path)
        identity = (record.get("device", -1), record.get("inode", -1))
        if record.get("status") == "OBSERVED" and identity in seen:
            record.update(status="SAME_FILE_ALIAS", same_file_as=seen[identity])
        else:
            record = probe_database(path)
            if record.get("inode") is not None:
                seen[identity] = record["path"]
        report["databases"].append(record)
    report["public_page_count"] = len(report["public_pages"])
    report["unique_public_card_count"] = len({p["car_uid"] for p in report["public_pages"]})
    report["missing_module_names"] = sorted(MODULE_NAMES - {Path(m["path"]).name for m in report["modules"]})
    report["database_comparison"] = _compare_databases(report["databases"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spec-db", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    root = args.root.resolve(strict=True)
    output = args.output.resolve()
    if output == root or root in output.parents:
        parser.error("OUTPUT_MUST_BE_OUTSIDE_ROOT")
    if output.exists() or args.output.is_symlink():
        parser.error("OUTPUT_MUST_NOT_EXIST")
    if not output.parent.is_dir():
        parser.error("OUTPUT_PARENT_MUST_EXIST")
    report = build_report(root, tuple(args.spec_db))
    # O_EXCL and O_NOFOLLOW prevent replacement and final-component symlink races.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(output, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "READ_ONLY_REPORT_WRITTEN", "output": str(output),
                      "runtime_verified": False, "consistent_snapshot": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
