#!/usr/bin/env python3
"""Prepare every currently published car's HTML into a new private directory.

No live HTML, databases or CRM state are written. Installation is a separate
coordinated operation. The published set comes from CRM, not a hard-coded 18.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

from ua_spec_permanent import ensure_html, owned_spans, validate_block, START, END


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def fingerprint(path):
    return {str(p): digest(p.read_bytes()) if p.exists() else None
            for p in (path, Path(str(path) + "-wal"))}


def published_snapshot(path):
    with sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True, timeout=20) as conn:
        conn.execute("PRAGMA query_only=ON")
        return conn.execute("SELECT auto_number,vin,published FROM cars WHERE published=1 ORDER BY auto_number").fetchall()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--renderer", type=Path, default=Path("/home/Carix/ua_additional_spec.py"))
    p.add_argument("--renderer-sha256", required=True)
    p.add_argument("--crm-db", type=Path, default=Path("/home/Carix/crm.db"))
    p.add_argument("--spec-db", type=Path, default=Path("/home/Carix/vin_specs_task111_v3.db"))
    p.add_argument("--page-root", type=Path, action="append")
    p.add_argument("--staging", type=Path, required=True)
    args = p.parse_args(argv)
    renderer_path, crm, db = (path.resolve(strict=True) for path in (args.renderer, args.crm_db, args.spec_db))
    require(not args.renderer.is_symlink(), "REGULAR_RENDERER_REQUIRED")
    data = renderer_path.read_bytes()
    require(digest(data) == args.renderer_sha256, "RENDERER_PIN_MISMATCH")
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("_issue84_readonly_renderer", loader=None))
    exec(compile(data, str(renderer_path), "exec"), module.__dict__)
    module.DB_PATH = module._UA110_SPEC_DB_PATH = db
    base_connect = module.connect
    def readonly_connect(readonly=True):
        require(readonly is True, "DATABASE_WRITE_FORBIDDEN")
        return base_connect(True)
    module.connect = readonly_connect
    roots = [path.resolve(strict=True) for path in (args.page_root or [Path("/home/Carix/video"), Path("/home/Carix/site")])]
    require(len({path.name for path in roots}) == len(roots), "DUPLICATE_ROOT_NAME")
    stage = args.staging.resolve()
    require(not stage.exists(), "STAGING_MUST_BE_NEW")
    require(all(stage != root and root not in stage.parents for root in roots), "STAGING_INSIDE_SOURCE_FORBIDDEN")
    before_db = fingerprint(db)
    cards = published_snapshot(crm)
    require(bool(cards) and len({row[0] for row in cards}) == len(cards), "PUBLISHED_UID_SET_INVALID")
    staged, pages, counts = [], [], {}
    css = module._css()
    for uid, _vin, _published in cards:
        rows = module.fetch_specs(uid)
        block = module.render_public_block(uid)
        cells = validate_block(block)
        expected = [(str(row["label_ru"]), module._value_with_unit(row["field_value"], row.get("unit"))) for row in rows]
        require(Counter(cells) == Counter(expected), "VISIBLE_FACT_MISMATCH:" + uid)
        counts[uid] = len(rows)
        for root in roots:
            source = root / (uid + ".html")
            require(source.is_file() and not source.is_symlink(), "REGULAR_PAGE_REQUIRED:" + str(source))
            before = source.read_bytes()
            after = ensure_html(before.decode("utf-8"), uid, renderer=lambda _uid, value=block: value, css=css).encode("utf-8")
            spans, protected = owned_spans(after.decode("utf-8"))
            actual = next(after.decode("utf-8")[left:right] for left, right, kind in spans if kind == "block")
            require(Counter(validate_block(actual)) == Counter(expected), "FINAL_FACT_MISMATCH:" + uid)
            relative = root.name + "/" + source.name
            staged.append((source, before, relative, after))
            pages.append({"uid": uid, "input": str(source), "candidate": relative,
                          "before_sha256": digest(before), "after_sha256": digest(after),
                          "protected_sha256": digest(protected.encode("utf-8")),
                          "visible_facts": len(rows), "protected_byte_changes": 0})
    require(fingerprint(db) == before_db, "SPEC_DATABASE_CHANGED_DURING_PREPARE")
    require(published_snapshot(crm) == cards, "PUBLISHED_SET_CHANGED_DURING_PREPARE")
    require(all(source.read_bytes() == before for source, before, _, _ in staged), "SOURCE_PAGE_CHANGED_DURING_PREPARE")
    report = {"mode": "PREPARE_ONLY", "task": "UA-ART-SPEC-PERSIST-18-10M-001",
              "created_at": datetime.now(timezone.utc).isoformat(), "renderer_sha256": args.renderer_sha256,
              "spec_database": before_db, "published_uids": sorted(counts),
              "visible_facts_by_uid": counts, "unique_visible_facts": sum(counts.values()),
              "page_count": len(pages), "production_writes": 0, "database_writes": 0, "pages": pages}
    stage.mkdir(mode=0o700, parents=True, exist_ok=False)
    for _, _, relative, after in staged:
        target = stage / relative
        target.parent.mkdir(mode=0o700, exist_ok=True)
        target.write_bytes(after)
        target.chmod(0o600)
    manifest = stage / "manifest.json"
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest.chmod(0o600)
    print(json.dumps({"result": "PREPARED_ONLY", "published_cards": len(cards), "pages": len(pages),
                      "unique_visible_facts": sum(counts.values()), "staging": str(stage), "production_writes": 0}))


if __name__ == "__main__":
    main()
