"""Rehearse canonical specification insertion on a cached HTML snapshot.

No network, production writes, or application imports. All candidate pages are
held in memory. Passing this check is not a full Gate B or live-server result.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_builder():
    spec = importlib.util.spec_from_file_location("cached_spec_dataset_builder", HERE / "build_verified_specs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(snapshot_root, dataset_path, spec_db, crm_db):
    snapshot_root, dataset_path = Path(snapshot_root).resolve(), Path(dataset_path).resolve()
    spec_db, crm_db = Path(spec_db).absolute(), Path(crm_db).absolute()
    builder = load_builder()
    databases_before = {"spec": builder.fingerprint(spec_db), "crm": builder.fingerprint(crm_db)}
    dataset_bytes = dataset_path.read_bytes()
    dataset = json.loads(dataset_bytes)
    rebuilt_dataset, database_report = builder.build(spec_db, crm_db)
    if dataset != rebuilt_dataset:
        raise RuntimeError("SAVED_DATASET_DIFFERS_FROM_PINNED_DATABASES")
    cards = {card["uid"]: card for card in dataset["cards"]}
    if list(cards) != builder.EXPECTED_UIDS:
        raise RuntimeError("PUBLISHED_CARD_SCOPE_MISMATCH")
    manifest_path = snapshot_root / "snapshot_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    publication = builder.renderer()
    checks, original_hashes = [], {}
    with builder.read_only(spec_db) as conn:
        conn.row_factory = sqlite3.Row
        for uid, card in cards.items():
            facts = [dict(row) for row in conn.execute("""
                SELECT a.*, m.label_ru, m.category, m.unit, m.verification_status, m.is_manual, m.is_visible
                FROM additional_specification a JOIN additional_specification_meta m
                  ON a.car_uid=m.car_uid AND a.field_key=m.field_key
                WHERE a.car_uid=? ORDER BY a.field_key
            """, (uid,))]
            canonical_block = publication.render_block(uid, facts)
            if canonical_block != card["spec_html"]:
                raise RuntimeError("CANONICAL_BLOCK_DIFFERS_FROM_SAVED_DATASET:" + uid)
            for folder in ("video", "site"):
                relative = folder + "/" + uid + ".html"
                path = snapshot_root / relative
                if path.is_symlink() or not path.is_file():
                    raise RuntimeError("SNAPSHOT_PAGE_MISSING_OR_SYMLINK:" + relative)
                original_bytes = path.read_bytes()
                original_hashes[relative] = sha(original_bytes)
                if relative not in entries or original_hashes[relative] != entries[relative]["sha256"]:
                    raise RuntimeError("SNAPSHOT_MANIFEST_HASH_MISMATCH:" + relative)
                source = original_bytes.decode("utf-8")
                outside = publication.strip_block(source).encode("utf-8")
                candidate = publication.inject(source, uid, facts)
                repeated_once = publication.inject(candidate, uid, facts)
                repeated_twice = publication.inject(repeated_once, uid, facts)
                validation = publication.validate_page(candidate, uid, facts, previous=source)
                rebuilt_pages = (candidate, repeated_once, repeated_twice)
                unchanged = all(publication.strip_block(page).encode("utf-8") == outside for page in rebuilt_pages)
                idempotent = candidate == repeated_once == repeated_twice
                if not unchanged or not idempotent:
                    raise RuntimeError("NON_SPECIFICATION_CHANGE_OR_NON_IDEMPOTENT_REBUILD:" + relative)
                if any(page.count('data-ua-additional-spec="1"') != 1 for page in rebuilt_pages):
                    raise RuntimeError("SPECIFICATION_BLOCK_DUPLICATED:" + relative)
                checks.append({"uid": uid, "path": relative, "status": "PASS",
                               "inspection_only": card["data_quality"]["inspection_only"],
                               "data_quality_status": card["data_quality"]["status"],
                               "rows": validation["rows"], "input_matches_snapshot_manifest": True,
                               "original_bytes": len(original_bytes), "candidate_bytes": len(candidate.encode()),
                               "original_sha256": original_hashes[relative],
                               "candidate_sha256": sha(candidate.encode()),
                               "first_rebuild_sha256": sha(repeated_once.encode()),
                               "second_rebuild_sha256": sha(repeated_twice.encode()),
                               "outside_spec_sha256_before": sha(outside),
                               "outside_spec_sha256_after": sha(publication.strip_block(candidate).encode()),
                               "outside_spec_byte_changes": 0, "idempotence": True,
                               "specification_block_count": 1,
                               "original_had_specification": publication._span(source) is not None,
                               "candidate_matches_saved_canonical_block": canonical_block in candidate,
                               "no_vin_advertisement": True})
    if any(sha((snapshot_root / path).read_bytes()) != digest for path, digest in original_hashes.items()):
        raise RuntimeError("INPUT_HTML_CHANGED_DURING_REHEARSAL")
    databases_after = {"spec": builder.fingerprint(spec_db), "crm": builder.fingerprint(crm_db)}
    if databases_before != databases_after:
        raise RuntimeError("INPUT_DATABASE_CHANGED_DURING_REHEARSAL")
    if manifest_path.read_bytes() != manifest_bytes or dataset_path.read_bytes() != dataset_bytes:
        raise RuntimeError("INPUT_MANIFEST_OR_DATASET_CHANGED_DURING_REHEARSAL")
    return {"task_id": "UA-ART-SPEC-AUTO-10-RESTORE-001", "status": "PASS_CACHED_REBUILD_ONLY",
            "full_gate_b_pass": False, "live_html_verified": False, "production_touched": False,
            "network_requests": 0, "candidate_pages_saved": False,
            "source": {"kind": "cached_task116_snapshot", "snapshot_name": snapshot_root.name,
                       "manifest_schema": manifest.get("schema"), "manifest_sha256": sha(manifest_bytes),
                       "manifest_file_mtime_utc": datetime.fromtimestamp(manifest_path.stat().st_mtime,
                                                                         timezone.utc).isoformat(),
                       "timestamp_note": "Filesystem timestamp only; HTML was not fetched from production during this check.",
                       "git_commit": None},
            "verified_dataset_sha256": sha(dataset_bytes),
            "spec_semantic_sha256": dataset["spec_semantic_sha256"],
            "crm_published_identity_sha256": dataset["crm_published_identity_sha256"],
            "unique_cards": len(cards), "html_pages": len(checks), "render_operations": len(checks) * 3,
            "repeat_rebuilds_per_page": 2, "all_pages_passed": all(check["status"] == "PASS" for check in checks),
            "all_outside_spec_bytes_unchanged": True, "all_rebuilds_idempotent": True,
            "input_html_byte_changes": 0, "input_database_byte_changes": 0,
            "database_hashes_before": {name: value["database"] for name, value in databases_before.items()},
            "database_hashes_after": {name: value["database"] for name, value in databases_after.items()},
            "ready_count": database_report["ready_count"], "needs_review_count": database_report["needs_review_count"],
            "excluded_drafts": ["UA-0017", "UA-0018"],
            "limitations": ["Cached HTML compatibility only; current public HTML and the running writer are not verified here.",
                            "UA-0016 is inspection-only because its CRM year conflicts with the inferred VIN model year.",
                            "Stored specification facts are not a fresh live verification of ten sources."],
            "cards": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--verified-specs", type=Path, default=HERE / "evidence/verified-specs.json")
    parser.add_argument("--spec-db", type=Path, required=True)
    parser.add_argument("--crm-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "evidence/all-card-rebuild.json")
    args = parser.parse_args()
    report = check(args.snapshot_root, args.verified_specs, args.spec_db, args.crm_db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({key: report[key] for key in ("status", "unique_cards", "html_pages", "render_operations",
                                                  "all_outside_spec_bytes_unchanged", "all_rebuilds_idempotent")}))


if __name__ == "__main__":
    main()
