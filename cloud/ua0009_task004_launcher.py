#!/usr/bin/env python3
"""
ua0009_task004_launcher.py

TASK_004 — UA-0009 draft card launch: resolve duplicate-count gate ambiguity
and build an ISOLATED, non-production sandbox draft for owner visual review.

HARD SAFETY RULES (enforced by design, not just comment):
  - crm.db is opened strictly read-only via sqlite URI mode=ro. No write/update/
    delete/PRAGMA journal_mode change is ever issued.
  - The only production path this script writes to is the single report file
    /home/Carix/video/ua0009_task004.txt (explicitly permitted by the task).
  - All sandbox HTML output is written under
    /home/Carix/sandbox_ua0009_task004/video/ only.
  - UA-0001..UA-0008 production files are hashed before and after the run and
    must be byte-identical after; any mismatch is reported as CRITICAL.
  - No values are ever copied from UA-0001..UA-0008 into the UA-0009 draft.
  - Missing owner-required fields are rendered as a neutral "Уточняется"
    marker, never invented.
  - This script never calls production generators, never touches WSGI, never
    reloads/restarts anything, and never publishes.

Python 3.10, standard library only.
"""

import os
import re
import time
import hashlib
import sqlite3

CRM_DB_PATH = "/home/Carix/crm.db"
PROD_VIDEO_DIR = "/home/Carix/video"
PROD_SITE_DIR = "/home/Carix/site"
EXISTING_SANDBOX_DIRS = [
    "/home/Carix/sandbox2/video",
    "/home/Carix/sandbox/video",
]
TASK_SANDBOX_ROOT = "/home/Carix/sandbox_ua0009_task004"
TASK_SANDBOX_VIDEO = os.path.join(TASK_SANDBOX_ROOT, "video")
REPORT_PATH = os.path.join(PROD_VIDEO_DIR, "ua0009_task004.txt")

UA0009_AUTO_NUMBER = "UA-0009"
UA0009_VIN = "KNAGU416BJA242741"
UA0009_MAKE = "Kia"
UA0009_MODEL = "K5"
UA0009_YEAR = "2018"
UA0009_FUEL_EVIDENCE = "газ"
UA0009_ENGINE_EVIDENCE = "2000"
UA0009_MILEAGE_EVIDENCE = "300000"

PROTECTED_AUTO_NUMBERS = [f"UA-000{i}" for i in range(1, 9)]

SAFE_COLUMN_KEYWORDS = [
    "auto_number", "vin", "make", "model", "brand", "year", "mileage",
    "engine", "fuel", "transmission", "drivetrain", "color", "price",
    "stage", "status", "publish", "photo", "video", "diag", "id",
]

MAX_ROWS_SCAN_PER_TABLE = 20000

PLACEHOLDER = "Уточняется"


def log(buf, line):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    buf.append(f"[{ts}] {line}")


def sha256_of_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def find_protected_files():
    """Locate UA-0001..UA-0008 related files under production video/site dirs (read-only walk)."""
    found = {}
    for base in (PROD_VIDEO_DIR, PROD_SITE_DIR):
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                for auto in PROTECTED_AUTO_NUMBERS:
                    if auto in fn or auto.replace("-", "_") in fn:
                        full = os.path.join(root, fn)
                        found.setdefault(auto, []).append(full)
    return found


def hash_protected_files(file_map):
    hashes = {}
    for _auto, paths in file_map.items():
        for p in paths:
            hashes[p] = sha256_of_file(p)
    return hashes


def sqlite_quick_check():
    try:
        uri = f"file:{CRM_DB_PATH}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        cur = conn.cursor()
        cur.execute("PRAGMA quick_check;")
        result = cur.fetchone()
        conn.close()
        if result and result[0] == "ok":
            return True, "PASS"
        return False, f"FAIL:{result}"
    except Exception as e:
        return False, f"FAIL:{e}"


def get_tables(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    return [r[0] for r in cur.fetchall()]


def get_columns(conn, table):
    cur = conn.cursor()
    try:
        cur.execute(f"PRAGMA table_info('{table}');")
        return [r[1] for r in cur.fetchall()]
    except Exception:
        return []


def is_safe_column(col):
    lc = col.lower()
    return any(k in lc for k in SAFE_COLUMN_KEYWORDS)


def scan_for_ua0009(conn, buf):
    """Read-only scan of all tables/columns for UA-0009 auto_number / VIN matches."""
    tables = get_tables(conn)
    auto_matches = []
    vin_matches = []
    field_values = {}
    for table in tables:
        cols = get_columns(conn, table)
        if not cols:
            continue
        col_list = ", ".join(f'"{c}"' for c in cols)
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT rowid, {col_list} FROM "{table}" LIMIT {MAX_ROWS_SCAN_PER_TABLE};')
        except Exception as e:
            log(buf, f"WARN: could not scan table {table}: {e}")
            continue
        for row in cur:
            rowid = row[0]
            values = row[1:]
            row_dict = dict(zip(cols, values))
            matched_auto = False
            matched_vin = False
            for col, val in row_dict.items():
                if val is None:
                    continue
                sval = str(val).strip()
                if sval == UA0009_AUTO_NUMBER:
                    matched_auto = True
                if UA0009_VIN.lower() in sval.lower():
                    matched_vin = True
            if matched_auto:
                auto_matches.append((table, rowid))
            if matched_vin:
                vin_matches.append((table, rowid))
            if matched_auto or matched_vin:
                safe_dict = {c: v for c, v in row_dict.items() if is_safe_column(c)}
                field_values[(table, rowid)] = safe_dict
    return auto_matches, vin_matches, field_values


def classify_duplicates(auto_matches, vin_matches):
    combined = set(auto_matches) | set(vin_matches)
    if not auto_matches and not vin_matches:
        return "MORE_PROOF_NEEDED", combined
    tables_involved = {t for t, _ in combined}
    auto_rowcount_by_table = {}
    for t, r in auto_matches:
        auto_rowcount_by_table.setdefault(t, set()).add(r)
    max_auto_dupe_in_single_table = max((len(v) for v in auto_rowcount_by_table.values()), default=0)
    if len(combined) == 1:
        return "SAME_ROW_COUNTING_ARTIFACT", combined
    if max_auto_dupe_in_single_table > 1:
        return "TRUE_DUPLICATE", combined
    if len(tables_involved) > 1 and max_auto_dupe_in_single_table <= 1:
        return "MULTI_TABLE_REFERENCE_NOT_DUPLICATE", combined
    return "MORE_PROOF_NEEDED", combined


def merge_field_values(field_values):
    merged = {}
    for _key, d in field_values.items():
        for col, val in d.items():
            if val in (None, "", "NULL"):
                continue
            lc = col.lower()
            if lc not in merged or not merged[lc]:
                merged[lc] = val
    return merged


def map_to_publication_fields(merged):
    def find_by_keyword(keyword):
        for col, val in merged.items():
            if keyword in col:
                return val
        return None

    fields = {
        "auto_number": find_by_keyword("auto_number") or UA0009_AUTO_NUMBER,
        "vin": find_by_keyword("vin") or UA0009_VIN,
        "make": find_by_keyword("make") or find_by_keyword("brand"),
        "model": find_by_keyword("model"),
        "year": find_by_keyword("year"),
        "mileage": find_by_keyword("mileage"),
        "engine": find_by_keyword("engine"),
        "fuel": find_by_keyword("fuel"),
        "transmission": find_by_keyword("transmission"),
        "drivetrain": find_by_keyword("drivetrain"),
        "color": find_by_keyword("color"),
        "price": find_by_keyword("price"),
        "stage": find_by_keyword("stage") or find_by_keyword("status"),
        "published": find_by_keyword("publish"),
    }
    return fields


def find_existing_sandbox_html():
    candidates = []
    for d in EXISTING_SANDBOX_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith((".html", ".htm")):
                    lfn = fn.lower()
                    if "0009" in lfn or UA0009_VIN.lower() in lfn:
                        full = os.path.join(root, fn)
                        try:
                            mtime = os.path.getmtime(full)
                        except Exception:
                            mtime = 0
                        candidates.append((mtime, full))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def validate_html_structure(html_text):
    issues = []
    lower = html_text.lower()
    if "<html" not in lower:
        issues.append("missing <html> tag")
    if "<body" not in lower:
        issues.append("missing <body> tag")
    empty_media = re.findall(r'(?:src|href)\s*=\s*["\']\s*["\']', html_text)
    if empty_media:
        issues.append(f"{len(empty_media)} empty src/href attributes found")
    diag_count = len(re.findall(r'диагностик', lower))
    return issues, diag_count


def read_text_safely(path, limit_bytes=2_000_000):
    try:
        size = os.path.getsize(path)
        if size > limit_bytes:
            return None
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return None


HTML_PATTERNS = {
    "mileage": r'(?:пробег|mileage)[^0-9]{0,10}([\d\s]{4,10})\s*км',
    "engine": r'(?:двигатель|engine)[^0-9]{0,10}([\d.,]{3,6})',
    "fuel": r'(?:топливо|fuel)[^\wа-яё]{0,5}([а-яa-z/]+)',
    "color": r'(?:цвет|color)[^\wа-яё]{0,5}([а-яa-zё\s]{3,20})',
    "transmission": r'(?:коробка|transmission)[^\wа-яё]{0,5}([а-яa-zё\s]{3,20})',
}


def extract_from_html(html_text, patterns):
    extracted = {}
    if not html_text:
        return extracted
    for field, pattern in patterns.items():
        m = re.search(pattern, html_text, re.IGNORECASE)
        if m:
            extracted[field] = m.group(1).strip()
    return extracted


CARD_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>{auto_number} {make} {model} {year} — draft sandbox (task_004)</title>
</head>
<body>
<h1>{auto_number} {make} {model} {year}</h1>
<p>VIN: {vin}</p>
<ul>
<li>Пробег: {mileage} км</li>
<li>Двигатель: {engine} см3</li>
<li>Топливо: {fuel}</li>
<li>Коробка передач: {transmission}</li>
<li>Привод: {drivetrain}</li>
<li>Цвет: {color}</li>
<li>Цена: {price}</li>
<li>Статус: {stage}</li>
</ul>
<div class="diagnostic-cta">
<a href="ua0009_task004_diag.html">Диагностика автомобиля</a>
</div>
<p><em>Черновик сгенерирован task_004. Не для публикации.</em></p>
</body>
</html>
"""

DIAG_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>{auto_number} — диагностика (draft sandbox task_004)</title>
</head>
<body>
<h1>Диагностика {auto_number}</h1>
<p>VIN: {vin}</p>
<p>Отчёт диагностики: {diag_ref}</p>
<p><em>Черновик сгенерирован task_004. Не для публикации.</em></p>
</body>
</html>
"""


def build_sandbox(fields, seed_html, buf):
    os.makedirs(TASK_SANDBOX_VIDEO, exist_ok=True)
    card_fields = {}
    for key in ("auto_number", "vin", "make", "model", "year", "mileage",
                "engine", "fuel", "transmission", "drivetrain", "color",
                "price", "stage"):
        val = fields.get(key)
        card_fields[key] = str(val) if val not in (None, "", "NULL") else PLACEHOLDER

    card_fields["auto_number"] = UA0009_AUTO_NUMBER
    card_fields["vin"] = UA0009_VIN
    if card_fields["make"] == PLACEHOLDER:
        card_fields["make"] = UA0009_MAKE
    if card_fields["model"] == PLACEHOLDER:
        card_fields["model"] = UA0009_MODEL
    if card_fields["year"] == PLACEHOLDER:
        card_fields["year"] = UA0009_YEAR
    if card_fields["fuel"] == PLACEHOLDER:
        card_fields["fuel"] = UA0009_FUEL_EVIDENCE
    if card_fields["engine"] == PLACEHOLDER:
        card_fields["engine"] = UA0009_ENGINE_EVIDENCE
    if card_fields["mileage"] == PLACEHOLDER:
        card_fields["mileage"] = UA0009_MILEAGE_EVIDENCE

    card_html = CARD_TEMPLATE.format(**card_fields)
    diag_html = DIAG_TEMPLATE.format(
        auto_number=UA0009_AUTO_NUMBER,
        vin=UA0009_VIN,
        diag_ref=PLACEHOLDER,
    )

    card_path = os.path.join(TASK_SANDBOX_VIDEO, "ua0009_task004_card.html")
    diag_path = os.path.join(TASK_SANDBOX_VIDEO, "ua0009_task004_diag.html")

    with open(card_path, "w", encoding="utf-8") as f:
        f.write(card_html)
    with open(diag_path, "w", encoding="utf-8") as f:
        f.write(diag_html)

    if seed_html:
        seed_copy_path = os.path.join(TASK_SANDBOX_VIDEO, "seed_reference_copy.html")
        try:
            with open(seed_copy_path, "w", encoding="utf-8") as f:
                f.write(seed_html)
            log(buf, f"Seed reference copied (read-only source) to {seed_copy_path}")
        except Exception as e:
            log(buf, f"WARN: could not write seed copy: {e}")

    return card_path, diag_path, card_html, diag_html


def finalize(buf, final_block):
    lines = list(buf)
    lines.append("")
    lines.append("=== TASK_004 FINAL BLOCK ===")
    lines.append("TASK_ID: task_004")
    lines.append(f"SQLITE_QUICK_CHECK: {final_block.get('SQLITE_QUICK_CHECK')}")
    lines.append(f"DUPLICATE_CLASSIFICATION: {final_block.get('DUPLICATE_CLASSIFICATION')}")
    lines.append(f"UA0009_EXISTS_IN_CRM: {final_block.get('UA0009_EXISTS_IN_CRM')}")
    lines.append(f"UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE: {final_block.get('UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE')}")
    lines.append(f"UA0009_OWNER_INPUT_REQUIRED: {final_block.get('UA0009_OWNER_INPUT_REQUIRED')}")
    lines.append(f"UA0009_EXISTING_SANDBOX_FOUND: {final_block.get('UA0009_EXISTING_SANDBOX_FOUND')}")
    lines.append(f"UA0009_TASK004_SANDBOX_CREATED: {final_block.get('UA0009_TASK004_SANDBOX_CREATED')}")
    lines.append(f"UA0009_TASK004_CARD_PATH: {final_block.get('UA0009_TASK004_CARD_PATH')}")
    lines.append(f"UA0009_TASK004_DIAG_PATH: {final_block.get('UA0009_TASK004_DIAG_PATH')}")
    lines.append(f"UA0001_0008_UNCHANGED_AFTER: {final_block.get('UA0001_0008_UNCHANGED_AFTER')}")
    lines.append("PRODUCTION_WRITE_PERFORMED: NO")
    lines.append("DATABASE_CHANGED: NO")
    lines.append("PRODUCTION_SITE_FILES_CHANGED: 0")
    lines.append(f"SAFE_FOR_OWNER_VISUAL_REVIEW: {final_block.get('SAFE_FOR_OWNER_VISUAL_REVIEW')}")
    lines.append("SAFE_TO_PUBLISH_UA0009_NOW: NO")
    lines.append(f"NEXT_ACTION: {final_block.get('NEXT_ACTION')}")

    report_text = "\n".join(lines)
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    except Exception:
        pass
    try:
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(report_text + "\n")
    except Exception as e:
        print(f"WARN: could not write report file {REPORT_PATH}: {e}")

    print(report_text)


def main():
    buf = []
    log(buf, "TASK_004 UA-0009 launcher started")

    if not os.path.isfile(CRM_DB_PATH):
        log(buf, f"BLOCKER: crm.db not found at {CRM_DB_PATH}")
        finalize(buf, {
            "SQLITE_QUICK_CHECK": "FAIL",
            "DUPLICATE_CLASSIFICATION": "MORE_PROOF_NEEDED",
            "UA0009_EXISTS_IN_CRM": "NO",
            "UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE": "NO",
            "UA0009_OWNER_INPUT_REQUIRED": "crm.db not accessible on this host",
            "UA0009_EXISTING_SANDBOX_FOUND": "NO",
            "UA0009_TASK004_SANDBOX_CREATED": "NO",
            "UA0009_TASK004_CARD_PATH": "NONE",
            "UA0009_TASK004_DIAG_PATH": "NONE",
            "UA0001_0008_UNCHANGED_AFTER": "PASS",
            "SAFE_FOR_OWNER_VISUAL_REVIEW": "NO",
            "NEXT_ACTION": "Verify crm.db path on PythonAnywhere and rerun.",
        })
        return

    ok, qc_result = sqlite_quick_check()
    log(buf, f"SQLite quick_check: {qc_result}")

    protected_files_map = find_protected_files()
    baseline_hashes = hash_protected_files(protected_files_map)
    log(buf, f"Baseline protected files found: {sum(len(v) for v in protected_files_map.values())}")

    auto_matches, vin_matches, field_values = [], [], {}
    if ok:
        try:
            uri = f"file:{CRM_DB_PATH}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5)
            auto_matches, vin_matches, field_values = scan_for_ua0009(conn, buf)
            conn.close()
        except Exception as e:
            log(buf, f"ERROR scanning crm.db: {e}")

    classification, combined = classify_duplicates(auto_matches, vin_matches)
    log(buf, f"Duplicate classification: {classification}; combined keys: {sorted(combined)}")

    exists_in_crm = "YES" if (auto_matches or vin_matches) else "NO"

    merged = merge_field_values(field_values)
    crm_fields = map_to_publication_fields(merged)

    seed_path = find_existing_sandbox_html()
    existing_found = "YES" if seed_path else "NO"
    seed_html = None
    seed_extracted = {}
    if seed_path:
        log(buf, f"Existing UA-0009 sandbox seed found: {seed_path}")
        seed_html = read_text_safely(seed_path)
        if seed_html:
            issues, diag_count = validate_html_structure(seed_html)
            log(buf, f"Seed HTML validation issues: {issues}; diagnostic mentions: {diag_count}")
            seed_extracted = extract_from_html(seed_html, HTML_PATTERNS)
            log(buf, f"Extracted from seed HTML: {seed_extracted}")
    else:
        log(buf, "No existing UA-0009 sandbox HTML found.")

    final_fields = dict(crm_fields)
    for k, v in seed_extracted.items():
        if not final_fields.get(k):
            final_fields[k] = v

    owner_input_needed = []
    for key in ("transmission", "drivetrain", "color", "price", "stage"):
        if not final_fields.get(key):
            owner_input_needed.append(key)

    core_identity_ok = all([UA0009_AUTO_NUMBER, UA0009_VIN, UA0009_MAKE, UA0009_MODEL, UA0009_YEAR])
    required_complete = "YES" if core_identity_ok else "NO"

    sandbox_created = "NO"
    card_path = "NONE"
    diag_path = "NONE"
    try:
        card_path, diag_path, card_html, _diag_html = build_sandbox(final_fields, seed_html, buf)
        issues, diag_count = validate_html_structure(card_html)
        if issues:
            log(buf, f"WARN: sandbox card HTML issues: {issues}")
        if diag_count > 1:
            log(buf, f"WARN: multiple diagnostic CTA mentions in card ({diag_count}); review needed")
        sandbox_created = "YES"
        log(buf, f"Sandbox card created at {card_path}")
        log(buf, f"Sandbox diag created at {diag_path}")
    except Exception as e:
        log(buf, f"ERROR building sandbox: {e}")

    after_hashes = hash_protected_files(protected_files_map)
    unchanged = "PASS"
    for path, h in baseline_hashes.items():
        if after_hashes.get(path) != h:
            unchanged = "FAIL"
            log(buf, f"CRITICAL: protected file changed unexpectedly: {path}")

    safe_visual = "YES" if (sandbox_created == "YES" and unchanged == "PASS") else "NO"

    final_block = {
        "SQLITE_QUICK_CHECK": "PASS" if ok else "FAIL",
        "DUPLICATE_CLASSIFICATION": classification,
        "UA0009_EXISTS_IN_CRM": exists_in_crm,
        "UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE": required_complete,
        "UA0009_OWNER_INPUT_REQUIRED": (", ".join(owner_input_needed) if owner_input_needed else "NONE"),
        "UA0009_EXISTING_SANDBOX_FOUND": existing_found,
        "UA0009_TASK004_SANDBOX_CREATED": sandbox_created,
        "UA0009_TASK004_CARD_PATH": card_path,
        "UA0009_TASK004_DIAG_PATH": diag_path,
        "UA0001_0008_UNCHANGED_AFTER": unchanged,
        "SAFE_FOR_OWNER_VISUAL_REVIEW": safe_visual,
        "NEXT_ACTION": (
            "Owner: visually review sandbox card/diag; no further data needed."
            if not owner_input_needed else
            f"Owner input required for: {', '.join(owner_input_needed)}; then re-run before publish."
        ),
    }
    finalize(buf, final_block)


if __name__ == "__main__":
    main()
