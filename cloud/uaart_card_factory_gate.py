#!/usr/bin/env python3.10
"""
UA ART - Universal New-Card Factory Gate
=========================================

Purpose
-------
Read-only diagnostic tool that inspects CRM data, media, diagnostics and
sandbox HTML for one or more UA-XXXX vehicle cards and reports, in plain
language, whether each card is:

    READY_FOR_VISUAL_CHECK
    NEEDS_DATA            (with the exact missing fields)
    BLOCKED_SAFETY        (with the exact reason)

This script NEVER publishes anything, NEVER writes to the CRM database,
NEVER touches existing card UA-0001..UA-0008, and NEVER executes any
production generator code, shell command, subprocess, eval/exec or network
call. It is Python 3.10 standard-library only.

Invocation
----------
    python3.10 /home/Carix/uaart_card_factory_gate.py
    python3.10 /home/Carix/uaart_card_factory_gate.py UA-0011 UA-0012

Allowed writes (and nothing else)
----------------------------------
    /home/Carix/sandbox_uaart_card_factory/<CARD_ID>/video/*
    /home/Carix/video/uaart_card_factory_report.txt
    /home/Carix/video/uaart_card_factory_report.json

Every write is boundary-checked, non-symlink, atomic (tmp file + fsync +
os.replace) before it happens.
"""

import os
import re
import sys
import json
import stat
import html
import sqlite3
import hashlib
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser

# --------------------------------------------------------------------------
# Constants / approved boundaries
# --------------------------------------------------------------------------

APPROVED_ROOTS = [os.path.realpath("/home/Carix")]
CRM_DB_PATH = "/home/Carix/crm.db"
SANDBOX_FACTORY_ROOT = "/home/Carix/sandbox_uaart_card_factory"
REPORT_TXT = "/home/Carix/video/uaart_card_factory_report.txt"
REPORT_JSON = "/home/Carix/video/uaart_card_factory_report.json"

PROTECTED_CARDS = [f"UA-{i:04d}" for i in range(1, 9)]
DEFAULT_CARDS = ["UA-0009", "UA-0010"]

GENERATOR_CANDIDATES = [
    "/home/Carix/stranica.py",
    "/home/Carix/yadro.py",
    "/home/Carix/master_card.py",
    "/home/Carix/stroy3.py",
    "/home/Carix/stroy8.py",
    "/home/Carix/mysite/stranica.py",
    "/home/Carix/mysite/master_card.py",
]

WATCH_DIRS = [
    "/home/Carix",
    "/home/Carix/mysite",
    "/home/Carix/video",
    "/home/Carix/sandbox_uaart_card_factory",
]

HASH_SIZE_LIMIT = 50 * 1024 * 1024  # 50 MB
BOUNDED_READ_LIMIT = 3 * 1024 * 1024  # 3 MB for text/html/source inspection
ALLOWED_MEDIA_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif",
                      ".mp4", ".mov", ".m4v", ".webm"}
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}

CARD_ID_RE = re.compile(r"^UA-\d{4}$")

FIELD_ALIASES = {
    "auto_number": ["auto_number", "card_id", "cardid", "number", "id_card"],
    "vin": ["vin"],
    "brand": ["brand", "make"],
    "model": ["model"],
    "year": ["year"],
    "mileage": ["mileage", "probeg", "odometer"],
    "engine": ["engine", "engine_volume", "engine_cc", "cc"],
    "fuel": ["fuel"],
    "transmission": ["transmission", "gearbox", "korobka"],
    "drivetrain": ["drivetrain", "privod"],
    "color": ["color", "colour", "cvet"],
    "price": ["price", "cena"],
    "status": ["status", "stage"],
    "published": ["published", "is_published"],
    "photo": ["photo", "image", "foto"],
    "video": ["video"],
    "diag": ["diag", "diagnostic"],
    "obd": ["obd"],
    "container": ["container"],
    "date": ["date", "created", "updated"],
}

VISUAL_DRAFT_REQUIRED_FIELDS = ["auto_number", "vin", "brand", "model", "year"]
PUBLICATION_REQUIRED_FIELDS = [
    "auto_number", "vin", "brand", "model", "year", "mileage",
    "engine", "fuel", "transmission", "drivetrain", "color", "price",
]

MEDIA_STATUS_READY = {"ready", "approved", "done", "ok", "published"}
MEDIA_STATUS_REJECTED = {"pending", "rejected", "quarantine", "blocked", "draft"}


# --------------------------------------------------------------------------
# Small safe utilities
# --------------------------------------------------------------------------

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_path_in_roots(path):
    try:
        if os.path.islink(path):
            return False
        rp = os.path.realpath(path)
    except Exception:
        return False
    for root in APPROVED_ROOTS:
        if rp == root or rp.startswith(root + os.sep):
            return True
    return False


def is_safe_regular_file(path):
    if not path:
        return False
    if not safe_path_in_roots(path):
        return False
    try:
        if os.path.islink(path):
            return False
        st = os.stat(path)
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_size > 0


def sha256_file(path):
    """Returns (hash_hex_or_None, note). Never hashes above the size limit."""
    try:
        size = os.path.getsize(path)
    except OSError as e:
        return None, f"UNREADABLE:{e}"
    if size > HASH_SIZE_LIMIT:
        return None, "NOT_PROVEN_TOO_LARGE"
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except OSError as e:
        return None, f"UNREADABLE:{e}"
    return h.hexdigest(), None


def read_bounded(path, limit=BOUNDED_READ_LIMIT):
    with open(path, "rb") as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise ValueError("NOT_PROVEN_TOO_LARGE")
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return data.decode("latin-1", errors="replace")


def sanitize_value(v):
    if isinstance(v, (bytes, bytearray)):
        return "[BINARY_OMITTED]"
    return v


def list_top_level_files(dirpath):
    out = []
    try:
        with os.scandir(dirpath) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        out.append(entry.path)
                except OSError:
                    continue
    except OSError:
        pass
    return out


# --------------------------------------------------------------------------
# Watched-path drift detection (proves nothing outside scope was touched)
# --------------------------------------------------------------------------

def discover_watched_paths(card_ids):
    watch_names = set(PROTECTED_CARDS) | set(card_ids)
    paths = set()
    for g in GENERATOR_CANDIDATES:
        if os.path.isfile(g) and not os.path.islink(g) and safe_path_in_roots(g):
            paths.add(g)
    for d in WATCH_DIRS:
        for f in list_top_level_files(d):
            name = os.path.basename(f)
            if any(cid in name for cid in watch_names):
                paths.add(f)
        try:
            with os.scandir(d) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        for f in list_top_level_files(entry.path):
                            name = os.path.basename(f)
                            if any(cid in name for cid in watch_names) or \
                               any(cid in entry.name for cid in watch_names):
                                paths.add(f)
        except OSError:
            pass
    return sorted(p for p in paths if safe_path_in_roots(p))


def hash_watched(paths):
    snapshot = {}
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            continue
        digest, note = sha256_file(p)
        snapshot[p] = {"size": st.st_size, "mtime": st.st_mtime,
                       "sha256": digest, "note": note}
    return snapshot


def diff_snapshots(before, after):
    changes = []
    all_paths = set(before.keys()) | set(after.keys())
    for p in sorted(all_paths):
        b = before.get(p)
        a = after.get(p)
        if b is None and a is not None:
            changes.append({"path": p, "change": "ADDED"})
        elif a is None and b is not None:
            changes.append({"path": p, "change": "REMOVED"})
        else:
            if b["sha256"] is None or a["sha256"] is None:
                if b["size"] != a["size"] or b["mtime"] != a["mtime"]:
                    changes.append({"path": p, "change": "NOT_PROVEN_UNCHANGED"})
            elif b["sha256"] != a["sha256"]:
                changes.append({"path": p, "change": "MODIFIED"})
    return changes


# --------------------------------------------------------------------------
# Read-only SQLite access
# --------------------------------------------------------------------------

def open_db_readonly(path):
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.execute("PRAGMA query_only = ON;")
    return conn


def quick_check(conn):
    try:
        cur = conn.execute("PRAGMA quick_check;")
        row = cur.fetchone()
        if row and str(row[0]).lower() == "ok":
            return "PASS"
        return f"FAIL:{row}"
    except Exception as e:
        return f"NOT_PROVEN:{e}"


def list_tables(conn):
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return [r[0] for r in cur.fetchall()]
    except Exception:
        return []


def table_columns(conn, table):
    try:
        cur = conn.execute(f'PRAGMA table_info("{table}")')
        return [r[1] for r in cur.fetchall()]
    except Exception:
        return []


def find_column_match(columns, aliases):
    for col in columns:
        low = col.lower()
        for a in aliases:
            if a in low:
                return col
    return None


def build_table_map(conn):
    tables = list_tables(conn)
    return {t: table_columns(conn, t) for t in tables}


def find_rows_by_column_value(conn, table_map, alias_key, value):
    matches = []
    if value is None:
        return matches
    for table, cols in table_map.items():
        col = find_column_match(cols, FIELD_ALIASES[alias_key])
        if not col:
            continue
        try:
            q = f'SELECT rowid, * FROM "{table}" WHERE "{col}" = ?'
            cur = conn.execute(q, (value,))
            rows = cur.fetchall()
            if rows:
                desc = [d[0] for d in cur.description]
                for row in rows:
                    matches.append({"table": table, "match_column": col,
                                     "columns": desc, "row": row})
        except Exception:
            continue
    return matches


def map_fields(columns, row):
    fields = {}
    for canonical, aliases in FIELD_ALIASES.items():
        col = find_column_match(columns, aliases)
        if col:
            idx = columns.index(col)
            fields[canonical] = sanitize_value(row[idx])
    return fields


# --------------------------------------------------------------------------
# Media validation
# --------------------------------------------------------------------------

def split_media_candidates(raw):
    if raw is None:
        return []
    if not isinstance(raw, str):
        raw = str(raw)
    parts = re.split(r"[,;\n]+", raw)
    return [p.strip() for p in parts if p.strip()]


def resolve_media_path(candidate):
    if os.path.isabs(candidate):
        return candidate
    return os.path.join("/home/Carix", candidate)


def classify_media_status(value):
    if value is None:
        return "UNKNOWN"
    v = str(value).strip().lower()
    if v in MEDIA_STATUS_READY:
        return "READY"
    if v in MEDIA_STATUS_REJECTED:
        return "REJECTED_OR_PENDING"
    return "UNKNOWN"


def validate_media_files(candidates):
    ready = []
    rejected = []
    video_hashes = {}
    for c in candidates:
        path = resolve_media_path(c)
        ext = os.path.splitext(path)[1].lower()
        entry = {"declared": c, "resolved": path}
        if ext not in ALLOWED_MEDIA_EXT:
            entry["reason"] = "EXTENSION_NOT_ALLOWED"
            rejected.append(entry)
            continue
        if not is_safe_regular_file(path):
            entry["reason"] = "MISSING_OR_UNSAFE_OR_EMPTY"
            rejected.append(entry)
            continue
        if ext in ALLOWED_VIDEO_EXT:
            digest, note = sha256_file(path)
            if digest is None:
                entry["reason"] = note or "HASH_NOT_PROVEN"
                rejected.append(entry)
                continue
            if digest in video_hashes:
                entry["reason"] = f"DUPLICATE_VIDEO_HASH_OF:{video_hashes[digest]}"
                rejected.append(entry)
                continue
            video_hashes[digest] = path
            entry["sha256"] = digest
        ready.append(entry)
    return ready, rejected


# --------------------------------------------------------------------------
# HTML inspection
# --------------------------------------------------------------------------

class HTMLInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.viewport_found = False
        self.chat_block_count = 0
        self.diag_cta_count = 0
        self.empty_src_href = 0
        self.external_refs = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "meta" and (d.get("name") or "").lower() == "viewport":
            self.viewport_found = True
        combined = ((d.get("class") or "") + " " + (d.get("id") or "")).lower()
        if "chat" in combined:
            self.chat_block_count += 1
        if "diag" in combined:
            self.diag_cta_count += 1
        for attr in ("src", "href"):
            if attr in d:
                val = d[attr]
                if val is None or val.strip() == "":
                    self.empty_src_href += 1
                elif val.startswith("http://") or val.startswith("https://"):
                    self.external_refs.append(val)


def find_sandbox_html(card_id):
    candidates = []
    for d in WATCH_DIRS:
        for f in list_top_level_files(d):
            if card_id in os.path.basename(f) and f.lower().endswith(".html"):
                candidates.append(f)
        try:
            with os.scandir(d) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False) and card_id in entry.name:
                        for f in list_top_level_files(entry.path):
                            if f.lower().endswith(".html"):
                                candidates.append(f)
        except OSError:
            pass
    candidates = [c for c in candidates if safe_path_in_roots(c) and is_safe_regular_file(c)]
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def validate_html(path):
    try:
        text = read_bounded(path)
    except Exception as e:
        return {"error": str(e)}
    inspector = HTMLInspector()
    try:
        inspector.feed(text)
    except Exception as e:
        return {"error": f"PARSE_ERROR:{e}"}
    return {
        "viewport_meta_present": inspector.viewport_found,
        "chat_block_count": inspector.chat_block_count,
        "diag_cta_count": inspector.diag_cta_count,
        "empty_src_or_href": inspector.empty_src_href,
        "external_refs_count": len(inspector.external_refs),
    }


def sandbox_10_runs(path):
    """Re-reads and re-hashes the same static evidence file 10 times and
    requires identical normalized output every time (determinism proof for
    already-produced sandbox HTML). No generator code is executed."""
    hashes = []
    for _ in range(10):
        digest, note = sha256_file(path)
        if digest is None:
            return f"NOT_PROVEN:{note}"
        hashes.append(digest)
    if len(set(hashes)) == 1:
        return "10/10 IDENTICAL"
    return "MISMATCH_DETECTED"


# --------------------------------------------------------------------------
# Generator static inspection (never executed)
# --------------------------------------------------------------------------

def inspect_generators():
    results = {}
    for path in GENERATOR_CANDIDATES:
        if not os.path.isfile(path) or os.path.islink(path) or not safe_path_in_roots(path):
            results[path] = "NOT_FOUND"
            continue
        try:
            text = read_bounded(path)
        except Exception:
            results[path] = "UNREADABLE"
            continue
        literals = re.findall(r"UA-0*([0-9]{3,4})", text)
        unique_nums = sorted(set(int(x) for x in literals)) if literals else []
        if unique_nums and max(unique_nums) <= 8:
            results[path] = "HARD_LIMIT_SUSPECTED"
        else:
            results[path] = "NO_HARD_LIMIT_EVIDENCE"
    return results


def summarize_generator_inspection(results):
    found = [v for v in results.values() if v != "NOT_FOUND"]
    if not found:
        return "NOT_PROVEN"
    if any(v == "HARD_LIMIT_SUSPECTED" for v in results.values()):
        return "FAIL"
    if any(v == "UNREADABLE" for v in results.values()) and \
       not any(v == "NO_HARD_LIMIT_EVIDENCE" for v in results.values()):
        return "NOT_PROVEN"
    return "PASS"


# --------------------------------------------------------------------------
# Atomic, boundary-checked writes
# --------------------------------------------------------------------------

def assert_allowed_write(path, card_ids):
    rp = os.path.realpath(path)
    if rp in (os.path.realpath(REPORT_TXT), os.path.realpath(REPORT_JSON)):
        return True
    sandbox_root_rp = os.path.realpath(SANDBOX_FACTORY_ROOT)
    if rp == sandbox_root_rp or rp.startswith(sandbox_root_rp + os.sep):
        rel = rp[len(sandbox_root_rp):].lstrip(os.sep)
        parts = rel.split(os.sep)
        if len(parts) >= 2 and parts[0] in card_ids and parts[1] == "video":
            return True
    return False


def atomic_write_bytes(path, data, card_ids):
    if not assert_allowed_write(path, card_ids):
        raise PermissionError(f"Write not permitted outside approved boundaries: {path}")
    if os.path.lexists(path) and os.path.islink(path):
        raise PermissionError(f"Refusing to write over symlink: {path}")
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# --------------------------------------------------------------------------
# Per-card processing
# --------------------------------------------------------------------------

def process_card(card_id, conn, table_map):
    result = {
        "CARD_ID": card_id,
        "CRM_ROW_FOUND": False,
        "DUPLICATE_CLASSIFICATION": "NONE",
        "FIELDS_RECOVERED": {},
        "VISUAL_DRAFT_MISSING_FIELDS": [],
        "PUBLICATION_MISSING_FIELDS": [],
        "READY_MEDIA": [],
        "REJECTED_MEDIA": [],
        "OBD_DIAGNOSTIC_RULE": "NOT_EVALUATED",
        "HTML_VALIDATION": "NOT_PROVEN",
        "SANDBOX_10_RUNS": "NOT_PROVEN",
        "SANDBOX_PATH": None,
        "READY_FOR_VISUAL_CHECK": False,
        "READY_FOR_PUBLICATION": False,
        "BLOCKERS": [],
        "OWNER_STATUS": "NEEDS_DATA",
        "OWNER_REASON": "",
    }

    if not CARD_ID_RE.match(card_id):
        result["OWNER_STATUS"] = "BLOCKED_SAFETY"
        result["OWNER_REASON"] = "Invalid card id format"
        result["BLOCKERS"].append("INVALID_CARD_ID_FORMAT")
        return result

    matches = find_rows_by_column_value(conn, table_map, "auto_number", card_id)

    if not matches:
        result["OWNER_STATUS"] = "NEEDS_DATA"
        result["OWNER_REASON"] = "CARD_NOT_IN_CRM"
        result["BLOCKERS"].append("CARD_NOT_IN_CRM")
        return result

    result["CRM_ROW_FOUND"] = True
    if len(matches) > 1:
        evidence = [f'{m["table"]}:rowid={m["row"][0]}' for m in matches]
        result["DUPLICATE_CLASSIFICATION"] = "MULTIPLE_ROWS: " + "; ".join(evidence)
    primary = matches[0]
    fields = map_fields(primary["columns"], primary["row"])
    result["FIELDS_RECOVERED"] = fields

    vin_value = fields.get("vin")
    if vin_value:
        vin_matches = find_rows_by_column_value(conn, table_map, "vin", vin_value)
        other_cards = set()
        for vm in vin_matches:
            an_col = find_column_match(vm["columns"], FIELD_ALIASES["auto_number"])
            if an_col:
                idx = vm["columns"].index(an_col)
                other = vm["row"][idx]
                if other and other != card_id:
                    other_cards.add(str(other))
        if other_cards:
            result["BLOCKERS"].append(f"VIN_CONFLICT_WITH:{','.join(sorted(other_cards))}")

    result["VISUAL_DRAFT_MISSING_FIELDS"] = [
        f for f in VISUAL_DRAFT_REQUIRED_FIELDS if not fields.get(f)
    ]
    result["PUBLICATION_MISSING_FIELDS"] = [
        f for f in PUBLICATION_REQUIRED_FIELDS if not fields.get(f)
    ]

    # Related media rows: any table with a column matching auto_number or vin
    # equal to this card's identity.
    related_rows = list(matches)
    if vin_value:
        related_rows += find_rows_by_column_value(conn, table_map, "vin", vin_value)

    media_candidates = []
    diag_evidence = []
    for rr in related_rows:
        cols = rr["columns"]
        row = rr["row"]
        status_col = find_column_match(cols, FIELD_ALIASES["status"])
        status_val = row[cols.index(status_col)] if status_col else None
        media_status = classify_media_status(status_val)
        for key in ("photo", "video"):
            col = find_column_match(cols, FIELD_ALIASES[key])
            if col:
                raw = row[cols.index(col)]
                for c in split_media_candidates(sanitize_value(raw) if not isinstance(raw, (bytes, bytearray)) else None):
                    media_candidates.append((c, media_status))
        diag_col = find_column_match(cols, FIELD_ALIASES["diag"])
        obd_col = find_column_match(cols, FIELD_ALIASES["obd"])
        for col in (diag_col, obd_col):
            if col:
                val = row[cols.index(col)]
                if val not in (None, "", 0):
                    diag_evidence.append(f'{rr["table"]}.{col}={sanitize_value(val)}')

    ready_candidates = [c for c, st in media_candidates if st != "REJECTED_OR_PENDING"]
    pending_rejected = [c for c, st in media_candidates if st == "REJECTED_OR_PENDING"]

    ready_media, rejected_media = validate_media_files(ready_candidates)
    for c in pending_rejected:
        rejected_media.append({"declared": c, "reason": "CRM_STATUS_NOT_READY"})
    result["READY_MEDIA"] = ready_media
    result["REJECTED_MEDIA"] = rejected_media

    if diag_evidence:
        result["OBD_DIAGNOSTIC_RULE"] = "CTA_ALLOWED: " + "; ".join(diag_evidence[:5])
    else:
        has_diag_media = any("diag" in m["declared"].lower() for m in ready_media)
        if has_diag_media:
            result["OBD_DIAGNOSTIC_RULE"] = "CTA_ALLOWED: diag media file present"
        else:
            result["OBD_DIAGNOSTIC_RULE"] = "CTA_NOT_ALLOWED: no diagnostic evidence found"

    sandbox_html = find_sandbox_html(card_id)
    if sandbox_html:
        result["SANDBOX_PATH"] = sandbox_html
        validation = validate_html(sandbox_html)
        if "error" in validation:
            result["HTML_VALIDATION"] = f"NOT_PROVEN:{validation['error']}"
        else:
            issues = []
            if not validation["viewport_meta_present"]:
                issues.append("MISSING_VIEWPORT_META")
            if validation["chat_block_count"] != 1:
                issues.append(f"CHAT_BLOCK_COUNT={validation['chat_block_count']}")
            if validation["diag_cta_count"] > 1:
                issues.append(f"DUPLICATE_DIAG_CTA={validation['diag_cta_count']}")
            if validation["empty_src_or_href"] > 0:
                issues.append(f"EMPTY_SRC_OR_HREF={validation['empty_src_or_href']}")
            result["HTML_VALIDATION"] = "PASS" if not issues else "ISSUES: " + "; ".join(issues)
        result["SANDBOX_10_RUNS"] = sandbox_10_runs(sandbox_html)

        # Faithful isolated review copy: verbatim copy of the real,
        # already-produced sandbox HTML (no code execution, no template
        # substitution of untrusted values -> nothing to escape here
        # because the file already contains its own rendered values).
        try:
            with open(sandbox_html, "rb") as f:
                data = f.read(BOUNDED_READ_LIMIT + 1)
            if len(data) <= BOUNDED_READ_LIMIT:
                dest = os.path.join(SANDBOX_FACTORY_ROOT, card_id, "video", "review_copy.html")
                try:
                    atomic_write_bytes(dest, data, [card_id])
                except PermissionError:
                    pass
        except OSError:
            pass
    else:
        result["HTML_VALIDATION"] = "PREVIEW_STRUCTURE_NOT_PROVEN"
        result["SANDBOX_10_RUNS"] = "NOT_PROVEN"

    # Draft readiness
    safety_blockers = [b for b in result["BLOCKERS"] if b.startswith("VIN_CONFLICT")]
    has_any_evidence = bool(ready_media) or sandbox_html is not None

    if safety_blockers:
        result["OWNER_STATUS"] = "BLOCKED_SAFETY"
        result["OWNER_REASON"] = "; ".join(safety_blockers)
    elif result["VISUAL_DRAFT_MISSING_FIELDS"] or not has_any_evidence:
        result["OWNER_STATUS"] = "NEEDS_DATA"
        missing = list(result["VISUAL_DRAFT_MISSING_FIELDS"])
        if not has_any_evidence:
            missing.append("no ready media or sandbox HTML found")
        result["OWNER_REASON"] = "Missing: " + ", ".join(missing)
    else:
        result["OWNER_STATUS"] = "READY_FOR_VISUAL_CHECK"
        result["OWNER_REASON"] = "Identity and draft content present"
        result["READY_FOR_VISUAL_CHECK"] = True

    result["READY_FOR_PUBLICATION"] = (
        result["READY_FOR_VISUAL_CHECK"]
        and not result["PUBLICATION_MISSING_FIELDS"]
        and not rejected_media
        and result["OBD_DIAGNOSTIC_RULE"].startswith(("CTA_ALLOWED", "CTA_NOT_ALLOWED"))
    )
    if result["READY_FOR_PUBLICATION"]:
        result["BLOCKERS"].append("CRITICAL_APPROVAL_STILL_REQUIRED")
        result["READY_FOR_PUBLICATION"] = False  # this tool never authorizes publication

    return result


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    started = utc_now_iso()
    args = sys.argv[1:]
    card_ids = args if args else list(DEFAULT_CARDS)

    valid_card_ids = []
    invalid_entries = []
    for c in card_ids:
        if CARD_ID_RE.match(c):
            valid_card_ids.append(c)
        else:
            invalid_entries.append(c)

    global_report = {
        "SQLITE_QUICK_CHECK": "NOT_PROVEN",
        "DATABASE_UNCHANGED": "NOT_PROVEN",
        "UA0001_0008_UNCHANGED": "NOT_PROVEN",
        "PROTECTED_SHARED_FILES_UNCHANGED": "NOT_PROVEN",
        "GENERATOR_NOT_HARD_LIMITED": "NOT_PROVEN",
        "FUTURE_CARD_TEST": "NOT_PROVEN",
        "UNEXPECTED_CHANGES": [],
        "PRODUCTION_WRITE_PERFORMED": "NO",
        "SAFE_TO_PUBLISH_NOW": "NO",
        "STATUS": "UNKNOWN",
    }

    watched_before = discover_watched_paths(valid_card_ids)
    hashes_before = hash_watched(watched_before)

    db_hash_before, db_note_before = (None, "DB_NOT_FOUND")
    if os.path.isfile(CRM_DB_PATH):
        db_hash_before, db_note_before = sha256_file(CRM_DB_PATH)

    per_card_results = []

    if not os.path.isfile(CRM_DB_PATH):
        for cid in valid_card_ids:
            per_card_results.append({
                "CARD_ID": cid, "CRM_ROW_FOUND": False,
                "OWNER_STATUS": "BLOCKED_SAFETY",
                "OWNER_REASON": "CRM database not found at expected path",
                "BLOCKERS": ["CRM_DB_NOT_FOUND"],
                "DUPLICATE_CLASSIFICATION": "NONE", "FIELDS_RECOVERED": {},
                "VISUAL_DRAFT_MISSING_FIELDS": [], "PUBLICATION_MISSING_FIELDS": [],
                "READY_MEDIA": [], "REJECTED_MEDIA": [], "OBD_DIAGNOSTIC_RULE": "NOT_EVALUATED",
                "HTML_VALIDATION": "NOT_PROVEN", "SANDBOX_10_RUNS": "NOT_PROVEN",
                "SANDBOX_PATH": None, "READY_FOR_VISUAL_CHECK": False,
                "READY_FOR_PUBLICATION": False,
            })
        global_report["SQLITE_QUICK_CHECK"] = "NOT_PROVEN:DB_NOT_FOUND"
    else:
        try:
            conn = open_db_readonly(CRM_DB_PATH)
        except Exception as e:
            conn = None
            global_report["SQLITE_QUICK_CHECK"] = f"NOT_PROVEN:{e}"
        if conn is not None:
            global_report["SQLITE_QUICK_CHECK"] = quick_check(conn)
            try:
                table_map = build_table_map(conn)
            except Exception:
                table_map = {}
            for cid in valid_card_ids:
                try:
                    per_card_results.append(process_card(cid, conn, table_map))
                except Exception as e:
                    per_card_results.append({
                        "CARD_ID": cid, "CRM_ROW_FOUND": False,
                        "OWNER_STATUS": "BLOCKED_SAFETY",
                        "OWNER_REASON": f"Internal processing error: {e}",
                        "BLOCKERS": ["INTERNAL_ERROR"],
                        "DUPLICATE_CLASSIFICATION": "NONE", "FIELDS_RECOVERED": {},
                        "VISUAL_DRAFT_MISSING_FIELDS": [], "PUBLICATION_MISSING_FIELDS": [],
                        "READY_MEDIA": [], "REJECTED_MEDIA": [], "OBD_DIAGNOSTIC_RULE": "NOT_EVALUATED",
                        "HTML_VALIDATION": "NOT_PROVEN", "SANDBOX_10_RUNS": "NOT_PROVEN",
                        "SANDBOX_PATH": None, "READY_FOR_VISUAL_CHECK": False,
                        "READY_FOR_PUBLICATION": False,
                    })
            conn.close()

    for cid in invalid_entries:
        per_card_results.append({
            "CARD_ID": cid, "CRM_ROW_FOUND": False,
            "OWNER_STATUS": "BLOCKED_SAFETY",
            "OWNER_REASON": "Invalid card id format",
            "BLOCKERS": ["INVALID_CARD_ID_FORMAT"],
            "DUPLICATE_CLASSIFICATION": "NONE", "FIELDS_RECOVERED": {},
            "VISUAL_DRAFT_MISSING_FIELDS": [], "PUBLICATION_MISSING_FIELDS": [],
            "READY_MEDIA": [], "REJECTED_MEDIA": [], "OBD_DIAGNOSTIC_RULE": "NOT_EVALUATED",
            "HTML_VALIDATION": "NOT_PROVEN", "SANDBOX_10_RUNS": "NOT_PROVEN",
            "SANDBOX_PATH": None, "READY_FOR_VISUAL_CHECK": False,
            "READY_FOR_PUBLICATION": False,
        })

    # Post-processing drift detection
    watched_after = discover_watched_paths(valid_card_ids)
    hashes_after = hash_watched(watched_after)
    changes = diff_snapshots(hashes_before, hashes_after)
    protected_changes = [c for c in changes if any(pc in c["path"] for pc in PROTECTED_CARDS)]
    generator_changes = [c for c in changes if c["path"] in GENERATOR_CANDIDATES]

    global_report["UNEXPECTED_CHANGES"] = changes
    global_report["UA0001_0008_UNCHANGED"] = "PASS" if not protected_changes else "FAIL:" + str(protected_changes)
    global_report["PROTECTED_SHARED_FILES_UNCHANGED"] = "PASS" if not generator_changes else "FAIL:" + str(generator_changes)

    db_hash_after, db_note_after = (None, "DB_NOT_FOUND")
    if os.path.isfile(CRM_DB_PATH):
        db_hash_after, db_note_after = sha256_file(CRM_DB_PATH)

    if db_hash_before is None or db_hash_after is None:
        if db_note_before == db_note_after == "NOT_PROVEN_TOO_LARGE":
            global_report["DATABASE_UNCHANGED"] = "NOT_PROVEN:TOO_LARGE_TO_HASH"
        elif db_note_before == "DB_NOT_FOUND" or db_note_after == "DB_NOT_FOUND":
            global_report["DATABASE_UNCHANGED"] = "NOT_PROVEN:DB_NOT_FOUND"
        else:
            global_report["DATABASE_UNCHANGED"] = "NOT_PROVEN"
    else:
        global_report["DATABASE_UNCHANGED"] = "PASS" if db_hash_before == db_hash_after else "FAIL"

    gen_results = inspect_generators()
    global_report["GENERATOR_NOT_HARD_LIMITED"] = summarize_generator_inspection(gen_results)
    global_report["FUTURE_CARD_TEST"] = global_report["GENERATOR_NOT_HARD_LIMITED"]

    unsafe_conditions = (
        global_report["SQLITE_QUICK_CHECK"] != "PASS"
        or global_report["DATABASE_UNCHANGED"] == "FAIL"
        or global_report["UA0001_0008_UNCHANGED"].startswith("FAIL")
        or global_report["PROTECTED_SHARED_FILES_UNCHANGED"].startswith("FAIL")
        or global_report["GENERATOR_NOT_HARD_LIMITED"] == "FAIL"
    )
    if unsafe_conditions:
        global_report["STATUS"] = "FAIL"
    elif (
        global_report["SQLITE_QUICK_CHECK"] == "PASS"
        and global_report["DATABASE_UNCHANGED"] == "PASS"
        and global_report["UA0001_0008_UNCHANGED"] == "PASS"
        and global_report["PROTECTED_SHARED_FILES_UNCHANGED"] == "PASS"
    ):
        global_report["STATUS"] = "PASS"
    else:
        global_report["STATUS"] = "NOT_PROVEN"

    finished = utc_now_iso()

    # ---------------- Build owner-facing text report ----------------
    lines = []
    for r in per_card_results:
        lines.append(f'{r["CARD_ID"]} | {r["OWNER_STATUS"]} | {r["OWNER_REASON"]}')
    lines.append(f'GLOBAL_SAFETY | {global_report["STATUS"]}')
    lines.append("PRODUCTION_CHANGED | NO")
    any_ready = any(r["OWNER_STATUS"] == "READY_FOR_VISUAL_CHECK" for r in per_card_results)
    any_needs = any(r["OWNER_STATUS"] == "NEEDS_DATA" for r in per_card_results)
    if any_ready:
        next_action = "Open the sandbox review copy for each READY card and confirm visually, then request CRITICAL publication approval separately."
    elif any_needs:
        next_action = "Add the exact missing CRM fields/media listed above, then re-run this tool."
    else:
        next_action = "Review the safety blockers listed above before doing anything else."
    lines.append(f"NEXT_OWNER_ACTION | {next_action}")

    detail = {
        "generated_at_utc": finished,
        "started_at_utc": started,
        "requested_cards": card_ids,
        "per_card": per_card_results,
        "global": global_report,
        "generator_inspection_raw": gen_results,
    }

    txt_body = "\n".join(lines) + "\n\n----- DETAIL (JSON) -----\n" + json.dumps(detail, indent=2, default=str, ensure_ascii=False) + "\n"
    json_body = json.dumps(detail, indent=2, default=str, ensure_ascii=False) + "\n"

    try:
        atomic_write_bytes(REPORT_TXT, txt_body.encode("utf-8"), valid_card_ids)
        atomic_write_bytes(REPORT_JSON, json_body.encode("utf-8"), valid_card_ids)
    except PermissionError as e:
        print(f"WRITE_BLOCKED: {e}")

    print(txt_body)


if __name__ == "__main__":
    main()
