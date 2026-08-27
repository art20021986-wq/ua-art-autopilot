# TASK 035 — CRM-SPEED-001 phase E: evidence integration and complete compatibility

## Authority and immutable safety boundary

Integrate the compile-clean TASK 034 evidence modules into the real TASK 032 orchestration. Work only under `cloud/`. Do not execute Gate A. Do not access PythonAnywhere, /home/Carix, real production URLs or network in tests. Do not modify Production, CRM, crm.db, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. Never publish UA-0009. Do not modify `tasks/`.

Required markers:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

Successful phase status is READY_FOR_CONTROLLER_REVIEW_PHASE_E, never READY_FOR_GATE_A.

## Independent controller result on commit b45ca4a288a671a945eff64e3b54334d0cd0ce4c

Compilation passed. All 60 focused TASK 034 tests passed. Full discovery ran 172 tests: 168 PASS, 2 FAIL, 2 ERROR.

Exact remaining regressions:

1. `candidates_compile` is absent when cars_ui semantic analysis blocks before phase 60. Record safe compile evidence from secure original bytes while retaining the transform predicate as BLOCKED.
2. Historical `build_manifest(package_dir, run_dir, receipt)` passes a receipt dict as the third positional argument. The new implementation incorrectly interprets it as a logical-path mapping and calls lstat on a list/dict value.
3. Historical verifier receipts use `status=GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL|BLOCKED` and `evidence`; focused TASK 034 receipts use `status=PASS|BLOCKED` and `predicates`. Support both explicitly and fail closed for ambiguity.
4. Historical two-argument `verify_receipt(receipt_path, manifest_path)` must automatically bind `run_dir/report.md` and return exactly `report_hash_mismatch` after report tampering.
5. For a historical receipt missing one required evidence predicate, the first reason must remain `missing_or_malformed_predicate:<key>`, not an unrelated schema error.

Do not modify or weaken existing tests. Fix the compatibility architecture.

## 1. Orchestration integration

Use `sqlite_ownership.py` and `ua0009_publication_check.py` as the exact canonical implementations. Do not duplicate their logic in crm_speed_gate_a.py.

- Read-only UA-0009 evidence before the candidate workload after secure input preflight.
- Read-only UA-0009 evidence again only after the entire workload.
- Compare through the canonical helper; missing/non-OK/changed evidence BLOCKS.
- Delegate publication probe to the exact canonical function with injected opener.
- Propagate query_only, quick_check, PII_EMITTED:NO, before/after hashes and publication result into receipt.
- Close database resources before transforms, hashing, HTTP probe or filesystem work.
- Tests use temporary SQLite only and fake opener.

## 2. Continue safe evidence after semantic block

Every fixed required predicate key must exist in the final receipt.

When transform_cars_ui blocks but secure bytes exist:

- keep admin/transform evidence BLOCKED;
- create a compile-only source map from exact secure original bytes;
- run check_candidates_compile without importing/executing;
- store `candidates_compile={status: OK, candidate_origin: original_due_to_transform_block, ...}` when syntax is valid;
- do not call this an accepted candidate and do not permit final PASS;
- safely collect all other independent evidence whose prerequisites exist.

Phase state must not erase later safe evidence. Unsafe/missing prerequisites produce explicit BLOCKED records.

## 3. Dual-schema fail-closed verifier

Explicitly recognize exactly two schemas:

A. Historical orchestration:
- status `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` or `BLOCKED`;
- fixed predicates in `evidence`;
- `production_write=NO`;
- optional legacy fields normalized without inventing evidence.

B. Standalone focused:
- status `PASS` or `BLOCKED`;
- fixed predicates in `predicates`;
- `production_write=NO`;
- `pii_emitted=NO`.

Reject a receipt that mixes conflicting forms. For historical form, check required predicates before unrelated optional-schema fields so a missing predicate returns `missing_or_malformed_predicate:<key>`.

Preserve all TASK 034 hardening: no-follow, regular/single-link, bounded size, stable identity, duplicate-key rejection, expected failures return false and never raise.

If manifest_path is passed and report_path omitted, automatically use `<run_dir>/report.md` when the manifest binds a report hash. Verify receipt and report hash. Tampered report must return exactly `report_hash_mismatch`.

## 4. Backward-compatible and canonical manifest

Preserve both call forms:

1. Historical: `build_manifest(package_dir, run_dir, receipt_dict)`.
2. Canonical: keyword logical artifact paths/evidence arguments from TASK 034.

Detect by structure, never by permissive exception fallback.

Historical result must provide all prior top-level fields including `receipt_sha256` and `report_sha256`, plus the new deterministic canonical binding fields. Securely hash existing receipt.json/report.md and bind package/input/candidate/diff/compilation/deterministic/SQLite/UA/publication/site/ledger evidence from the receipt.

Canonical logical-path mapping may contain a single path or an explicitly documented bounded list of paths. Normalize safely; never pass list/dict directly to lstat. Reject duplicates, escape, symlink, hard-link and non-regular entries.

Manifest must be deterministic, JSON-serializable and have no self-reference cycle.

## 5. Receipt consistency

The orchestration receipt must contain:

- all fixed required evidence keys;
- sqlite read-only/query_only/quick_check evidence;
- ua0009 before/after non-PII hashes and equality result;
- canonical publication result;
- candidates_compile even after safe semantic transform block;
- phases 20/40/60/80/100;
- site before/after;
- allowed-write ledger;
- production_write NO;
- pii_emitted NO;
- final unmet predicates and BLOCKED/PASS consistency.

No hard-coded OK.

## Mandatory tests

Create `cloud/crm_speed_optimization/test_task_035_integration.py` proving:

1. The exact four independent controller regressions now pass.
2. Historical manifest call and canonical manifest call both work and are deterministic.
3. Lists of bounded artifact paths are normalized and hashed; dict/non-path surprise blocks cleanly.
4. Historical and focused verifier schemas pass valid fixtures and block malformed/mixed fixtures.
5. Missing historical predicate returns exact prefix `missing_or_malformed_predicate`.
6. Receipt tamper returns receipt_hash_mismatch; report tamper returns report_hash_mismatch.
7. Orchestration uses canonical sqlite_ownership and publication functions by identity/monkeypatch delegation.
8. SQLite evidence occurs before and after the full workload, not adjacent.
9. PII seed strings never appear in receipt/report/manifest.
10. Safe compile evidence remains present after a semantic transform block while final status stays BLOCKED.
11. All previous 172 tests remain intact and pass.

Controller target:

`python3 -m py_compile cloud/crm_speed_optimization/*.py && python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'`

## Deliverables

Return complete contents for exactly:

- `cloud/crm_speed_optimization/crm_speed_gate_a.py`
- `cloud/crm_speed_optimization/build_manifest.py`
- `cloud/crm_speed_optimization/verify_gate_a.py`
- `cloud/crm_speed_optimization/test_task_035_integration.py`
- `cloud/crm_speed_optimization/TASK_035_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Do not rewrite sqlite_ownership.py or ua0009_publication_check.py; import/delegate to their current canonical implementations. Do not return unrelated files. No placeholders, credentials, PII, production imports or production-write capability.

## Exact current source snapshots


## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

```python
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

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/build_manifest.py

```python
"""
build_manifest.py (TASK 034)

Standalone, syntactically simple, deterministic manifest builder. No
production access -- only explicit data arguments and a caller-supplied
run directory. Unsafe paths, symlinks, non-regular/hard-linked files,
duplicate logical paths, and files outside the resolved run directory
are all rejected with a plain ValueError (never a raised OSError from
half-open files, never a crash on unexpected input).

The manifest binds: package code hashes, run-directory artifact hashes
(candidates/diffs/reports/receipts, keyed by logical name), the
allowed-write ledger, SQLite ownership evidence, UA-0009 before/after
evidence, the canonical publication result, and a fixed PII_EMITTED:NO
flag. Output is deterministic and JSON-serializable via canonical_json.
The manifest never contains a hash of itself (no self-referential
cycle). Integration with a central orchestrator is deferred to a later
task; this module is used standalone with explicitly passed evidence.
"""
import hashlib
import json
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQUIRED_MANIFEST_FIELDS = [
    "package_code_hashes",
    "run_artifact_hashes",
    "allowed_write_ledger",
    "sqlite_evidence",
    "ua0009_evidence_before",
    "ua0009_evidence_after",
    "publication_evidence",
    "pii_emitted",
]


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _secure_hash_file(path, must_be_within=None):
    """Hash a single file after rejecting symlinks, non-regular files,
    hard-linked files (nlink != 1), and (when must_be_within is given)
    files whose real path resolves outside that directory."""
    if os.path.islink(path):
        raise ValueError(f"symlink_rejected:{os.path.basename(path)}")
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise ValueError(f"stat_failed:{type(exc).__name__}")
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("not_regular_file")
    if st.st_nlink != 1:
        raise ValueError("hard_linked_file_rejected")
    if must_be_within is not None:
        real = os.path.realpath(path)
        base = os.path.realpath(must_be_within)
        try:
            common = os.path.commonpath([real, base])
        except ValueError:
            raise ValueError("path_outside_run_dir")
        if common != base:
            raise ValueError("path_outside_run_dir")
    return _sha256_file(path)


def _package_code_hashes(package_dir):
    hashes = {}
    seen = set()
    for name in sorted(os.listdir(package_dir)):
        if not name.endswith(".py"):
            continue
        full = os.path.join(package_dir, name)
        if os.path.islink(full):
            raise ValueError(f"symlink_package_file_rejected:{name}")
        if not os.path.isfile(full):
            continue
        if name in seen:
            raise ValueError(f"duplicate_package_file:{name}")
        seen.add(name)
        hashes[name] = _secure_hash_file(full)
    return hashes


def build_manifest(
    package_dir,
    run_dir,
    run_artifact_paths=None,
    allowed_write_ledger=None,
    sqlite_evidence=None,
    ua0009_evidence_before=None,
    ua0009_evidence_after=None,
    publication_evidence=None,
):
    """Build a deterministic manifest dict. run_artifact_paths maps a
    logical name (e.g. 'receipt', 'report', 'candidate_cars_ui',
    'diff_cars_ui') to an on-disk path that must resolve inside
    run_dir. Evidence arguments are bound as-is (already-computed
    dict/dataclass-derived structures) -- this function does not
    compute evidence itself."""
    if not os.path.isdir(run_dir):
        raise ValueError("run_dir_missing")
    if os.path.islink(run_dir):
        raise ValueError("run_dir_is_symlink")
    run_dir_real = os.path.realpath(run_dir)

    run_artifact_paths = run_artifact_paths or {}
    artifact_hashes = {}
    seen_logical = set()
    for logical_name in sorted(run_artifact_paths):
        if logical_name in seen_logical:
            raise ValueError(f"duplicate_logical_path:{logical_name}")
        seen_logical.add(logical_name)
        path = run_artifact_paths[logical_name]
        artifact_hashes[logical_name] = _secure_hash_file(path, must_be_within=run_dir_real)

    ledger_items = allowed_write_ledger or []
    sorted_ledger = sorted(ledger_items, key=lambda item: json.dumps(item, sort_keys=True, default=str))

    manifest = {
        "package_code_hashes": _package_code_hashes(package_dir),
        "run_artifact_hashes": artifact_hashes,
        "allowed_write_ledger": sorted_ledger,
        "sqlite_evidence": sqlite_evidence if sqlite_evidence is not None else {},
        "ua0009_evidence_before": ua0009_evidence_before if ua0009_evidence_before is not None else {},
        "ua0009_evidence_after": ua0009_evidence_after if ua0009_evidence_after is not None else {},
        "publication_evidence": publication_evidence if publication_evidence is not None else {},
        "pii_emitted": "NO",
    }

    for field_name in REQUIRED_MANIFEST_FIELDS:
        if field_name not in manifest:
            raise ValueError(f"manifest_missing_field:{field_name}")
    return manifest


def canonical_json(manifest):
    """Deterministic, sorted, JSON-serializable rendering of a
    manifest."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: build_manifest.py <package_dir> <run_dir>")
        sys.exit(2)
    manifest = build_manifest(sys.argv[1], sys.argv[2])
    print(canonical_json(manifest))

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/build_manifest.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/verify_gate_a.py

```python
"""
verify_gate_a.py (TASK 034)

Standalone, bounded, fail-closed verification of a Gate A receipt (and
optionally a bound manifest). This module never imports or executes
any candidate code and never touches production. All expected failure
conditions (OSError, UnicodeError, JSONDecodeError, ValueError,
TypeError, duplicate JSON keys, symlinks, hard links, oversized files,
files outside the run directory) are caught and returned as
(False, sanitized_reason) -- this module never raises for them.

Integration with a central orchestrator's exact receipt schema is
deferred to a later task; REQUIRED_PREDICATES below defines the fixed
set of predicate keys this standalone verifier enforces.
"""
import json
import os
import stat
import sys
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQUIRED_PREDICATES = [
    "sqlite_quick_check_ok",
    "ua0009_fingerprint_unchanged",
    "ua0009_not_public",
    "pii_not_emitted",
    "production_write_no",
]

VALID_STATUSES = ("PASS", "BLOCKED")
MAX_JSON_BYTES = 2_000_000


def _sanitize(exc):
    return type(exc).__name__


def _secure_stat_check(path, run_dir_real):
    if os.path.islink(path):
        return False, "symlink_rejected"
    try:
        st = os.lstat(path)
    except OSError as exc:
        return False, f"stat_failed:{_sanitize(exc)}"
    if not stat.S_ISREG(st.st_mode):
        return False, "not_regular_file"
    if st.st_nlink != 1:
        return False, "hard_linked_rejected"
    real = os.path.realpath(path)
    try:
        common = os.path.commonpath([real, run_dir_real])
    except ValueError:
        return False, "path_outside_run_dir"
    if common != run_dir_real:
        return False, "path_outside_run_dir"
    if st.st_size > MAX_JSON_BYTES:
        return False, "file_too_large"
    return True, "ok"


def _no_dup_keys(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate_key:{k}")
        d[k] = v
    return d


def _secure_read_json(path, run_dir_real):
    ok, reason = _secure_stat_check(path, run_dir_real)
    if not ok:
        return None, reason
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        text = raw.decode("utf-8")
        data = json.loads(text, object_pairs_hook=_no_dup_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return None, f"read_failed:{_sanitize(exc)}"
    return data, "ok"


def _secure_hash_file(path, run_dir_real):
    ok, reason = _secure_stat_check(path, run_dir_real)
    if not ok:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_receipt(receipt_path, manifest_path=None, run_dir=None, report_path=None):
    """Verify a Gate A receipt. `run_dir` defaults to the receipt's own
    directory, preserving the historical two-positional-argument call
    pattern verify_receipt(receipt_path, manifest_path). Never raises
    for expected malformed/tampered/oversized/symlink/hard-link/
    missing-evidence conditions -- always returns (bool, reason)."""
    try:
        effective_run_dir = run_dir if run_dir is not None else os.path.dirname(os.path.abspath(receipt_path))
        if os.path.islink(effective_run_dir) or not os.path.isdir(effective_run_dir):
            return False, "invalid_run_dir"
        run_dir_real = os.path.realpath(effective_run_dir)

        data, reason = _secure_read_json(receipt_path, run_dir_real)
        if data is None:
            return False, reason
        if not isinstance(data, dict):
            return False, "receipt_not_object"

        if data.get("production_write") != "NO":
            return False, "production_write_not_no"
        if data.get("pii_emitted") != "NO":
            return False, "pii_emitted_not_no"
        status = data.get("status")
        if status not in VALID_STATUSES:
            return False, f"unexpected_status:{status}"

        predicates = data.get("predicates")
        if not isinstance(predicates, dict):
            return False, "missing_predicates_block"
        for key in REQUIRED_PREDICATES:
            item = predicates.get(key)
            if not isinstance(item, dict) or "status" not in item:
                return False, f"missing_or_malformed_predicate:{key}"
            if item["status"] not in ("OK", "BLOCKED"):
                return False, f"unknown_predicate_status:{key}"

        if status == "PASS":
            if data.get("unmet_predicates"):
                return False, "pass_status_with_unmet_predicates"
            for key in REQUIRED_PREDICATES:
                if predicates.get(key, {}).get("status") != "OK":
                    return False, f"pass_status_but_predicate_not_ok:{key}"

        if manifest_path is not None:
            manifest, mreason = _secure_read_json(manifest_path, run_dir_real)
            if manifest is None:
                return False, mreason
            if not isinstance(manifest, dict):
                return False, "manifest_not_object"
            actual_receipt_hash = _secure_hash_file(receipt_path, run_dir_real)
            if actual_receipt_hash is None:
                return False, "receipt_rehash_failed"
            if manifest.get("receipt_sha256") != actual_receipt_hash:
                return False, "receipt_hash_mismatch"
            if report_path is not None:
                actual_report_hash = _secure_hash_file(report_path, run_dir_real)
                if actual_report_hash is None:
                    return False, "report_rehash_failed"
                if manifest.get("report_sha256") != actual_report_hash:
                    return False, "report_hash_mismatch"

        return True, "ok"
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return False, f"unexpected_error:{_sanitize(exc)}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: verify_gate_a.py <receipt.json> [manifest.json]")
        sys.exit(2)
    manifest_arg = sys.argv[2] if len(sys.argv) > 2 else None
    ok, reason = verify_receipt(sys.argv[1], manifest_path=manifest_arg)
    print(json.dumps({"ok": ok, "reason": reason}))
    sys.exit(0 if ok else 1)

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/verify_gate_a.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py

```python
"""
sqlite_ownership.py (TASK 034)

Two independent capabilities live in this module:

1. The original structural (AST-based) transformation and verifier
   enforcing short SQLite ownership: SELECT rows are materialized into
   ordinary immutable values and the cursor/connection are closed
   BEFORE any slow-call category (formatting/hash/sleep/network/
   filesystem/Telegram I/O). Preserved unchanged for compatibility.

2. A new canonical, read-only, fail-closed SQLite evidence API used to
   prove UA-0009 row identity/ownership without ever emitting raw field
   values, names, phones, messages, blobs, or database pages. Only
   structural table/column identifiers, bounded row counts/identity
   hashes, and SHA-256 digests are returned.

No network access. No production paths. No writes. No migrations, WAL
changes, VACUUM, REINDEX, or mutable PRAGMAs are ever issued.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
import stat
import sys
import urllib.parse
from dataclasses import dataclass, asdict
from typing import List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------
# Section 1: original AST-based short-ownership transform (unchanged
# public interface: AnchorNotFoundError, find_db_handle_names,
# verify_no_live_handle_across_slow_call, transform_short_ownership).
# --------------------------------------------------------------------

SLOW_CALL_NAMES = {
    "sleep", "time.sleep",
    "send_message", "send_photo", "send_video", "send_document",
    "reply_photo", "reply_video", "reply_text", "reply_document",
    "requests.get", "requests.post", "urlopen",
    "open", "write", "system", "run", "Popen", "call",
    "render", "generate", "build",
}


class AnchorNotFoundError(Exception):
    pass


def _iter_functions(tree: ast.AST, names: Set[str]):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            yield node


def _call_qualname(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = ""
        if isinstance(func.value, ast.Name):
            base = func.value.id + "."
        return base + func.attr
    return ""


def find_db_handle_names(func) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("connect"):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
    return names


def verify_no_live_handle_across_slow_call(func) -> List[str]:
    """Walk the statements of `func` in execution order (including simple
    nested blocks) and report violations where a DB handle name (or a
    cursor derived from it) is still open -- i.e. not yet closed -- at
    the point a slow call occurs. Conservative: anything that cannot be
    proven safe is reported as a violation.
    """
    handle_names = find_db_handle_names(func)
    if not handle_names:
        return []
    cursor_names: Set[str] = set()
    state = {"closed": False}
    violations: List[str] = []

    def walk_stmts(stmts):
        for stmt in stmts:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                qual = _call_qualname(stmt.value)
                if qual.endswith("cursor") and isinstance(stmt.value.func, ast.Attribute):
                    owner = getattr(stmt.value.func.value, "id", None)
                    if owner in handle_names:
                        for t in stmt.targets:
                            if isinstance(t, ast.Name):
                                cursor_names.add(t.id)
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    qual = _call_qualname(node)
                    owner = qual.split(".")[0] if "." in qual else None
                    if qual.endswith("close") and (owner in handle_names or owner in cursor_names):
                        state["closed"] = True
                    if any(qual == s or qual.endswith("." + s) or qual == s.split(".")[-1]
                           for s in SLOW_CALL_NAMES):
                        if not state["closed"]:
                            violations.append(
                                f"line {getattr(node, 'lineno', '?')}: slow call "
                                f"'{qual}' before DB handle close"
                            )
            if isinstance(stmt, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                for field in ("body", "orelse", "finalbody"):
                    block = getattr(stmt, field, None)
                    if isinstance(block, list):
                        walk_stmts(block)
                handlers = getattr(stmt, "handlers", None)
                if handlers:
                    for h in handlers:
                        walk_stmts(h.body)

    walk_stmts(func.body)
    return violations


def _ensure_short_timeout(func, handle_names: Set[str]) -> None:
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("connect"):
                has_timeout = any(kw.arg == "timeout" for kw in node.value.keywords)
                if not has_timeout:
                    node.value.keywords.append(
                        ast.keyword(arg="timeout", value=ast.Constant(value=2))
                    )


def transform_short_ownership(source: str, function_names: Set[str]) -> str:
    """Rewrite the named functions so the sqlite3 connection/cursor is
    guaranteed closed (via try/finally) immediately after the last
    statement referencing the DB handle, before any subsequent
    formatting/slow work. Sets a short (2s) connect timeout if none is
    given. Raises AnchorNotFoundError if a function or its DB handle
    cannot be unambiguously identified.
    """
    tree = ast.parse(source)
    found = list(_iter_functions(tree, function_names))
    found_names = {f.name for f in found}
    missing = function_names - found_names
    if missing:
        raise AnchorNotFoundError(f"functions not found: {sorted(missing)}")

    for func in found:
        handle_names = find_db_handle_names(func)
        if not handle_names:
            raise AnchorNotFoundError(
                f"no sqlite3.connect anchor found in function {func.name}"
            )
        _ensure_short_timeout(func, handle_names)

        handle_stmt_indices = []
        for idx, stmt in enumerate(func.body):
            refs_handle = any(
                isinstance(n, ast.Name) and n.id in handle_names
                for n in ast.walk(stmt)
            )
            if refs_handle:
                handle_stmt_indices.append(idx)
        if not handle_stmt_indices:
            raise AnchorNotFoundError(
                f"DB handle {handle_names} unused after connect in {func.name}"
            )
        last_db_idx = max(handle_stmt_indices)
        db_block = func.body[: last_db_idx + 1]
        rest_block = func.body[last_db_idx + 1:]

        close_stmts = []
        for name in sorted(handle_names):
            close_call = ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id=name, ctx=ast.Load()),
                                        attr="close", ctx=ast.Load()),
                    args=[], keywords=[],
                )
            )
            close_stmts.append(close_call)

        try_node = ast.Try(body=db_block, handlers=[], orelse=[], finalbody=close_stmts)
        func.body = [try_node] + rest_block
        ast.fix_missing_locations(func)

    return ast.unparse(tree)


# --------------------------------------------------------------------
# Section 2: canonical read-only, fail-closed SQLite evidence API
# (TASK 034). Standard library only. Never raises for expected
# operational conditions (missing/locked/malformed/ambiguous/overflow);
# always returns a structured OwnershipEvidence with status OK/BLOCKED.
# --------------------------------------------------------------------

MAX_TABLES = 50
MAX_COLUMNS = 50
MAX_ROWS = 1000
MAX_SERIALIZED_BYTES = 1_000_000


@dataclass
class OwnershipEvidence:
    status: str  # "OK" or "BLOCKED"
    reason: str
    quick_check: Optional[str] = None
    query_only: Optional[int] = None
    table: Optional[str] = None
    row_count: Optional[int] = None
    rows_sha256: Optional[str] = None
    evidence_sha256: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def _sanitize(exc: BaseException) -> str:
    # Only the exception class name is ever surfaced -- never the
    # message, which could embed a path or a fragment of data.
    return type(exc).__name__


def _validate_db_path(path: str):
    """Validate the database path with lstat: must be a regular,
    non-symlink file with a stable identity (nlink == 1). Fails closed
    on any hard-link surprise."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        return False, f"path_stat_failed:{_sanitize(exc)}"
    if stat.S_ISLNK(st.st_mode):
        return False, "path_is_symlink"
    if not stat.S_ISREG(st.st_mode):
        return False, "path_not_regular_file"
    if st.st_nlink != 1:
        return False, "path_hard_linked"
    return True, "ok"


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def collect_ua0009_ownership_evidence(
    db_path: str,
    table: str,
    id_column: str,
    id_value: str = "UA-0009",
    timeout: float = 2.0,
    max_tables: int = MAX_TABLES,
    max_columns: int = MAX_COLUMNS,
    max_rows: int = MAX_ROWS,
    max_serialized_bytes: int = MAX_SERIALIZED_BYTES,
) -> OwnershipEvidence:
    """Read-only, fail-closed evidence collection selecting exactly one
    row identified by the configured exact identifier-column rule
    (table/id_column/id_value). The cursor and connection are always
    closed BEFORE any hashing/serialization occurs. Never raises for
    expected operational conditions."""
    valid, reason = _validate_db_path(db_path)
    if not valid:
        return OwnershipEvidence(status="BLOCKED", reason=reason)

    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    quick_check_val = None
    query_only_val = None

    try:
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    except sqlite3.Error as exc:
        return OwnershipEvidence(status="BLOCKED", reason=f"open_failed:{_sanitize(exc)}")

    rows = None
    try:
        try:
            cur = conn.cursor()
            try:
                cur.execute("PRAGMA query_only=ON")
                row = cur.execute("PRAGMA query_only").fetchone()
                query_only_val = row[0] if row else None

                row = cur.execute("PRAGMA quick_check").fetchone()
                quick_check_val = row[0] if row else None
                if quick_check_val != "ok":
                    return OwnershipEvidence(
                        status="BLOCKED", reason="quick_check_not_ok",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )

                tables = cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' LIMIT ?",
                    (max_tables + 1,),
                ).fetchall()
                if len(tables) > max_tables:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="table_overflow",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )
                table_names = {r[0] for r in tables}
                if table not in table_names:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="missing_table",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )

                columns = cur.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
                if len(columns) > max_columns:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="column_overflow",
                        quick_check=quick_check_val, query_only=query_only_val, table=table,
                    )
                column_names = {c[1] for c in columns}
                if id_column not in column_names:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="missing_column",
                        quick_check=quick_check_val, query_only=query_only_val, table=table,
                    )

                select_sql = (
                    f"SELECT rowid, * FROM {_quote_ident(table)} "
                    f"WHERE {_quote_ident(id_column)} = ? LIMIT ?"
                )
                rows = cur.execute(select_sql, (id_value, max_rows + 1)).fetchall()
            finally:
                cur.close()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return OwnershipEvidence(
            status="BLOCKED", reason=f"sqlite_error:{_sanitize(exc)}",
            quick_check=quick_check_val, query_only=query_only_val,
        )

    # Cursor and connection are now closed. Only materialized, immutable
    # values remain; hashing/serialization happens strictly below.
    if not rows:
        return OwnershipEvidence(
            status="BLOCKED", reason="missing_row",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )
    if len(rows) > 1:
        return OwnershipEvidence(
            status="BLOCKED", reason="ambiguous_row",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )

    serialized = repr(rows[0]).encode("utf-8")
    if len(serialized) > max_serialized_bytes:
        return OwnershipEvidence(
            status="BLOCKED", reason="serialized_overflow",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )
    row_hash = hashlib.sha256(serialized).hexdigest()
    combined = hashlib.sha256(
        f"{quick_check_val}|{query_only_val}|{table}|{id_column}|{row_hash}".encode("utf-8")
    ).hexdigest()

    return OwnershipEvidence(
        status="OK", reason="ok", quick_check=quick_check_val, query_only=query_only_val,
        table=table, row_count=1, rows_sha256=row_hash, evidence_sha256=combined,
    )


def compare_ownership_evidence(before: OwnershipEvidence, after: OwnershipEvidence):
    """Pure comparison helper for before/after UA-0009 evidence. OK only
    when both evidence objects are complete (status OK) and their
    evidence_sha256 hashes match exactly."""
    if before.status != "OK" or after.status != "OK":
        return False, "incomplete_evidence"
    if not before.evidence_sha256 or not after.evidence_sha256:
        return False, "incomplete_evidence"
    if before.evidence_sha256 != after.evidence_sha256:
        return False, "hash_mismatch"
    return True, "ok"

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/ua0009_publication_check.py

```python
"""
ua0009_publication_check.py (TASK 034)

Canonical no-redirect publication probe for UA-0009. Only an actual
HTTP 404 or 410 response counts as "not published"; every other
outcome (2xx, 3xx, other 4xx, 5xx, DNS/TLS/timeout/refused/proxy/
network failure represented as status -1, malformed response, or any
exception) is treated as BLOCKED. Redirects are never followed. HTTPS
is required and URLs with embedded credentials are rejected. Tests
inject an opener; this module never performs real network access from
its own tests.

Existing public names (PublicationCheckResult, resolve_canonical_url,
probe_no_redirect, sqlite_quick_check, check_ua0009_not_public,
CONFIG_ENV_VAR, CONFIG_FILE_CANDIDATE, _NoRedirect) remain importable
as thin adapters over the new canonical_probe_ua0009 logic -- no logic
is duplicated.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CONFIG_ENV_VAR = "UA0009_CANONICAL_URL"
CONFIG_FILE_CANDIDATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config", "ua0009_endpoint.json"
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class PublicationProbeResult:
    status: str  # "PASS" or "BLOCKED"
    reason: str
    url: Optional[str] = None
    status_code: Optional[int] = None


@dataclass
class PublicationCheckResult:
    ok: bool
    reason: str
    url: Optional[str] = None
    http_status: Optional[int] = None
    quick_check: Optional[str] = None


def _sanitize(exc: BaseException) -> str:
    return type(exc).__name__


def _validate_https_url(url):
    if not isinstance(url, str) or not url:
        return False, "malformed_url"
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False, "malformed_url"
    if parsed.scheme != "https":
        return False, "non_https_url"
    if not parsed.netloc:
        return False, "malformed_url"
    if "@" in parsed.netloc:
        return False, "embedded_credentials"
    try:
        if parsed.username or parsed.password:
            return False, "embedded_credentials"
    except ValueError:
        return False, "embedded_credentials"
    return True, "ok"


def canonical_probe_ua0009(url: str, opener=None, timeout: float = 5.0) -> PublicationProbeResult:
    """The single canonical no-redirect publication probe. Requires a
    valid HTTPS URL with no embedded credentials. Only HTTP 404/410
    PASS; every other outcome BLOCKS with a bounded structured reason."""
    ok, reason = _validate_https_url(url)
    if not ok:
        return PublicationProbeResult(status="BLOCKED", reason=reason, url=url)

    active_opener = opener if opener is not None else urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, method="GET")

    try:
        response = active_opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        if status_code in (404, 410):
            return PublicationProbeResult(status="PASS", reason="not_found", url=url, status_code=status_code)
        return PublicationProbeResult(
            status="BLOCKED", reason=f"unexpected_status:{status_code}", url=url, status_code=status_code
        )
    except urllib.error.URLError:
        return PublicationProbeResult(status="BLOCKED", reason="network_error", url=url, status_code=-1)
    except (TimeoutError, OSError):
        return PublicationProbeResult(status="BLOCKED", reason="network_error", url=url, status_code=-1)
    except Exception as exc:  # pragma: no cover - defensive, fail closed
        return PublicationProbeResult(status="BLOCKED", reason=f"exception:{_sanitize(exc)}", url=url)

    try:
        if hasattr(response, "__enter__"):
            with response as resp:
                status_code = resp.getcode()
        else:
            status_code = response.getcode()
    except Exception as exc:  # pragma: no cover - defensive, fail closed
        return PublicationProbeResult(status="BLOCKED", reason=f"malformed_response:{_sanitize(exc)}", url=url)

    if status_code in (404, 410):
        return PublicationProbeResult(status="PASS", reason="not_found", url=url, status_code=status_code)
    return PublicationProbeResult(
        status="BLOCKED", reason=f"unexpected_status:{status_code}", url=url, status_code=status_code
    )


def resolve_canonical_url() -> Optional[str]:
    env_val = os.environ.get(CONFIG_ENV_VAR)
    if env_val:
        return env_val.strip()
    if os.path.isfile(CONFIG_FILE_CANDIDATE) and not os.path.islink(CONFIG_FILE_CANDIDATE):
        try:
            with open(CONFIG_FILE_CANDIDATE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            url = data.get("ua0009_canonical_url")
            if isinstance(url, str) and url.strip():
                return url.strip()
        except (OSError, json.JSONDecodeError):
            return None
    return None


def probe_no_redirect(url: str, timeout: float = 5.0, opener=None) -> int:
    """Compatibility adapter over canonical_probe_ua0009. Preserves the
    historical int-returning interface: returns a raw HTTP status code,
    or -1 for network failure / non-HTTP-status BLOCKED outcomes."""
    result = canonical_probe_ua0009(url, opener=opener, timeout=timeout)
    if result.status_code is not None:
        return result.status_code
    return -1


def sqlite_quick_check(db_path: str, timeout: float = 2.0) -> str:
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    except sqlite3.Error as exc:
        return f"error:{_sanitize(exc)}"
    try:
        conn.execute("PRAGMA query_only=1")
        cur = conn.execute("PRAGMA quick_check")
        row = cur.fetchone()
        cur.close()
        return row[0] if row else "unknown"
    except sqlite3.Error as exc:
        return f"error:{_sanitize(exc)}"
    finally:
        conn.close()


def check_ua0009_not_public(db_path: str, url: Optional[str] = None, opener=None) -> PublicationCheckResult:
    """Compatibility adapter combining the canonical no-redirect probe
    with a read-only SQLite quick_check. Fail-closed: a missing
    configured URL BLOCKS -- it is never silently skipped."""
    active_url = url if url is not None else resolve_canonical_url()
    if not active_url:
        return PublicationCheckResult(
            ok=False,
            reason="BLOCKED: no configured UA0009 canonical URL "
                   f"(set {CONFIG_ENV_VAR} or {CONFIG_FILE_CANDIDATE})",
        )

    probe = canonical_probe_ua0009(active_url, opener=opener)
    quick_check = sqlite_quick_check(db_path)
    quick_ok = (quick_check == "ok")
    ok = bool(probe.status == "PASS" and quick_ok)
    reason = "ok" if ok else f"BLOCKED: probe={probe.status}:{probe.reason} quick_check={quick_check!r}"
    return PublicationCheckResult(
        ok=ok, reason=reason, url=active_url, http_status=probe.status_code, quick_check=quick_check,
    )

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/ua0009_publication_check.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_032_orchestration.py

```python
"""Offline, deterministic tests for TASK 032: real orchestration entry
point, secure run lifecycle, measured phases, and manifest/verification
integrity. No network access. No /home/Carix paths. Only temporary
directories, local files, and fake HTTPS openers are used.
"""
import os
import sys
import json
import time
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import crm_speed_gate_a as gate_a
import build_manifest
import verify_gate_a
import RUN_GATE_A_CRM_SPEED as launcher

from test_crm_speed_gate_a import (
    CLEAN_CARS_UI, CLEAN_USERCUSTOMIZE, CLEAN_AVTOPEREDACHA,
    DB_FUNCTION_SOURCE, _FakeOpener,
)

CARS_UI_SIDE_EFFECT_SOURCE = """def gallery(update, context):
    undefined_name_reference_only_fails_if_executed()
def video_gallery(update, context): pass
def diag_photo_show(update, context): pass
def diag_video_show(update, context): pass
"""


def _fake_opener_404():
    return _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))


def _make_temp_config():
    tmp = tempfile.mkdtemp(prefix="task032_")
    names = [
        "usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
        "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py",
    ]
    required = []
    for name in names:
        p = os.path.join(tmp, name)
        if name == "cars_ui.py":
            content = CLEAN_CARS_UI
        elif name == "usercustomize.py":
            content = CLEAN_USERCUSTOMIZE
        elif name == "avtoperedacha.py":
            content = CLEAN_AVTOPEREDACHA
        else:
            content = "# fixture" + os.linesep
        with open(p, "w") as fh:
            fh.write(content)
        required.append(p)

    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    required.append(db_path)

    backup_path = os.path.join(tmp, "backup.tar.gz")
    with open(backup_path, "wb") as fh:
        fh.write(b"fixture-backup-bytes")
    backup_sha = gate_a._sha256_file(backup_path)

    site_root1 = os.path.join(tmp, "site")
    site_root2 = os.path.join(tmp, "video")
    site_root3 = os.path.join(tmp, "public_html")
    for root in (site_root1, site_root2, site_root3):
        os.makedirs(root)
        with open(os.path.join(root, "index.html"), "w") as fh:
            fh.write("<html></html>")
        with open(os.path.join(root, "katalog.html"), "w") as fh:
            fh.write("<html></html>")

    run_root = os.path.join(tmp, "qa_root")
    os.makedirs(run_root, mode=0o700)

    config = {
        "required_inputs": required,
        "site_roots": {
            site_root1: ["index.html", "katalog.html"],
            site_root2: ["index.html", "katalog.html"],
            site_root3: ["index.html", "katalog.html"],
        },
        "ua0009_url": "https://example.com/UA-0009.html",
        "run_root": run_root,
        "backup_archive": backup_path,
        "backup_archive_sha256": backup_sha,
        "protected_function_names": [],
        "db_function_source": DB_FUNCTION_SOURCE,
        "min_free_bytes": 1024,
    }
    return config, tmp


class _TempConfigCase(unittest.TestCase):
    def setUp(self):
        self.cfg, self.tmp = _make_temp_config()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class LauncherTests(unittest.TestCase):
    def test_launcher_calls_orchestration_and_propagates_pass(self):
        fake_receipt = {
            "status": "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL",
            "run_id": "x", "unmet_predicates": [], "phases": [], "production_write": "NO",
        }
        calls = []

        def fake_orchestrate(cfg):
            calls.append(cfg)
            return fake_receipt

        rc = launcher.main(orchestrate=fake_orchestrate, config={"marker": True})
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [{"marker": True}])

    def test_launcher_propagates_blocked_nonzero(self):
        fake_receipt = {
            "status": "BLOCKED", "run_id": "x", "unmet_predicates": ["a"],
            "phases": [], "production_write": "NO",
        }
        rc = launcher.main(orchestrate=lambda cfg: fake_receipt, config={})
        self.assertEqual(rc, 1)

    def test_launcher_internal_error_is_nonzero(self):
        def boom(cfg):
            raise RuntimeError("deliberate")
        rc = launcher.main(orchestrate=boom, config={})
        self.assertEqual(rc, 1)


class RunDirCreationTests(_TempConfigCase):
    def test_exactly_one_validated_run_dir_created_before_safewriter(self):
        seen = []
        original_init = gate_a.SafeWriter.__init__

        def spy_init(self, run_dir):
            seen.append(os.path.isdir(run_dir) and not os.path.islink(run_dir))
            return original_init(self, run_dir)

        with mock.patch.object(gate_a.SafeWriter, "__init__", spy_init):
            gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())

        self.assertTrue(seen)
        self.assertTrue(all(seen))
        subdirs = [
            d for d in os.listdir(self.cfg["run_root"])
            if os.path.isdir(os.path.join(self.cfg["run_root"], d))
        ]
        self.assertEqual(len(subdirs), 1)


class SecureInputTests(_TempConfigCase):
    def test_symlink_input_blocks(self):
        target = self.cfg["required_inputs"][0]
        os.remove(target)
        os.symlink(os.path.join(self.tmp, "crm.db"), target)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("symlink_input" in b for b in receipt.get("blockers", [])))

    def test_missing_input_blocks(self):
        target = self.cfg["required_inputs"][0]
        os.remove(target)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("missing_input" in b for b in receipt.get("blockers", [])))

    def test_hardlink_input_blocks(self):
        target = self.cfg["required_inputs"][0]
        other = os.path.join(self.tmp, "other_copy.py")
        os.link(target, other)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any("hard_linked_input" in b for b in receipt.get("blockers", [])))


class BackupOrderingTests(_TempConfigCase):
    def test_backup_mismatch_blocks_before_candidate_creation(self):
        self.cfg["backup_archive_sha256"] = "0" * 64
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertNotIn("candidates_compile", receipt["evidence"])
        self.assertTrue(any("backup_verification_failed" in b for b in receipt.get("blockers", [])))


class LockDuplicateTests(_TempConfigCase):
    def test_duplicate_lock_returns_promptly_without_altering_owner_evidence(self):
        qa_root_real = os.path.realpath(self.cfg["run_root"])
        holder = canonical_modules.CrossProcessLock(os.path.join(qa_root_real, "gate_a.lock"))
        self.assertTrue(holder.acquire())
        try:
            before = holder._read_evidence()
            t0 = time.time()
            receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
            elapsed = time.time() - t0
            after = holder._read_evidence()
            self.assertLess(elapsed, 2.0)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertIn("gate_a_lock_held", receipt.get("blockers", []))
            self.assertEqual(before.token, after.token)
        finally:
            holder.release()


class PhaseOrderTests(_TempConfigCase):
    def test_phase_order_and_measured_durations(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        phase_nums = [p["phase"] for p in receipt["phases"]]
        self.assertEqual(phase_nums, [20, 40, 60, 80, 100])
        for p in receipt["phases"]:
            self.assertGreaterEqual(p["end"], p["start"])
            self.assertGreaterEqual(p["duration"], 0)
        self.assertEqual(receipt["phases"][-1]["status"], "finished")


class InventorySurroundTests(_TempConfigCase):
    def test_inventories_surround_entire_workload(self):
        call_count = {"n": 0}
        original = gate_a.scan_bounded_inventory

        def counting(*args, **kwargs):
            call_count["n"] += 1
            return original(*args, **kwargs)

        with mock.patch.object(gate_a, "scan_bounded_inventory", counting):
            receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())

        n_roots = len(self.cfg["site_roots"])
        self.assertEqual(call_count["n"], n_roots * 2)
        self.assertIn("before", receipt["site_inventories"])
        self.assertIn("after", receipt["site_inventories"])


class CompileOnlyTests(_TempConfigCase):
    def test_candidates_compile_without_import_execution(self):
        cars_ui_path = [p for p in self.cfg["required_inputs"] if p.endswith("cars_ui.py")][0]
        with open(cars_ui_path, "w") as fh:
            fh.write(CARS_UI_SIDE_EFFECT_SOURCE)
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertIn("candidates_compile", receipt["evidence"])
        self.assertEqual(receipt["evidence"]["candidates_compile"]["status"], "OK")


def _clean_pass_fixture(tmp):
    required = []
    names = [
        "usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
        "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py",
    ]
    for name in names:
        p = os.path.join(tmp, name)
        with open(p, "w") as fh:
            fh.write("# fixture" + os.linesep)
        required.append(p)
    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    required.append(db_path)

    backup_archive = os.path.join(tmp, "backup.tar.gz")
    with open(backup_archive, "wb") as fh:
        fh.write(b"fixture-backup-bytes")
    backup_sha256 = gate_a._sha256_file(backup_archive)

    site_root = os.path.join(tmp, "site")
    os.makedirs(site_root)
    with open(os.path.join(site_root, "index.html"), "w") as fh:
        fh.write("<html></html>")
    with open(os.path.join(site_root, "katalog.html"), "w") as fh:
        fh.write("<html></html>")

    run_dir = os.path.join(tmp, "run")
    fp = {"a": 1}
    return {
        "required_inputs": required,
        "backup_archive": backup_archive,
        "backup_archive_sha256": backup_sha256,
        "cars_ui_source": CLEAN_CARS_UI,
        "usercustomize_source": CLEAN_USERCUSTOMIZE,
        "avtoperedacha_source": CLEAN_AVTOPEREDACHA,
        "protected_fingerprints_before": fp,
        "protected_fingerprints_after": dict(fp),
        "db_path": db_path,
        "ua0009_fingerprint_before": {"h": "same"},
        "ua0009_fingerprint_after": {"h": "same"},
        "ua0009_url": "https://example.com/UA-0009.html",
        "ua0009_opener": _fake_opener_404(),
        "site_root": site_root,
        "allowed_site_names": ["index.html", "katalog.html"],
        "protected_function_names": ["upload_media", "delete_media"],
        "tmp_dir": tmp,
        "db_function_source": DB_FUNCTION_SOURCE,
        "site_before": {"x": 1},
        "site_after": {"x": 1},
        "run_dir": run_dir,
    }


class ManifestVerifyTests(_TempConfigCase):
    def test_receipt_and_manifest_hash_tamper_detected(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertIsNotNone(receipt.get("run_id"))
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
        self.assertTrue(os.path.isdir(run_dir))

        package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
        manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh)

        receipt_path = os.path.join(run_dir, "receipt.json")
        ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path)
        self.assertTrue(ok, reason)

        with open(receipt_path, "r") as fh:
            data = fh.read()
        with open(receipt_path, "w") as fh:
            fh.write(data + os.linesep + "tampered")

        ok2, reason2 = verify_gate_a.verify_receipt(receipt_path, manifest_path)
        self.assertFalse(ok2)

    def test_missing_required_predicate_blocks_verification(self):
        tmp2 = tempfile.mkdtemp(prefix="task032_legacy_")
        try:
            fixture = _clean_pass_fixture(tmp2)
            receipt = gate_a.run_gate_a(fixture)
            self.assertEqual(receipt["status"], "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL")
            del receipt["evidence"]["backup_verified"]
            receipt_path = os.path.join(tmp2, "tampered_receipt.json")
            with open(receipt_path, "w") as fh:
                json.dump(receipt, fh)
            ok, reason = verify_gate_a.verify_receipt(receipt_path)
            self.assertFalse(ok)
            self.assertTrue(reason.startswith("missing_or_malformed_predicate"))
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_altered_candidate_diff_report_blocks_verification(self):
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        run_dir = os.path.join(self.cfg["run_root"], receipt["run_id"])
        package_dir = os.path.dirname(os.path.abspath(gate_a.__file__))
        manifest = build_manifest.build_manifest(package_dir, run_dir, receipt)
        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh)
        report_path = os.path.join(run_dir, "report.md")
        with open(report_path, "a") as fh:
            fh.write("tampered-line" + os.linesep)
        ok, reason = verify_gate_a.verify_receipt(os.path.join(run_dir, "receipt.json"), manifest_path)
        self.assertFalse(ok)
        self.assertEqual(reason, "report_hash_mismatch")


class BlockedNonzeroTests(_TempConfigCase):
    def test_blocked_orchestration_returns_nonzero_with_complete_evidence(self):
        self.cfg["backup_archive_sha256"] = "0" * 64

        def orchestrate(cfg):
            return gate_a.orchestrate_gate_a(cfg, opener=_fake_opener_404())

        rc = launcher.main(orchestrate=orchestrate, config=self.cfg)
        self.assertEqual(rc, 1)

    def test_blocked_receipt_has_bounded_evidence(self):
        self.cfg["backup_archive_sha256"] = "0" * 64
        receipt = gate_a.orchestrate_gate_a(self.cfg, opener=_fake_opener_404())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("phases", receipt)
        self.assertIn("blockers", receipt)
        self.assertEqual(receipt["production_write"], "NO")


class RebuildQueueAckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task032_rq_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_slow_callback_still_yields_prompt_enqueue_return(self):
        lock_path = os.path.join(self.tmp, "rebuild.lock")
        release_cb = threading.Event()

        def slow_cb():
            release_cb.wait(timeout=3)

        q = canonical_modules.RebuildQueue(slow_cb, lock_path)
        t0 = time.time()
        status = q.enqueue()
        elapsed = time.time() - t0
        self.assertEqual(status, "accepted")
        self.assertLess(elapsed, 0.20)
        release_cb.set()
        q.shutdown(timeout=5)

    def test_immediate_observation_sees_callback_entry(self):
        lock_path = os.path.join(self.tmp, "rebuild.lock")
        entered = threading.Event()

        def cb():
            entered.set()

        q = canonical_modules.RebuildQueue(cb, lock_path)
        status = q.enqueue()
        self.assertEqual(status, "accepted")
        self.assertTrue(entered.is_set())
        q.shutdown(timeout=5)


if __name__ == "__main__":
    unittest.main()

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_032_orchestration.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_034_evidence_modules.py

```python
"""Offline, deterministic, temporary-directory-only tests for TASK 034:
four standalone evidence modules (sqlite_ownership, ua0009_publication_
check, build_manifest, verify_gate_a). No network access. No
/home/Carix or production paths. No PythonAnywhere access. No Gate A
execution.
"""
import hashlib
import json
import os
import py_compile
import shutil
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite_ownership
import ua0009_publication_check as ua_check
import build_manifest
import verify_gate_a

MODULE_FILES = [
    "sqlite_ownership.py",
    "ua0009_publication_check.py",
    "build_manifest.py",
    "verify_gate_a.py",
    "test_task_034_evidence_modules.py",
]

SEEDED_SECRET = "no-pii-seed-marker-should-not-leak"


class CompileTests(unittest.TestCase):
    def test_all_modules_compile(self):
        base = os.path.dirname(os.path.abspath(__file__))
        for name in MODULE_FILES:
            path = os.path.join(base, name)
            py_compile.compile(path, doraise=True)


def _make_db(tmp, table="cards", column="code", value="UA-0009", extra_rows=None):
    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, {column} TEXT, secret TEXT)")
    conn.execute(f"INSERT INTO {table} ({column}, secret) VALUES (?, ?)", (value, SEEDED_SECRET))
    if extra_rows:
        for row_val in extra_rows:
            conn.execute(f"INSERT INTO {table} ({column}, secret) VALUES (?, ?)", (row_val, "extra"))
    conn.commit()
    conn.close()
    return db_path


class SqliteOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task034_sqlite_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_quick_check_ok_and_query_only_confirmed(self):
        db = _make_db(self.tmp)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "OK")
        self.assertEqual(ev.quick_check, "ok")
        self.assertEqual(ev.query_only, 1)

    def test_missing_db_blocks(self):
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(
            os.path.join(self.tmp, "nope.db"), "cards", "code", "UA-0009"
        )
        self.assertEqual(ev.status, "BLOCKED")

    def test_symlink_db_blocks(self):
        db = _make_db(self.tmp)
        link = os.path.join(self.tmp, "link.db")
        os.symlink(db, link)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(link, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "path_is_symlink")

    def test_hardlink_db_blocks(self):
        db = _make_db(self.tmp)
        other = os.path.join(self.tmp, "other.db")
        os.link(db, other)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "path_hard_linked")

    def test_malformed_db_blocks(self):
        bad = os.path.join(self.tmp, "bad.db")
        with open(bad, "wb") as fh:
            fh.write(b"not a real sqlite database file, garbage bytes here" * 10)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(bad, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "BLOCKED")

    def test_locked_db_blocks_identical_bytes_before_after(self):
        db = _make_db(self.tmp)
        with open(db, "rb") as fh:
            before_bytes = fh.read()
        conn = sqlite3.connect(db)
        conn.execute("BEGIN EXCLUSIVE")
        try:
            ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009", timeout=0.2)
            self.assertEqual(ev.status, "BLOCKED")
        finally:
            conn.rollback()
            conn.close()
        with open(db, "rb") as fh:
            after_bytes = fh.read()
        self.assertEqual(before_bytes, after_bytes)

    def test_missing_table_and_column_block(self):
        db = _make_db(self.tmp)
        ev1 = sqlite_ownership.collect_ua0009_ownership_evidence(db, "nope", "code", "UA-0009")
        self.assertEqual(ev1.status, "BLOCKED")
        self.assertEqual(ev1.reason, "missing_table")
        ev2 = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "nope", "UA-0009")
        self.assertEqual(ev2.status, "BLOCKED")
        self.assertEqual(ev2.reason, "missing_column")

    def test_missing_row_blocks(self):
        db = _make_db(self.tmp)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-9999")
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "missing_row")

    def test_ambiguous_rows_block(self):
        db = _make_db(self.tmp, extra_rows=["UA-0009"])
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "ambiguous_row")

    def test_table_overflow_blocks(self):
        db = _make_db(self.tmp)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(
            db, "cards", "code", "UA-0009", max_tables=0
        )
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "table_overflow")

    def test_evidence_has_no_seeded_pii(self):
        db = _make_db(self.tmp)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        serialized = json.dumps(ev.to_dict())
        self.assertNotIn(SEEDED_SECRET, serialized)

    def test_compare_before_after_identical_is_ok(self):
        db = _make_db(self.tmp)
        before = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        after = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        ok, reason = sqlite_ownership.compare_ownership_evidence(before, after)
        self.assertTrue(ok, reason)

    def test_compare_before_after_changed_blocks(self):
        db = _make_db(self.tmp)
        before = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        conn = sqlite3.connect(db)
        conn.execute("UPDATE cards SET secret = 'changed-value' WHERE code = 'UA-0009'")
        conn.commit()
        conn.close()
        after = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        ok, reason = sqlite_ownership.compare_ownership_evidence(before, after)
        self.assertFalse(ok)

    def test_incomplete_evidence_compare_blocks(self):
        blocked = sqlite_ownership.OwnershipEvidence(status="BLOCKED", reason="x")
        ok_ev = sqlite_ownership.OwnershipEvidence(status="OK", reason="ok", evidence_sha256="a" * 64)
        ok, reason = sqlite_ownership.compare_ownership_evidence(blocked, ok_ev)
        self.assertFalse(ok)
        self.assertEqual(reason, "incomplete_evidence")

    def test_cursor_and_connection_closed_before_hashing(self):
        db = _make_db(self.tmp)
        events = []
        orig_connect = sqlite_ownership.sqlite3.connect
        orig_sha256 = sqlite_ownership.hashlib.sha256

        class ProxyCursor:
            def __init__(self, real):
                self._real = real

            def execute(self, *a, **kw):
                return self._real.execute(*a, **kw)

            def close(self):
                events.append("cursor_close")
                self._real.close()

        class ProxyConn:
            def __init__(self, real):
                self._real = real

            def cursor(self):
                return ProxyCursor(self._real.cursor())

            def close(self):
                events.append("conn_close")
                self._real.close()

        def fake_connect(*args, **kwargs):
            return ProxyConn(orig_connect(*args, **kwargs))

        def tracking_sha256(*args, **kwargs):
            events.append("sha256")
            return orig_sha256(*args, **kwargs)

        with mock.patch.object(sqlite_ownership.sqlite3, "connect", fake_connect), \
             mock.patch.object(sqlite_ownership.hashlib, "sha256", tracking_sha256):
            ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")

        self.assertEqual(ev.status, "OK")
        self.assertIn("cursor_close", events)
        self.assertIn("conn_close", events)
        self.assertIn("sha256", events)
        self.assertLess(events.index("cursor_close"), events.index("sha256"))
        self.assertLess(events.index("conn_close"), events.index("sha256"))

    def test_public_names_still_importable(self):
        self.assertTrue(hasattr(sqlite_ownership, "transform_short_ownership"))
        self.assertTrue(hasattr(sqlite_ownership, "verify_no_live_handle_across_slow_call"))
        self.assertTrue(hasattr(sqlite_ownership, "find_db_handle_names"))
        self.assertTrue(hasattr(sqlite_ownership, "AnchorNotFoundError"))


class FakeResponse:
    def __init__(self, code):
        self._code = code

    def getcode(self):
        return self._code

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class BadResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, code=None, raise_exc=None):
        self.code = code
        self.raise_exc = raise_exc

    def open(self, req, timeout=None):
        if self.raise_exc:
            raise self.raise_exc
        return FakeResponse(self.code)


class BadOpener:
    def open(self, req, timeout=None):
        return BadResponse()


class PublicationCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task034_pub_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_404_passes(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "PASS")

    def test_410_passes(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 410, "gone", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "PASS")

    def test_200_blocks(self):
        opener = FakeOpener(code=200)
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")

    def test_redirect_status_blocks(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 301, "moved", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")

    def test_other_4xx_blocks(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 403, "forbidden", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")

    def test_5xx_blocks(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 500, "err", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")

    def test_network_error_blocks_status_minus_one(self):
        opener = FakeOpener(raise_exc=urllib.error.URLError("no network"))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.status_code, -1)

    def test_malformed_response_blocks(self):
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=BadOpener())
        self.assertEqual(result.status, "BLOCKED")

    def test_non_https_blocks(self):
        result = ua_check.canonical_probe_ua0009("http://example.com/UA-0009.html", opener=FakeOpener(code=404))
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason, "non_https_url")

    def test_malformed_url_blocks(self):
        result = ua_check.canonical_probe_ua0009("not-a-url", opener=FakeOpener(code=404))
        self.assertEqual(result.status, "BLOCKED")

    def test_embedded_credentials_block(self):
        result = ua_check.canonical_probe_ua0009("https://user:pass@example.com/x", opener=FakeOpener(code=404))
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason, "embedded_credentials")

    def test_legacy_probe_no_redirect_returns_status_code(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        code = ua_check.probe_no_redirect("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(code, 404)

    def test_legacy_probe_no_redirect_network_error_returns_minus_one(self):
        opener = FakeOpener(raise_exc=urllib.error.URLError("down"))
        code = ua_check.probe_no_redirect("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(code, -1)

    def test_legacy_check_ua0009_not_public_fails_closed_without_url(self):
        db = _make_db(self.tmp)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ua_check.CONFIG_ENV_VAR, None)
            result = ua_check.check_ua0009_not_public(db, url=None, opener=FakeOpener(code=404))
        self.assertFalse(result.ok)

    def test_legacy_check_ua0009_not_public_ok_on_404_and_quickcheck_ok(self):
        db = _make_db(self.tmp)
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        result = ua_check.check_ua0009_not_public(db, url="https://example.com/UA-0009.html", opener=opener)
        self.assertTrue(result.ok, result.reason)

    def test_legacy_check_ua0009_not_public_blocks_on_200(self):
        db = _make_db(self.tmp)
        opener = FakeOpener(code=200)
        result = ua_check.check_ua0009_not_public(db, url="https://example.com/UA-0009.html", opener=opener)
        self.assertFalse(result.ok)

    def test_public_names_still_importable(self):
        self.assertTrue(hasattr(ua_check, "PublicationCheckResult"))
        self.assertTrue(hasattr(ua_check, "resolve_canonical_url"))
        self.assertTrue(hasattr(ua_check, "sqlite_quick_check"))
        self.assertTrue(hasattr(ua_check, "check_ua0009_not_public"))
        self.assertTrue(hasattr(ua_check, "CONFIG_ENV_VAR"))
        self.assertTrue(hasattr(ua_check, "CONFIG_FILE_CANDIDATE"))


class BuildManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task034_manifest_")
        self.package_dir = os.path.join(self.tmp, "package")
        os.makedirs(self.package_dir)
        with open(os.path.join(self.package_dir, "mod_a.py"), "w") as fh:
            fh.write("x = 1\n")
        self.run_dir = os.path.join(self.tmp, "run")
        os.makedirs(self.run_dir)
        self.receipt_path = os.path.join(self.run_dir, "receipt.json")
        with open(self.receipt_path, "w") as fh:
            json.dump({"status": "PASS"}, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_deterministic_manifest_from_identical_inputs(self):
        kwargs = dict(
            run_artifact_paths={"receipt": self.receipt_path},
            allowed_write_ledger=[{"path": "a", "sha256": "x"}, {"path": "b", "sha256": "y"}],
            sqlite_evidence={"quick_check": "ok"},
            ua0009_evidence_before={"h": "1"},
            ua0009_evidence_after={"h": "1"},
            publication_evidence={"status": "PASS"},
        )
        m1 = build_manifest.build_manifest(self.package_dir, self.run_dir, **kwargs)
        m2 = build_manifest.build_manifest(self.package_dir, self.run_dir, **kwargs)
        self.assertEqual(build_manifest.canonical_json(m1), build_manifest.canonical_json(m2))

    def test_pii_emitted_field_is_no(self):
        m = build_manifest.build_manifest(self.package_dir, self.run_dir)
        self.assertEqual(m["pii_emitted"], "NO")

    def test_manifest_has_no_self_referential_hash(self):
        m = build_manifest.build_manifest(self.package_dir, self.run_dir)
        self.assertNotIn("manifest_sha256", m)

    def test_symlink_run_artifact_blocks(self):
        link = os.path.join(self.run_dir, "link_receipt.json")
        os.symlink(self.receipt_path, link)
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(
                self.package_dir, self.run_dir, run_artifact_paths={"receipt": link}
            )

    def test_hardlink_run_artifact_blocks(self):
        other = os.path.join(self.run_dir, "other_receipt.json")
        os.link(self.receipt_path, other)
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(
                self.package_dir, self.run_dir, run_artifact_paths={"receipt": other}
            )

    def test_outside_run_dir_blocks(self):
        outside = os.path.join(self.tmp, "outside.json")
        with open(outside, "w") as fh:
            fh.write("{}")
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(
                self.package_dir, self.run_dir, run_artifact_paths={"receipt": outside}
            )

    def test_symlink_package_file_blocks(self):
        link = os.path.join(self.package_dir, "mod_link.py")
        os.symlink(os.path.join(self.package_dir, "mod_a.py"), link)
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(self.package_dir, self.run_dir)

    def test_missing_run_dir_blocks(self):
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(self.package_dir, os.path.join(self.tmp, "nope"))


class VerifyGateATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task034_verify_")
        self.run_dir = os.path.join(self.tmp, "run")
        os.makedirs(self.run_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _predicates_ok(self):
        return {k: {"status": "OK"} for k in verify_gate_a.REQUIRED_PREDICATES}

    def _write_receipt(self, data, name="receipt.json"):
        path = os.path.join(self.run_dir, name)
        with open(path, "w") as fh:
            json.dump(data, fh)
        return path

    def test_pass_receipt_verifies_ok(self):
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(), "unmet_predicates": [],
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertTrue(ok, reason)

    def test_legacy_two_positional_arg_call_still_works(self):
        receipt = {
            "status": "BLOCKED", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(),
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, None)
        self.assertTrue(ok, reason)

    def test_missing_predicate_blocks(self):
        preds = self._predicates_ok()
        del preds[verify_gate_a.REQUIRED_PREDICATES[0]]
        receipt = {
            "status": "BLOCKED", "production_write": "NO", "pii_emitted": "NO",
            "predicates": preds,
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("missing_or_malformed_predicate"))

    def test_pass_with_unmet_predicate_blocks(self):
        preds = self._predicates_ok()
        preds[verify_gate_a.REQUIRED_PREDICATES[0]] = {"status": "BLOCKED"}
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": preds, "unmet_predicates": [],
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_production_write_not_no_blocks(self):
        receipt = {
            "status": "BLOCKED", "production_write": "YES", "pii_emitted": "NO",
            "predicates": self._predicates_ok(),
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "production_write_not_no")

    def test_pii_emitted_not_no_blocks(self):
        receipt = {
            "status": "BLOCKED", "production_write": "NO", "pii_emitted": "YES",
            "predicates": self._predicates_ok(),
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "pii_emitted_not_no")

    def test_symlink_receipt_blocks(self):
        real = self._write_receipt({"status": "BLOCKED", "production_write": "NO",
                                     "pii_emitted": "NO", "predicates": self._predicates_ok()})
        link = os.path.join(self.run_dir, "link.json")
        os.symlink(real, link)
        ok, reason = verify_gate_a.verify_receipt(link, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_hardlink_receipt_blocks(self):
        real = self._write_receipt({"status": "BLOCKED", "production_write": "NO",
                                     "pii_emitted": "NO", "predicates": self._predicates_ok()})
        other = os.path.join(self.run_dir, "hardlink.json")
        os.link(real, other)
        ok, reason = verify_gate_a.verify_receipt(other, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_non_regular_file_blocks(self):
        # a directory named receipt.json is not a regular file
        fake_dir = os.path.join(self.run_dir, "dir_receipt.json")
        os.makedirs(fake_dir)
        ok, reason = verify_gate_a.verify_receipt(fake_dir, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_duplicate_key_blocks(self):
        path = os.path.join(self.run_dir, "dup.json")
        with open(path, "w") as fh:
            fh.write(
                '{"status": "BLOCKED", "status": "PASS", "production_write": "NO", '
                '"pii_emitted": "NO", "predicates": {}}'
            )
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_extra_data_blocks(self):
        path = os.path.join(self.run_dir, "extra.json")
        with open(path, "w") as fh:
            fh.write('{"status": "BLOCKED"} garbage-extra-data')
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_non_utf8_blocks(self):
        path = os.path.join(self.run_dir, "bad.json")
        with open(path, "wb") as fh:
            fh.write(b"\xff\xfe\x00\x01not utf8")
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_oversized_blocks(self):
        path = os.path.join(self.run_dir, "big.json")
        with open(path, "w") as fh:
            fh.write('{"status": "BLOCKED", "pad": "' + ("a" * (verify_gate_a.MAX_JSON_BYTES + 100)) + '"}')
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_manifest_hash_binding_ok_then_tamper_detected(self):
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(), "unmet_predicates": [],
        }
        receipt_path = self._write_receipt(receipt)
        receipt_hash = verify_gate_a._secure_hash_file(receipt_path, os.path.realpath(self.run_dir))
        manifest = {"receipt_sha256": receipt_hash}
        manifest_path = os.path.join(self.run_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh)

        ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path=manifest_path, run_dir=self.run_dir)
        self.assertTrue(ok, reason)

        with open(receipt_path, "a") as fh:
            fh.write(" ")
        ok2, reason2 = verify_gate_a.verify_receipt(receipt_path, manifest_path=manifest_path, run_dir=self.run_dir)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "receipt_hash_mismatch")

    def test_missing_evidence_manifest_blocks(self):
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(), "unmet_predicates": [],
        }
        receipt_path = self._write_receipt(receipt)
        manifest_path = os.path.join(self.run_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump({}, fh)
        ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path=manifest_path, run_dir=self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "receipt_hash_mismatch")

    def test_manifest_malformed_blocks(self):
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(), "unmet_predicates": [],
        }
        receipt_path = self._write_receipt(receipt)
        manifest_path = os.path.join(self.run_dir, "manifest.json")
        with open(manifest_path, "wb") as fh:
            fh.write(b"{not valid json")
        ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path=manifest_path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_public_names_still_importable(self):
        self.assertTrue(hasattr(verify_gate_a, "verify_receipt"))
        self.assertTrue(hasattr(verify_gate_a, "REQUIRED_PREDICATES"))


class CrossModuleImportCompatibilityTests(unittest.TestCase):
    def test_all_four_modules_importable_together(self):
        self.assertTrue(hasattr(sqlite_ownership, "transform_short_ownership"))
        self.assertTrue(hasattr(ua0009_publication_check_module(), "resolve_canonical_url"))
        self.assertTrue(hasattr(build_manifest, "build_manifest"))
        self.assertTrue(hasattr(verify_gate_a, "verify_receipt"))


def ua0009_publication_check_module():
    return ua_check


if __name__ == "__main__":
    unittest.main()

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_task_034_evidence_modules.py
