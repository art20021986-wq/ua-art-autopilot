#!/usr/bin/env python3
"""Fail-closed validator for TASK 098 QA outputs.

The validator checks generated cloud artifacts only. It executes the documented SQLite
DDL in an in-memory database; it never connects to a real database or production.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterator

ROOT = Path("cloud/task_097_editorial_atlas_news")
QA = Path("cloud/task_098_editorial_atlas_qa")
SAFETY_KEYS = (
    "production_touched",
    "crm_touched",
    "catalog_touched",
    "public_files_touched",
    "autopublication_enabled",
)

REQUIRED = [
    ROOT / "evidence.json",
    ROOT / "dedup_scoring_autopilot.md",
    ROOT / "data_model_pipeline.md",
    ROOT / "seo_routing_audit.md",
    ROOT / "report.md",
    ROOT / "source_registry.csv",
    ROOT / "source_audit_report.md",
    QA / "README.md",
    QA / "evidence_qa.json",
    QA / "live_seo_evidence.md",
    QA / "redirect_domain_qa.md",
    QA / "source_probe_qa.md",
    QA / "qa_report.md",
    QA / "workflow_qa_started_at.txt",
    QA / "live_site_probe.json",
    QA / "robots_live.txt",
    QA / "sitemap_live_excerpt.xml",
    QA / "redirect_probe.json",
    QA / "source_probe_qa_machine.json",
    Path("cloud/latest_status.md"),
    Path("cloud/owner_reply.md"),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def walk_json(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + (str(key),)
            yield child_path, child
            yield from walk_json(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, path + (str(index),))


def normalize_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def has_semantic_task_id(document: dict[str, Any], task_number: int) -> bool:
    """Require a task-labelled field whose value semantically identifies TASK 098."""
    expected = f"task_{task_number:03d}"
    compact = f"task{task_number:03d}"
    for path, value in walk_json(document):
        path_text = "_".join(path).lower()
        if "task" not in path_text:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value == task_number:
            return True
        normalized = normalize_token(value)
        if normalized == expected or normalized == compact:
            return True
        compact_value = re.sub(r"[^a-z0-9]", "", str(value).lower())
        if compact in compact_value:
            return True
    return False


def has_semantic_count(document: dict[str, Any], required_count: int) -> bool:
    """Accept equivalent flat/nested field names while preserving the exact invariant."""
    for path, value in walk_json(document):
        key = "_".join(path).lower().replace("-", "_")
        if not ("non" in key and "normal" in key):
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value == required_count:
            return True
        if isinstance(value, str) and value.isdigit() and int(value) == required_count:
            return True
        if isinstance(value, list) and len(value) == required_count:
            return True
    return False


def extract_sql(markdown: str) -> str:
    blocks = re.findall(r"```sql\s*(.*?)```", markdown, re.I | re.S)
    candidates = [block for block in blocks if re.search(r"\bCREATE\s+TABLE\b", block, re.I)]
    require(bool(candidates), "No executable SQLite DDL code block found")
    # The specification requires one complete appendix; use the richest DDL block.
    return max(candidates, key=len)


def validate_files() -> None:
    for path in REQUIRED:
        require(path.is_file() and path.stat().st_size > 0, f"Missing or empty: {path}")

    latest = Path("cloud/latest_status.md").read_text(encoding="utf-8")
    require(re.search(r"^TASK_ID: task_098$", latest, re.M) is not None, "latest_status task mismatch")
    require(re.search(r"^PRODUCTION_TOUCHED: NO$", latest, re.M) is not None, "production safety line missing")
    require(re.search(r"^OWNER_ACTION_REQUIRED: NO$", latest, re.M) is not None, "owner action should be NO")


def validate_evidence() -> None:
    evidence = load_json(ROOT / "evidence.json")
    qa = load_json(QA / "evidence_qa.json")
    task097_commit = utc("2026-08-30T16:49:39Z")
    now = dt.datetime.now(dt.timezone.utc)
    generated = utc(str(evidence["generated_at_utc"]))
    require(task097_commit <= generated <= now + dt.timedelta(minutes=5), "Implausible generated_at_utc")
    require(evidence.get("task097_result_commit_at_utc") == "2026-08-30T16:49:39Z", "Commit timestamp not preserved")
    corrections = evidence.get("evidence_corrections")
    require(isinstance(corrections, list) and corrections, "Evidence correction ledger missing")
    correction_text = json.dumps(corrections, ensure_ascii=False)
    require("2026-08-30T17:00:00Z" in correction_text, "Original erroneous timestamp not recorded")
    require("task_098" in correction_text, "QA task not identified in correction ledger")
    require(int(evidence.get("source_probe_rows", 0)) == 70, "TASK097 evidence source count changed")
    require(evidence.get("source_probe_geo_counts") == {"UA": 10, "GE": 10, "KR": 10, "JP": 10, "US": 10, "EU": 10, "CN": 10}, "Geo counts changed")
    for key in SAFETY_KEYS:
        require(evidence.get(key) is False, f"TASK097 safety flag not false: {key}")
        require(qa.get(key) is False, f"TASK098 safety flag not false: {key}")
    require(has_semantic_task_id(qa, 98), "QA evidence does not semantically identify task_098")
    require(int(qa.get("live_seo_probe_rows", 0)) == 6, "QA live SEO row count mismatch")
    require(int(qa.get("redirect_probe_rows", 0)) == 9, "QA redirect row count mismatch")
    require(has_semantic_count(qa, 24), "QA evidence does not encode the exact 24 non-normal sources")


def validate_image_rights() -> None:
    text = (ROOT / "dedup_scoring_autopilot.md").read_text(encoding="utf-8")
    require("IMAGE_RIGHTS_STATUS" in text, "IMAGE_RIGHTS_STATUS missing")
    require("IMAGE_RIGHTS_CONFIDENCE" in text, "IMAGE_RIGHTS_CONFIDENCE missing")
    require(re.search(r"IMAGE_RIGHTS_CONFIDENCE\s*(?:>=|≥)\s*95", text) is not None, "Image confidence threshold 95 missing")
    require("IMAGE_RIGHTS_CONFIDENCE == CONFIRMED" not in text, "Old numeric/string type mismatch remains")
    require(all(token in text for token in ("OWNED", "LICENSED", "REUSABLE", "PROHIBITED", "UNKNOWN")), "Rights enum incomplete")
    require(re.search(r"rights.{0,100}(?:evidence|доказ|документ)", text, re.I | re.S) is not None, "Durable rights evidence requirement missing")


def validate_sqlite_spec() -> None:
    markdown = (ROOT / "data_model_pipeline.md").read_text(encoding="utf-8")
    require("SQLite 3" in markdown, "SQLite 3 engine decision missing")
    require("PRAGMA foreign_keys = ON" in markdown, "Foreign-key pragma missing")
    require("publication_outbox" in markdown, "Publication outbox missing")
    require(re.search(r"staging|приватн.{0,30}каталог|временн.{0,30}релиз", markdown, re.I | re.S) is not None, "Filesystem staging design missing")
    require(re.search(r"release pointer|current symlink|atomic rename|versioned release|указател.{0,30}релиз|верс(?:ионн|ійн).{0,30}каталог", markdown, re.I | re.S) is not None, "Atomic release-pointer design missing")

    sql = extract_sql(markdown)
    require(re.search(r"\bTIMESTAMPTZ\b|\bJSONB\b", sql, re.I) is None, "PostgreSQL-only type remains inside SQLite DDL")
    require(re.search(r"IN\s*\([^)]*\bNULL\b[^)]*\)", sql, re.I | re.S) is None, "NULL remains inside IN() CHECK")
    stories_pos = re.search(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+news_stories", sql, re.I)
    items_pos = re.search(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+source_items", sql, re.I)
    require(stories_pos is not None and items_pos is not None and stories_pos.start() < items_pos.start(), "Referenced-table ordering is not fixed")

    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(sql)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        core_tables = {
            "news_sources",
            "news_stories",
            "source_items",
            "story_sources",
            "story_fact_cards",
            "news_translations",
            "news_publications",
            "approval_queue",
            "autopilot_settings",
            "news_audit_log",
            "publication_outbox",
        }
        missing = core_tables - tables
        require(not missing, f"SQLite DDL missing core tables: {sorted(missing)}")

        image_table = next((name for name in ("news_image_assets", "image_assets") if name in tables), None)
        require(image_table is not None, "SQLite DDL lacks an image-assets/rights table")
        image_columns = {row[1] for row in connection.execute(f"PRAGMA table_info({image_table})")}
        require(any("status" in col and "right" in col for col in image_columns), "Image-rights status column missing")
        require(any("confidence" in col and "right" in col for col in image_columns), "Image-rights confidence column missing")
        require(any(("evidence" in col or "license" in col) for col in image_columns), "Image-rights evidence column missing")

        require(any(name in tables for name in ("failed_jobs", "dead_letter_jobs", "dead_letter")), "Failure/dead-letter table missing")
        approval_sql_row = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='approval_queue'").fetchone()
        require(approval_sql_row is not None, "approval_queue missing after DDL execution")
        require(re.search(r"IN\s*\([^)]*\bNULL\b", approval_sql_row[0], re.I | re.S) is None, "approval_queue NULL-in-IN defect remains")
        fk_value = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        require(int(fk_value) == 1, "DDL did not enable SQLite foreign keys")
    finally:
        connection.close()


def validate_machine_counts() -> None:
    machine = load_json(QA / "source_probe_qa_machine.json")
    require(machine.get("rows") == 70, "Machine source rows mismatch")
    require(machine.get("normal_lt_400_count") == 46, "Normal source count mismatch")
    require(machine.get("non_normal_count") == 24, "Non-normal source count mismatch")
    non_normal_ids = list(machine.get("non_normal_source_ids", []))
    mvp_ids = list(machine.get("mvp_source_ids", []))
    require(len(non_normal_ids) == len(set(non_normal_ids)) == 24, "Non-normal ID list invalid")
    require(len(mvp_ids) == len(set(mvp_ids)) == 15, "MVP ID list invalid")
    source_qa = (QA / "source_probe_qa.md").read_text(encoding="utf-8")
    for source_id in non_normal_ids:
        require(source_id in source_qa, f"Non-normal source omitted from QA report: {source_id}")

    with (ROOT / "source_registry.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == 70, "Registry no longer has 70 rows")
    registry_mvp = [row["source_id"] for row in rows if row.get("decision") == "APPROVE_MVP"]
    require(set(registry_mvp) == set(mvp_ids), "MVP mismatch between registry and machine QA")
    source_report = (ROOT / "source_audit_report.md").read_text(encoding="utf-8")
    consolidated = (ROOT / "report.md").read_text(encoding="utf-8")
    for source_id in mvp_ids:
        require(source_id in source_report and source_id in consolidated, f"MVP ID inconsistent across reports: {source_id}")

    site_rows = load_json(QA / "live_site_probe.json")
    redirect_rows = load_json(QA / "redirect_probe.json")
    require(isinstance(site_rows, list) and len(site_rows) == 6, "Raw live-site probe must have 6 rows")
    require(isinstance(redirect_rows, list) and len(redirect_rows) == 9, "Raw redirect probe must have 9 rows")


def main() -> None:
    validate_files()
    validate_evidence()
    validate_image_rights()
    validate_sqlite_spec()
    validate_machine_counts()
    print("TASK098_QA_VALIDATION_PASS")


if __name__ == "__main__":
    main()
