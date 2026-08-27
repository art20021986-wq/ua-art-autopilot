# TASK 034 — CRM-SPEED-001 phase D: standalone evidence modules, compile-clean

## Authority and immutable safety boundary

Recover safely from TASK 033, which was rejected before commit because generated build_manifest.py had a SyntaxError. Implement only the four standalone evidence modules and their focused offline tests. Integration into the central orchestrator is intentionally deferred to TASK 035.

Work only under `cloud/`. Do not execute Gate A. Do not access PythonAnywhere, /home/Carix, real URLs or network. Do not modify Production, CRM, crm.db, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, or UA-0009. Never publish UA-0009. Do not modify `tasks/`.

Every status/report:

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

Successful phase status: READY_FOR_CONTROLLER_REVIEW_PHASE_D. Never READY_FOR_GATE_A.

## Mandatory module 1: sqlite_ownership.py

Implement a canonical standard-library-only read-only evidence API.

- Validate database path with lstat/fstat: regular, non-symlink, stable identity; fail closed on hard-link surprise.
- Open only with quoted canonical URI `file:<path>?mode=ro`, `uri=True`, short timeout.
- Enable `PRAGMA query_only=ON`; record its confirmed value.
- Run `PRAGMA quick_check`; require exactly one value exactly `ok`.
- No migrations, write transactions, WAL changes, VACUUM, REINDEX or mutable PRAGMA.
- Bounded schema introspection: explicit maximum tables, columns, rows and serialized bytes.
- Use configured exact identifier-column rules to select exact `UA-0009`.
- Safely quote only identifiers confirmed by introspection.
- Materialize rows into immutable values, close cursor/connection, then serialize/hash.
- Output only structural table/column identifiers, bounded row indexes/identity hashes and SHA-256. Never output raw field values, names, phones, messages, blobs or database pages.
- Return structured BLOCKED for missing/locked/malformed/ambiguous/overflow/identity-change conditions; never raise expected operational errors.
- Expose a pure comparison helper for before/after evidence; OK only when both complete evidence objects are OK and hashes match.
- Preserve existing public transform_short_ownership/check interfaces unless stricter fail-closed behavior requires a documented compatibility adapter.

## Mandatory module 2: ua0009_publication_check.py

This is the single canonical no-redirect publication probe.

- Require a valid HTTPS URL with no embedded credentials.
- Accept an injected opener; tests never use network.
- Never follow redirects.
- Only actual HTTP 404 or 410 passes.
- 2xx, 3xx, other 4xx, 5xx, DNS/TLS/timeout/refused/proxy/network status -1, malformed response or exception all BLOCK.
- Return bounded structured status/reason/status_code.
- Preserve existing public function names through thin adapters, never duplicate logic.

## Mandatory module 3: build_manifest.py

Rewrite as syntactically simple, compile-clean deterministic manifest builder.

- Use only explicit data arguments/run directory; no production access.
- Reject unsafe paths, symlinks, non-regular/hard-linked files, duplicate logical paths and files outside the resolved run directory.
- Securely hash package code, source fingerprints, candidates, diffs, reports, receipt-relevant outputs and allowed-write ledger.
- Bind SQLite quick_check/query_only/open-mode evidence, UA-0009 before/after hashes, PII_EMITTED:NO, and canonical publication result.
- Deterministic sorted JSON-serializable output.
- No self-referential manifest hash cycle.
- Keep syntax straightforward and run py_compile mentally before returning.

## Mandatory module 4: verify_gate_a.py

Implement bounded fail-closed verification.

- Secure no-follow reads; reject symlink, non-regular, hard-linked, replaced, oversized or outside-run files.
- Catch OSError, UnicodeError, JSONDecodeError, ValueError, TypeError and expected failures; return `(False, sanitized_reason)`, never raise.
- Reject duplicate JSON keys.
- Require JSON objects and bounded structures.
- Verify fixed required predicates, phase structure/status, PASS/BLOCKED consistency, production_write NO, PII_EMITTED NO, and manifest hashes for all bound outputs.
- Malformed/extra-data/non-UTF8/oversized/tampered/missing evidence blocks.
- Never import or execute candidates.

## Mandatory focused tests

Create `cloud/crm_speed_optimization/test_task_034_evidence_modules.py` proving:

1. Every delivered Python module compiles.
2. Read-only SQLite quick_check exactly ok and query_only confirmed.
3. Locked/malformed/missing/symlink/hard-link DB blocks with identical bytes before/after.
4. Bounded UA-0009 evidence contains structural hashes but no seeded PII strings.
5. Missing/ambiguous/overflow/evidence-change blocks.
6. Cursor and connection close before hashing/formatting/probe hook.
7. HTTP 404/410 pass; 200/3xx/other 4xx/5xx/status -1/network/malformed URL/non-HTTPS block.
8. Malformed/extra-data/duplicate-key/non-UTF8/oversized receipt and manifest return false without raising.
9. Symlink/hard-link/non-regular/replacement race/altered output hash blocks.
10. Deterministic manifest generation from identical inputs is byte-equivalent after canonical JSON serialization.
11. Existing public names remain import-compatible.

All tests are offline, deterministic and temporary-directory-only.

Controller target:

`python3 -m py_compile cloud/crm_speed_optimization/*.py && python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'`

## Deliverables

Return complete contents for exactly:

- `cloud/crm_speed_optimization/sqlite_ownership.py`
- `cloud/crm_speed_optimization/ua0009_publication_check.py`
- `cloud/crm_speed_optimization/build_manifest.py`
- `cloud/crm_speed_optimization/verify_gate_a.py`
- `cloud/crm_speed_optimization/test_task_034_evidence_modules.py`
- `cloud/crm_speed_optimization/TASK_034_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

Do not return crm_speed_gate_a.py or unrelated files in this phase. No placeholders, TODO-only code, credentials, PII, production imports or production-write capability. Every Python file must compile before response.

## Exact current source snapshots


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
