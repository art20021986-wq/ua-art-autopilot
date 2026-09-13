"""Prepare the owner's manual16 restoration payload; never install or publish.

Only stable private snapshot copies are read. The existing semantic data pins,
renderer and shell validator remain authoritative. The generated private plan
contains vehicle identities and must not be committed to a public repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
UIDS = [f"UA-{n:04d}" for n in range(1, 17)]
DRAFTS = ["UA-0017", "UA-0018"]
PATHS = [f"{folder}/{uid}.html" for uid in UIDS for folder in ("video", "site")]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":")).encode()


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def json_value(value):
    return {"bytes_hex": value.hex()} if isinstance(value, bytes) else value


def full_row_digest(row):
    return sha(canonical({key: json_value(value) for key, value in row.items()}))


def read(path, root):
    require(not path.is_symlink() and path.is_file(), "INPUT_MISSING_OR_SYMLINK:" + path.name)
    require(path.resolve().is_relative_to(root), "INPUT_ESCAPES_SNAPSHOT")
    require(all(not part.is_symlink() for part in path.parents if part != root.parent), "INPUT_SYMLINK_PARENT")
    return path.read_bytes()


def builder():
    spec = importlib.util.spec_from_file_location("manual16_stored_fact_builder", BASE / "build_verified_specs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def correct_year(raw, relative, manifest):
    """Apply only exact, separately reviewed UTF-8 year spans to UA-0016.

    The plan is a private review input bound to the complete source bytes.
    It is not a general text replacement or permission to alter another field.
    """
    if not relative.endswith("/UA-0016.html"):
        return raw, []
    record = manifest.get(relative)
    require(isinstance(record, dict), "UA0016_REVIEWED_YEAR_SPANS_MISSING")
    require(record.get("source_sha256") == sha(raw), "UA0016_YEAR_SOURCE_CHANGED")
    edits = record.get("edits")
    require(isinstance(edits, list) and 0 < len(edits) <= 30, "UA0016_YEAR_SPAN_COUNT")
    require(edits == sorted(edits, key=lambda item: item["start"]), "UA0016_YEAR_SPAN_ORDER")
    previous_end = -1
    for item in edits:
        start, end = item["start"], item["end"]
        require(type(start) is int and type(end) is int and 0 <= start < end <= len(raw), "UA0016_YEAR_SPAN_RANGE")
        require(start >= previous_end, "UA0016_YEAR_SPAN_OVERLAP")
        require(item.get("old") == "1999" and item.get("new") == "2017", "UA0016_YEAR_UNAPPROVED_VALUE")
        require(raw[start:end] == b"1999", "UA0016_YEAR_SPAN_CHANGED")
        before, after = item.get("context_before", "").encode(), item.get("context_after", "").encode()
        require(len(before) >= 8 and len(after) >= 8, "UA0016_YEAR_CONTEXT_TOO_SHORT")
        require(start >= len(before) and raw[start-len(before):start] == before and raw[end:end+len(after)] == after,
                "UA0016_YEAR_CONTEXT_CHANGED")
        require(item.get("reason") in {"main_vehicle_year", "vehicle_title", "vehicle_metadata", "vehicle_summary"},
                "UA0016_YEAR_UNREVIEWED_CONTEXT")
        previous_end = end
    require(any(item["reason"] == "main_vehicle_year" for item in edits), "UA0016_MAIN_YEAR_NOT_CORRECTED")
    output = raw
    for item in reversed(edits):
        output = output[:item["start"]] + b"2017" + output[item["end"]:]
    return output, edits


def prepare(snapshot, output, year_review, supplement):
    snapshot = Path(snapshot).absolute()
    require(snapshot.is_dir() and not snapshot.is_symlink(), "SNAPSHOT_ROOT_INVALID")
    snapshot = snapshot.resolve()
    output = Path(output).absolute()
    require(not output.exists() and not output.is_relative_to(snapshot), "OUTPUT_MUST_BE_NEW_AND_OUTSIDE_SNAPSHOT")
    manifest_raw = read(snapshot / "snapshot.json", snapshot)
    manifest = json.loads(manifest_raw)
    require(manifest.get("production_changed") is False, "SNAPSHOT_PRODUCTION_CHANGE_NOT_EXCLUDED")
    require(isinstance(manifest.get("observed_at_utc"), str), "SNAPSHOT_TIME_MISSING")
    require(datetime.fromisoformat(manifest["observed_at_utc"]).tzinfo is not None, "SNAPSHOT_TIMEZONE_MISSING")
    entries = manifest.get("records", [])
    require(len({entry["path"] for entry in entries}) == len(entries), "DUPLICATE_MANIFEST_PATH")
    entries = {entry["path"]: entry for entry in entries}
    require(set(PATHS).issubset(entries) and {"crm.db", "vin_specs_task111_v3.db"}.issubset(entries), "SNAPSHOT_SCOPE_INCOMPLETE")
    originals = {relative: read(snapshot / relative, snapshot) for relative in [*PATHS, "crm.db", "vin_specs_task111_v3.db"]}
    for relative, raw in originals.items():
        require(sha(raw) == entries[relative]["sha256"], "SNAPSHOT_HASH_MISMATCH:" + relative)
        require(len(raw) == entries[relative]["bytes"], "SNAPSHOT_SIZE_MISMATCH:" + relative)
    require(all(len(originals[path]) <= 4 * 1024 * 1024 for path in PATHS), "PRIMARY_PAGE_TOO_LARGE")
    export = builder()
    before_db = {name: export.fingerprint(snapshot / name) for name in ("crm.db", "vin_specs_task111_v3.db")}
    dataset, database_report = export.build(snapshot / "vin_specs_task111_v3.db", snapshot / "crm.db")
    require([card["uid"] for card in dataset["cards"]] == UIDS, "PUBLISHED_UID_SCOPE_CHANGED")
    require(all(not card["data_quality"]["inspection_only"] for card in dataset["cards"]), "STORED_FACT_CONTEXT_UNRESOLVED")
    with export.read_only(snapshot / "crm.db") as connection:
        connection.row_factory = sqlite3.Row
        crm = [dict(row) for row in connection.execute("SELECT * FROM cars ORDER BY auto_number")]
    by_uid = {row["auto_number"]: row for row in crm}
    require(len(by_uid) == len(crm) == 18, "CRM_ID_SCOPE_CHANGED")
    supplement = Path(supplement).absolute()
    require(supplement.is_file() and not supplement.is_symlink(), "SUPPLEMENT_MISSING")
    supplement_raw = supplement.read_bytes()
    extra = json.loads(supplement_raw)
    require(extra.get("schema") == manifest.get("schema") and extra.get("observed_at_utc") == manifest["observed_at_utc"],
            "SUPPLEMENT_SNAPSHOT_BINDING")
    extra_records = extra.get("records", [])
    require(len(extra_records) == len(entries), "SUPPLEMENT_RECORD_COUNT")
    extra_entries = {item["path"]: item for item in extra_records}
    require(set(extra_entries) == set(entries), "SUPPLEMENT_RECORD_SCOPE")
    for relative, entry in entries.items():
        require(all(extra_entries[relative].get(key) == value for key, value in entry.items()), "SUPPLEMENT_RECORD_CHANGED")
        require(type(extra_entries[relative].get("mode")) is int and 0 <= extra_entries[relative]["mode"] <= 0o777,
                "SUPPLEMENT_MODE_INVALID")
    require(extra.get("global_atomic_snapshot") is False, "SUPPLEMENT_ATOMICITY_OVERCLAIM")
    require(extra.get("production_changed") is False and extra.get("input_identities_unchanged") is True,
            "SUPPLEMENT_INPUT_STABILITY_MISSING")
    journals = extra.get("journal_states", [])
    require({item.get("path") for item in journals} == {name + suffix for name in ("crm.db", "vin_specs_task111_v3.db")
            for suffix in ("-wal", "-shm", "-journal")}, "SUPPLEMENT_DATABASE_JOURNALS_MISSING")
    require(all(item.get("exists") is False or item.get("bytes") == 0 for item in journals), "SUPPLEMENT_ACTIVE_DATABASE_JOURNAL")
    protected = extra.get("protected_drafts", [])
    require([item.get("uid") for item in protected] == DRAFTS, "DRAFT_CAPTURE_MISSING")
    for item in protected:
        row = by_uid[item["uid"]]
        require(row["published"] == 0 and item.get("published") == 0, "DRAFT_ALREADY_PUBLISHED")
        require(item.get("row_sha256") == full_row_digest(row), "DRAFT_ROW_CAPTURE_MISMATCH")
        pages = item.get("pages", [])
        require([p.get("path") for p in pages] == [f"{folder}/{item['uid']}.html" for folder in ("video", "site")],
                "DRAFT_PAGE_CAPTURE_INCOMPLETE")
        for page in pages:
            require(type(page.get("exists")) is bool, "DRAFT_PAGE_EXISTENCE_UNKNOWN")
            require(not page["exists"] or isinstance(page.get("sha256"), str) and len(page["sha256"]) == 64,
                    "DRAFT_PAGE_HASH_MISSING")
    year_review = Path(year_review).absolute()
    require(year_review.is_file() and not year_review.is_symlink(), "YEAR_REVIEW_MISSING")
    year_raw = year_review.read_bytes()
    reviewed = json.loads(year_raw)
    require(reviewed.get("schema") == "UA-ART-MANUAL16-YEAR-SPANS-1", "YEAR_REVIEW_SCHEMA")
    year_spans = reviewed.get("pages", {})
    require(set(year_spans) == {"video/UA-0016.html", "site/UA-0016.html"}, "YEAR_REVIEW_SCOPE")
    publication = export.renderer()
    candidates, checks = {}, []
    with export.read_only(snapshot / "vin_specs_task111_v3.db") as connection:
        connection.row_factory = sqlite3.Row
        for card in dataset["cards"]:
            uid = card["uid"]
            facts = [dict(row) for row in connection.execute("""
                SELECT a.*, m.label_ru, m.category, m.unit, m.verification_status, m.is_manual, m.is_visible
                FROM additional_specification a JOIN additional_specification_meta m
                  ON a.car_uid=m.car_uid AND a.field_key=m.field_key
                WHERE a.car_uid=? ORDER BY a.field_key
            """, (uid,))]
            require(publication.render_block(uid, facts) == card["spec_html"], "STORED_RENDER_DIFFERS")
            for folder in ("video", "site"):
                relative = f"{folder}/{uid}.html"
                original = originals[relative]
                year_corrected, year_edits = correct_year(original, relative, year_spans)
                source = year_corrected.decode("utf-8")
                result = publication.inject(source, uid, facts)
                require(publication.inject(result, uid, facts) == result, "NON_IDEMPOTENT_SPEC_REBUILD")
                validation = publication.validate_page(result, uid, facts, previous=source)
                delta = publication.card_shell.permitted_delta(source, result, uid)
                assets = publication.card_shell.validate_shell_assets(original.decode("utf-8"), result)
                candidates[relative] = result.encode("utf-8")
                checks.append({"path": relative, "before_sha256": sha(original), "after_sha256": sha(candidates[relative]),
                               "before_mode": extra_entries[relative]["mode"],
                               "rows": validation["rows"], "visible_vin_count": validation["visible_vin_count"],
                               "shell_assets": assets, "spec_vin_delta": delta, "year_edits": year_edits})
    require({name: export.fingerprint(snapshot / name) for name in before_db} == before_db, "INPUT_DATABASE_CHANGED")
    require(all(read(snapshot / relative, snapshot) == raw for relative, raw in originals.items()), "SNAPSHOT_CHANGED")
    require(read(snapshot / "snapshot.json", snapshot) == manifest_raw and year_review.read_bytes() == year_raw,
            "REVIEW_INPUT_CHANGED")
    require(supplement.read_bytes() == supplement_raw, "SUPPLEMENT_CHANGED")
    target = by_uid["UA-0016"]
    require(str(target["year"]) == "1999" and str(target["vin"])[-4:] == "1028" and target["published"] == 1,
            "UA0016_CONDITIONAL_TARGET_CHANGED")
    after_row = {**target, "year": "2017"}
    plan = {"schema": "UA-ART-MANUAL16-PREPARED-PAYLOAD-1", "task_id": "UA-ART-SPEC-AUTO-10-RESTORE-001",
            "status": "PREPARED_WRITE_NOT_AUTHORIZED", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_snapshot_sha256": sha(manifest_raw), "supplement_sha256": sha(supplement_raw), "input_observed_at_utc": manifest["observed_at_utc"],
            "input_global_atomic_snapshot": False, "supplement_observed_at_utc": extra.get("supplement_observed_at_utc"),
            "capture_archive_sha256": extra.get("capture_archive_sha256"), "database_journal_states": journals,
            "source_semantic_sha256": database_report["spec_semantic_sha256"],
            "crm_identity_sha256": database_report["crm_all_identity_sha256"],
            "crm_all_rows_sha256": sha(canonical([{key: json_value(value) for key, value in row.items()} for row in crm])),
            "crm_proposed_all_rows_sha256": sha(canonical([{key: json_value(value) for key, value in
                (after_row if row["auto_number"] == "UA-0016" else row).items()} for row in crm])),
            "spec_semantic_fields": export.SPEC_FIELDS,
            "published_scope": UIDS, "protected_drafts": protected,
            "crm_conditional_change": {"table": "cars", "field": "year", "old": "1999", "new": "2017",
                "where": {"id": target["id"], "auto_number": "UA-0016", "vin": target["vin"], "year": "1999", "published": 1},
                "before_full_row_sha256": full_row_digest(target), "after_full_row_sha256": full_row_digest(after_row),
                "expected_affected_rows": 1, "all_other_cells_unchanged": True},
            "pages": checks, "year_review_sha256": sha(year_raw),
            "source_files": {str(path.relative_to(BASE)): sha(path.read_bytes()) for path in
                (Path(__file__).resolve(), BASE / "build_verified_specs.py", BASE / "runtime/spec_publication.py",
                 BASE / "runtime/card_shell.py", BASE / "runtime/source_policy.py", BASE / "runtime/profile_library.py")},
            "production_changed": False, "network_requests": 0, "crm_runtime_modules_imported": False,
            "pure_reviewed_modules_imported": ["build_verified_specs", "spec_publication", "card_shell", "source_policy", "profile_library"],
            "full_gate_b_pass": False, "external_writers_verified": False, "crm_runtime_installed": False,
            "publication_button_ready": False, "new_card_publication": "OWNER_MANUAL_ONLY_17_THEN_18",
            "remaining_execution_gates": ["verified old-writer drain", "reviewed lock handoff for HTML/CRM transaction",
                "durable exact backup and conditional rollback", "existing release Gate B and exact authorization",
                "fresh preconditions before writes", "actual public16 readback", "installed CRM runtime verification"]}
    plan["payload_plan_sha256"] = sha(canonical(plan))
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for relative, raw in candidates.items():
        path = output / "candidate" / relative
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)
        path.chmod(0o600)
    diff = []
    for relative in PATHS:
        diff.extend(difflib.unified_diff(originals[relative].decode().splitlines(keepends=True),
            candidates[relative].decode().splitlines(keepends=True), fromfile="before/" + relative, tofile="candidate/" + relative))
    (output / "candidate.diff").write_text("".join(diff), encoding="utf-8")
    (output / "candidate.diff").chmod(0o600)
    (output / "private-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    (output / "private-plan.json").chmod(0o600)
    return {"status": plan["status"], "payload_plan_sha256": plan["payload_plan_sha256"], "cards": 16,
            "html_pages": len(checks), "visible_facts": database_report["visible_rows"],
            "ua0016_year_patch_prepared": True, "protected_drafts": DRAFTS,
            "production_changed": False, "publication_button_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year-review", type=Path, required=True)
    parser.add_argument("--supplement", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.snapshot, args.output, args.year_review, args.supplement), ensure_ascii=False))


if __name__ == "__main__":
    main()
