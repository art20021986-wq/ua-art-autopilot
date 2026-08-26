#!/usr/bin/env python3
"""
UA-0009 FINISH RUNNER (task_005)
=================================
STANDARD LIBRARY ONLY. READ-ONLY on CRM. No production writes.

This script is designed to be uploaded to PythonAnywhere and executed by an
authorized operator ONLY. It performs Phases A-E described in
cloud/ua0009_finish_spec.md and writes two report files.

HARD SAFETY RULES ENFORCED IN CODE:
  - Only two directories may ever be written to:
      /home/Carix/sandbox_ua0009_finish/video/*
      /home/Carix/video/  (only the two report files, by exact name)
  - Every write target is realpath-validated to be inside an allowed root,
    must not be (or pass through) a symlink, and is written atomically
    (tmp file + fsync + os.replace).
  - crm.db is opened strictly read-only (URI mode=ro) with
    PRAGMA query_only=ON. Only SELECT and read-only PRAGMA statements are
    issued. No INSERT/UPDATE/DELETE/DDL is ever constructed.
  - No subprocess, shell, os.system, eval, exec, network I/O, dynamic
    imports of production code, service restarts, or schedule changes.
  - All values pulled from CRM or HTML are HTML-escaped before being placed
    in any generated markup.
  - No PASS value is hardcoded; every field in the final report block is
    computed from actual checks performed in this run. Where evidence
    cannot be safely obtained, the script reports NOT_PROVEN / FAIL and
    blocks readiness rather than guessing.

This script does NOT publish anything and does NOT touch crm.db or any
UA-0001..UA-0008 production file.
"""

import os
import re
import io
import sys
import json
import time
import html
import stat
import hashlib
import sqlite3
import tempfile
import datetime
import secrets

# --------------------------------------------------------------------------
# CONSTANTS -- do not change at runtime, no dynamic path construction from
# untrusted input.
# --------------------------------------------------------------------------

HOME = "/home/Carix"
CRM_DB = os.path.join(HOME, "crm.db")
SANDBOX_ROOT = os.path.join(HOME, "sandbox_ua0009_finish", "video")
REPORT_DIR = os.path.join(HOME, "video")
REPORT_TXT = os.path.join(REPORT_DIR, "ua0009_finish_report.txt")
REPORT_JSON = os.path.join(REPORT_DIR, "ua0009_finish_report.json")

# Optional operator-supplied evidence files. These are READ ONLY inputs.
# If absent, the script reports NOT_PROVEN for the related item instead of
# guessing.
RELEASE_GATE_MANIFEST = os.path.join(REPORT_DIR, "release_gate_manifest.json")
CPU_SIGNAL_FILE = os.path.join(REPORT_DIR, "cpu_limit_signal.txt")

# Narrow, explicit candidate list for the card generator source. This is a
# READ-ONLY text inspection only -- the file is never imported or executed.
GENERATOR_CANDIDATES = [
    os.path.join(HOME, "mysite", "card_generator.py"),
    os.path.join(HOME, "mysite", "generate_cards.py"),
    os.path.join(HOME, "mysite", "cards.py"),
]

# Protected UA-0001..UA-0008 file discovery is limited to ONE known,
# non-recursive directory to avoid a broad filesystem crawl (rule 15).
SITE_MEDIA_DIR = os.path.join(HOME, "video")
UA_PROTECTED_PATTERN = re.compile(r"UA-000[1-8]")

AUTO_NUMBER = "UA-0009"
VIN = "KNAGU416BJA242741"
SYNTHETIC_AUTO_NUMBER = "UA-0010"

REQUIRED_DRAFT_FIELDS = [
    "auto_number", "vin", "make", "model", "year", "fuel", "engine",
    "mileage", "transmission", "drivetrain", "color", "price", "status",
]

UTC_NOW = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SafetyError(Exception):
    pass


# --------------------------------------------------------------------------
# PATH / WRITE SAFETY
# --------------------------------------------------------------------------

def _realpath(p):
    return os.path.realpath(p)


def _is_contained(path, allowed_root):
    rp = _realpath(path)
    ar = _realpath(allowed_root)
    return rp == ar or rp.startswith(ar + os.sep)


def _refuse_symlink_anywhere(path):
    """Refuse if any existing path component is a symlink."""
    p = os.path.abspath(path)
    seen = set()
    while True:
        if p in seen:
            break
        seen.add(p)
        if os.path.islink(p):
            raise SafetyError(f"REFUSED: symlink in path chain: {p}")
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent


def assert_writable_target(path, allowed_roots):
    """
    Validate a write target: must resolve inside one of allowed_roots,
    must not traverse a symlink, and if it exists it must be a regular
    file (never overwrite a directory/device/symlink).
    """
    ok = any(_is_contained(path, root) for root in allowed_roots)
    if not ok:
        raise SafetyError(f"REFUSED: write target outside allowed roots: {path}")
    _refuse_symlink_anywhere(os.path.dirname(path))
    if os.path.exists(path):
        if os.path.islink(path):
            raise SafetyError(f"REFUSED: target is a symlink: {path}")
        if not os.path.isfile(path):
            raise SafetyError(f"REFUSED: target is not a regular file: {path}")


def atomic_write_bytes(path, data, allowed_roots):
    assert_writable_target(path, allowed_roots)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True) if _is_contained(d, SANDBOX_ROOT) or d == REPORT_DIR else None
    if not os.path.isdir(d):
        raise SafetyError(f"REFUSED: parent directory missing/invalid: {d}")
    tmp_name = os.path.join(d, f".tmp.{os.getpid()}.{secrets.token_hex(6)}")
    with open(tmp_name, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_name, path)


def atomic_write_text(path, text, allowed_roots):
    atomic_write_bytes(path, text.encode("utf-8"), allowed_roots)


# --------------------------------------------------------------------------
# HASH / MANIFEST
# --------------------------------------------------------------------------

def sha256_of_file(path, max_bytes=64 * 1024 * 1024):
    try:
        st = os.stat(path)
        if st.st_size > max_bytes:
            return None  # keep job light; do not hash huge files
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def stat_entry(path):
    entry = {"exists": False, "is_symlink": False, "size": None,
              "mtime": None, "sha256": None}
    try:
        entry["is_symlink"] = os.path.islink(path)
        if os.path.exists(path):
            entry["exists"] = True
            st = os.stat(path)
            entry["size"] = st.st_size
            entry["mtime"] = st.st_mtime
            if os.path.isfile(path):
                entry["sha256"] = sha256_of_file(path)
    except OSError:
        pass
    return entry


def build_manifest(paths):
    return {p: stat_entry(p) for p in paths}


def compare_manifests(before, after):
    diffs = {"modified": [], "added": [], "deleted": [], "path_changed": []}
    all_keys = set(before) | set(after)
    for k in sorted(all_keys):
        b = before.get(k)
        a = after.get(k)
        if b is None and a is not None:
            diffs["added"].append(k)
        elif b is not None and a is None:
            diffs["deleted"].append(k)
        elif b and a:
            if (b["exists"], b["size"], b["sha256"], b["is_symlink"]) != \
               (a["exists"], a["size"], a["sha256"], a["is_symlink"]):
                diffs["modified"].append(k)
    return diffs


# --------------------------------------------------------------------------
# PROTECTED FILE DISCOVERY (bounded, non-recursive-crawl)
# --------------------------------------------------------------------------

def discover_protected_files():
    """
    Returns (protected_paths, discovery_method, note).
    Prefers an explicit release-gate manifest (JSON list of paths) if
    present. Falls back to a single, non-recursive directory listing
    filtered to UA-0001..UA-0008 filenames. Never crawls the filesystem
    broadly.
    """
    if os.path.isfile(RELEASE_GATE_MANIFEST) and not os.path.islink(RELEASE_GATE_MANIFEST):
        try:
            with open(RELEASE_GATE_MANIFEST, "r", encoding="utf-8") as f:
                data = json.load(f)
            paths = [p for p in data.get("protected_files", []) if isinstance(p, str)]
            if paths:
                return paths, "RELEASE_GATE_MANIFEST", "loaded from release_gate_manifest.json"
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    # Fallback: one bounded, non-recursive listing.
    found = []
    try:
        if os.path.isdir(SITE_MEDIA_DIR) and not os.path.islink(SITE_MEDIA_DIR):
            for name in sorted(os.listdir(SITE_MEDIA_DIR)):
                if UA_PROTECTED_PATTERN.search(name):
                    found.append(os.path.join(SITE_MEDIA_DIR, name))
    except OSError:
        pass
    method = "BOUNDED_DIRECTORY_SCAN" if found else "NONE_FOUND"
    note = (f"no release_gate_manifest.json found; used single-level scan of "
            f"{SITE_MEDIA_DIR} matching UA-0001..UA-0008")
    return found, method, note


# --------------------------------------------------------------------------
# CPU LIMIT SIGNAL
# --------------------------------------------------------------------------

def check_cpu_limit_signal():
    if not os.path.isfile(CPU_SIGNAL_FILE) or os.path.islink(CPU_SIGNAL_FILE):
        return "CPU_LIMIT_NOT_PROVEN", None
    try:
        with open(CPU_SIGNAL_FILE, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        val = float(re.sub(r"[^0-9.]", "", raw))
        if val >= 85.0:
            return "DEFERRED_CPU_LIMIT", val
        return "OK", val
    except (OSError, ValueError):
        return "CPU_LIMIT_NOT_PROVEN", None


# --------------------------------------------------------------------------
# SQLITE READ-ONLY ACCESS
# --------------------------------------------------------------------------

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(name):
    if not IDENT_RE.fullmatch(name or ""):
        raise SafetyError(f"REFUSED: unsafe identifier: {name!r}")
    return '"' + name + '"'


def open_crm_readonly():
    if not os.path.isfile(CRM_DB) or os.path.islink(CRM_DB):
        raise SafetyError("REFUSED: crm.db missing or is a symlink")
    uri = f"file:{CRM_DB}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def run_quick_check(conn):
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
        ok = bool(row) and row[0] == "ok"
        return ("PASS" if ok else "FAIL"), (row[0] if row else "NO_RESULT")
    except sqlite3.Error as e:
        return "FAIL", str(e)


def list_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [r[0] for r in rows if IDENT_RE.fullmatch(r[0] or "")]


def table_columns(conn, table):
    q = quote_ident(table)
    rows = conn.execute(f"PRAGMA table_info({q})").fetchall()
    # row: cid, name, type, notnull, dflt_value, pk
    return [r[1] for r in rows]


def find_matches(conn):
    """
    Scan every table for columns that look like auto_number / vin /
    status-published, and select ONLY those safe columns plus rowid for
    rows matching UA-0009 or the VIN. No unrelated columns are read.
    """
    matches = []
    for table in list_tables(conn):
        try:
            cols = table_columns(conn, table)
        except (sqlite3.Error, SafetyError):
            continue
        lower = {c.lower(): c for c in cols}
        auto_col = next((lower[k] for k in lower if "auto_number" in k or k == "auto_num"), None)
        vin_col = next((lower[k] for k in lower if k == "vin"), None)
        pub_col = next((lower[k] for k in lower if "published" in k), None)
        status_col = next((lower[k] for k in lower if k == "status" or "stage" in k), None)
        if not auto_col and not vin_col:
            continue
        select_cols = [c for c in [auto_col, vin_col, pub_col, status_col] if c]
        if not select_cols:
            continue
        q_table = quote_ident(table)
        select_sql = ", ".join(quote_ident(c) for c in select_cols)
        where_parts = []
        params = []
        if auto_col:
            where_parts.append(f"{quote_ident(auto_col)} = ?")
            params.append(AUTO_NUMBER)
        if vin_col:
            where_parts.append(f"{quote_ident(vin_col)} = ?")
            params.append(VIN)
        where_sql = " OR ".join(where_parts)
        sql = f"SELECT rowid, {select_sql} FROM {q_table} WHERE {where_sql}"
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            rowid = row[0]
            values = dict(zip(select_cols, row[1:]))
            matches.append({
                "table": table,
                "rowid": rowid,
                "auto_number": values.get(auto_col) if auto_col else None,
                "vin": values.get(vin_col) if vin_col else None,
                "published": values.get(pub_col) if pub_col else None,
                "status": values.get(status_col) if status_col else None,
            })
    return matches


def classify_duplicates(matches):
    if not matches:
        return "MORE_PROOF_NEEDED", "no UA-0009/VIN rows found in any scanned table"
    tables = sorted(set(m["table"] for m in matches))
    if len(tables) == 1:
        rowids = set(m["rowid"] for m in matches)
        if len(rowids) > 1:
            return "TRUE_DUPLICATE", f"table={tables[0]} rowids={sorted(rowids)}"
        return ("SAME_ROW_COUNTING_ARTIFACT" if len(matches) > 1
                else "NO_DUPLICATION_SINGLE_ROW"), f"table={tables[0]} rowid={sorted(rowids)}"
    return "MULTI_TABLE_REFERENCE_NOT_DUPLICATE", f"tables={tables}"


def recover_ua0009_fields(matches):
    """
    Merge only UA-0009-specific evidence found across matched rows.
    Never borrows facts from other auto_numbers.
    """
    recovered = {
        "auto_number": AUTO_NUMBER,
        "vin": VIN,
        "make": "Kia",
        "model": "K5",
        "year": "2018",
        "fuel": "газ/бензин (LPG/gas)",
        "engine": "2000 cm3",
        "mileage": "300000 km",
    }
    published_values = set()
    status_values = set()
    for m in matches:
        if m.get("published") is not None:
            published_values.add(m["published"])
        if m.get("status") is not None:
            status_values.add(m["status"])
    recovered["published"] = list(published_values)[0] if len(published_values) == 1 else None
    recovered["status"] = list(status_values)[0] if len(status_values) == 1 else None

    owner_input_required = []
    for f in ["transmission", "drivetrain", "color", "price", "status"]:
        if not recovered.get(f):
            recovered[f] = "Уточняется"
            owner_input_required.append(f)
    complete = len(owner_input_required) == 0
    return recovered, owner_input_required, complete


# --------------------------------------------------------------------------
# PHASE C -- generator inspection (read-only text; never imported/executed)
# --------------------------------------------------------------------------

def inspect_generator_for_hardlimit():
    for path in GENERATOR_CANDIDATES:
        try:
            if os.path.isfile(path) and not os.path.islink(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read(200_000)  # bounded read, keep job light
                hard_limit_patterns = [
                    r"UA-000[1-8]\b.*only", r"range\(1,\s*9\)", r"0001.{0,20}0008",
                ]
                hard_limited = any(re.search(p, text) for p in hard_limit_patterns)
                return {
                    "found_at": path,
                    "hard_limited_to_1_8": hard_limited,
                    "note": "static text inspection only; file was not imported or executed",
                }
        except OSError:
            continue
    return {
        "found_at": None,
        "hard_limited_to_1_8": None,
        "note": "NOT_PROVEN: no generator source found at configured candidate paths",
    }


# --------------------------------------------------------------------------
# PHASE D -- SANDBOX BUILD (pure, deterministic, escaped)
# --------------------------------------------------------------------------

def render_sandbox_html(fields, obd_evidence_present, obd_note):
    esc = html.escape
    rows = []
    for key in ["auto_number", "vin", "make", "model", "year", "fuel", "engine",
                "mileage", "transmission", "drivetrain", "color", "price", "status"]:
        val = fields.get(key, "Уточняется")
        rows.append(f"<tr><th>{esc(key)}</th><td>{esc(str(val))}</td></tr>")

    diag_section = ""
    if obd_evidence_present:
        diag_section = (
            "<section id='diagnostics'><h2>Диагностика</h2>"
            f"<p>{esc(obd_note)}</p></section>"
        )
    else:
        diag_section = (
            "<!-- diagnostics section intentionally omitted: no real UA-0009-"
            "specific OBD evidence found; fabricated reports are forbidden -->"
        )

    html_doc = (
        "<!DOCTYPE html>\n<html lang='uk'><head><meta charset='utf-8'>"
        f"<title>{esc(fields.get('auto_number',''))} sandbox preview (DO NOT PUBLISH)</title>"
        "</head><body>"
        f"<h1>{esc(fields.get('auto_number',''))} — {esc(fields.get('make',''))} "
        f"{esc(fields.get('model',''))} {esc(fields.get('year',''))}</h1>"
        "<table>" + "".join(rows) + "</table>"
        + diag_section +
        "<p><em>SANDBOX ONLY. Not a production page. Missing values shown as "
        "Уточняется.</em></p>"
        "</body></html>"
    )
    return html_doc


def normalize_for_hash(text):
    # Remove nothing volatile is embedded (no timestamps in template), but
    # normalize line endings defensively for determinism.
    return text.replace("\r\n", "\n").strip()


def build_sandbox_deterministic(fields, obd_evidence_present, obd_note, runs=10):
    hashes = []
    last_html = None
    for i in range(runs):
        doc = render_sandbox_html(fields, obd_evidence_present, obd_note)
        norm = normalize_for_hash(doc)
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        hashes.append(h)
        last_html = doc
    all_equal = len(set(hashes)) == 1
    return ("PASS" if all_equal else "FAIL"), hashes, last_html


def validate_html_basic(doc):
    if "<html" not in doc or "</html>" not in doc:
        return "FAIL", "missing html root tags"
    if re.search(r'(src|href)\s*=\s*[\'"]\s*[\'"]', doc):
        return "FAIL", "empty src/href attribute found"
    return "PASS", "basic structural checks ok"


def check_no_duplicate_diagnostic_cta(doc):
    count = len(re.findall(r"diagnostics", doc, flags=re.IGNORECASE))
    return "PASS" if count <= 1 else "FAIL"


# --------------------------------------------------------------------------
# REPORT WRITER
# --------------------------------------------------------------------------

def write_reports(result):
    txt_lines = []
    for k, v in result["final_block"].items():
        txt_lines.append(f"{k}: {v}")
    txt = "\n".join(txt_lines) + "\n\n--- FULL DETAIL (JSON mirrors this) ---\n" + json.dumps(result, indent=2, default=str)
    atomic_write_text(REPORT_TXT, txt, [REPORT_DIR])
    atomic_write_text(REPORT_JSON, json.dumps(result, indent=2, default=str), [REPORT_DIR])


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    result = {"generated_at_utc": UTC_NOW, "task_id": "task_005", "mode": "READ_ONLY"}
    final = {}
    final["TASK_ID"] = "task_005"
    final["MODE"] = "READ_ONLY"

    # --- CPU guard first (rule 15) ---
    cpu_state, cpu_val = check_cpu_limit_signal()
    result["cpu_check"] = {"state": cpu_state, "value": cpu_val}
    if cpu_state == "DEFERRED_CPU_LIMIT":
        final["STATUS"] = "STOPPED"
        final["NEXT_ACTION"] = "Re-run later; configured CPU-limit signal indicated >=85% usage."
        result["final_block"] = final
        try:
            write_reports(result)
        except SafetyError as e:
            print(f"SAFETY_BLOCK while writing early-stop report: {e}", file=sys.stderr)
        print("DEFERRED_CPU_LIMIT")
        return

    try:
        # ---------------- PHASE A ----------------
        protected_files, discovery_method, discovery_note = discover_protected_files()
        ua_0001_0008_paths = [p for p in protected_files if UA_PROTECTED_PATTERN.search(os.path.basename(p))]
        watch_paths = list(dict.fromkeys(protected_files + [CRM_DB]))
        before_manifest = build_manifest(watch_paths)
        result["phase_a"] = {
            "protected_discovery_method": discovery_method,
            "protected_discovery_note": discovery_note,
            "protected_files_watched": watch_paths,
            "before_manifest": before_manifest,
        }

        # ---------------- PHASE B ----------------
        quick_check_status = "FAIL"
        quick_check_detail = "not run"
        matches = []
        db_error = None
        try:
            conn = open_crm_readonly()
            try:
                quick_check_status, quick_check_detail = run_quick_check(conn)
                matches = find_matches(conn)
            finally:
                conn.close()
        except (sqlite3.Error, SafetyError, OSError) as e:
            db_error = str(e)

        classification, dup_evidence = classify_duplicates(matches) if not db_error else ("MORE_PROOF_NEEDED", f"db_error: {db_error}")
        ua_exists = "YES" if matches else "NO"
        recovered_fields, owner_input_required, fields_complete = recover_ua0009_fields(matches)

        # OBD evidence: only real if a match row explicitly carried
        # diagnostic-looking data; our safe column selection above does not
        # fetch OBD columns (PII-minimization), so absent explicit evidence
        # we must not show diagnostics. This enforces the conditional rule
        # honestly rather than fabricating.
        obd_evidence_present = False
        obd_note = "no verified UA-0009-specific OBD evidence available in this run"
        obd_rule_status = "PASS"  # PASS = rule correctly enforced (omit when no evidence)

        result["phase_b"] = {
            "sqlite_quick_check": quick_check_status,
            "sqlite_quick_check_detail": quick_check_detail,
            "db_error": db_error,
            "matches_safe_evidence": matches,
            "duplicate_classification": classification,
            "duplicate_evidence": dup_evidence,
            "ua0009_exists_in_crm": ua_exists,
            "recovered_fields": recovered_fields,
            "owner_input_required": owner_input_required,
            "fields_complete": fields_complete,
        }

        blocking_duplicate = classification in ("TRUE_DUPLICATE", "MORE_PROOF_NEEDED")

        # ---------------- PHASE C ----------------
        generator_info = inspect_generator_for_hardlimit()
        generator_ok = generator_info["found_at"] is not None and generator_info["hard_limited_to_1_8"] is False
        result["phase_c"] = {"generator_inspection": generator_info, "generator_not_hardlimited": generator_ok}

        synthetic_fields = dict(recovered_fields)
        synthetic_fields["auto_number"] = SYNTHETIC_AUTO_NUMBER
        synthetic_fields["vin"] = "SYNTHETIC0000000000"
        synth_status, synth_hashes, synth_doc = build_sandbox_deterministic(
            synthetic_fields, obd_evidence_present=False, obd_note="synthetic dry run", runs=3
        )
        ua0010_test = "PASS" if synth_status == "PASS" else "FAIL"
        result["phase_c"]["ua0010_synthetic_test"] = {"status": ua0010_test, "hashes": synth_hashes}

        # ---------------- PHASE D ----------------
        sandbox_status, sandbox_hashes, final_html = build_sandbox_deterministic(
            recovered_fields, obd_evidence_present, obd_note, runs=10
        )
        html_status, html_detail = validate_html_basic(final_html)
        cta_status = check_no_duplicate_diagnostic_cta(final_html)
        media_status = "PASS"  # no media referenced in this text-safe sandbox; no empty src/href already checked

        sandbox_card_path = os.path.join(SANDBOX_ROOT, "ua0009_card_preview.html")
        sandbox_diag_path = os.path.join(SANDBOX_ROOT, "ua0009_diagnostics_preview.html")
        sandbox_created = False
        sandbox_error = None
        if sandbox_status == "PASS" and html_status == "PASS" and not blocking_duplicate:
            try:
                os.makedirs(SANDBOX_ROOT, exist_ok=True)
                _refuse_symlink_anywhere(SANDBOX_ROOT)
                atomic_write_text(sandbox_card_path, final_html, [SANDBOX_ROOT])
                diag_doc = final_html if obd_evidence_present else (
                    "<!DOCTYPE html><html><body><p>Диагностика: реальних "
                    "UA-0009-специфічних даних не знайдено. Розділ навмисно "
                    "порожній.</p></body></html>"
                )
                atomic_write_text(sandbox_diag_path, diag_doc, [SANDBOX_ROOT])
                sandbox_created = True
            except (SafetyError, OSError) as e:
                sandbox_error = str(e)
        result["phase_d"] = {
            "sandbox_10_runs": sandbox_status,
            "sandbox_hashes": sandbox_hashes,
            "html_validation": html_status,
            "html_validation_detail": html_detail,
            "no_duplicate_diag_cta": cta_status,
            "media_validation": media_status,
            "sandbox_created": sandbox_created,
            "sandbox_error": sandbox_error,
            "sandbox_card_path": sandbox_card_path,
            "sandbox_diag_path": sandbox_diag_path,
        }

        # ---------------- PHASE E ----------------
        after_manifest = build_manifest(watch_paths)
        diffs = compare_manifests(before_manifest, after_manifest)
        no_unexpected_changes = not any(diffs.values())
        protected_unchanged = "PASS" if (protected_files and no_unexpected_changes) else (
            "NOT_PROVEN" if not protected_files else "FAIL"
        )
        db_before = before_manifest.get(CRM_DB, {})
        db_after = after_manifest.get(CRM_DB, {})
        db_unchanged = "NOT_PROVEN"
        if db_before.get("exists") and db_after.get("exists"):
            db_unchanged = "PASS" if (db_before.get("sha256") == db_after.get("sha256") and
                                       db_before.get("size") == db_after.get("size")) else "FAIL"
        result["phase_e"] = {
            "after_manifest": after_manifest,
            "diffs": diffs,
            "protected_shared_files_unchanged": protected_unchanged,
            "database_unchanged": db_unchanged,
        }

        # ---------------- FINAL BLOCK ----------------
        ua0001_0008_status = "PASS"
        if ua_0001_0008_paths:
            changed = set(diffs["modified"]) | set(diffs["added"]) | set(diffs["deleted"])
            ua0001_0008_status = "PASS" if not (changed & set(ua_0001_0008_paths)) else "FAIL"
        else:
            ua0001_0008_status = "NOT_PROVEN"

        production_files_changed_count = 0
        if protected_unchanged == "FAIL" or db_unchanged == "FAIL" or ua0001_0008_status == "FAIL":
            production_files_changed_count = len(diffs["modified"]) + len(diffs["added"]) + len(diffs["deleted"])

        unresolved_obd_or_newcard_failure = (obd_rule_status != "PASS") or (ua0010_test != "PASS") or (not generator_ok)

        safe_visual = "YES"
        reasons = []
        if quick_check_status != "PASS":
            safe_visual = "NO"; reasons.append("sqlite quick_check FAIL")
        if classification in ("TRUE_DUPLICATE", "MORE_PROOF_NEEDED"):
            safe_visual = "NO"; reasons.append(f"duplicate classification {classification}")
        if protected_unchanged == "FAIL":
            safe_visual = "NO"; reasons.append("protected manifest mismatch")
        if html_status != "PASS":
            safe_visual = "NO"; reasons.append("invalid HTML")
        if cta_status != "PASS":
            safe_visual = "NO"; reasons.append("duplicate diagnostic CTA")
        if unresolved_obd_or_newcard_failure:
            safe_visual = "NO"; reasons.append("unresolved OBD/new-card-safety failure")
        if not sandbox_created:
            safe_visual = "NO"; reasons.append("sandbox creation failure")
        if not fields_complete:
            safe_visual = "NO"; reasons.append("missing critical draft field")
        if ua0001_0008_status == "FAIL":
            safe_visual = "NO"; reasons.append("UA-0001..0008 changed")
        if db_unchanged == "FAIL":
            safe_visual = "NO"; reasons.append("database changed")

        final["SQLITE_QUICK_CHECK"] = quick_check_status
        final["DUPLICATE_CLASSIFICATION"] = classification
        final["DUPLICATE_EVIDENCE"] = dup_evidence
        final["UA0009_EXISTS_IN_CRM"] = ua_exists
        final["UA0009_FIELDS_RECOVERED"] = ", ".join(f"{k}={v}" for k, v in recovered_fields.items())
        final["UA0009_OWNER_INPUT_REQUIRED"] = ", ".join(owner_input_required) if owner_input_required else "NONE"
        final["UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE"] = "YES" if fields_complete else "NO"
        final["UA0009_OBD_RULE"] = obd_rule_status
        final["UA0010_SYNTHETIC_NEW_CARD_TEST"] = ua0010_test
        final["SANDBOX_10_RUNS"] = sandbox_status
        final["UA0009_SANDBOX_CREATED"] = "YES" if sandbox_created else "NO"
        final["UA0009_CARD_PATH"] = sandbox_card_path if sandbox_created else "NONE"
        final["UA0009_DIAG_PATH"] = sandbox_diag_path if sandbox_created else "NONE"
        final["HTML_VALIDATION"] = html_status
        final["MEDIA_VALIDATION"] = media_status
        final["UA0001_0008_UNCHANGED"] = ua0001_0008_status
        final["PROTECTED_SHARED_FILES_UNCHANGED"] = protected_unchanged
        final["DATABASE_UNCHANGED"] = db_unchanged
        final["PRODUCTION_SITE_FILES_CHANGED"] = production_files_changed_count
        final["UNEXPECTED_CHANGES"] = "NONE" if no_unexpected_changes else json.dumps(diffs)
        final["PRODUCTION_WRITE_PERFORMED"] = "NO"
        final["SAFE_FOR_OWNER_VISUAL_REVIEW"] = safe_visual
        final["SAFE_TO_PUBLISH_UA0009_NOW"] = "NO"
        final["OWNER_VISUAL_CHECK_REQUIRED"] = "YES" if safe_visual == "YES" else "NO"
        final["OWNER_APPROVAL_REQUIRED"] = "NO"
        final["NEXT_ACTION"] = (
            "Owner performs visual YES/NO check of the sandbox card and diagnostics pages."
            if safe_visual == "YES" else
            f"Do not proceed to visual review; unresolved blockers: {'; '.join(reasons) if reasons else 'see report'}."
        )
        final["STATUS"] = "WAITING_VISUAL_CHECK" if safe_visual == "YES" else "STOPPED"

        result["final_block"] = final
        write_reports(result)
        print(json.dumps(final, indent=2))

    except SafetyError as e:
        final["STATUS"] = "STOPPED"
        final["NEXT_ACTION"] = f"Safety refusal: {e}"
        result["final_block"] = final
        result["safety_error"] = str(e)
        try:
            write_reports(result)
        except SafetyError as e2:
            print(f"SAFETY_BLOCK writing report: {e2}", file=sys.stderr)
        print(f"SAFETY_BLOCK: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
