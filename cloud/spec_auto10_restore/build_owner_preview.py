"""Build a non-interactive full-card layout Preview from the pinned snapshot.

The isolated iframe cannot submit forms or execute the original CRM scripts.
This is a view of saved HTML and confirmed stored facts, not a production page.
"""
from pathlib import Path
import argparse
import hashlib
import html
import json
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "runtime"))
import spec_publication
import card_shell


def build(snapshot_root, spec_db, output):
    source_path = Path(snapshot_root) / "video/UA-0010.html"
    source_bytes = source_path.read_bytes()
    snapshot = json.loads((Path(snapshot_root) / "snapshot_manifest.json").read_text())
    entry = next(e for e in snapshot["entries"] if e["path"] == "video/UA-0010.html")
    if hashlib.sha256(source_bytes).hexdigest() != entry["sha256"]:
        raise RuntimeError("SOURCE_SNAPSHOT_MISMATCH")
    conn = sqlite3.connect(Path(spec_db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        facts = [dict(row) for row in conn.execute('''
            SELECT a.*,m.label_ru,m.category,m.unit,m.verification_status,m.is_manual,m.is_visible
            FROM additional_specification a JOIN additional_specification_meta m
            ON a.car_uid=m.car_uid AND a.field_key=m.field_key
            WHERE a.car_uid='UA-0010' ORDER BY a.field_key
        ''')]
    finally:
        conn.close()
    expected = next(c for c in json.loads((HERE / "evidence/verified-specs.json").read_text())["cards"]
                    if c["uid"] == "UA-0010")
    if spec_publication.render_block("UA-0010", facts) != expected["spec_html"]:
        raise RuntimeError("STORED_FACTS_DIFFER_FROM_VERIFIED_DATASET")
    before = source_bytes.decode("utf-8")
    after = spec_publication.inject(before, "UA-0010", facts)
    card_shell.permitted_delta(before, after, "UA-0010")
    checked = card_shell.validate_one_visible_vin(after, "UA-0010")
    card_shell.validate_shell_assets(before, after)
    # Base URL is a presentation-only addition; it is absent from the candidate.
    display = after.replace("<head>", '<head><base href="https://www.uaart.com.ua/video/">', 1)
    body = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UA ART — полная карточка Preview</title><style>
    *{box-sizing:border-box}body{margin:0;background:#0b1723;color:#edf2f8;font:16px/1.5 system-ui,sans-serif}header{max-width:1000px;margin:auto;padding:16px}a{color:#e6b864}p{margin:8px 0}iframe{display:block;width:100%;height:calc(100dvh - 170px);min-height:600px;border:0;background:#0b1723}strong{color:#f2b54b}
    </style></head><body><header><a href="/">← Все 16 спецификаций</a><p><strong>UA-0010: один VIN и дополнительная спецификация</strong></p><p>Это копия сохранённой карточки с прежним оформлением. Прокрутите к техническим данным и нажмите «Переглянути характеристики». На рабочем сайте обновление ещё не установлено.</p></header><iframe title="Полная карточка UA-0010 — проверочная копия" sandbox srcdoc="FRAME"></iframe></body></html>'''
    Path(output).write_text(body.replace("FRAME", html.escape(display, quote=True)), encoding="utf-8")
    return {"status": "PASS_LAYOUT_PREVIEW_ONLY", "uid": "UA-0010", "rows": expected["rows"],
            "visible_vin_check": checked, "candidate_sha256": hashlib.sha256(after.encode()).hexdigest(),
            "saved_snapshot_sha256": entry["sha256"], "original_scripts_sandboxed": True,
            "production_changed": False, "fresh_source_verification": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--spec-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.snapshot_root, args.spec_db, args.output), ensure_ascii=False))
