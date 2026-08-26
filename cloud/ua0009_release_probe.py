#!/usr/bin/env python3
"""
UA-0009 RELEASE GATE PROBE (task_003)
======================================

STRICTLY READ-ONLY against UA ART production.

What this script does:
  1. SQLite stability decision inputs (journal_mode, quick_check, busy_timeout
     evidence from source text, connection-lifetime evidence in stroy3.py /
     stranica.py).
  2. UA-0009 CRM completeness audit (field presence classification, VIN /
     auto_number duplicate counts).
  3. UA-0009 sandbox readiness audit (locate UA-0001..UA-0008 public files,
     locate any UA-0009 public files, locate generator/source evidence,
     compute bounded SHA-256 baseline for UA-0001..UA-0008 protected files).

Hard guarantees:
  - Opens crm.db ONLY with sqlite3 URI mode=ro ("file:...?mode=ro").
  - Never executes INSERT / UPDATE / DELETE / PRAGMA journal_mode=... (write
    forms). Only ever reads PRAGMA values (which is a SELECT-style read, not
    a write, when no value is assigned).
  - Never imports UA ART application modules (no `import stroy3`, no
    `import stranica`, no Flask/Django app import). Source files are opened
    as plain text and scanned with regex only.
  - Never prints secrets, tokens, private keys, raw customer PII outside the
    UA-0009 record, or any DB blob / base64 payload. Media/list fields are
    reported as counts + safe filenames only.
  - The ONLY filesystem write performed anywhere by this script is the
    single output report file at OUTPUT_PATH. No other file, directory
    (besides the parent of OUTPUT_PATH), or database is ever written.

Candidate paths below are best-effort guesses about the PythonAnywhere
layout. The script is tolerant of missing paths: every candidate that does
not exist is logged as PATH_NOT_FOUND and skipped. If your real production
layout differs, edit the *_CANDIDATES lists below (still read-only) and
re-run. This script performs no destructive actions regardless of which
candidates resolve.

Usage (on PythonAnywhere, in a bash console):
    python3 ua0009_release_probe.py

Output:
    /home/Carix/video/ua0009_release_gate.txt   (created/overwritten only)
    Also mirrored to stdout.
"""

import os
import re
import sys
import sqlite3
import hashlib
import traceback
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# CONFIG - candidate production paths (read-only probing, edit if needed)
# ---------------------------------------------------------------------------

OUTPUT_PATH = "/home/Carix/video/ua0009_release_gate.txt"

DB_CANDIDATES = [
    "/home/Carix/crm.db",
    "/home/Carix/mysite/crm.db",
    "/home/Carix/ua_art/crm.db",
    "/home/Carix/UA_ART/crm.db",
    "/home/Carix/db/crm.db",
]

SOURCE_CANDIDATES = {
    "stroy3.py": [
        "/home/Carix/stroy3.py",
        "/home/Carix/mysite/stroy3.py",
        "/home/Carix/ua_art/stroy3.py",
        "/home/Carix/UA_ART/stroy3.py",
    ],
    "stranica.py": [
        "/home/Carix/stranica.py",
        "/home/Carix/mysite/stranica.py",
        "/home/Carix/ua_art/stranica.py",
        "/home/Carix/UA_ART/stranica.py",
    ],
}

# Candidate public/static directories where UA-000X card/site/diag files may live
PUBLIC_DIR_CANDIDATES = [
    "/home/Carix/mysite/static",
    "/home/Carix/mysite/static/cards",
    "/home/Carix/mysite/cards",
    "/home/Carix/static",
    "/home/Carix/public",
    "/home/Carix/mysite/public",
    "/home/Carix/video",
]

# Recognized car ids for baseline
BASELINE_IDS = [f"UA-000{n}" for n in range(1, 9)]  # UA-0001..UA-0008
TARGET_ID_VARIANTS = ["UA-0009", "UA0009", "0009", "9"]

# CRM field name candidates we look for in schema (case-insensitive substrings)
FIELD_PATTERNS = {
    "auto_number": ["auto_number", "autonumber", "car_number", "number"],
    "vin": ["vin"],
    "make": ["make", "brand", "marka"],
    "model": ["model"],
    "year": ["year", "god"],
    "mileage": ["mileage", "probeg", "odometer"],
    "engine": ["engine", "dvigatel"],
    "fuel": ["fuel", "toplivo"],
    "transmission": ["transmission", "korobka", "gearbox"],
    "drivetrain": ["drivetrain", "privod", "drive"],
    "color": ["color", "colour", "cvet"],
    "price": ["price", "cena", "cost"],
    "stage": ["stage", "status", "stadiya"],
    "published": ["published", "is_published", "public"],
    "photos": ["photo", "image", "foto"],
    "videos": ["video"],
    "diagnostic": ["diag", "diagnostic", "diagnostika"],
}

MAX_FILE_HASH_BYTES = 25 * 1024 * 1024  # 25MB bound per file for sha256 baseline
MAX_FILES_PER_ID = 30  # bound to keep the probe fast/safe

# ---------------------------------------------------------------------------

lines = []  # report buffer


def log(section, text=""):
    lines.append(f"[{section}] {text}" if text else f"[{section}]")


def hr(title):
    lines.append("")
    lines.append("=" * 78)
    lines.append(title)
    lines.append("=" * 78)


def find_first_existing(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def find_first_existing_dir(paths):
    out = []
    for p in paths:
        if p and os.path.isdir(p):
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# TRACK 1: SQLite stability
# ---------------------------------------------------------------------------

def probe_sqlite(db_path):
    result = {
        "db_path": db_path,
        "quick_check": None,
        "journal_mode": None,
        "error": None,
    }
    if not db_path:
        result["error"] = "NO_DB_CANDIDATE_FOUND"
        return result
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        cur = conn.cursor()
        cur.execute("PRAGMA quick_check;")
        qc = cur.fetchall()
        result["quick_check"] = "; ".join(str(r[0]) for r in qc) if qc else "UNKNOWN"
        cur.execute("PRAGMA journal_mode;")
        jm = cur.fetchone()
        result["journal_mode"] = jm[0] if jm else "UNKNOWN"
        conn.close()
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def scan_source_for_sqlite_evidence(name, path):
    """Pure text scan. No import, no execution."""
    evidence = {
        "path": path,
        "busy_timeout": [],
        "connect_calls": 0,
        "close_calls": 0,
        "select_or_fetch": 0,
        "long_ops_hint": [],
        "error": None,
    }
    if not path:
        evidence["error"] = "PATH_NOT_FOUND"
        return evidence
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        evidence["error"] = f"{type(e).__name__}: {e}"
        return evidence

    for m in re.finditer(r"busy_timeout\s*=?\s*\(?\s*(\d+)", text, re.IGNORECASE):
        evidence["busy_timeout"].append(m.group(1))
    for m in re.finditer(r"PRAGMA\s+busy_timeout\s*=\s*(\d+)", text, re.IGNORECASE):
        evidence["busy_timeout"].append(m.group(1))

    evidence["connect_calls"] = len(re.findall(r"sqlite3\.connect\s*\(", text))
    evidence["close_calls"] = len(re.findall(r"\.close\s*\(\s*\)", text))
    evidence["select_or_fetch"] = len(
        re.findall(r"(SELECT\s|\.fetchone\(|\.fetchall\(|\.fetchmany\()", text, re.IGNORECASE)
    )

    # Heuristic: look for time-consuming calls (requests, sleep, subprocess,
    # PIL image ops, ffmpeg, moviepy) that appear textually AFTER a connect()
    # but BEFORE the matching close(), suggesting the connection/cursor is
    # held open during long external work (evidence FOR early-close fix).
    long_op_markers = ["requests.", "time.sleep", "subprocess.", "moviepy", "ffmpeg", "Image.open", "urlopen"]
    connect_positions = [m.start() for m in re.finditer(r"sqlite3\.connect\s*\(", text)]
    close_positions = [m.start() for m in re.finditer(r"\.close\s*\(\s*\)", text)]
    for cpos in connect_positions:
        # find the nearest close after this connect
        nxt_close = min([p for p in close_positions if p > cpos], default=None)
        window_end = nxt_close if nxt_close is not None else min(cpos + 4000, len(text))
        window = text[cpos:window_end]
        for marker in long_op_markers:
            if marker in window:
                lineno = text.count("\n", 0, cpos) + 1
                evidence["long_ops_hint"].append(f"connect@line{lineno}:contains:{marker}")

    return evidence


# ---------------------------------------------------------------------------
# TRACK 2: UA-0009 CRM completeness
# ---------------------------------------------------------------------------

def discover_schema(conn):
    cur = conn.cursor()
    cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
    tables = cur.fetchall()
    schema = {}
    for name, sql in tables:
        try:
            cur.execute(f"PRAGMA table_info('{name}')")
            cols = [r[1] for r in cur.fetchall()]
        except Exception:
            cols = []
        schema[name] = {"sql": sql or "", "columns": cols}
    return schema


def guess_vehicle_table(schema):
    """Find table most likely holding vehicle/CRM records (has auto_number-like
    or vin-like column)."""
    best = None
    best_score = -1
    for tname, meta in schema.items():
        cols_lower = [c.lower() for c in meta["columns"]]
        score = 0
        for field, patterns in FIELD_PATTERNS.items():
            for p in patterns:
                if any(p in c for c in cols_lower):
                    score += 1
                    break
        if score > best_score:
            best_score = score
            best = tname
    return best, best_score


def map_columns(schema, table):
    cols = schema[table]["columns"]
    cols_lower = {c.lower(): c for c in cols}
    mapping = {}
    for field, patterns in FIELD_PATTERNS.items():
        found = None
        for p in patterns:
            for cl, orig in cols_lower.items():
                if p in cl:
                    found = orig
                    break
            if found:
                break
        mapping[field] = found
    return mapping


SAFE_MEDIA_EXT = re.compile(r"\.(jpg|jpeg|png|webp|gif|mp4|mov|avi|pdf|txt)$", re.IGNORECASE)


def safe_repr_value(field, value):
    """Return a safe string representation: counts for media/list fields,
    plain values otherwise. Never print blobs/base64."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return f"<binary {len(value)} bytes - not printed>"
    text = str(value)
    if len(text) > 2000 and ("base64" in text.lower() or re.match(r"^[A-Za-z0-9+/=]{500,}$", text)):
        return "<large-encoded-payload - not printed>"
    if field in ("photos", "videos", "diagnostic"):
        # try to split as list of paths/filenames
        parts = re.split(r"[,;\n\|]", text)
        parts = [os.path.basename(p.strip()) for p in parts if p.strip()]
        return f"count={len(parts)} files={parts[:10]}" + (" ..." if len(parts) > 10 else "")
    if len(text) > 300:
        return text[:300] + "...<truncated>"
    return text


def audit_ua0009(conn, schema):
    table, score = guess_vehicle_table(schema)
    audit = {
        "table": table,
        "table_confidence_score": score,
        "exists": False,
        "row": {},
        "classification": {},
        "vin_duplicates": 0,
        "auto_number_duplicates": 0,
        "error": None,
    }
    if not table:
        audit["error"] = "NO_CANDIDATE_TABLE_FOUND"
        return audit

    mapping = map_columns(schema, table)
    audit["column_mapping"] = mapping
    auto_col = mapping.get("auto_number")
    vin_col = mapping.get("vin")

    cur = conn.cursor()
    row = None
    used_col = None
    used_val = None
    if auto_col:
        for variant in TARGET_ID_VARIANTS:
            try:
                cur.execute(f"SELECT * FROM '{table}' WHERE \"{auto_col}\" = ? LIMIT 1", (variant,))
                r = cur.fetchone()
                if r:
                    row = r
                    used_col = auto_col
                    used_val = variant
                    break
            except Exception:
                continue
    if not row and vin_col:
        # cannot guess VIN value; skip VIN-based lookup without owner data
        pass

    if row:
        colnames = [d[0] for d in cur.description]
        audit["exists"] = True
        rowdict = dict(zip(colnames, row))
        audit["matched_by"] = f"{used_col}={used_val}"
        for field, col in mapping.items():
            if col and col in rowdict:
                val = rowdict[col]
                safe_val = safe_repr_value(field, val)
                present = val is not None and str(val).strip() != ""
                audit["row"][field] = safe_val
                if present:
                    audit["classification"][field] = "PRESENT"
                else:
                    audit["classification"][field] = "MISSING"
            else:
                audit["row"][field] = None
                audit["classification"][field] = "MISSING_COLUMN_NOT_FOUND"

        # Fields that are typically owner-supplied and cannot be safely derived
        owner_required_candidates = ["vin", "mileage", "price", "color", "photos", "videos", "diagnostic"]
        for f in owner_required_candidates:
            if audit["classification"].get(f) in ("MISSING", "MISSING_COLUMN_NOT_FOUND"):
                audit["classification"][f] = "OWNER_INPUT_REQUIRED"

        # published/stage could sometimes be derived (default to draft) - flag as derivable
        for f in ["published", "stage"]:
            if audit["classification"].get(f) in ("MISSING", "MISSING_COLUMN_NOT_FOUND"):
                audit["classification"][f] = "CAN_DERIVE_SAFELY_FROM_EXISTING_UA0009_DATA"

        # duplicate checks
        if vin_col and rowdict.get(vin_col):
            vin_val = rowdict[vin_col]
            try:
                cur.execute(f"SELECT COUNT(*) FROM '{table}' WHERE \"{vin_col}\" = ?", (vin_val,))
                cnt = cur.fetchone()[0]
                audit["vin_duplicates"] = max(0, cnt - 1)
            except Exception:
                pass
        if auto_col:
            try:
                cur.execute(f"SELECT COUNT(*) FROM '{table}' WHERE \"{auto_col}\" = ?", (used_val,))
                cnt = cur.fetchone()[0]
                audit["auto_number_duplicates"] = max(0, cnt - 1)
            except Exception:
                pass
    else:
        audit["error"] = "UA0009_ROW_NOT_FOUND"

    return audit


# ---------------------------------------------------------------------------
# TRACK 3: Sandbox readiness
# ---------------------------------------------------------------------------

def sha256_of_file(path, max_bytes=MAX_FILE_HASH_BYTES):
    try:
        size = os.path.getsize(path)
        if size > max_bytes:
            return f"SKIPPED_TOO_LARGE({size}bytes)"
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    except Exception as e:
        return f"ERROR:{type(e).__name__}"


def find_id_files(public_dirs, car_id):
    matches = []
    id_variants = [car_id, car_id.replace("-", ""), car_id.lower(), car_id.replace("-", "").lower()]
    for d in public_dirs:
        try:
            for root, dirs, files in os.walk(d):
                # bound walk depth
                depth = root[len(d):].count(os.sep)
                if depth > 4:
                    dirs[:] = []
                    continue
                for fn in files:
                    if any(v in fn for v in id_variants):
                        matches.append(os.path.join(root, fn))
                        if len(matches) >= MAX_FILES_PER_ID:
                            return matches
        except Exception:
            continue
    return matches


def scan_source_for_generator_evidence(name, path):
    ev = {"path": path, "hits": [], "error": None}
    if not path:
        ev["error"] = "PATH_NOT_FOUND"
        return ev
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {e}"
        return ev
    markers = ["TEMPLATE", "STATIC_ROOT", "CARDS_DIR", "def generate_card", "def build_card",
               "render_template", "OUTPUT_DIR", "PUBLIC_DIR", "def publish"]
    for m in markers:
        for mm in re.finditer(re.escape(m), text):
            lineno = text.count("\n", 0, mm.start()) + 1
            ev["hits"].append(f"{m}@line{lineno}")
    return ev


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    now = datetime.now(timezone.utc).isoformat()
    hr("UA-0009 RELEASE GATE PROBE (task_003) - READ ONLY")
    log("TIMESTAMP_UTC", now)
    log("MODE", "READ_ONLY - no production writes, no DB writes, no imports of UA ART modules")

    # -------------------- TRACK 1: SQLite --------------------
    hr("TRACK 1: SQLITE STABILITY DECISION")
    db_path = find_first_existing(DB_CANDIDATES)
    log("DB_CANDIDATES_TRIED", ", ".join(DB_CANDIDATES))
    log("DB_PATH_USED", db_path or "NONE_FOUND")

    sqlite_result = probe_sqlite(db_path)
    log("QUICK_CHECK", sqlite_result.get("quick_check"))
    log("JOURNAL_MODE", sqlite_result.get("journal_mode"))
    if sqlite_result.get("error"):
        log("SQLITE_PROBE_ERROR", sqlite_result["error"])

    source_evidence = {}
    for name, candidates in SOURCE_CANDIDATES.items():
        path = find_first_existing(candidates)
        log(f"{name}_PATH_USED", path or "NONE_FOUND")
        source_evidence[name] = scan_source_for_sqlite_evidence(name, path)
        ev = source_evidence[name]
        log(f"{name}_busy_timeout_hits", ev["busy_timeout"] or "NONE_FOUND")
        log(f"{name}_connect_calls", ev["connect_calls"])
        log(f"{name}_close_calls", ev["close_calls"])
        log(f"{name}_select_or_fetch_calls", ev["select_or_fetch"])
        log(f"{name}_long_ops_while_connection_may_be_open", ev["long_ops_hint"] or "NONE_FOUND")
        if ev.get("error"):
            log(f"{name}_ERROR", ev["error"])

    # Decide recommendation
    jm = (sqlite_result.get("journal_mode") or "").lower()
    qc = (sqlite_result.get("quick_check") or "").lower()
    quick_check_pass = qc == "ok"

    long_ops_found = any(source_evidence[n]["long_ops_hint"] for n in source_evidence)
    any_busy_timeout = any(source_evidence[n]["busy_timeout"] for n in source_evidence)
    any_source_found = any(source_evidence[n]["path"] for n in source_evidence)

    if not any_source_found or sqlite_result.get("error"):
        recommendation = "MORE_PROOF_NEEDED"
        rec_reason = "Source files and/or DB could not be located/opened from candidate paths; real path confirmation required before deciding fix scope."
    elif long_ops_found and not any_busy_timeout:
        recommendation = "WAL_CANDIDATE"
        rec_reason = ("Evidence of long external operations (network/subprocess/media) occurring while a "
                      "connection may still be open, with no busy_timeout configured in source text. "
                      "WAL reduces writer/reader blocking risk more robustly than a single early-close patch.")
    elif long_ops_found and any_busy_timeout:
        recommendation = "TARGETED_FIX"
        rec_reason = ("Long-operation-while-connected pattern found but busy_timeout is already configured; "
                      "closing the connection/cursor immediately after the SELECT/fetch (before long work) "
                      "is likely sufficient and lower-risk than a journal_mode change.")
    else:
        recommendation = "MORE_PROOF_NEEDED"
        rec_reason = ("No clear long-operation-while-connected pattern detected in the scanned window; "
                      "insufficient textual evidence to choose between targeted fix and WAL without deeper "
                      "trace/log review.")

    log("SQLITE_RECOMMENDATION", recommendation)
    log("SQLITE_RECOMMENDATION_REASON", rec_reason)

    # -------------------- TRACK 2: CRM completeness --------------------
    hr("TRACK 2: UA-0009 CRM COMPLETENESS")
    ua0009_audit = {"exists": False, "error": "DB_NOT_OPENED"}
    schema = {}
    if db_path and not sqlite_result.get("error"):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            schema = discover_schema(conn)
            log("TABLES_FOUND", list(schema.keys()))
            ua0009_audit = audit_ua0009(conn, schema)
            conn.close()
        except Exception as e:
            ua0009_audit = {"exists": False, "error": f"{type(e).__name__}: {e}"}

    log("CANDIDATE_TABLE", ua0009_audit.get("table"))
    log("TABLE_CONFIDENCE_SCORE", ua0009_audit.get("table_confidence_score"))
    log("COLUMN_MAPPING", ua0009_audit.get("column_mapping"))
    log("UA0009_EXISTS", ua0009_audit.get("exists"))
    if ua0009_audit.get("error"):
        log("UA0009_AUDIT_ERROR", ua0009_audit["error"])
    log("UA0009_MATCHED_BY", ua0009_audit.get("matched_by"))

    classification = ua0009_audit.get("classification", {})
    for field in FIELD_PATTERNS.keys():
        cls = classification.get(field, "NOT_CHECKED")
        val = ua0009_audit.get("row", {}).get(field)
        log(f"FIELD[{field}]", f"classification={cls} value={val}")

    log("VIN_DUPLICATES", ua0009_audit.get("vin_duplicates", 0))
    log("AUTO_NUMBER_DUPLICATES", ua0009_audit.get("auto_number_duplicates", 0))

    missing_fields = [f for f, c in classification.items() if c in ("MISSING", "MISSING_COLUMN_NOT_FOUND")]
    owner_input_fields = [f for f, c in classification.items() if c == "OWNER_INPUT_REQUIRED"]
    required_complete = ua0009_audit.get("exists", False) and len(missing_fields) == 0 and len(owner_input_fields) == 0

    # -------------------- TRACK 3: Sandbox readiness --------------------
    hr("TRACK 3: UA-0009 SANDBOX READINESS")
    public_dirs = find_first_existing_dir(PUBLIC_DIR_CANDIDATES)
    log("PUBLIC_DIR_CANDIDATES_TRIED", ", ".join(PUBLIC_DIR_CANDIDATES))
    log("PUBLIC_DIRS_FOUND", public_dirs or "NONE_FOUND")

    baseline = {}
    baseline_capture_ok = True
    for car_id in BASELINE_IDS:
        files = find_id_files(public_dirs, car_id) if public_dirs else []
        entry = []
        for fp in files:
            entry.append({"path": fp, "sha256": sha256_of_file(fp)})
        baseline[car_id] = entry
        log(f"BASELINE[{car_id}]_FILE_COUNT", len(entry))
        for e in entry[:10]:
            log(f"BASELINE[{car_id}]_FILE", f"{e['path']} sha256={e['sha256']}")
        if public_dirs and len(entry) == 0:
            # not necessarily an error (car may not have files), do not fail hard
            pass

    if not public_dirs:
        baseline_capture_ok = False

    ua0009_files = find_id_files(public_dirs, "UA-0009") if public_dirs else []
    log("UA0009_PUBLIC_FILE_COUNT", len(ua0009_files))
    for fp in ua0009_files[:10]:
        log("UA0009_PUBLIC_FILE", fp)

    gen_evidence = {}
    for name, candidates in SOURCE_CANDIDATES.items():
        path = find_first_existing(candidates)
        gen_evidence[name] = scan_source_for_generator_evidence(name, path)
        log(f"{name}_GENERATOR_EVIDENCE", gen_evidence[name]["hits"] or "NONE_FOUND")
        if gen_evidence[name].get("error"):
            log(f"{name}_GENERATOR_EVIDENCE_ERROR", gen_evidence[name]["error"])

    sandbox_data_sufficient = required_complete  # need complete CRM data first
    sandbox_ready = sandbox_data_sufficient and bool(public_dirs) and baseline_capture_ok

    log("SANDBOX_BUILD_PREREQUISITES", [
        "1. UA0009_REQUIRED_FIELDS_COMPLETE must be YES (owner supplies OWNER_INPUT_REQUIRED fields)",
        "2. Real public/static directory path confirmed (candidates above must be validated on PythonAnywhere)",
        "3. Generator/source path confirmed via source-evidence markers above (or owner points to exact generator script)",
        "4. UA-0001..UA-0008 baseline SHA-256 captured BEFORE any sandbox build to allow diffing/rollback verification",
        "5. Sandbox build target must be an isolated path, never overwriting UA-0001..UA-0008 or existing UA-0009 public files",
    ])
    log("RELEASE_ACCEPTANCE_GATES", [
        "A. SQLITE_RELEASE_RECOMMENDATION resolved and (if WAL) explicitly approved by owner as CRITICAL change",
        "B. UA0009_REQUIRED_FIELDS_COMPLETE == YES with 0 VIN/auto_number duplicates",
        "C. Sandbox card visually reviewed by owner before any production publish",
        "D. UA-0001..UA-0008 baseline hashes re-verified unchanged after sandbox build",
        "E. Explicit owner approval recorded before SAFE_TO_PUBLISH_UA0009_NOW can ever become YES",
    ])

    # -------------------- FINAL MANDATORY BLOCK --------------------
    hr("FINAL MANDATORY BLOCK")

    sqlite_quick_check_str = "PASS" if quick_check_pass else "FAIL"
    vin_dupes = ua0009_audit.get("vin_duplicates", 0)
    auto_dupes = ua0009_audit.get("auto_number_duplicates", 0)

    safe_to_prepare_fix_task = recommendation in ("TARGETED_FIX", "WAL_CANDIDATE")
    safe_to_build_sandbox_next = (
        ua0009_audit.get("exists", False)
        and required_complete
        and vin_dupes == 0
        and auto_dupes == 0
    )

    final = []
    final.append(f"SQLITE_QUICK_CHECK: {sqlite_quick_check_str}")
    final.append(f"SQLITE_JOURNAL_MODE: {sqlite_result.get('journal_mode') or 'UNKNOWN'}")
    final.append(f"SQLITE_RELEASE_RECOMMENDATION: {recommendation}")
    final.append(f"UA0009_EXISTS_IN_CRM: {'YES' if ua0009_audit.get('exists') else 'NO'}")
    final.append(f"UA0009_VIN_DUPLICATES: {vin_dupes}")
    final.append(f"UA0009_AUTO_NUMBER_DUPLICATES: {auto_dupes}")
    final.append(f"UA0009_REQUIRED_FIELDS_COMPLETE: {'YES' if required_complete else 'NO'}")
    final.append(f"UA0009_MISSING_FIELDS: {', '.join(missing_fields) if missing_fields else 'NONE'}")
    final.append(f"UA0009_OWNER_INPUT_REQUIRED: {', '.join(owner_input_fields) if owner_input_fields else 'NONE'}")
    final.append(f"UA0009_PUBLIC_FILES_EXIST: {'YES' if ua0009_files else 'NO'}")
    final.append(f"UA0001_0008_BASELINE_CAPTURED: {'PASS' if baseline_capture_ok else 'FAIL'}")
    final.append(f"UA0009_SANDBOX_READY: {'YES' if sandbox_ready else 'NO'}")
    final.append(f"SAFE_TO_PREPARE_FIX_TASK: {'YES' if safe_to_prepare_fix_task else 'NO'}")
    final.append(f"SAFE_TO_BUILD_UA0009_SANDBOX_NEXT: {'YES' if safe_to_build_sandbox_next else 'NO'}")
    final.append("SAFE_TO_PUBLISH_UA0009_NOW: NO")
    final.append("PRODUCTION_WRITE_PERFORMED: NO")
    final.append("DATABASE_CHANGED: NO")
    final.append("SITE_FILES_CHANGED: 0")
    next_action = (
        "Run this probe on PythonAnywhere; if DB/source/public-dir candidates did not resolve, "
        "update the *_CANDIDATES lists with confirmed real paths and re-run (still read-only). "
        "Then route findings to owner for OWNER_INPUT_REQUIRED fields and CRITICAL sign-off on "
        "SQLITE_RELEASE_RECOMMENDATION before any fix/sandbox task begins."
    )
    final.append(f"NEXT_ACTION: {next_action}")

    for l in final:
        lines.append(l)

    report_text = "\n".join(str(x) for x in lines)

    # ---- ONLY filesystem write in this script ----
    out_dir = os.path.dirname(OUTPUT_PATH)
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(report_text + "\n")
        wrote_ok = True
    except Exception as e:
        wrote_ok = False
        report_text += f"\n\n[WRITE_ERROR] Could not write {OUTPUT_PATH}: {type(e).__name__}: {e}"

    print(report_text)
    if not wrote_ok:
        print("\nWARNING: report file could not be written; see WRITE_ERROR above.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FATAL_PROBE_ERROR (no production write performed):", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
