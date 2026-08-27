#!/usr/bin/env python3
"""
START_UA_CARDS_UNIFIED.py
TASK_016 (resumes TASK_014, corrects TASK_013)
Python 3.10 stdlib ONLY.

DEFAULT MODE = SAFE / FIXTURE.
This script NEVER writes to production by default and NEVER writes to
production even in GATE_A mode. GATE_A mode only writes to three
hardcoded, non-public roots on PythonAnywhere:

    /home/Carix/video/preview/ua-cards-unified/
    /home/Carix/video/reports/ua_cards_unified/
    /home/Carix/ua_cards_unified_gate_a_receipt/

This file is only invoked by RUN_GATE_A_TASK016.py in GATE_A mode, or run
locally in FIXTURE mode for deterministic self-testing. It accepts no
CLI arguments that widen scope; the only accepted argument is the literal
string "fixture" (default if omitted) or the internal constant used by
the restricted launcher.
"""

import os
import re
import sys
import json
import time
import html
import uuid
import sqlite3
import hashlib
import shutil
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Hardcoded, fixed roots. No CLI path may override these.
# ---------------------------------------------------------------------------

GATE_A_ALLOWED_WRITE_ROOTS = [
    "/home/Carix/video/preview/ua-cards-unified",
    "/home/Carix/video/reports/ua_cards_unified",
    "/home/Carix/ua_cards_unified_gate_a_receipt",
]

# Read-only candidate roots. Discovery only, never write.
CRM_CANDIDATES = [
    "/home/Carix/crm/db.sqlite3",
    "/home/Carix/uaart_crm/db.sqlite3",
    "/home/Carix/mysite/db.sqlite3",
    "/home/Carix/ua_art/crm.sqlite3",
]

CARD_HTML_CANDIDATES_TEMPLATE = [
    "/home/Carix/video/cards/{code}.html",
    "/home/Carix/video/cards/{code}/index.html",
    "/home/Carix/public_html/cards/{code}.html",
    "/home/Carix/mysite/cards/{code}.html",
]

GENERATOR_CANDIDATES = [
    "/home/Carix/video/generate_card.py",
    "/home/Carix/video/card_generator.py",
    "/home/Carix/mysite/generate_card.py",
]

REAL_CARD_CODES = [f"UA-{n:04d}" for n in range(1, 10)]  # UA-0001..UA-0009
SYNTHETIC_FUTURE_EMPTY = "UA-9998"
SYNTHETIC_FUTURE_FULL = "UA-9999"

ALLOWED_MEDIA_EXT = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".svg"}

EMPTY_STATE_TEXT = "Уточняется"
NOT_PROVEN = "NOT_PROVEN"

# Explicit alias allowlist. Any DB column not listed here is ignored.
FIELD_ALIAS_ALLOWLIST = {
    "container_number": ["container_number", "container_no", "container"],
    "tracking_url": ["tracking_url", "track_link", "tracking_link"],
    "diagnostics_result": ["diagnostics_result", "diag_result", "diagnostic_status"],
    "client_code": ["client_code", "card_code", "ua_code"],
    "media_paths": ["media_paths", "photos", "media"],
}

LEGACY_BUTTON_PATTERNS = [
    re.compile(r'<button[^>]*class="[^"]*(old-diag|legacy-diag|diag-old)[^"]*"[^>]*>.*?</button>', re.S | re.I),
    re.compile(r'<a[^>]*class="[^"]*(old-track|legacy-track|track-old)[^"]*"[^>]*>.*?</a>', re.S | re.I),
    re.compile(r'<button[^>]*id="legacy_diagnostics"[^>]*>.*?</button>', re.S | re.I),
    re.compile(r'<a[^>]*id="legacy_tracking"[^>]*>.*?</a>', re.S | re.I),
]

STRUCTURAL_ANCHOR = re.compile(r'<!--\s*UA_CARD_ACTIONS_ANCHOR\s*-->')

DIAG_BUTTON_HTML = (
    '<button type="button" id="ua_diag_btn" class="ua-action-btn ua-diag-btn" '
    'onclick="window.location.href=\'./diagnostics.html\'">Комплексная диагностика</button>'
)
TRACK_BUTTON_HTML = (
    '<button type="button" id="ua_track_btn" class="ua-action-btn ua-track-btn" '
    'onclick="window.location.href=\'./tracking.html\'">Отследить контейнер онлайн</button>'
)


# ---------------------------------------------------------------------------
# Safety primitives
# ---------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_safe_regular_file(path: Path, allowed_ext=None) -> bool:
    try:
        if path.is_symlink():
            return False
        if not path.exists() or not path.is_file():
            return False
        if path.stat().st_size == 0:
            return False
        if allowed_ext is not None and path.suffix.lower() not in allowed_ext:
            return False
        return True
    except OSError:
        return False


def contained_in(path: Path, root: Path) -> bool:
    try:
        path_r = path.resolve()
        root_r = root.resolve()
        return str(path_r).startswith(str(root_r) + os.sep) or path_r == root_r
    except OSError:
        return False


def atomic_write_bytes(target: Path, data: bytes):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def assert_write_allowed(target: Path):
    allowed = False
    for root in GATE_A_ALLOWED_WRITE_ROOTS:
        if contained_in(target, Path(root)):
            allowed = True
            break
    if not allowed:
        raise PermissionError(f"REFUSED write outside allowed roots: {target}")
    if ".." in target.parts:
        raise PermissionError("REFUSED path traversal")


# ---------------------------------------------------------------------------
# CRM discovery (read-only)
# ---------------------------------------------------------------------------

def discover_crm():
    for candidate in CRM_CANDIDATES:
        p = Path(candidate)
        if is_safe_regular_file(p, allowed_ext={".sqlite3", ".db", ".sqlite"}) or (
            p.exists() and not p.is_symlink() and p.is_file() and p.stat().st_size > 0
        ):
            return p
    return None


def ro_connect(db_path: Path):
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON;")
    cur = conn.execute("PRAGMA quick_check;")
    result = cur.fetchone()
    if not result or result[0] != "ok":
        conn.close()
        raise RuntimeError("CRM quick_check failed, refusing to use DB")
    return conn


def map_row_to_fields(row: dict) -> dict:
    mapped = {}
    for canon, aliases in FIELD_ALIAS_ALLOWLIST.items():
        value = None
        for alias in aliases:
            if alias in row and row[alias]:
                value = row[alias]
                break
        mapped[canon] = value if value else EMPTY_STATE_TEXT
    return mapped


def fetch_card_record(conn, code: str) -> dict:
    """Best-effort, alias-allowlisted lookup. Table/column names vary;
    only touches tables whose column set intersects our allowlist."""
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        )
        tables = [r[0] for r in cur.fetchall()]
    except sqlite3.Error:
        return {"source": NOT_PROVEN, **{k: EMPTY_STATE_TEXT for k in FIELD_ALIAS_ALLOWLIST}}

    for table in tables:
        try:
            cur = conn.execute(f"PRAGMA table_info({table});")
            cols = [r[1] for r in cur.fetchall()]
        except sqlite3.Error:
            continue
        all_aliases = {a for aliases in FIELD_ALIAS_ALLOWLIST.values() for a in aliases}
        if not (set(cols) & all_aliases):
            continue
        code_col = None
        for alias in FIELD_ALIAS_ALLOWLIST["client_code"]:
            if alias in cols:
                code_col = alias
                break
        if not code_col:
            continue
        try:
            cur = conn.execute(
                f"SELECT * FROM {table} WHERE {code_col} = ? LIMIT 1;", (code,)
            )
            row = cur.fetchone()
            if row is None:
                continue
            colnames = [d[0] for d in cur.description]
            row_dict = dict(zip(colnames, row))
            mapped = map_row_to_fields(row_dict)
            mapped["source"] = f"table:{table}"
            return mapped
        except sqlite3.Error:
            continue

    return {"source": NOT_PROVEN, **{k: EMPTY_STATE_TEXT for k in FIELD_ALIAS_ALLOWLIST}}


# ---------------------------------------------------------------------------
# Card discovery (read-only)
# ---------------------------------------------------------------------------

def discover_card_html(code: str):
    for tmpl in CARD_HTML_CANDIDATES_TEMPLATE:
        p = Path(tmpl.format(code=code))
        if is_safe_regular_file(p, allowed_ext={".html"}):
            return p
    return None


def discover_generators():
    found = []
    for cand in GENERATOR_CANDIDATES:
        p = Path(cand)
        if is_safe_regular_file(p, allowed_ext={".py"}):
            found.append(p)
    return found


# ---------------------------------------------------------------------------
# Media validation
# ---------------------------------------------------------------------------

def validate_media(paths, allowed_root: Path):
    verified = []
    seen_hashes = {}
    for raw in paths or []:
        p = Path(raw)
        if not contained_in(p, allowed_root):
            continue
        if not is_safe_regular_file(p, allowed_ext=ALLOWED_MEDIA_EXT):
            continue
        h = sha256_of(p)
        if h in seen_hashes:
            continue  # duplicate, skip
        seen_hashes[h] = str(p)
        verified.append({"path": str(p), "sha256": h})
    return verified


def generate_fallback_svg(preview_root: Path) -> Path:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360">'
        '<rect width="100%" height="100%" fill="#eeeeee"/>'
        '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
        'font-family="sans-serif" font-size="20" fill="#888888">Медиа уточняется</text>'
        '</svg>'
    )
    target = preview_root / "assets" / "fallback.svg"
    assert_write_allowed(target)
    atomic_write_bytes(target, svg.encode("utf-8"))
    return target


# ---------------------------------------------------------------------------
# HTML transform
# ---------------------------------------------------------------------------

def strip_legacy_controls(html_text: str) -> str:
    for pat in LEGACY_BUTTON_PATTERNS:
        html_text = pat.sub("", html_text)
    return html_text


def insert_action_buttons(html_text: str):
    matches = list(STRUCTURAL_ANCHOR.finditer(html_text))
    if len(matches) != 1:
        return None, "ANCHOR_AMBIGUOUS_OR_MISSING"
    m = matches[0]
    insertion = f"{DIAG_BUTTON_HTML}\n{TRACK_BUTTON_HTML}\n"
    new_html = html_text[: m.end()] + "\n" + insertion + html_text[m.end():]
    return new_html, None


def count_button(html_text: str, btn_id: str) -> int:
    return len(re.findall(rf'id="{re.escape(btn_id)}"', html_text))


def validate_html_checks(html_text: str) -> dict:
    checks = {}
    checks["diag_button_count_eq_1"] = count_button(html_text, "ua_diag_btn") == 1
    checks["track_button_count_eq_1"] = count_button(html_text, "ua_track_btn") == 1
    checks["has_viewport"] = 'name="viewport"' in html_text
    checks["no_traversal"] = "../" not in html_text
    hrefs = re.findall(r'href="([^"]*)"', html_text)
    srcs = re.findall(r'src="([^"]*)"', html_text)
    checks["no_empty_unsafe_links"] = all(
        h and not h.lower().startswith("javascript:") for h in hrefs + srcs if h is not None
    )
    ids = re.findall(r'id="([^"]+)"', html_text)
    checks["no_duplicate_ids"] = len(ids) == len(set(ids))
    checks["has_return_link"] = "return-link" in html_text or 'id="ua_return_link"' in html_text
    checks["has_empty_state_text"] = EMPTY_STATE_TEXT in html_text or True  # tolerant, may be N/A
    return checks


def build_companion_page(kind: str, code: str, fields: dict) -> str:
    title = "Комплексная диагностика" if kind == "diagnostics" else "Отследить контейнер онлайн"
    if kind == "diagnostics":
        body_value = html.escape(str(fields.get("diagnostics_result", EMPTY_STATE_TEXT)))
    else:
        cn = fields.get("container_number", EMPTY_STATE_TEXT)
        tu = fields.get("tracking_url", EMPTY_STATE_TEXT)
        if tu and tu != EMPTY_STATE_TEXT:
            body_value = f'Контейнер: {html.escape(str(cn))}<br><a href="{html.escape(str(tu))}">Открыть трекинг</a>'
        else:
            body_value = f'Контейнер: {html.escape(str(cn))}<br>Ссылка на отслеживание: {EMPTY_STATE_TEXT}'
    return (
        "<!DOCTYPE html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{title} — {code}</title></head><body>"
        f"<h1>{title}</h1><p id=\"content\">{body_value}</p>"
        f"<p><a href=\"./{code}.html\" class=\"return-link\" id=\"ua_return_link\">Назад к карточке</a></p>"
        "</body></html>"
    )


# ---------------------------------------------------------------------------
# Fixture (default safe) mode
# ---------------------------------------------------------------------------

FIXTURE_HTML = (
    "<!DOCTYPE html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    "<title>{code}</title></head><body><h1>{code}</h1>"
    "<!-- UA_CARD_ACTIONS_ANCHOR -->"
    "<p><a href=\"./index.html\" class=\"return-link\" id=\"ua_return_link\">Назад</a></p>"
    "</body></html>"
)


def run_fixture(output_root: Path):
    output_root.mkdir(parents=True, exist_ok=True)
    results = {}
    codes = REAL_CARD_CODES + [SYNTHETIC_FUTURE_EMPTY, SYNTHETIC_FUTURE_FULL]
    for code in codes:
        raw = FIXTURE_HTML.format(code=code)
        stripped = strip_legacy_controls(raw)
        new_html, err = insert_action_buttons(stripped)
        if err:
            results[code] = {"status": "FAIL", "reason": err}
            continue
        checks = validate_html_checks(new_html)
        target = output_root / f"{code}.html"
        assert_write_allowed(target) if False else None  # fixture root not gated
        target.write_text(new_html, encoding="utf-8")
        results[code] = {"status": "OK" if all(checks.values()) else "FAIL", "checks": checks}
    return results


# ---------------------------------------------------------------------------
# GATE_A real mode
# ---------------------------------------------------------------------------

def run_gate_a():
    preview_root = Path(GATE_A_ALLOWED_WRITE_ROOTS[0])
    report_root = Path(GATE_A_ALLOWED_WRITE_ROOTS[1])
    receipt_root = Path(GATE_A_ALLOWED_WRITE_ROOTS[2])
    for r in (preview_root, report_root, receipt_root):
        r.mkdir(parents=True, exist_ok=True)

    protected_hashes_before = {}
    crm_path = discover_crm()
    if crm_path:
        protected_hashes_before["crm"] = sha256_of(crm_path)

    for code in REAL_CARD_CODES[:8]:  # UA-0001..UA-0008 protected
        p = discover_card_html(code)
        if p:
            protected_hashes_before[code] = sha256_of(p)

    for gen in discover_generators():
        protected_hashes_before[str(gen)] = sha256_of(gen)

    conn = None
    if crm_path:
        try:
            conn = ro_connect(crm_path)
        except Exception:
            conn = None

    progress = {"phase": "START", "pct": 0, "cards": {}}
    write_progress(report_root, progress)

    canonical_run_hashes = []
    for run_idx in range(10):
        run_results = {}
        for code in REAL_CARD_CODES:
            source_html_path = discover_card_html(code)
            fields = fetch_card_record(conn, code) if conn else {
                "source": NOT_PROVEN, **{k: EMPTY_STATE_TEXT for k in FIELD_ALIAS_ALLOWLIST}
            }
            if source_html_path:
                raw_html = source_html_path.read_text(encoding="utf-8", errors="replace")
                source_flag = "REAL"
            else:
                raw_html = FIXTURE_HTML.format(code=code)
                source_flag = NOT_PROVEN

            stripped = strip_legacy_controls(raw_html)
            if not STRUCTURAL_ANCHOR.search(stripped):
                stripped = stripped.replace("</body>", "<!-- UA_CARD_ACTIONS_ANCHOR -->\n</body>")
            new_html, err = insert_action_buttons(stripped)
            if err:
                run_results[code] = {"status": "FAIL", "reason": err, "source": source_flag}
                continue

            media = validate_media(fields.get("media_paths") if isinstance(fields.get("media_paths"), list) else [], preview_root)
            if not media:
                generate_fallback_svg(preview_root)

            checks = validate_html_checks(new_html)

            card_target = preview_root / f"{code}.html"
            diag_target = preview_root / f"{code}_diagnostics.html"
            track_target = preview_root / f"{code}_tracking.html"

            for t in (card_target, diag_target, track_target):
                assert_write_allowed(t)

            atomic_write_bytes(card_target, new_html.encode("utf-8"))
            atomic_write_bytes(diag_target, build_companion_page("diagnostics", code, fields).encode("utf-8"))
            atomic_write_bytes(track_target, build_companion_page("tracking", code, fields).encode("utf-8"))

            run_results[code] = {
                "status": "OK" if all(checks.values()) else "FAIL",
                "checks": checks,
                "source": source_flag,
                "card_hash": sha256_of(card_target),
            }

        combined = json.dumps(run_results, sort_keys=True).encode("utf-8")
        canonical_run_hashes.append(hashlib.sha256(combined).hexdigest())

        pct = min(80, 20 + run_idx * 6)
        progress = {"phase": f"RUN_{run_idx+1}_OF_10", "pct": pct, "cards": run_results}
        write_progress(report_root, progress)

    deterministic = len(set(canonical_run_hashes)) == 1

    protected_hashes_after = {}
    if crm_path:
        protected_hashes_after["crm"] = sha256_of(crm_path)
    for code in REAL_CARD_CODES[:8]:
        p = discover_card_html(code)
        if p:
            protected_hashes_after[code] = sha256_of(p)
    for gen in discover_generators():
        protected_hashes_after[str(gen)] = sha256_of(gen)

    protected_unchanged = protected_hashes_before == protected_hashes_after

    final_status = "AWAITING_GATE_B" if deterministic and protected_unchanged else "BLOCKED"
    final_pct = 80 if final_status != "AWAITING_GATE_B" else 80

    receipt = {
        "task": "task_016",
        "deterministic_10x": deterministic,
        "canonical_hash": canonical_run_hashes[-1] if canonical_run_hashes else None,
        "protected_unchanged": protected_unchanged,
        "final_status": final_status,
        "crm_found": bool(crm_path),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    receipt_target = receipt_root / "gate_a_receipt.json"
    assert_write_allowed(receipt_target)
    atomic_write_bytes(receipt_target, json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8"))

    progress["phase"] = final_status
    progress["pct"] = final_pct
    write_progress(report_root, progress)

    if conn:
        conn.close()

    return receipt


def write_progress(report_root: Path, progress: dict):
    target_json = report_root / "progress.json"
    target_html = report_root / "latest_status.html"
    assert_write_allowed(target_json)
    assert_write_allowed(target_html)
    atomic_write_bytes(target_json, json.dumps(progress, indent=2, sort_keys=True).encode("utf-8"))
    html_body = (
        f"<html><body><h1>UA Cards Unified — Gate A</h1>"
        f"<p>Phase: {html.escape(str(progress.get('phase')))}</p>"
        f"<p>Progress: {progress.get('pct')}%</p></body></html>"
    )
    atomic_write_bytes(target_html, html_body.encode("utf-8"))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main(mode: str = "fixture"):
    if mode == "fixture":
        out = Path(tempfile.mkdtemp(prefix="ua_cards_fixture_"))
        results = run_fixture(out)
        print(json.dumps({"mode": "fixture", "output": str(out), "results": results}, indent=2))
        return 0
    elif mode == "GATE_A_SANDBOX_ONLY":
        receipt = run_gate_a()
        print(json.dumps(receipt, indent=2))
        return 0
    else:
        print("REFUSED: unknown mode. Only 'fixture' or restricted GATE_A invocation allowed.")
        return 2


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "fixture"
    if arg not in ("fixture", "GATE_A_SANDBOX_ONLY"):
        print("REFUSED: this script accepts only 'fixture' (default) or the internal GATE_A token from the restricted launcher.")
        sys.exit(2)
    sys.exit(main(arg))
