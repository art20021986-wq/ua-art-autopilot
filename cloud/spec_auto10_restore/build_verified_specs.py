"""Build a sanitized Preview dataset from semantically matched database copies.

This is a read-only export, not a publisher or a fresh source verification.
The pinned semantic hashes must first be confirmed against the running server.
No CRM application modules are imported and no network request is made.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys

SPEC_SHA256 = "ec45ac8ffc088f93a98857c81a6a95aac7b81ce8f7b8a466019a9a7e9e3572b3"
CRM_ALL_SHA256 = "ac3e8b4666c8db7d401673c1d42e1c3cc0b7e4c9e2cc528b72ce63cceede00bc"
CRM_PUBLISHED_SHA256 = "0c26cb2672accba3e64aa018ecf3732f44bac740fb9c235a2adf57ad61b21443"
SPEC_FIELDS = {
    "additional_specification": "car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field",
    "additional_specification_meta": "car_uid,field_key,label_ru,category,unit,evidence_count,source_domains_json,source_urls_json,verification_status,model_match_score,is_manual,is_visible",
}
CRM_FIELDS = "id,auto_number,vin,brand,model,year,fuel,engine_cc,engine,gearbox,published"
EXPECTED_UIDS = [f"UA-{number:04d}" for number in range(1, 17)]
HERE = Path(__file__).resolve().parent


class ExportError(RuntimeError):
    pass


def digest(value, *, sort_keys=False):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, separators=(",", ":"),
                                     sort_keys=sort_keys).encode()).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for data in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(data)
    return result.hexdigest()


def fingerprint(path):
    if not path.is_file() or path.is_symlink():
        raise ExportError("DATABASE_MISSING_OR_SYMLINK")
    result = {"database": file_digest(path)}
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            if suffix != "-shm" and sidecar.stat().st_size:
                raise ExportError("DATABASE_REQUIRES_STABLE_SNAPSHOT")
            result[suffix] = file_digest(sidecar)
    return result


@contextlib.contextmanager
def read_only(path):
    with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        yield conn


def renderer():
    module_spec = importlib.util.spec_from_file_location("spec_preview_renderer", HERE / "runtime/spec_publication.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def identity_policy():
    """Load only the pure source policy; never load the CRM or its worker."""
    runtime = HERE / "runtime"
    sys.path.insert(0, str(runtime))
    try:
        policy = importlib.import_module("source_policy")
        if Path(policy.__file__).resolve() != runtime / "source_policy.py":
            raise ExportError("UNEXPECTED_SOURCE_POLICY_MODULE")
        return policy
    finally:
        sys.path.pop(0)


def identity_quality(card, policy):
    """Flag conflicts, not infer a replacement for operator-owned fields."""
    crm = dict(zip(CRM_FIELDS.split(","), card))
    profile = policy.match_profile(crm)
    issues = []
    try:
        inferred_year = policy.vin_model_year(crm["vin"])
    except policy.SourcePolicyError:
        inferred_year = None
    match = re.fullmatch(r"(?:19|20)\d{2}", str(crm["year"] or ""))
    crm_year = int(match.group()) if match else None
    code = str(crm["vin"] or "")[9:10]
    year_status = "NOT_ESTABLISHED"
    if inferred_year is not None and crm_year is not None:
        delta = abs(inferred_year - crm_year)
        if code.isdigit() and delta > 1:
            # The existing policy excludes these European-market chassis codes.
            year_status = "NUMERIC_CODE_NOT_ASSUMED_TO_BE_MODEL_YEAR"
            inferred_year = None
        elif delta > 1:
            year_status = "CONFLICT_REQUIRES_REVIEW"
            issues.append("CRM_YEAR_DIFFERS_FROM_INFERRED_VIN_MODEL_YEAR")
        else:
            year_status = "MATCH" if not delta else "WITHIN_ONE_YEAR"
    if not crm_year:
        issues.append("CRM_YEAR_MISSING_OR_INVALID")
    aliases = {"к5": "k5", "к 5": "k5", "б класса": "b class", "б класс": "b class"}
    normalized_model = policy._norm(crm["model"])
    normalized_model = aliases.get(normalized_model, normalized_model)
    normalized_brand = policy._norm(crm["brand"])
    brand_match = model_match = None
    if profile:
        brand_match = any(policy._norm(token) in normalized_brand for token in profile["brand_tokens"])
        model_match = any(policy._norm(token) in normalized_model for token in profile["model_tokens"])
        if not brand_match:
            issues.append("CRM_BRAND_DIFFERS_FROM_EXACT_VIN_PROFILE")
        if not model_match:
            issues.append("CRM_MODEL_DIFFERS_FROM_EXACT_VIN_PROFILE")
    else:
        issues.append("NO_EXACT_VIN_PROFILE_FOR_CONTEXT_CHECK")
    status = "NEEDS_REVIEW" if issues else "STORED_CONTEXT_MATCH"
    result = {"status": status, "inspection_only": bool(issues), "eligible_for_stored_fact_restore": not issues,
              "issues": issues, "profile_id": profile["id"] if profile else None,
              "profile_brand_matches": brand_match, "profile_model_matches": model_match,
              "crm_year": crm["year"], "year_check": year_status, "inferred_model_year": inferred_year,
              "inference_is_not_vehicle_document_verification": True}
    if "CRM_YEAR_DIFFERS_FROM_INFERRED_VIN_MODEL_YEAR" in issues:
        result["warning_uk"] = (f"Потрібна перевірка: у CRM зазначено {crm_year} рік, а код модельного року VIN "
                                f"вказує на {inferred_year}. Збережені характеристики показано лише для звірки; публікацію заблоковано.")
        result["warning_ru"] = (f"Нужна проверка: в CRM указан {crm_year} год, а код модельного года VIN "
                                f"указывает на {inferred_year}. Сохранённые характеристики показаны только для сверки; публикация заблокирована.")
    elif issues:
        result["warning_uk"] = "Дані автомобіля потребують перевірки. Збережені характеристики показано лише для звірки."
        result["warning_ru"] = "Данные автомобиля требуют проверки. Сохранённые характеристики показаны только для сверки."
    return result


def build(spec_db, crm_db):
    spec_db, crm_db = Path(spec_db).absolute(), Path(crm_db).absolute()
    before = {"spec": fingerprint(spec_db), "crm": fingerprint(crm_db)}
    with read_only(spec_db) as conn:
        raw_spec = {table: conn.execute("SELECT " + fields + " FROM " + table +
                                      " ORDER BY car_uid,field_key").fetchall()
                    for table, fields in SPEC_FIELDS.items()}
    if digest(raw_spec, sort_keys=True) != SPEC_SHA256:
        raise ExportError("SPEC_SEMANTIC_HASH_MISMATCH")
    with read_only(crm_db) as conn:
        all_cards = conn.execute("SELECT " + CRM_FIELDS + " FROM cars ORDER BY auto_number").fetchall()
    published = [row for row in all_cards if row[-1] == 1]
    if digest(all_cards) != CRM_ALL_SHA256 or digest(published) != CRM_PUBLISHED_SHA256:
        raise ExportError("CRM_IDENTITY_HASH_MISMATCH")
    if len(all_cards) != 18 or [row[1] for row in published] != EXPECTED_UIDS:
        raise ExportError("PUBLISHED_CARD_SCOPE_MISMATCH")

    publication = renderer()
    policy = identity_policy()
    quality_by_uid = {card[1]: identity_quality(card, policy) for card in all_cards}
    fact_columns = SPEC_FIELDS["additional_specification"].split(",")
    meta_columns = SPEC_FIELDS["additional_specification_meta"].split(",")
    metadata = {(row[0], row[1]): dict(zip(meta_columns, row))
                for row in raw_spec["additional_specification_meta"]}
    cards, checks = [], []
    for card in published:
        card_uid = publication.uid(card[1])
        raw_card = {table: [row for row in rows if row[0] == card_uid]
                    for table, rows in raw_spec.items()}
        facts = []
        for row in raw_card["additional_specification"]:
            fact = dict(zip(fact_columns, row))
            key = (card_uid, fact["field_key"])
            if key not in metadata:
                raise ExportError("SPEC_METADATA_MISSING:" + card_uid)
            facts.append({**fact, **metadata[key]})
        normalized = publication.normalize_facts(facts)
        if not normalized:
            raise ExportError("VISIBLE_SPECIFICATION_EMPTY:" + card_uid)
        block = publication.render_block(card_uid, facts)
        validation = publication.validate_page(block, card_uid, facts)
        if re.search(r"<script\b|<a\b|https?://|onclick=", block, re.I):
            raise ExportError("EXTERNAL_OR_ACTIVE_SPECIFICATION_CONTENT:" + card_uid)
        per_card_sha = digest(raw_card, sort_keys=True)
        cards.append({"uid": card_uid, "brand": card[3], "model": card[4], "year": card[5],
                      "vin_last4": str(card[2] or "")[-4:], "rows": len(normalized),
                      "data_quality": quality_by_uid[card_uid],
                      "semantic_sha256": per_card_sha, "spec_html": block})
        checks.append({"uid": card_uid, "rows": len(normalized), "stored_rows": len(facts),
                       "hidden_rows": sum(not bool(f["is_visible"]) for f in facts),
                       "manual_rows": sum(bool(f["is_manual"]) and bool(f["is_visible"]) for f in facts),
                       "validation": validation["status"], "no_ads": True,
                       "data_quality": quality_by_uid[card_uid],
                       "semantic_sha256": per_card_sha, "render_sha256": file_text_digest(block)})

    after = {"spec": fingerprint(spec_db), "crm": fingerprint(crm_db)}
    if before != after:
        raise ExportError("INPUT_DATABASE_CHANGED_DURING_EXPORT")
    dataset = {"task_id": "UA-ART-SPEC-AUTO-10-RESTORE-001", "scope": "published_cards_only",
               "data_basis": "server_matched_stored_facts", "fresh_source_verification": False,
               "ready_count": sum(not card["data_quality"]["inspection_only"] for card in cards),
               "needs_review_count": sum(card["data_quality"]["inspection_only"] for card in cards),
               "spec_semantic_sha256": SPEC_SHA256, "crm_published_identity_sha256": CRM_PUBLISHED_SHA256,
               "cards": cards}
    report = {"status": "PASS", "scope": "read_only_preview_export", "production_touched": False,
              "network_requests": 0, "fresh_source_verification": False,
              "spec_semantic_sha256": SPEC_SHA256, "crm_all_identity_sha256": CRM_ALL_SHA256,
              "crm_published_identity_sha256": CRM_PUBLISHED_SHA256,
              "database_hashes_before": {key: val["database"] for key, val in before.items()},
              "database_hashes_after": {key: val["database"] for key, val in after.items()},
              "database_byte_changes": 0, "input_sidecars_unchanged": True,
              "published_cards": len(cards), "visible_rows": sum(card["rows"] for card in cards),
              "ready_count": dataset["ready_count"], "needs_review_count": dataset["needs_review_count"],
              "ready_count_meaning": "Stored facts eligible for restoration after the remaining Gate B checks; not fresh trim verification.",
              "excluded_drafts": ["UA-0017", "UA-0018"], "no_ads": True,
              "identity_checks_all_cards": [{"uid": card[1], "published": card[-1] == 1,
                                            "data_quality": quality_by_uid[card[1]]} for card in all_cards],
              "cards": checks}
    serialized = json.dumps([dataset, report], ensure_ascii=False)
    for card in all_cards:
        vin = str(card[2] or "")
        if len(vin) > 4 and vin in serialized:
            raise ExportError("FULL_VIN_WOULD_BE_EXPORTED")
    return dataset, report


def file_text_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-db", type=Path, required=True)
    parser.add_argument("--crm-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=HERE / "evidence")
    args = parser.parse_args()
    dataset, report = build(args.spec_db, args.crm_db)
    outputs = [(args.output_dir / "verified-specs.json", dataset),
               (args.output_dir / "verified-specs-report.json", report)]
    if any(path.exists() for path, _ in outputs):
        raise ExportError("OUTPUT_EXISTS_USE_A_NEW_DIRECTORY")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for path, value in outputs:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(json.dumps({"status": "PASS", "cards": report["published_cards"],
                      "rows": report["visible_rows"], "database_byte_changes": 0}))


if __name__ == "__main__":
    main()
