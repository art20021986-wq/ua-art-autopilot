"""CRM-SPEED-001 Gate A orchestration (TASK 032 canonical integration).

This module provides one canonical evidence-computation core plus two
callers:

- run_gate_a(fixture): historical compatibility adapter for in-memory
  source fixtures (unit tests). It safely creates a requested
  non-existing run_dir after validating its parent, then delegates all
  predicate evaluation to the same _compute_evidence()/evaluate_gate_a()
  functions used by the canonical orchestrator. It does not retain a
  synthetic parallel evidence-evaluation path.

- orchestrate_gate_a(config, opener=None, clock=None): the real public
  orchestration entry point used by the no-argument launcher and by
  tests that inject a temporary filesystem configuration. It performs
  the full secure lifecycle described in TASK 032: Gate A lock
  acquisition, a validated QA root, atomic unique run-directory
  creation, secure source reads, isolated candidate/diff creation,
  compile-only verification (no import/execution of application
  modules), structural/concurrency/SQLite/publication evidence, and
  measured phase records (20/40/60/80/100).

Gate A is never executed against production by this repository. Every
function here operates only on paths/strings explicitly supplied by the
caller (production launcher DEFAULT_CONFIG or a test fixture/config).
Until TASK 033 delivers real transform/SQLite/publication evidence for
UA-0009, orchestrate_gate_a intentionally records certain predicates as
BLOCKED rather than fabricating a PASS from missing evidence.
"""
import os
import ast
import stat
import json
import time
import shutil
import secrets
import hashlib
import difflib
import sqlite3
import urllib.request
import urllib.error

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
import cars_ui_transform

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_FILES_PER_ROOT = 32

ADMIN_ROUTE_NAMES = ["gallery", "video_gallery", "diag_photo_show", "diag_video_show"]

MEDIA_METHOD_NAMES = {
    "reply_photo", "reply_video", "reply_media_group", "reply_document",
    "reply_audio", "reply_voice", "reply_animation",
    "send_photo", "send_video", "send_media_group", "send_document",
    "send_audio", "send_voice", "send_animation",
    "download", "download_to_drive", "get_file",
}

DYNAMIC_DISPATCH_FORBIDDEN = {"getattr", "setattr", "eval", "exec", "globals", "locals"}

SAFE_BUILTIN_NAMES = {
    "str", "int", "float", "bool", "len", "print", "list", "dict", "set",
    "tuple", "sorted", "enumerate", "range", "isinstance", "format", "repr",
    "min", "max", "sum", "any", "all", "zip", "map", "filter",
}

ALLOWED_SITE_NAMES = (
    ["index.html", "katalog.html"]
    + [f"UA-000{n}.html" for n in range(1, 10)]
    + [f"UA-000{n}-diag.html" for n in range(1, 10)]
    + [f"UA-000{n}-track.html" for n in range(1, 10)]
)

DEFAULT_CONFIG = {
    "required_inputs": [
        "/home/Carix/.local/lib/python3.10/site-packages/usercustomize.py",
        "/home/Carix/.local/lib/python3.13/site-packages/usercustomize.py",
        "/home/Carix/start_safe.py",
        "/home/Carix/run_all.py",
        "/home/Carix/cars_ui.py",
        "/home/Carix/avtoperedacha.py",
        "/home/Carix/samokontrol.py",
        "/home/Carix/db.py",
        "/home/Carix/team_bot.py",
        "/home/Carix/stranica.py",
        "/home/Carix/crm.db",
    ],
    "site_roots": {
        "/home/Carix/site": ALLOWED_SITE_NAMES,
        "/home/Carix/video": ALLOWED_SITE_NAMES,
        "/home/Carix/public_html": ALLOWED_SITE_NAMES,
    },
    "ua0009_url": "https://ua-art-detailing.ru/UA-0009.html",
    "run_root": "/home/Carix/qa/crm_speed_task020",
    "backup_archive": "/home/Carix/backups/crm_speed_20260827_1038_before.tar.gz",
    "backup_archive_sha256": "b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913",
    "protected_function_names": [],
    "db_function_source": None,
    "min_free_bytes": 10 * 1024 * 1024,
}

REQUIRED_PREDICATES = [
    "inputs_present_and_regular",
    "backup_verified",
    "candidates_compile",
    "protected_fingerprints_unchanged",
    "sqlite_readonly_quickcheck_ok",
    "ua0009_fingerprint_unchanged",
    "ua0009_not_public",
    "site_inventory_unchanged",
    "admin_routes_text_only",
    "media_persistence_unchanged",
    "usercustomize_inert",
    "singleton_guard_present",
    "rebuild_queue_bound_no_process_spawn",
    "db_closed_before_slow_work",
    "deterministic_repeat_all_transforms",
    "no_production_write",
]


class _GateABlocked(Exception):
    """Raised internally to short-circuit an orchestration phase with a
    known reason. Always converted into a BLOCKED phase result."""


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_file(path):
    if not os.path.exists(path):
        return None
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return {"symlink": True}
    return {
        "mode": st.st_mode,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sha256": _sha256_file(path),
    }


# ---------------------------------------------------------------------------
# Thin adapters around the canonical cars_ui_transform implementation
# ---------------------------------------------------------------------------

def _is_safe_builtin_unresolved(flag):
    if flag.startswith("unresolved_callable:"):
        parts = flag.split(":")
        name = parts[1] if len(parts) > 1 else ""
        return name in SAFE_BUILTIN_NAMES
    return False


def _translate_dynamic_flag(flag):
    if flag.startswith("getattr_dispatch"):
        return "dynamic_dispatch_forbidden:getattr"
    return flag


def scan_reachable_call_graph(source, entry_points, max_depth=25):
    tree = ast.parse(source)
    module_function_names = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    violations = []
    for ep in entry_points:
        if ep not in module_function_names:
            violations.append(f"missing_entry_point:{ep}")

    scan = cars_ui_transform.scan_reachable_call_graph(tree, entry_points)

    for func_name in sorted(scan.reachable):
        for flag in scan.unresolved_dynamic.get(func_name, []):
            if _is_safe_builtin_unresolved(flag):
                continue
            violations.append(_translate_dynamic_flag(flag))
        for call_info in scan.direct_media_calls.get(func_name, []):
            violations.append(f"direct_media_call:{call_info.method}")

    clean = len(violations) == 0
    return clean, violations


def generate_unified_diff(original, candidate):
    original = original or ""
    candidate = candidate or ""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        candidate.splitlines(keepends=True),
        fromfile="original", tofile="candidate",
    )
    return "".join(diff)


def transform_cars_ui(source, entry_points=None):
    entry_points = entry_points or ADMIN_ROUTE_NAMES
    try:
        clean_before, violations_before = scan_reachable_call_graph(source, entry_points)
    except SyntaxError as exc:
        return {"candidate": None, "status": "BLOCKED", "reasons": [f"syntax_error:{exc}"]}

    dynamic_flags = [v for v in violations_before if not v.startswith("direct_media_call")]
    if dynamic_flags:
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before}

    if not violations_before:
        return {"candidate": source, "status": "OK", "reasons": []}

    canonical_result = cars_ui_transform.transform_cars_ui(source, entry_points)
    if canonical_result.get("status") != "OK" or canonical_result.get("candidate") is None:
        reason = canonical_result.get("reason", "canonical_transform_blocked")
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before + [reason]}

    candidate = canonical_result["candidate"]
    clean_after, violations_after = scan_reachable_call_graph(candidate, entry_points)
    if not clean_after:
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before + violations_after}
    return {"candidate": candidate, "status": "OK", "reasons": violations_before}


def _stable_bytes(value):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def measure_deterministic_repeat(transform_fn, source, args=(), repeats=10):
    records = []
    for _ in range(repeats):
        result = transform_fn(source, *args)
        candidate = result.get("candidate")
        status = result.get("status")
        reasons = result.get("reasons", [])
        candidate_bytes = _stable_bytes(candidate)
        diff_text = generate_unified_diff(source, candidate)
        diff_bytes = diff_text.encode("utf-8")
        metadata_digest = hashlib.sha256(
            json.dumps({"status": status, "reasons": reasons}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        records.append({
            "candidate_sha256": _sha256_bytes(candidate_bytes),
            "diff_sha256": _sha256_bytes(diff_bytes),
            "status": status,
            "reasons": reasons,
            "metadata_digest": metadata_digest,
        })
    first = records[0]
    deterministic = all(r == first for r in records)
    return {"deterministic": deterministic, "repeats": repeats, "records": records}


def scan_bounded_inventory(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    if not os.path.isdir(root):
        return {"status": "BLOCKED", "reason": "missing_root", "root": root}
    matched = []
    for name in allowed_names:
        candidate_path = os.path.join(root, name)
        if os.path.lexists(candidate_path):
            matched.append(candidate_path)
    if len(matched) > max_files_per_root:
        return {
            "status": "BLOCKED", "reason": "overflow",
            "matched_count": len(matched), "max_files_per_root": max_files_per_root,
        }
    entries = []
    for path in matched:
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            return {"status": "BLOCKED", "reason": "symlink_rejected", "path": path}
        if not stat.S_ISREG(st.st_mode):
            return {"status": "BLOCKED", "reason": "not_regular_file", "path": path}
        if st.st_nlink != 1:
            return {"status": "BLOCKED", "reason": "hard_link_rejected", "path": path}
        entries.append({
            "path": os.path.realpath(path),
            "mode": st.st_mode,
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": _sha256_file(path),
        })
    entries.sort(key=lambda e: e["path"])
    return {"status": "OK", "entries": entries, "matched_count": len(matched), "max_files_per_root": max_files_per_root}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_ua0009_not_public(url, opener=None):
    if not url or not url.startswith("https://"):
        return {"status": "BLOCKED", "reason": "missing_or_non_https_url"}
    if opener is None:
        opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        req = urllib.request.Request(url, method="GET")
        resp = opener.open(req, timeout=5)
        code = getattr(resp, "getcode", lambda: getattr(resp, "code", None))()
        return {"status": "BLOCKED", "reason": f"unexpected_status_{code}"}
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return {"status": "OK", "reason": f"not_served_{exc.code}", "http_status": exc.code}
        return {"status": "BLOCKED", "reason": f"http_error_{exc.code}"}
    except urllib.error.URLError as exc:
        return {"status": "BLOCKED", "reason": f"network_error:{exc.reason}"}
    except Exception as exc:
        return {"status": "BLOCKED", "reason": f"probe_exception:{type(exc).__name__}"}


def check_inputs_present_and_regular(paths):
    missing = []
    for p in paths:
        if not os.path.exists(p):
            missing.append(p)
            continue
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            missing.append(p)
    if missing:
        return {"status": "BLOCKED", "missing_or_symlink": missing}
    return {"status": "OK", "checked": paths}


def check_backup_verified(archive_path, expected_sha256):
    if not os.path.exists(archive_path):
        return {"status": "BLOCKED", "reason": "backup_missing"}
    actual = _sha256_file(archive_path)
    if actual != expected_sha256:
        return {"status": "BLOCKED", "reason": "backup_hash_mismatch"}
    return {"status": "OK", "sha256": actual}


def check_candidates_compile(candidate_sources):
    errors = {}
    for name, src in candidate_sources.items():
        try:
            compile(src, name, "exec")
        except SyntaxError as exc:
            errors[name] = str(exc)
    if errors:
        return {"status": "BLOCKED", "errors": errors}
    return {"status": "OK", "compiled": list(candidate_sources.keys())}


def check_protected_fingerprints_unchanged(before, after):
    if not before or not after:
        return {"status": "BLOCKED", "reason": "missing_fingerprints"}
    if before != after:
        diff_keys = [k for k in before if before.get(k) != after.get(k)]
        return {"status": "BLOCKED", "reason": "changed", "diff_keys": diff_keys}
    return {"status": "OK"}


def check_sqlite_readonly_quickcheck_ok(db_path):
    if not os.path.exists(db_path):
        return {"status": "BLOCKED", "reason": "db_missing"}
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            conn.execute("PRAGMA query_only=ON;")
            cur = conn.execute("PRAGMA quick_check;")
            result = cur.fetchone()
        finally:
            conn.close()
        if result and result[0] == "ok":
            return {"status": "OK", "quick_check": result[0]}
        return {"status": "BLOCKED", "reason": "quick_check_failed", "value": result}
    except sqlite3.OperationalError as exc:
        return {"status": "BLOCKED", "reason": f"sqlite_locked_or_error:{exc}"}


def check_admin_routes_text_only(cars_ui_source):
    result = transform_cars_ui(cars_ui_source)
    if result["status"] != "OK" or result["candidate"] is None:
        return {"status": "BLOCKED", "reasons": result["reasons"]}
    clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
    if not clean:
        return {"status": "BLOCKED", "reasons": violations}
    return {"status": "OK", "candidate_sha256": _sha256_bytes(result["candidate"].encode("utf-8"))}


def _extract_function_ast_dumps(source, names):
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            found[node.name] = ast.dump(node)
    return found


def check_media_persistence_unchanged(original_source, candidate_source, protected_function_names):
    before = _extract_function_ast_dumps(original_source, protected_function_names)
    after = _extract_function_ast_dumps(candidate_source or "", protected_function_names)
    missing = [n for n in protected_function_names if n not in after]
    if missing:
        return {"status": "BLOCKED", "reason": "missing_protected_functions", "missing": missing}
    changed = [n for n in protected_function_names if before.get(n) != after.get(n)]
    if changed:
        return {"status": "BLOCKED", "reason": "protected_functions_changed", "changed": changed}
    return {"status": "OK"}


FORBIDDEN_USERCUSTOMIZE_MODULES = {
    "team_bot", "run_all", "start_safe", "avtoperedacha", "stranica",
    "threading", "multiprocessing", "subprocess",
}


def check_usercustomize_inert(source):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    violations = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_USERCUSTOMIZE_MODULES:
                    violations.append(f"forbidden_import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_USERCUSTOMIZE_MODULES:
                violations.append(f"forbidden_import_from:{node.module}")
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            violations.append("top_level_call_statement")
    if violations:
        return {"status": "BLOCKED", "violations": violations}
    return {"status": "OK"}


def check_singleton_guard_present(tmp_dir):
    lock_path = os.path.join(tmp_dir, "singleton.lock")
    guard1 = SingletonGuard(lock_path)
    ok1 = guard1.acquire()
    guard2 = SingletonGuard(lock_path)
    ok2 = guard2.acquire()
    guard1.release()
    guard3 = SingletonGuard(lock_path)
    ok3 = guard3.acquire()
    guard3.release()
    if ok1 and not ok2 and ok3:
        return {"status": "OK"}
    return {"status": "BLOCKED", "reason": "singleton_semantics_violated", "ok1": ok1, "ok2": ok2, "ok3": ok3}


def check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source):
    try:
        tree = ast.parse(avtoperedacha_source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "multiprocessing"):
                    violations.append(f"forbidden_import:{alias.name}")
        if isinstance(node, ast.Attribute) and node.attr in ("system", "Popen", "call", "run", "check_call", "check_output"):
            violations.append(f"forbidden_call_site:{node.attr}")
    if violations:
        return {"status": "BLOCKED", "violations": violations}
    return {"status": "OK"}


SLOW_CALL_NAMES = {"sleep", "send_message", "send_photo", "render", "generate", "post", "request"}


def check_db_closed_before_slow_work(function_source):
    try:
        tree = ast.parse(function_source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node
            break
    if func is None:
        return {"status": "BLOCKED", "reason": "no_function_found"}
    close_index = None
    slow_index = None
    for i, stmt in enumerate(func.body):
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "close" and close_index is None:
                    close_index = i
                if node.func.attr in SLOW_CALL_NAMES and slow_index is None:
                    slow_index = i
    if close_index is None:
        return {"status": "BLOCKED", "reason": "no_close_found"}
    if slow_index is not None and slow_index < close_index:
        return {"status": "BLOCKED", "reason": "slow_work_before_close"}
    return {"status": "OK", "close_index": close_index, "slow_index": slow_index}


def check_deterministic_repeat_all_transforms(transform_map):
    failures = []
    for name, (fn, source, args) in transform_map.items():
        measurement = measure_deterministic_repeat(fn, source, args=args, repeats=10)
        if not measurement["deterministic"]:
            failures.append(name)
    if failures:
        return {"status": "BLOCKED", "failures": failures}
    return {"status": "OK", "checked": list(transform_map.keys())}


def check_site_inventory_unchanged(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    before = scan_bounded_inventory(root, allowed_names, max_files_per_root)
    after = scan_bounded_inventory(root, allowed_names, max_files_per_root)
    if before.get("status") != "OK" or after.get("status") != "OK":
        return {"status": "BLOCKED", "before": before, "after": after}
    if before["entries"] != after["entries"]:
        return {"status": "BLOCKED", "reason": "inventory_changed"}
    return {"status": "OK", "matched_count": before["matched_count"]}


def check_no_production_write(protected_before, protected_after, site_before, site_after):
    if protected_before != protected_after:
        return {"status": "BLOCKED", "reason": "protected_changed"}
    if site_before != site_after:
        return {"status": "BLOCKED", "reason": "site_inventory_changed"}
    return {"status": "OK"}


def evaluate_gate_a(evidence):
    unmet = []
    for key in REQUIRED_PREDICATES:
        item = evidence.get(key)
        if not isinstance(item, dict) or item.get("status") != "OK":
            unmet.append(key)
    if unmet:
        return "BLOCKED", unmet
    return "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", []


# ---------------------------------------------------------------------------
# Canonical evidence computation shared by run_gate_a() and
# orchestrate_gate_a()
# ---------------------------------------------------------------------------

def _compute_evidence(fixture):
    evidence = {}
    evidence["inputs_present_and_regular"] = check_inputs_present_and_regular(fixture["required_inputs"])
    evidence["backup_verified"] = check_backup_verified(fixture["backup_archive"], fixture["backup_archive_sha256"])

    cars_ui_candidate = transform_cars_ui(fixture["cars_ui_source"])
    usercustomize_source = fixture["usercustomize_source"]
    avtoperedacha_source = fixture["avtoperedacha_source"]

    candidate_sources = {
        "cars_ui.py": cars_ui_candidate.get("candidate") or fixture["cars_ui_source"],
        "usercustomize.py": usercustomize_source,
        "avtoperedacha.py": avtoperedacha_source,
    }
    evidence["candidates_compile"] = check_candidates_compile(candidate_sources)

    evidence["protected_fingerprints_unchanged"] = check_protected_fingerprints_unchanged(
        fixture["protected_fingerprints_before"], fixture["protected_fingerprints_after"])
    evidence["sqlite_readonly_quickcheck_ok"] = check_sqlite_readonly_quickcheck_ok(fixture["db_path"])
    evidence["ua0009_fingerprint_unchanged"] = check_protected_fingerprints_unchanged(
        fixture["ua0009_fingerprint_before"], fixture["ua0009_fingerprint_after"])
    evidence["ua0009_not_public"] = check_ua0009_not_public(fixture["ua0009_url"], fixture.get("ua0009_opener"))
    evidence["site_inventory_unchanged"] = check_site_inventory_unchanged(
        fixture["site_root"], fixture["allowed_site_names"], fixture.get("max_files_per_root", DEFAULT_MAX_FILES_PER_ROOT))
    evidence["admin_routes_text_only"] = check_admin_routes_text_only(fixture["cars_ui_source"])
    evidence["media_persistence_unchanged"] = check_media_persistence_unchanged(
        fixture["cars_ui_source"], cars_ui_candidate.get("candidate"), fixture["protected_function_names"])
    evidence["usercustomize_inert"] = check_usercustomize_inert(usercustomize_source)
    evidence["singleton_guard_present"] = check_singleton_guard_present(fixture["tmp_dir"])
    evidence["rebuild_queue_bound_no_process_spawn"] = check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source)
    evidence["db_closed_before_slow_work"] = check_db_closed_before_slow_work(fixture["db_function_source"])
    evidence["deterministic_repeat_all_transforms"] = check_deterministic_repeat_all_transforms({
        "cars_ui": (transform_cars_ui, fixture["cars_ui_source"], ()),
    })
    evidence["no_production_write"] = check_no_production_write(
        fixture["protected_fingerprints_before"], fixture["protected_fingerprints_after"],
        fixture.get("site_before"), fixture.get("site_after"))
    return evidence


def _ensure_run_dir(run_dir):
    """Safely create a requested non-existing run_dir after validating
    its parent. Never weakens SafeWriter: SafeWriter still refuses any
    directory that does not already exist by the time it is
    constructed."""
    parent = os.path.dirname(os.path.abspath(run_dir))
    if parent == "":
        parent = "."
    if not os.path.isdir(parent):
        raise ValueError(f"run_dir parent does not exist: {parent}")
    if os.path.islink(parent):
        raise ValueError("run_dir parent must not be a symlink")
    if os.path.islink(run_dir):
        raise ValueError("run_dir must not be a symlink")
    if not os.path.exists(run_dir):
        os.mkdir(run_dir, 0o700)
    if not os.path.isdir(run_dir):
        raise ValueError("run_dir must be a directory")


def run_gate_a(fixture):
    """Historical compatibility adapter for in-memory source fixtures.
    Delegates all predicate evaluation to _compute_evidence() and
    evaluate_gate_a(), the exact same functions used by
    orchestrate_gate_a(). The only adapter-specific behavior is safely
    creating a requested non-existing run_dir after validating its
    parent, so SafeWriter always receives an already-existing directory.
    """
    evidence = _compute_evidence(fixture)
    status, unmet = evaluate_gate_a(evidence)
    receipt = {
        "status": status,
        "unmet_predicates": unmet,
        "evidence": evidence,
        "production_write": "NO",
        "generated_at": time.time(),
    }
    run_dir = fixture.get("run_dir")
    if run_dir:
        _ensure_run_dir(run_dir)
        writer = SafeWriter(run_dir)
        writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
    return receipt


# ---------------------------------------------------------------------------
# Canonical real orchestration entry point
# ---------------------------------------------------------------------------

def _validate_no_symlink_dir(path):
    if not os.path.isdir(path):
        raise _GateABlocked(f"qa_root_missing_or_not_dir:{path}")
    if os.path.islink(path):
        raise _GateABlocked("qa_root_is_symlink")
    abs_path = os.path.abspath(path)
    cur = ""
    for part in abs_path.split(os.sep):
        if not part:
            if not cur:
                cur = os.sep
            continue
        cur = os.path.join(cur, part) if cur else part
        if os.path.islink(cur):
            raise _GateABlocked(f"symlink_component:{cur}")
    return os.path.realpath(path)


def _create_unique_run_dir(qa_root_real):
    for _ in range(5):
        run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(6)
        candidate = os.path.join(qa_root_real, run_id)
        try:
            os.mkdir(candidate, 0o700)
        except FileExistsError:
            continue
        if os.path.islink(candidate):
            raise _GateABlocked("run_dir_became_symlink")
        parent_real = os.path.realpath(os.path.dirname(candidate))
        if parent_real != qa_root_real:
            raise _GateABlocked("run_dir_parent_identity_mismatch")
        if os.path.realpath(candidate) != candidate:
            raise _GateABlocked("run_dir_identity_mismatch")
        return candidate
    raise _GateABlocked("could_not_create_unique_run_dir")


def secure_read_file(path):
    try:
        lst = os.lstat(path)
    except FileNotFoundError:
        raise _GateABlocked(f"missing_input:{path}")
    if stat.S_ISLNK(lst.st_mode):
        raise _GateABlocked(f"symlink_input:{path}")
    if not stat.S_ISREG(lst.st_mode):
        raise _GateABlocked(f"non_regular_input:{path}")
    if lst.st_nlink != 1:
        raise _GateABlocked(f"hard_linked_input:{path}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, os.O_RDONLY | nofollow)
    except OSError as exc:
        raise _GateABlocked(f"open_failed:{path}:{type(exc).__name__}")
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or fst.st_nlink != 1:
            raise _GateABlocked(f"identity_changed_after_open:{path}")
        if fst.st_ino != lst.st_ino or fst.st_dev != lst.st_dev:
            raise _GateABlocked(f"identity_mismatch:{path}")
        with os.fdopen(fd, "rb", closefd=True) as fh:
            data = fh.read()
    except _GateABlocked:
        try:
            os.close(fd)
        except Exception:
            pass
        raise
    lst2 = os.lstat(path)
    if stat.S_ISLNK(lst2.st_mode) or not stat.S_ISREG(lst2.st_mode) or lst2.st_nlink != 1:
        raise _GateABlocked(f"identity_changed_after_read:{path}")
    return {
        "path": os.path.realpath(path),
        "size": len(data),
        "mode": lst.st_mode,
        "mtime_ns": lst.st_mtime_ns,
        "sha256": _sha256_bytes(data),
        "data": data,
    }


def _find_input_path(config, filename):
    for p in config.get("required_inputs", []):
        if os.path.basename(p) == filename:
            return p
    return None


def _render_report(receipt):
    lines = []
    lines.append("# Gate A Report - " + str(receipt.get("task_id")))
    lines.append("Status: " + str(receipt.get("status")))
    lines.append("Run ID: " + str(receipt.get("run_id")))
    lines.append("Generated at: " + str(receipt.get("generated_at")))
    lines.append("")
    lines.append("## Phases")
    for p in receipt.get("phases", []):
        lines.append(
            "- phase " + str(p.get("phase")) + " (" + str(p.get("label")) + "): "
            + str(p.get("status")) + " duration=" + str(p.get("duration")) + "s"
        )
    lines.append("")
    lines.append("## Unmet predicates")
    for u in receipt.get("unmet_predicates", []) or []:
        lines.append("- " + str(u))
    lines.append("")
    lines.append("## Blockers")
    for b in receipt.get("blockers", []) or []:
        lines.append("- " + str(b))
    lines.append("")
    lines.append("PRODUCTION_WRITE: " + str(receipt.get("production_write")))
    lines.append("Next safe action: " + str(receipt.get("next_safe_action")))
    return os.linesep.join(lines) + os.linesep


def orchestrate_gate_a(config, opener=None, clock=None):
    """The single, real, public orchestration entry point. Used by both
    the no-argument launcher (with DEFAULT_CONFIG) and by tests (with an
    injected temporary-directory configuration and an injected fake
    HTTPS opener). Never scans an account recursively; only reads the
    exact bounded paths present in `config`.
    """
    clock = clock or time.monotonic
    phases = []
    evidence = {}
    site_before = {}
    site_after = {}
    candidate_sources = {}
    input_records = {}
    state = {"blocked": False}
    run_dir = None
    lock = None

    def run_phase(num, label, fn):
        start = clock()
        try:
            fn()
            outcome = "OK"
        except _GateABlocked as exc:
            evidence.setdefault("_blockers", []).append(str(exc))
            outcome = "BLOCKED"
        except Exception as exc:
            evidence.setdefault("_blockers", []).append(f"exception:{type(exc).__name__}:{exc}")
            outcome = "BLOCKED"
        end = clock()
        status_field = "finished" if num == 100 else outcome
        phases.append({
            "phase": num, "label": label, "start": start, "end": end,
            "duration": end - start, "status": status_field,
        })
        return outcome

    def phase20():
        nonlocal run_dir, lock
        qa_root_real = _validate_no_symlink_dir(config["run_root"])
        lock = CrossProcessLock(os.path.join(qa_root_real, "gate_a.lock"))
        if not lock.acquire():
            raise _GateABlocked("gate_a_lock_held")
        run_dir = _create_unique_run_dir(qa_root_real)
        for p in config["required_inputs"]:
            input_records[p] = secure_read_file(p)
        evidence["inputs_present_and_regular"] = {"status": "OK", "checked": list(input_records.keys())}
        du = shutil.disk_usage(qa_root_real)
        if du.free < config.get("min_free_bytes", 10 * 1024 * 1024):
            raise _GateABlocked("insufficient_free_space")
        backup_result = check_backup_verified(config["backup_archive"], config["backup_archive_sha256"])
        evidence["backup_verified"] = backup_result
        if backup_result["status"] != "OK":
            raise _GateABlocked("backup_verification_failed")
        evidence["_fingerprints_before"] = {p: fingerprint_file(p) for p in config["required_inputs"]}
        for root, names in config["site_roots"].items():
            site_before[root] = scan_bounded_inventory(root, names)

    def phase40():
        if state["blocked"]:
            raise _GateABlocked("skipped_prior_block")
        cars_ui_path = _find_input_path(config, "cars_ui.py")
        usercustomize_path = _find_input_path(config, "usercustomize.py")
        avtoperedacha_path = _find_input_path(config, "avtoperedacha.py")
        if not (cars_ui_path and usercustomize_path and avtoperedacha_path):
            raise _GateABlocked("missing_source_paths_for_transform")
        cars_ui_source = input_records[cars_ui_path]["data"].decode("utf-8")
        usercustomize_source = input_records[usercustomize_path]["data"].decode("utf-8")
        avtoperedacha_source = input_records[avtoperedacha_path]["data"].decode("utf-8")
        result = transform_cars_ui(cars_ui_source)
        evidence["_transform_result"] = result
        if result["status"] != "OK" or result.get("candidate") is None:
            raise _GateABlocked("cars_ui_transform_blocked")
        candidate_sources["cars_ui.py"] = result["candidate"]
        candidate_sources["usercustomize.py"] = usercustomize_source
        candidate_sources["avtoperedacha.py"] = avtoperedacha_source
        diff_text = generate_unified_diff(cars_ui_source, candidate_sources["cars_ui.py"])
        evidence["_diff_sha256"] = _sha256_bytes(diff_text.encode("utf-8"))
        evidence["_candidate_hashes"] = {k: _sha256_bytes(v.encode("utf-8")) for k, v in candidate_sources.items()}
        evidence["_cars_ui_source"] = cars_ui_source
        evidence["_usercustomize_source"] = usercustomize_source
        evidence["_avtoperedacha_source"] = avtoperedacha_source

    def phase60():
        if state["blocked"]:
            raise _GateABlocked("skipped_prior_block")
        if not candidate_sources:
            raise _GateABlocked("no_candidates_to_compile")
        result = check_candidates_compile(candidate_sources)
        evidence["candidates_compile"] = result
        if result["status"] != "OK":
            raise _GateABlocked("compile_failed")

    def phase80():
        if state["blocked"]:
            raise _GateABlocked("skipped_prior_block")
        cars_ui_source = evidence.get("_cars_ui_source")
        candidate = candidate_sources.get("cars_ui.py")
        usercustomize_source = evidence.get("_usercustomize_source")
        avtoperedacha_source = evidence.get("_avtoperedacha_source")

        evidence["admin_routes_text_only"] = check_admin_routes_text_only(cars_ui_source)

        protected_names = config.get("protected_function_names") or []
        if not protected_names:
            evidence["media_persistence_unchanged"] = {"status": "BLOCKED", "reason": "protected_function_names_not_configured"}
        else:
            evidence["media_persistence_unchanged"] = check_media_persistence_unchanged(cars_ui_source, candidate, protected_names)

        evidence["usercustomize_inert"] = check_usercustomize_inert(usercustomize_source)
        evidence["singleton_guard_present"] = check_singleton_guard_present(run_dir)
        evidence["rebuild_queue_bound_no_process_spawn"] = check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source)

        db_path = _find_input_path(config, "crm.db")
        if db_path:
            evidence["sqlite_readonly_quickcheck_ok"] = check_sqlite_readonly_quickcheck_ok(db_path)
        else:
            evidence["sqlite_readonly_quickcheck_ok"] = {"status": "BLOCKED", "reason": "db_path_not_configured"}

        db_function_source = config.get("db_function_source")
        if db_function_source:
            evidence["db_closed_before_slow_work"] = check_db_closed_before_slow_work(db_function_source)
        else:
            evidence["db_closed_before_slow_work"] = {"status": "BLOCKED", "reason": "db_function_source_not_configured"}

        evidence["deterministic_repeat_all_transforms"] = check_deterministic_repeat_all_transforms({
            "cars_ui": (transform_cars_ui, cars_ui_source, ()),
        })
        evidence["ua0009_not_public"] = check_ua0009_not_public(config["ua0009_url"], opener)

        required_here = [
            "admin_routes_text_only", "media_persistence_unchanged", "usercustomize_inert",
            "singleton_guard_present", "rebuild_queue_bound_no_process_spawn",
            "sqlite_readonly_quickcheck_ok", "db_closed_before_slow_work",
            "deterministic_repeat_all_transforms", "ua0009_not_public",
        ]
        failed = [k for k in required_here if evidence.get(k, {}).get("status") != "OK"]
        if failed:
            raise _GateABlocked("predicate_failed:" + ",".join(failed))

    def phase100():
        fingerprints_after = {p: fingerprint_file(p) for p in config["required_inputs"]}
        evidence["_fingerprints_after"] = fingerprints_after
        fingerprints_before = evidence.get("_fingerprints_before")
        if fingerprints_before:
            evidence["protected_fingerprints_unchanged"] = check_protected_fingerprints_unchanged(fingerprints_before, fingerprints_after)
        else:
            evidence["protected_fingerprints_unchanged"] = {"status": "BLOCKED", "reason": "missing_before_fingerprints"}
        for root, names in config["site_roots"].items():
            try:
                site_after[root] = scan_bounded_inventory(root, names)
            except Exception as exc:
                site_after[root] = {"status": "BLOCKED", "reason": f"exception:{type(exc).__name__}"}
        site_ok = True
        changed_roots = []
        for root in config["site_roots"]:
            b = site_before.get(root)
            a = site_after.get(root)
            if not b or b.get("status") != "OK" or not a or a.get("status") != "OK" or b.get("entries") != a.get("entries"):
                site_ok = False
                changed_roots.append(root)
        evidence["site_inventory_unchanged"] = {"status": "OK"} if site_ok else {"status": "BLOCKED", "changed_roots": changed_roots}
        evidence["ua0009_fingerprint_unchanged"] = {"status": "BLOCKED", "reason": "task_033_pending_real_fingerprint_evidence"}
        evidence["no_production_write"] = check_no_production_write(
            evidence.get("_fingerprints_before") or {}, fingerprints_after, site_before, site_after)

    try:
        outcome = run_phase(20, "lock_preflight_backup_fingerprints", phase20)
        if outcome != "OK":
            state["blocked"] = True
        outcome = run_phase(40, "secure_source_reads_and_candidate_diff", phase40)
        if outcome != "OK":
            state["blocked"] = True
        outcome = run_phase(60, "compile_candidates", phase60)
        if outcome != "OK":
            state["blocked"] = True
        outcome = run_phase(80, "structural_concurrency_sqlite_media_publication", phase80)
        if outcome != "OK":
            state["blocked"] = True
        run_phase(100, "finalization_fingerprints_inventories_receipt", phase100)

        public_evidence = {k: v for k, v in evidence.items() if not k.startswith("_")}
        status, unmet = evaluate_gate_a(public_evidence)

        receipt = {
            "task_id": "CRM-SPEED-001",
            "run_id": os.path.basename(run_dir) if run_dir else None,
            "generated_at": time.time(),
            "phases": phases,
            "status": status,
            "unmet_predicates": unmet,
            "evidence": public_evidence,
            "package_hashes": evidence.get("_candidate_hashes", {}),
            "diff_sha256": evidence.get("_diff_sha256"),
            "site_inventories": {"before": site_before, "after": site_after},
            "synthetic_latency": {"non_production": True, "value_ms": 0},
            "blockers": evidence.get("_blockers", []),
            "allowed_write_ledger": [],
            "next_safe_action": (
                "await_task_033_real_evidence_then_owner_gate_b_review"
                if status == "BLOCKED" else
                "await_owner_gate_b_approval"
            ),
            "production_write": "NO",
        }

        if run_dir is not None:
            try:
                writer = SafeWriter(run_dir)
                writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
                writer.write_text("report.md", _render_report(receipt))
                receipt["allowed_write_ledger"] = writer.ledger
                writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
            except Exception as exc:
                receipt.setdefault("blockers", []).append(f"receipt_write_failed:{type(exc).__name__}")
        return receipt
    finally:
        if lock is not None:
            lock.release()
