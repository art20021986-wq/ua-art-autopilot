"""Import a pinned private snapshot into a new store and prepare page copies.

This command never installs files, opens the live CRM, or calls an upstream.
Its output includes private data and must not be committed to public GitHub.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import json
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urljoin

from .store import SpecStore
from .crm_bridge import CrmBridge, identity_from_crm
from .render import compose_page, render_block, validate_page

EXPECTED_PAYLOAD_SHA = "301e45050ce7a163825e0429d36929d81f4d4fe723c3342af166baf3fc311597"
UIDS = [f"UA-{n:04d}" for n in range(1, 17)]
DRAFTS = ["UA-0017", "UA-0018"]


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read_file(root, relative):
    path = root / relative
    require(not path.is_symlink() and path.is_file(), "INVALID_INPUT_FILE:" + relative)
    require(path.resolve().is_relative_to(root), "INPUT_ESCAPES_ROOT")
    require(all(not p.is_symlink() for p in path.parents if p != root.parent), "SYMLINK_PARENT")
    return path.read_bytes()


def row_hash(rows):
    return sha(canonical([{k: ({"bytes_hex": v.hex()} if isinstance(v, bytes) else v)
                           for k, v in row.items()} for row in rows]))


def preview_content(page):
    # Presentation-only adaptation: relative media load from the original site;
    # fragment links resolve within this script-disabled, separately served document.
    base = "https://www.uaart.com.ua/video/"
    display = re.sub(r'<script\b[^>]*>.*?</script\s*>', '', page, flags=re.I | re.S)
    display = re.sub(r'<base\b[^>]*>', '', display, flags=re.I)
    def tag(match):
        return re.sub(r'\b(src|poster|href)\s*=\s*([\"\'])(.*?)\2',
                      lambda m: m[1] + '=' + m[2] + html.escape(urljoin(base, html.unescape(m[3])), quote=True) + m[2],
                      match[0], flags=re.I | re.S)
    display = re.sub(r'<(?:img|source|video|audio|link)\b[^>]*>', tag, display, flags=re.I | re.S)
    display = re.sub(r'url\(\s*([\"\']?)([^)\"\']+)\1\s*\)',
                     lambda m: 'url("' + urljoin(base, m[2].strip()) + '")', display, flags=re.I)
    csp = ('<meta http-equiv="Content-Security-Policy" content="'
           "script-src 'none'; connect-src 'none'; form-action 'none'; frame-src 'none'; base-uri 'none'"
           '">')
    display = re.sub(r'<head\b[^>]*>', lambda m: m[0] + csp, display, count=1, flags=re.I)
    return display


def preview_frame(uid):
    return ('<!doctype html><html lang="uk"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex,nofollow"><title>UA ART '+ uid +' Preview</title>'
            '<style>body{margin:0;background:#0b1723;color:#edf2f8;font:16px/1.45 system-ui}header{padding:14px 18px}'
            'p{margin:7px 0}a{color:#e6b864}iframe{display:block;width:100%;height:calc(100dvh - 132px);'
            'min-height:620px;border:0}strong{color:#f2b54b}</style></head><body>'
            '<header><a href="/">← Усі 16 автомобілів</a><p><strong>'+uid+' · Нова додаткова специфікація</strong></p>'
            '<p>Копія для перегляду. Зміни на робочому сайті ще не встановлено. Прокрутіть до характеристик.</p></header>'
            '<iframe title="Картка '+ uid +' — перевірочна копія" sandbox src="/cards/content/' + uid + '.html"></iframe></body></html>')


def prepare(snapshot_root, prior_payload, output_root):
    snapshot_root, prior_payload = Path(snapshot_root).resolve(), Path(prior_payload).resolve()
    output_root = Path(output_root).absolute()
    require(not output_root.exists(), "OUTPUT_MUST_BE_NEW")
    require(not output_root.is_relative_to(snapshot_root) and not output_root.is_relative_to(prior_payload),
            "OUTPUT_MUST_NOT_OVERLAP_INPUT")
    manifest_raw = read_file(snapshot_root, "snapshot.json")
    manifest = json.loads(manifest_raw)
    plan = json.loads(read_file(prior_payload, "private-plan.json"))
    claimed = plan.pop("payload_plan_sha256")
    require(sha(canonical(plan)) == claimed == EXPECTED_PAYLOAD_SHA, "PRIOR_PAYLOAD_CHANGED")
    require(plan["input_snapshot_sha256"] == sha(manifest_raw), "SNAPSHOT_PLAN_MISMATCH")
    require(plan["production_changed"] is False
            and plan["status"] == "PREPARED_WRITE_NOT_AUTHORIZED"
            and plan["new_card_publication"] == "OWNER_MANUAL_ONLY_17_THEN_18",
            "PRIOR_PAYLOAD_NOT_PREPARATION_ONLY")
    require(plan["published_scope"] == UIDS, "PUBLISHED_SCOPE_CHANGED")
    records = {x["path"]: x for x in manifest["records"]}
    tracked = {}
    for relative in ["crm.db", "vin_specs_task111_v3.db"] + [x["path"] for x in plan["pages"]]:
        raw = read_file(snapshot_root, relative)
        require(sha(raw) == records[relative]["sha256"], "SNAPSHOT_HASH_CHANGED:" + relative)
        tracked[relative] = sha(raw)
    for name in ["crm.db", "vin_specs_task111_v3.db"]:
        require(not any((snapshot_root / (name + suffix)).exists() for suffix in ("-wal", "-journal")),
                "DATABASE_NOT_A_STABLE_COPY")
    with contextlib.closing(sqlite3.connect((snapshot_root / "crm.db").as_uri()+"?mode=ro&immutable=1", uri=True)) as c:
        c.row_factory = sqlite3.Row
        cars = [dict(row) for row in c.execute("SELECT * FROM cars ORDER BY auto_number")]
    require(row_hash(cars) == plan["crm_all_rows_sha256"], "CRM_FULL_ROWS_CHANGED")
    require([x["auto_number"] for x in cars] == UIDS + DRAFTS, "CRM_UID_SCOPE_CHANGED")
    require([x["auto_number"] for x in cars if x["published"]] == UIDS, "PUBLICATION_FLAGS_CHANGED")
    facts_by_uid = {}
    with contextlib.closing(sqlite3.connect((snapshot_root / "vin_specs_task111_v3.db").as_uri()+"?mode=ro&immutable=1", uri=True)) as c:
        c.row_factory = sqlite3.Row
        for uid in UIDS + DRAFTS:
            facts_by_uid[uid] = [dict(row) for row in c.execute('''SELECT a.*, m.label_ru,m.category,m.unit,
                m.verification_status,m.is_manual,m.is_visible,m.evidence_count,m.source_domains_json,m.source_urls_json
                FROM additional_specification a JOIN additional_specification_meta m
                ON a.car_uid=m.car_uid AND a.field_key=m.field_key WHERE a.car_uid=? ORDER BY a.field_key''', (uid,))]
    require(sum(map(len, facts_by_uid.values())) == 557, "STORED_FACT_SCOPE_CHANGED")
    require(all(not facts_by_uid[uid] for uid in DRAFTS), "DRAFT_FACT_SCOPE_CHANGED")
    prepared_inputs = {}
    for item in plan["pages"]:
        raw = read_file(prior_payload, "candidate/" + item["path"])
        require(sha(raw) == item["after_sha256"], "PRIOR_CANDIDATE_CHANGED:" + item["path"])
        require(tracked[item["path"]] == item["before_sha256"], "PAGE_SOURCE_CHANGED")
        prepared_inputs[item["path"]] = raw
    require(set(prepared_inputs) == {f"{folder}/{uid}.html" for folder in ("video", "site") for uid in UIDS},
            "CANDIDATE_PAGE_SCOPE_CHANGED")
    output_root.mkdir(mode=0o700, parents=True)
    with SpecStore(output_root / "spec-rebuild.db") as store:
        cards_output, checks = [], []
        by_uid = {car["auto_number"]: car for car in cars}
        receipt_id = "legacy-snapshot:" + sha(manifest_raw)
        for uid in UIDS + DRAFTS:
            row = dict(by_uid[uid])
            if uid == "UA-0016":
                require(str(row["year"]) == "1999" and str(row["vin"])[-4:] == "1028", "OWNER_YEAR_SCOPE_CHANGED")
                row["year"] = "2017"
            canonical_uid, identity = identity_from_crm(row)
            require(canonical_uid == uid, "CRM_IDENTITY_UID_CHANGED")
            state = store.upsert_vehicle(uid, identity, published=bool(row["published"]))
            if facts_by_uid[uid]:
                store.import_legacy(uid, facts_by_uid[uid], receipt_id)
            restored = store.get_facts(uid, include_hidden=True)
            require(len(restored) == len(facts_by_uid[uid]), "MIGRATION_COUNT_MISMATCH:" + uid)
            before_save = store.get_vehicle(uid)
            CrmBridge(store).saved(row)
            after_save = store.get_vehicle(uid)
            require(before_save["revision"] == after_save["revision"]
                    and before_save["identity_hash"] == after_save["identity_hash"]
                    and store.get_facts(uid, include_hidden=True) == restored,
                    "FIRST_CRM_SAVE_INVALIDATES_MIGRATION:" + uid)
            if uid in DRAFTS:
                require(not store.get_facts(uid), "DRAFT_FACTS_CREATED")
                continue
            visible = store.get_facts(uid)
            require(len(visible) == sum(bool(f["is_visible"]) for f in facts_by_uid[uid]), "VISIBLE_FACT_COUNT_MISMATCH:" + uid)
            block = render_block(uid, visible)
            cards_output.append({"uid": uid, "brand": row["brand"], "model": row["model"], "year": identity["year"],
                                 "vin_last4": str(row["vin"])[-4:], "rows": len(visible), "spec_html": block,
                                 "pending_crm_update": uid == "UA-0016", "fresh_source_verification": False,
                                 "full_card_url": "/cards/"+uid+".html"})
            for folder in ("video", "site"):
                relative = f"{folder}/{uid}.html"
                original = prepared_inputs[relative].decode("utf-8")
                candidate = compose_page(original, uid, visible)
                checked = validate_page(candidate, uid, visible, previous=original)
                require(compose_page(candidate, uid, visible) == candidate, "RENDER_NOT_IDEMPOTENT:"+relative)
                dst = output_root / "candidate" / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(candidate, encoding="utf-8")
                checks.append({"path": relative, "original_snapshot_sha256": tracked[relative],
                               "prepared_base_sha256": sha(prepared_inputs[relative]), "candidate_sha256": sha(candidate.encode()),
                               "rows": len(visible), "validation": checked, "render_idempotent": True})
                if folder == "video":
                    preview = output_root / "preview-pages" / (uid + ".html")
                    preview.parent.mkdir(exist_ok=True)
                    preview.write_text(preview_frame(uid), encoding="utf-8")
                    content = output_root / "preview-pages" / "content" / (uid + ".html")
                    content.parent.mkdir(exist_ok=True)
                    content.write_text(preview_content(candidate), encoding="utf-8")
        for relative, expected in tracked.items():
            require(sha(read_file(snapshot_root, relative)) == expected, "INPUT_CHANGED_DURING_PREPARATION")
        for uid in DRAFTS:
            require(not any((output_root / "candidate" / folder / (uid + ".html")).exists() for folder in ("video", "site")),
                    "DRAFT_PAGE_CREATED")
        report = {"schema": "UA-ART-SPEC-REBUILD10-SNAPSHOT-1", "task_id": "UA-ART-SPEC-REBUILD-10-001",
                  "status": "PASS_PRIVATE_COPY_PREPARATION", "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                  "source_snapshot_observed_at_utc": manifest.get("observed_at_utc"), "input_snapshot_sha256": sha(manifest_raw),
                  "prior_preparation_payload_sha256": claimed, "published_cards_in_snapshot": 16, "candidate_pages": len(checks),
                  "stored_facts": 557, "visible_facts": sum(c["rows"] for c in cards_output), "hidden_facts": 7,
                  "protected_drafts": DRAFTS, "input_files_changed": 0, "network_requests": 0,
                  "fresh_source_verification": False, "production_changed": False, "crm_runtime_installed": False,
                  "canonical_crm_save_retains_migrated_facts": True,
                  "full_gate_b_pass": False, "publication_button_ready": {uid: False for uid in DRAFTS}, "pages": checks}
        (output_root / "preview-data.json").write_text(json.dumps({"cards": cards_output}, ensure_ascii=False), encoding="utf-8")
        (output_root / "receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--prior-payload", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = prepare(args.snapshot, args.prior_payload, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "pages"}, ensure_ascii=False))
