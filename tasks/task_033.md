# TASK 033 — CRM-SPEED-001 phase C: fail-closed SQLite, UA-0009 and publication evidence

## Authority and immutable safety boundary

Continue owner-approved TASK 030 after TASK 032. Work only under `cloud/`. Do not execute Gate A. Do not access PythonAnywhere, /home/Carix, real production URLs, or the network in tests. Do not modify Production, CRM, crm.db, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. Never publish UA-0009. Do not modify `tasks/`.

Required markers in all status/report files:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

Successful phase status is READY_FOR_CONTROLLER_REVIEW_PHASE_C, never READY_FOR_GATE_A.

## Independent controller result on commit a7e153ecf91c010d6b0b289adeef9bda489741b7

Compilation passed. Full discovery ran 112 tests: 110 PASS, 1 FAIL, 1 ERROR.

Exact defects:

1. `verify_gate_a.verify_receipt` lets malformed JSON raise `json.JSONDecodeError`. Every malformed, unreadable, symlinked, non-regular, hard-linked, oversized or structurally invalid receipt/manifest must return a bounded fail-closed `(False, reason)`, never raise.
2. `CompileOnlyTests.test_candidates_compile_without_import_execution` receives no `candidates_compile` evidence because an earlier semantic transform block prevents phase 60. Safe independent evidence collection must continue where prerequisites exist. It is valid to compile the securely read original candidate bytes for compile-only evidence while separately retaining the transform predicate as BLOCKED. Never treat an untransformed/blocked candidate as an accepted transform and never convert final BLOCKED to PASS.

Do not delete, skip, rename or weaken these or any existing tests.

## 1. Evidence collection after an earlier block

Refactor orchestration so a semantic failure in one predicate does not erase other safely obtainable evidence.

- Each 20/40/60/80/100 phase always records a result.
- If secure source bytes exist, phase 60 records `candidates_compile` even when a phase-40 transform predicate is BLOCKED.
- When a transform is blocked, compile may use the exact secure original source only to prove syntax/no import execution; record candidate_origin=original_due_to_block and keep the transform predicate BLOCKED.
- Independent checks continue only when their own prerequisites are present and safe.
- Skipped evidence must be an explicit BLOCKED object with a bounded reason, never absent.
- Final status remains BLOCKED if any required predicate is missing/non-OK.
- Phase 100 still performs final fingerprints/inventories and evidence emission after earlier blocks whenever safe.

## 2. Robust fail-closed receipt and manifest verification

`verify_receipt` and manifest verification must:

- reject symlink, non-regular and hard-linked receipt/manifest/output;
- securely read with no-follow/lstat/fstat identity checks before/after;
- enforce bounded file size and UTF-8/JSON object structure;
- catch every expected I/O, Unicode and JSON parsing error and return `(False, sanitized_reason)`;
- reject duplicate keys using an object_pairs_hook;
- reject unknown status, malformed phases, unsafe paths, missing fixed predicates, altered hashes and inconsistent PASS/BLOCKED state;
- verify the manifest binds receipt, report, package code, source fingerprints, candidates, diffs and allowed writes;
- never follow symlinks or read outside the resolved run directory;
- never execute/import candidate files.

Malformed evidence is BLOCKED, never an exception and never PASS.

## 3. Canonical read-only SQLite inspection

Implement one canonical SQLite evidence API in `sqlite_ownership.py`, used by `crm_speed_gate_a.py`. No duplicate divergent logic.

Requirements:

- accept only a regular non-symlink database path; reject hard-linked surprise if policy cannot prove identity;
- open with URI `file:<quoted-canonical-path>?mode=ro`, `uri=True`;
- set `PRAGMA query_only=ON`;
- use a short explicit busy timeout suitable for interactive reads;
- execute `PRAGMA quick_check` and require exactly one row whose value is exactly `ok`;
- lock, timeout, malformed DB, I/O error or any exception returns BLOCKED without mutation;
- never run schema migrations, WAL changes, VACUUM, REINDEX, writes or mutable PRAGMA;
- close cursor and connection in every branch before hashing, formatting, publication probe, filesystem work or other slow work.

## 4. Bounded UA-0009 database evidence without PII

Perform bounded schema introspection:

- cap number of tables, columns, candidate tables, rows and serialized evidence bytes;
- identify all possible UA-0009 rows through explicit configured identifier-column rules and exact identifier value `UA-0009`;
- quote identifiers safely after validating them against introspected names;
- materialize selected rows into ordinary immutable Python values while the read-only connection is open;
- close the cursor/connection before canonical serialization and hashing;
- output only table name, identifier-column name, bounded structural row identity/index metadata, column-name set and cryptographic row hashes;
- never output customer names, phones, messages, raw field values, database pages or blobs;
- missing evidence, ambiguous identifier mapping, overflow, duplicate ambiguity, lock or malformed schema is BLOCKED;
- calculate one canonical evidence SHA-256.

Capture this evidence before candidate workload and again after the entire workload. `ua0009_fingerprint_unchanged` is OK only when both complete evidence objects are OK and hashes match.

## 5. One canonical UA-0009 publication probe

`ua0009_publication_check.py` is the only implementation. Every gate/orchestrator adapter delegates to it.

Requirements:

- URL must be present, well-formed HTTPS, without embedded credentials;
- use an injected opener in tests;
- disable redirects; never convert a redirect into a final target request;
- only an actual HTTP 404 or 410 response proves not published;
- 2xx, 3xx, 4xx other than 404/410, 5xx, malformed response, DNS, TLS, timeout, refused connection, proxy error, network status -1 or any exception is BLOCKED;
- return bounded structured status/reason/status_code;
- no real network in tests.

Remove or convert every duplicate publication implementation into a thin delegate to this canonical function.

## 6. Receipt/manifest binding

Extend manifest and receipt evidence with:

- SQLite open mode/query_only/quick_check result;
- bounded UA-0009 before and after evidence hashes;
- explicit PII_EMITTED: NO;
- canonical publication probe result;
- manifest hashes binding these fields;
- final equality predicate;
- any blocker and next safe action.

Never hard-code these predicates to OK.

## Mandatory tests

Create `cloud/crm_speed_optimization/test_task_033_sqlite_ua0009.py`.

Tests must be offline and temporary-directory-only and must prove:

1. The two exact controller regressions above now pass.
2. Malformed/extra-data/duplicate-key/non-UTF8/oversized JSON returns false without raising.
3. Receipt/manifest symlink, hard-link, non-regular path, replacement race and altered hash block.
4. SQLite URI is read-only/query_only with short timeout; quick_check exactly ok passes.
5. Locked, malformed, missing, symlinked and hard-linked DB block without mutation.
6. UA-0009 rows are found across bounded configured tables; output contains hashes/structure but no raw PII.
7. Missing, ambiguous and overflow UA evidence blocks.
8. Connection/cursor are closed before serialization, hashing and publication calls.
9. Before/after equal hashes pass; changed/missing/non-OK evidence blocks.
10. HTTP 404 and 410 pass; 200/3xx/other 4xx/5xx/network error/status -1/malformed URL/non-HTTPS block.
11. `crm_speed_gate_a` and any other adapter delegate to the exact canonical publication function.
12. All historical TASK 031 and TASK 032 tests remain intact and pass.

Controller target:

`python3 -m py_compile cloud/crm_speed_optimization/*.py && python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'`

## Deliverables

Return complete contents for exactly:

- `cloud/crm_speed_optimization/crm_speed_gate_a.py`
- `cloud/crm_speed_optimization/sqlite_ownership.py`
- `cloud/crm_speed_optimization/ua0009_publication_check.py`
- `cloud/crm_speed_optimization/build_manifest.py`
- `cloud/crm_speed_optimization/verify_gate_a.py`
- `cloud/crm_speed_optimization/test_task_033_sqlite_ua0009.py`
- `cloud/crm_speed_optimization/TASK_033_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Do not return unrelated files. Implement complete mutually consistent code, not placeholders or report-only claims. No credentials, PII, production imports or production-write capability.

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

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py

```python
"""
sqlite_ownership.py

Structural (AST-based) transformation and verifier enforcing short SQLite
ownership: SELECT rows are materialized into ordinary immutable values
and the cursor/connection are closed BEFORE any slow-call category
(formatting/hash/sleep/network/filesystem/Telegram I/O).

Only exact, unambiguous anchors are transformed. Anything ambiguous
raises AnchorNotFoundError so the caller can BLOCK and leave the
candidate file unmodified.
"""
from __future__ import annotations

import ast
import os
import sys
from typing import List, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/sqlite_ownership.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/ua0009_publication_check.py

```python
"""
ua0009_publication_check.py

Fail-closed publication check for UA-0009. A missing canonical URL
configuration produces BLOCKED, not SKIPPED -- no environment-variable
omission may silently pass. PRAGMA quick_check must equal exactly 'ok';
a transient lock produces BLOCKED without any mutation.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
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
class PublicationCheckResult:
    ok: bool
    reason: str
    url: Optional[str] = None
    http_status: Optional[int] = None
    quick_check: Optional[str] = None


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


def probe_no_redirect(url: str, timeout: float = 5.0) -> int:
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, method="GET")
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError:
        return -1


def sqlite_quick_check(db_path: str, timeout: float = 2.0) -> str:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
    try:
        conn.execute("PRAGMA query_only=1")
        cur = conn.execute("PRAGMA quick_check")
        row = cur.fetchone()
        cur.close()
        return row[0] if row else "unknown"
    except sqlite3.OperationalError as exc:
        return f"error:{exc}"
    finally:
        conn.close()


def check_ua0009_not_public(db_path: str) -> PublicationCheckResult:
    url = resolve_canonical_url()
    if not url:
        return PublicationCheckResult(
            ok=False,
            reason="BLOCKED: no configured UA0009 canonical URL "
                   f"(set {CONFIG_ENV_VAR} or {CONFIG_FILE_CANDIDATE})",
        )
    status = probe_no_redirect(url)
    not_served = status in (404, 410) or status == -1
    try:
        quick_check = sqlite_quick_check(db_path)
        quick_ok = (quick_check == "ok")
    except Exception as exc:  # pragma: no cover - defensive
        quick_check = f"error:{exc}"
        quick_ok = False

    ok = bool(not_served and quick_ok)
    reason = "ok" if ok else f"BLOCKED: status={status} quick_check={quick_check!r}"
    return PublicationCheckResult(
        ok=ok, reason=reason, url=url, http_status=status, quick_check=quick_check,
    )

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/ua0009_publication_check.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/build_manifest.py

```python
"""Canonical manifest builder for a completed Gate A run directory
(TASK 032). Read-only against the package directory and the run
directory's own receipt/report files. Never follows symlinks, rejects
duplicate/missing/unsafe/non-regular package files, and binds package
code hashes, secure source fingerprints, candidate/diff hashes,
compilation evidence, deterministic-repeat evidence, SQLite/UA-0009/
publication evidence, before/after site inventories, the allowed-write
ledger, and receipt/report hashes into one deterministic manifest.
"""
import os
import sys
import json
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQUIRED_MANIFEST_FIELDS = [
    "package_code_hashes",
    "secure_source_fingerprints",
    "candidate_hashes",
    "diff_sha256",
    "compilation_result",
    "deterministic_repeat",
    "sqlite_evidence",
    "ua0009_evidence",
    "publication_evidence",
    "site_inventory_before",
    "site_inventory_after",
    "allowed_write_ledger",
    "report_sha256",
    "receipt_sha256",
]


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _package_code_hashes(package_dir):
    hashes = {}
    seen = set()
    for name in sorted(os.listdir(package_dir)):
        if not name.endswith(".py"):
            continue
        full = os.path.join(package_dir, name)
        if os.path.islink(full):
            raise ValueError(f"symlink package file rejected: {name}")
        if not os.path.isfile(full):
            continue
        if name in seen:
            raise ValueError(f"duplicate package file: {name}")
        seen.add(name)
        hashes[name] = _sha256_file(full)
    return hashes


def build_manifest(package_dir, run_dir, receipt):
    """receipt must be the exact dict produced by run_gate_a() or
    orchestrate_gate_a() (or an equivalent JSON-loaded structure). Does
    not fabricate any field: if the receipt lacks required evidence, the
    corresponding manifest field is set from whatever the receipt
    actually contains (which may itself be a BLOCKED sub-record)."""
    if not os.path.isdir(run_dir):
        raise ValueError("run_dir must exist")
    if os.path.islink(run_dir):
        raise ValueError("run_dir must not be a symlink")

    evidence = receipt.get("evidence", {}) or {}
    manifest = {
        "package_code_hashes": _package_code_hashes(package_dir),
        "secure_source_fingerprints": evidence.get("inputs_present_and_regular", {}),
        "candidate_hashes": receipt.get("package_hashes", {}),
        "diff_sha256": receipt.get("diff_sha256"),
        "compilation_result": evidence.get("candidates_compile", {}),
        "deterministic_repeat": evidence.get("deterministic_repeat_all_transforms", {}),
        "sqlite_evidence": evidence.get("sqlite_readonly_quickcheck_ok", {}),
        "ua0009_evidence": evidence.get("ua0009_fingerprint_unchanged", {}),
        "publication_evidence": evidence.get("ua0009_not_public", {}),
        "site_inventory_before": receipt.get("site_inventories", {}).get("before", {}),
        "site_inventory_after": receipt.get("site_inventories", {}).get("after", {}),
        "allowed_write_ledger": receipt.get("allowed_write_ledger", []),
        "report_sha256": None,
        "receipt_sha256": None,
    }

    receipt_path = os.path.join(run_dir, "receipt.json")
    report_path = os.path.join(run_dir, "report.md")
    if os.path.isfile(receipt_path) and not os.path.islink(receipt_path):
        manifest["receipt_sha256"] = _sha256_file(receipt_path)
    if os.path.isfile(report_path) and not os.path.islink(report_path):
        manifest["report_sha256"] = _sha256_file(report_path)

    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            raise ValueError(f"manifest missing required field: {field}")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: build_manifest.py <package_dir> <run_dir>")
        sys.exit(2)
    package_dir = sys.argv[1]
    run_dir = sys.argv[2]
    receipt_path = os.path.join(run_dir, "receipt.json")
    receipt = {}
    if os.path.isfile(receipt_path):
        with open(receipt_path, "r") as fh:
            receipt = json.load(fh)
    manifest = build_manifest(package_dir, run_dir, receipt)
    print(json.dumps(manifest, indent=2, default=str))

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/build_manifest.py

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/verify_gate_a.py

```python
"""Canonical, read-only verification of a Gate A receipt (TASK 032).
Enumerates the fixed REQUIRED_PREDICATES set; every absent, malformed, or
non-OK/BLOCKED predicate value blocks. Verifies receipt/manifest hashes
and bound outputs when a manifest is supplied. Never executes Gate A and
never touches production. No pass is derived from hard-coded booleans,
self-referential presence checks, or caller-supplied after snapshots --
only from the evidence already recorded in the receipt itself.
"""
import os
import sys
import json
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crm_speed_gate_a import REQUIRED_PREDICATES  # noqa: E402

VALID_STATUSES = ("GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", "BLOCKED")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_receipt(receipt_path, manifest_path=None):
    if os.path.islink(receipt_path):
        return False, "receipt_is_symlink"
    with open(receipt_path, "r") as fh:
        receipt = json.load(fh)

    if receipt.get("production_write") != "NO":
        return False, "production_write_not_declared_no"
    if receipt.get("status") not in VALID_STATUSES:
        return False, f"unexpected_status:{receipt.get('status')}"

    evidence = receipt.get("evidence", {}) or {}
    for key in REQUIRED_PREDICATES:
        item = evidence.get(key)
        if not isinstance(item, dict) or "status" not in item:
            return False, f"missing_or_malformed_predicate:{key}"
        if item["status"] not in ("OK", "BLOCKED"):
            return False, f"unknown_predicate_status:{key}"

    if receipt.get("status") == "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL":
        if receipt.get("unmet_predicates"):
            return False, "pass_status_with_unmet_predicates"
        for key in REQUIRED_PREDICATES:
            if evidence.get(key, {}).get("status") != "OK":
                return False, f"pass_status_but_predicate_not_ok:{key}"

    if manifest_path is not None:
        if os.path.islink(manifest_path):
            return False, "manifest_is_symlink"
        with open(manifest_path, "r") as fh:
            manifest = json.load(fh)
        run_dir = os.path.dirname(os.path.abspath(receipt_path))
        actual_receipt_hash = _sha256_file(receipt_path)
        if manifest.get("receipt_sha256") != actual_receipt_hash:
            return False, "receipt_hash_mismatch"
        report_path = os.path.join(run_dir, "report.md")
        if os.path.isfile(report_path):
            if os.path.islink(report_path):
                return False, "report_is_symlink"
            actual_report_hash = _sha256_file(report_path)
            if manifest.get("report_sha256") != actual_report_hash:
                return False, "report_hash_mismatch"

    return True, "ok"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: verify_gate_a.py <receipt.json> [manifest.json]")
        sys.exit(2)
    manifest_path = sys.argv[2] if len(sys.argv) > 2 else None
    ok, reason = verify_receipt(sys.argv[1], manifest_path)
    print(json.dumps({"ok": ok, "reason": reason}))
    sys.exit(0 if ok else 1)

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/verify_gate_a.py

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

## BEGIN EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_crm_speed_gate_a.py

```python
"""Offline test suite for CRM-SPEED-001 Gate A package (round 3 corrections).

Run with: python -m unittest test_crm_speed_gate_a -v
from inside cloud/crm_speed_optimization/. This suite never touches
production, /home/Carix, or PythonAnywhere.
"""
import os
import sys
import time
import uuid
import random
import sqlite3
import tempfile
import unittest
import multiprocessing
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import cross_process_lock
import rebuild_queue as rebuild_queue_module
import safe_writer as safe_writer_module
import crm_speed_gate_a as gate_a

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
from crm_speed_gate_a import (
    scan_reachable_call_graph, transform_cars_ui, measure_deterministic_repeat,
    scan_bounded_inventory, check_ua0009_not_public, evaluate_gate_a, run_gate_a,
    DEFAULT_MAX_FILES_PER_ROOT, ADMIN_ROUTE_NAMES,
)


# ---------------------------------------------------------------------------
# Identity assertions (correction D)
# ---------------------------------------------------------------------------

class IdentityTests(unittest.TestCase):
    def test_cross_process_lock_identity(self):
        self.assertIs(cross_process_lock.CrossProcessLock, canonical_modules.CrossProcessLock)
        self.assertIs(gate_a.CrossProcessLock, canonical_modules.CrossProcessLock)

    def test_rebuild_queue_identity(self):
        self.assertIs(rebuild_queue_module.RebuildQueue, canonical_modules.RebuildQueue)
        self.assertIs(gate_a.RebuildQueue, canonical_modules.RebuildQueue)

    def test_safe_writer_identity(self):
        self.assertIs(safe_writer_module.SafeWriter, canonical_modules.SafeWriter)
        self.assertIs(gate_a.SafeWriter, canonical_modules.SafeWriter)

    def test_singleton_guard_identity(self):
        self.assertIs(cross_process_lock.SingletonGuard, canonical_modules.SingletonGuard)
        self.assertIs(gate_a.SingletonGuard, canonical_modules.SingletonGuard)


# ---------------------------------------------------------------------------
# Correction A: dynamic dispatch call-graph scanner + cars_ui transform
# ---------------------------------------------------------------------------

class CarsUiTransformTests(unittest.TestCase):
    def test_dynamic_dispatch_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn(open('x.jpg', 'rb'))\n"
            "def video_gallery(update, context):\n"
            "    pass\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any(r.startswith("dynamic_dispatch_forbidden") for r in result["reasons"]))

    def test_getattr_computed_name_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    name = pick_name()\n"
            "    fn = getattr(update.message, name)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_bound_method_alias_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    sender(open('x.jpg','rb'))\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_dict_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = {'photo': update.message.reply_photo}\n"
            "    handlers['photo']()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_list_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = [update.message.reply_photo]\n"
            "    handlers[0]()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_lambda_media_call_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    f = lambda: update.message.reply_photo(open('x.jpg','rb'))\n"
            "    f()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_return_alias_blocks(self):
        source = (
            "def _pick(update):\n"
            "    return update.message.reply_photo\n"
            "def gallery(update, context):\n"
            "    fn = _pick(update)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_await_alias_blocks(self):
        source = (
            "async def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    await sender()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_nested_helper_media_call_blocks(self):
        source = (
            "def _send(update):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def gallery(update, context):\n"
            "    _send(update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        self.assertIsNotNone(result["candidate"])
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo", result["candidate"])

    def test_ambiguous_unresolved_callable_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    dispatch_table[update.kind](update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_direct_simple_media_call_transforms_cleanly(self):
        source = (
            "def gallery(update, context):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def video_gallery(update, context):\n"
            "    update.message.reply_video(open('x.mp4','rb'))\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo(", result["candidate"])
        self.assertIn("reply_text", result["candidate"])


# ---------------------------------------------------------------------------
# Correction B: deterministic repeat with agreed API
# ---------------------------------------------------------------------------

class DeterministicRepeatTests(unittest.TestCase):
    def test_deterministic_transform_passes(self):
        source = "def gallery(update, context):\n    update.message.reply_photo(1)\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source, args=(), repeats=10)
        self.assertTrue(measurement["deterministic"])
        self.assertEqual(measurement["repeats"], 10)

    def test_deterministic_transform_passes_with_source_kwarg(self):
        source = "def gallery(update, context): pass\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source=source, repeats=10)
        self.assertTrue(measurement["deterministic"])

    def _nondeterministic_random_content(self, source):
        return {"candidate": source + f"# {random.random()}", "status": "OK", "reasons": []}

    def _nondeterministic_time(self, source):
        return {"candidate": source + f"# {time.time()}", "status": "OK", "reasons": []}

    def _nondeterministic_uuid(self, source):
        return {"candidate": source + f"# {uuid.uuid4().hex}", "status": "OK", "reasons": []}

    def _nondeterministic_unordered_set(self, source):
        s = {random.randint(0, 10**9) for _ in range(5)}
        return {"candidate": source + f"# {sorted(s) if random.random() > 2 else list(s)}", "status": "OK", "reasons": []}

    def _nondeterministic_metadata(self, source):
        return {"candidate": source, "status": "OK", "reasons": [f"seen_at:{time.time()}"]}

    def test_nondeterministic_transform_blocks(self):
        source = "x = 1\n"
        variants = [
            self._nondeterministic_random_content,
            self._nondeterministic_time,
            self._nondeterministic_uuid,
            self._nondeterministic_unordered_set,
            self._nondeterministic_metadata,
        ]
        for variant in variants:
            measurement = measure_deterministic_repeat(variant, source, args=(), repeats=10)
            self.assertFalse(measurement["deterministic"], variant.__name__)
            forced_status, unmet = evaluate_gate_a({
                **{k: {"status": "OK"} for k in gate_a.REQUIRED_PREDICATES},
                "deterministic_repeat_all_transforms": {"status": "BLOCKED", "failures": [variant.__name__]},
            })
            self.assertEqual(forced_status, "BLOCKED")
            self.assertIn("deterministic_repeat_all_transforms", unmet)


# ---------------------------------------------------------------------------
# Correction C: real, honest overflow test with production default preserved
# ---------------------------------------------------------------------------

class SiteInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in ["index.html", "katalog.html", "UA-0001.html"]:
            with open(os.path.join(self.tmp.name, name), "w") as fh:
                fh.write("<html></html>")

    def test_production_default_max_is_32(self):
        self.assertEqual(DEFAULT_MAX_FILES_PER_ROOT, 32)

    def test_overflow_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "overflow")
        self.assertEqual(result["matched_count"], 3)

    def test_exact_boundary_n_passes(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=3)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["matched_count"], 3)

    def test_boundary_n_plus_one_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")

    def test_default_production_cap_accepts_up_to_32(self):
        for i in range(2, 10):
            with open(os.path.join(self.tmp.name, f"UA-000{i}.html"), "w") as fh:
                fh.write("<html></html>")
        allowed = list(gate_a.ALLOWED_SITE_NAMES)
        result = scan_bounded_inventory(self.tmp.name, allowed)
        self.assertEqual(result["status"], "OK")
        self.assertLessEqual(result["matched_count"], 32)

    def test_missing_root_blocks(self):
        result = scan_bounded_inventory(os.path.join(self.tmp.name, "nope"), ["index.html"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_symlink_rejected(self):
        target = os.path.join(self.tmp.name, "index.html")
        link = os.path.join(self.tmp.name, "katalog.html")
        os.remove(link)
        os.symlink(target, link)
        result = scan_bounded_inventory(self.tmp.name, ["index.html", "katalog.html"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "symlink_rejected")


# ---------------------------------------------------------------------------
# Publication probe fail-closed behavior
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, code):
        self._code = code

    def getcode(self):
        return self._code


class _FakeOpener:
    def __init__(self, raise_exc=None, response_code=None):
        self.raise_exc = raise_exc
        self.response_code = response_code

    def open(self, req, timeout=5):
        if self.raise_exc is not None:
            raise self.raise_exc
        return _FakeResponse(self.response_code)


class PublicationProbeTests(unittest.TestCase):
    def test_404_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_410_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 410, "gone", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_200_blocks(self):
        opener = _FakeOpener(response_code=200)
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_redirect_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 302, "redir", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_network_error_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.URLError("connection refused"))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_non_https_blocks(self):
        result = check_ua0009_not_public("http://example.com/UA-0009.html")
        self.assertEqual(result["status"], "BLOCKED")

    def test_missing_url_blocks(self):
        result = check_ua0009_not_public("")
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# CrossProcessLock stress test (aggregate >=100 contention attempts)
# ---------------------------------------------------------------------------

def _contender_worker(lock_path, start_barrier, result_queue, hold_event):
    guard = CrossProcessLock(lock_path)
    start_barrier.wait()
    acquired = guard.acquire()
    result_queue.put((os.getpid(), acquired))
    if acquired:
        hold_event.wait(timeout=5)
        guard.release()


class CrossProcessLockStressTests(unittest.TestCase):
    def test_simultaneous_stale_takeover_only_one_wins(self):
        ctx = multiprocessing.get_context("fork") if hasattr(multiprocessing, "get_context") else multiprocessing
        rounds = 25
        contenders_per_round = 4
        for round_idx in range(rounds):
            with tempfile.TemporaryDirectory() as tmp:
                lock_path = os.path.join(tmp, "test.lock")
                with open(lock_path, "w") as fh:
                    fh.write(f"999999|stale|deadtoken|{time.time() - 100000}\n")
                start_barrier = ctx.Barrier(contenders_per_round)
                result_queue = ctx.Queue()
                hold_event = ctx.Event()
                procs = [
                    ctx.Process(target=_contender_worker, args=(lock_path, start_barrier, result_queue, hold_event))
                    for _ in range(contenders_per_round)
                ]
                for p in procs:
                    p.start()
                results = [result_queue.get(timeout=10) for _ in procs]
                hold_event.set()
                for p in procs:
                    p.join(timeout=10)
                winners = [r for r in results if r[1]]
                self.assertEqual(len(winners), 1, f"round {round_idx}: {results}")

    def test_release_then_fresh_contender_can_acquire(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            first = CrossProcessLock(lock_path)
            self.assertTrue(first.acquire())
            first.release()
            second = CrossProcessLock(lock_path)
            self.assertTrue(second.acquire())
            second.release()

    def test_idempotent_release_no_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            lock = CrossProcessLock(lock_path)
            self.assertTrue(lock.acquire())
            lock.release()
            lock.release()

    def test_release_after_directory_removed_does_not_raise(self):
        tmp = tempfile.mkdtemp()
        lock_path = os.path.join(tmp, "test.lock")
        lock = CrossProcessLock(lock_path)
        self.assertTrue(lock.acquire())
        import shutil
        shutil.rmtree(tmp)
        lock.release()


# ---------------------------------------------------------------------------
# RebuildQueue and SafeWriter basic behavior
# ---------------------------------------------------------------------------

class RebuildQueueTests(unittest.TestCase):
    def test_burst_coalesces_to_one_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            q = RebuildQueue(lambda: calls.append(1), os.path.join(tmp, "rebuild.lock"))
            statuses = [q.enqueue() for _ in range(5)]
            self.assertIn("accepted", statuses)
            self.assertGreaterEqual(len(calls), 1)

    def test_requires_bound_callback(self):
        with self.assertRaises(ValueError):
            RebuildQueue(None, "/tmp/whatever.lock")


class SafeWriterTests(unittest.TestCase):
    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            with self.assertRaises(ValueError):
                writer.write_text("../escape.txt", "x")

    def test_writes_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            target = writer.write_text("out.txt", "hello")
            with open(target) as fh:
                self.assertEqual(fh.read(), "hello")


# ---------------------------------------------------------------------------
# Correction E: real synthetic end-to-end Gate A
# ---------------------------------------------------------------------------

CLEAN_CARS_UI = (
    "def gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'photos: {count}')\n"
    "def video_gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'videos: {count}')\n"
    "def diag_photo_show(update, context):\n"
    "    update.message.reply_text('diag photo text')\n"
    "def diag_video_show(update, context):\n"
    "    update.message.reply_text('diag video text')\n"
    "def count_media(update):\n"
    "    return len(update.media)\n"
    "def upload_media(path, data):\n"
    "    with open(path, 'wb') as fh:\n"
    "        fh.write(data)\n"
    "    return True\n"
    "def delete_media(path):\n"
    "    import os as _os\n"
    "    _os.remove(path)\n"
    "    return True\n"
)

CLEAN_USERCUSTOMIZE = "import sys\n\n\ndef _noop():\n    return None\n"

CLEAN_AVTOPEREDACHA = (
    "import sqlite3\n"
    "import time\n"
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)

DB_FUNCTION_SOURCE = (
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)


class EndToEndGateATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.required_input_paths = []
        for name in ["usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
                     "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py"]:
            p = os.path.join(self.tmp.name, name)
            with open(p, "w") as fh:
                fh.write("# fixture\n")
            self.required_input_paths.append(p)

        self.db_path = os.path.join(self.tmp.name, "crm.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()
        self.required_input_paths.append(self.db_path)

        self.backup_archive = os.path.join(self.tmp.name, "backup.tar.gz")
        with open(self.backup_archive, "wb") as fh:
            fh.write(b"fixture-backup-bytes")
        self.backup_sha256 = gate_a._sha256_file(self.backup_archive)

        self.site_root = os.path.join(self.tmp.name, "site")
        os.makedirs(self.site_root)
        with open(os.path.join(self.site_root, "index.html"), "w") as fh:
            fh.write("<html></html>")
        with open(os.path.join(self.site_root, "katalog.html"), "w") as fh:
            fh.write("<html></html>")

        self.run_dir = os.path.join(self.tmp.name, "run")

        fp = {"a": 1}
        self.fixture = {
            "required_inputs": self.required_input_paths,
            "backup_archive": self.backup_archive,
            "backup_archive_sha256": self.backup_sha256,
            "cars_ui_source": CLEAN_CARS_UI,
            "usercustomize_source": CLEAN_USERCUSTOMIZE,
            "avtoperedacha_source": CLEAN_AVTOPEREDACHA,
            "protected_fingerprints_before": fp,
            "protected_fingerprints_after": dict(fp),
            "db_path": self.db_path,
            "ua0009_fingerprint_before": {"h": "same"},
            "ua0009_fingerprint_after": {"h": "same"},
            "ua0009_url": "https://example.com/UA-0009.html",
            "ua0009_opener": _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None)),
            "site_root": self.site_root,
            "allowed_site_names": ["index.html", "katalog.html"],
            "protected_function_names": ["upload_media", "delete_media"],
            "tmp_dir": self.tmp.name,
            "db_function_source": DB_FUNCTION_SOURCE,
            "site_before": {"x": 1},
            "site_after": {"x": 1},
            "run_dir": self.run_dir,
        }

    def test_clean_fixture_reaches_pass_awaiting_approval(self):
        receipt = run_gate_a(self.fixture)
        self.assertEqual(receipt["status"], "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", receipt["unmet_predicates"])
        self.assertEqual(receipt["unmet_predicates"], [])
        self.assertEqual(receipt["production_write"], "NO")
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "receipt.json")))

    def test_backup_hash_mismatch_blocks(self):
        bad = dict(self.fixture)
        bad["backup_archive_sha256"] = "0" * 64
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("backup_verified", receipt["unmet_predicates"])

    def test_protected_fingerprint_change_blocks(self):
        bad = dict(self.fixture)
        bad["protected_fingerprints_after"] = {"a": 2}
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("protected_fingerprints_unchanged", receipt["unmet_predicates"])
        self.assertIn("no_production_write", receipt["unmet_predicates"])

    def test_publication_probe_200_blocks(self):
        bad = dict(self.fixture)
        bad["ua0009_opener"] = _FakeOpener(response_code=200)
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("ua0009_not_public", receipt["unmet_predicates"])

    def test_dynamic_dispatch_in_cars_ui_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
            "def upload_media(path, data): return True\n"
            "def delete_media(path): return True\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("admin_routes_text_only", receipt["unmet_predicates"])

    def test_usercustomize_forbidden_import_blocks(self):
        bad = dict(self.fixture)
        bad["usercustomize_source"] = "import team_bot\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("usercustomize_inert", receipt["unmet_predicates"])

    def test_rebuild_subprocess_blocks(self):
        bad = dict(self.fixture)
        bad["avtoperedacha_source"] = "import subprocess\ndef run():\n    subprocess.Popen(['x'])\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("rebuild_queue_bound_no_process_spawn", receipt["unmet_predicates"])

    def test_slow_work_before_close_blocks(self):
        bad = dict(self.fixture)
        bad["db_function_source"] = (
            "def kolonki_cars(conn):\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    time.sleep(0)\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    return rows\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("db_closed_before_slow_work", receipt["unmet_predicates"])

    def test_site_inventory_overflow_blocks(self):
        bad = dict(self.fixture)
        bad["allowed_site_names"] = ["index.html", "katalog.html"]
        bad["max_files_per_root"] = 1
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("site_inventory_unchanged", receipt["unmet_predicates"])

    def test_media_persistence_function_removed_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = CLEAN_CARS_UI.replace(
            "def delete_media(path):\n    import os as _os\n    _os.remove(path)\n    return True\n", "")
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("media_persistence_unchanged", receipt["unmet_predicates"])

    def test_missing_input_blocks(self):
        bad = dict(self.fixture)
        bad["required_inputs"] = self.required_input_paths + [os.path.join(self.tmp.name, "missing.py")]
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("inputs_present_and_regular", receipt["unmet_predicates"])


if __name__ == "__main__":
    unittest.main()

```

## END EXACT CURRENT SOURCE: cloud/crm_speed_optimization/test_crm_speed_gate_a.py
