#!/usr/bin/env python3
"""Fail-closed, data-only UA0022 forward reconciliation builder.

The builder reads an immutable-main checkout plus two pinned evidence files.
It never contacts a service, edits its inputs, reloads the site, or retries
publication/rollback.  It emits proposed repository-state bytes and a CAS plan.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import pathlib
import re


TASK = "UA-ART-UA0022-PUBLISH-REPAIR-003"
RUN = "35490449348"
REQ_SHA = "334c361c22ebee11fd3d1fb8f8e1cd34178976966bb3011297e05ad51b4902ba"
TXID = "tx-35490449348-334c361c22ebee11"
MAIN = "6e3eb6a68bb65caa34e3ea40c3f386f19d5f14b7"
TX_REL = f"state/transactions/{TASK}.{REQ_SHA}.{RUN}.json"
CLAIM_REL = f"state/claims/{TASK}.{REQ_SHA}.{RUN}.json"
HALT_REL = "state/AUTOPILOT_HALT.json"
BACKUP_REL = f"state/receipts/{TASK}-BACKUP.json"
REQUEST_REL = f"tasks/requests/{TASK}.json"
RECEIPT_REL = f"state/receipts/{TASK}.json"
RECON_REL = f"state/reconciliations/{TASK}.{RUN}.forward-reconciliation.json"
EVIDENCE_REL = f"state/reconciliations/{TASK}.{RUN}.availability-evidence.json"
HISTORY = f"state/halt_history/{TASK}.{RUN}"
HISTORY_HALT_REL = f"{HISTORY}/halt.json"
HISTORY_RECEIPT_REL = f"{HISTORY}/receipt.json"

REPO_INPUTS = {TX_REL, CLAIM_REL, HALT_REL, BACKUP_REL, REQUEST_REL}
ADDITIONS = {RECEIPT_REL, RECON_REL, EVIDENCE_REL, HISTORY_HALT_REL, HISTORY_RECEIPT_REL}
HTTP_KEYS = {"apex_home", "www_home", "catalog", "ua0022_card", "ua0022_diagnostic"}
RUNTIME_KEYS = {"cars_ui.py", "stranica.py", "publish_transaction_guard.py", "publication_fence.py"}
EXPECTED_URLS = {
    "apex_home": "https://www.uaart.com.ua/video/index.html",
    "www_home": "https://www.uaart.com.ua/video/index.html",
    "catalog": "https://www.uaart.com.ua/video/katalog.html",
    "ua0022_card": "https://www.uaart.com.ua/video/UA-0022.html",
    "ua0022_diagnostic": "https://www.uaart.com.ua/video/UA-0022-diag.html",
}
INSTALL_EVIDENCE_PATH = (
    "cloud/task088_v5_acceptance/point4_status_completion_20260920/"
    "UA0022_ACTUAL_INSTALL_RECEIPT_OBSERVED.json"
)
INSTALL_EVIDENCE_BLOB = "cf7d980bf1b21b35614e7149151622b38161963c"
INSTALL_EVIDENCE_COMMIT = "528e64f083d9aacb85f75337cca281c5134d2ab0"
HEALTH_EVIDENCE_PATH = (
    "cloud/emergency_availability_20260920/forward_reconciliation_candidate_v2/"
    "FRESH_HEALTH.json"
)
HEALTH_EVIDENCE_BLOB = "7bb5ee152a6debccc9f0ebb4cac13f2a38d04b2c"
HEALTH_EVIDENCE_COMMIT = "7a306b25b12432a0bf10325102956578fd512553"
SHA_RE = re.compile(r"[0-9a-f]{64}")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


class ReconcileError(RuntimeError):
    pass


def fail(ok: bool, code: str) -> None:
    if not ok:
        raise ReconcileError(code)


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc(value: str) -> dt.datetime:
    fail(isinstance(value, str) and value.endswith("Z"), "TIME_FORMAT")
    parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    fail(parsed.tzinfo is not None, "TIME_TZ")
    return parsed


def stable_json(path: pathlib.Path) -> tuple[bytes, dict]:
    fail(path.is_file() and not path.is_symlink(), "INPUT_NOT_REGULAR:" + str(path))
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    fail((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "INPUT_CHANGED")
    try:
        value = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise ReconcileError("INPUT_JSON:" + str(path)) from exc
    fail(isinstance(value, dict), "INPUT_OBJECT:" + str(path))
    return raw, value


def exact_json(path: pathlib.Path, expected: str) -> tuple[bytes, dict]:
    raw, value = stable_json(path)
    fail(sha(raw) == expected, "INPUT_SHA256:" + str(path))
    return raw, value


def build(root: pathlib.Path, manifest_path: pathlib.Path, install_path: pathlib.Path,
          health_path: pathlib.Path, reconciled_at: str) -> tuple[dict, dict[str, bytes]]:
    reconciled = utc(reconciled_at)
    manifest_raw, manifest = stable_json(manifest_path)
    fail(manifest.get("schema_version") == "UAART-UA0022-FORWARD-INPUT-MANIFEST-2",
         "MANIFEST_SCHEMA")
    fail(manifest.get("main") == MAIN, "MANIFEST_MAIN")
    repo_manifest = manifest.get("repo_inputs", {})
    fail(set(repo_manifest) == REPO_INPUTS, "MANIFEST_REPO_KEYS")
    fail(set(manifest.get("must_not_exist", [])) == ADDITIONS, "MANIFEST_ABSENCE_KEYS")
    external = manifest.get("external", {})
    fail(set(external) == {"install", "health"}, "MANIFEST_EXTERNAL_KEYS")
    install_entry = external["install"]
    health_entry = external["health"]
    fail(install_entry.get("path") == INSTALL_EVIDENCE_PATH, "INSTALL_PROVENANCE_PATH")
    fail(install_entry.get("blob_sha") == INSTALL_EVIDENCE_BLOB, "INSTALL_PROVENANCE_BLOB")
    fail(install_entry.get("source_commit") == INSTALL_EVIDENCE_COMMIT,
         "INSTALL_PROVENANCE_COMMIT")
    fail(health_entry.get("path") == HEALTH_EVIDENCE_PATH, "HEALTH_PROVENANCE_PATH")
    fail(health_entry.get("blob_sha") == HEALTH_EVIDENCE_BLOB, "HEALTH_PROVENANCE_BLOB")
    fail(health_entry.get("source_commit") == HEALTH_EVIDENCE_COMMIT,
         "HEALTH_PROVENANCE_COMMIT")
    for name, entry in external.items():
        fail(SHA_RE.fullmatch(entry.get("sha256", "")) is not None,
             "EXTERNAL_SHA:" + name)
        fail(GIT_SHA_RE.fullmatch(entry.get("blob_sha", "")) is not None,
             "EXTERNAL_BLOB:" + name)
        fail(GIT_SHA_RE.fullmatch(entry.get("source_commit", "")) is not None,
             "EXTERNAL_COMMIT:" + name)

    raw: dict[str, bytes] = {}
    values: dict[str, dict] = {}
    for rel in sorted(REPO_INPUTS):
        entry = repo_manifest[rel]
        fail(SHA_RE.fullmatch(entry.get("sha256", "")) is not None, "MANIFEST_SHA:" + rel)
        raw[rel], values[rel] = exact_json(root / rel, entry["sha256"])
    for rel in ADDITIONS:
        fail(not (root / rel).exists(), "ADDITION_EXISTS:" + rel)

    install_raw, install = exact_json(install_path, install_entry["sha256"])
    health_raw, health = exact_json(health_path, health_entry["sha256"])
    tx = copy.deepcopy(values[TX_REL])
    claim = copy.deepcopy(values[CLAIM_REL])
    halt, backup, request = values[HALT_REL], values[BACKUP_REL], values[REQUEST_REL]

    fail(tx.get("schema_version") == "UA-ART-PRODUCTION-TRANSACTION-2", "TX_SCHEMA")
    fail(tx.get("task_id") == TASK and str(tx.get("run_id")) == RUN, "TX_IDENTITY")
    fail(tx.get("request_sha256") == REQ_SHA and tx.get("transaction_id") == TXID, "TX_BINDING")
    fail(tx.get("status") == "ROLLING_BACK", "TX_STATUS")
    fail(claim.get("task_execution_status") == "BLOCKED_ROOT_CAUSE", "CLAIM_STATUS")
    fail(claim.get("production_transaction_status") == "ROLLING_BACK", "CLAIM_TX_STATUS")
    fail(claim.get("production_transaction_id") == TXID and claim.get("request_sha256") == REQ_SHA,
         "CLAIM_BINDING")
    fail(halt.get("status") == "EMERGENCY_HALT" and halt.get("task_id") == TASK, "HALT_IDENTITY")
    fail(str(halt.get("run_id")) == RUN and halt.get("request_sha256") == REQ_SHA, "HALT_BINDING")
    fail(backup.get("status") == "PASS" and backup.get("backup") == "PASS", "BACKUP_STATUS")
    fail(backup.get("task_id") == TASK and str(backup.get("run_id")) == RUN and
         backup.get("transaction_id") == TXID and backup.get("request_sha256") == REQ_SHA,
         "BACKUP_BINDING")
    fail(request.get("task_id") == TASK and request.get("production_required") is True, "REQUEST_IDENTITY")

    observed_receipt = install.get("receipt", {})
    installer = observed_receipt.get("installer", {})
    crm_resume = observed_receipt.get("crm_resume", {})
    fail(install.get("source") == "AUTHENTICATED_PYTHONANYWHERE_FILE_EDITOR", "INSTALL_SOURCE")
    fail(observed_receipt.get("status") == "PASS" and observed_receipt.get("safe_to_stop") is True,
         "INSTALL_RECEIPT")
    fail(installer.get("status") == "PASS" and installer.get("task_id") == TASK and
         installer.get("target") == "UA-0022", "INSTALL_IDENTITY")
    for key in ("integrity_pass", "post_check_pass", "other_rows_unchanged",
                "protected_pages_unchanged", "target_media_unchanged",
                "target_original_media_unchanged", "ua_ge_prices_unchanged", "publication_pass"):
        fail(installer.get(key) is True, "INSTALL_ASSERTION:" + key)
    fail(crm_resume.get("enabled") is True and crm_resume.get("state") == "Running", "CRM_RESUME")
    runtime = installer.get("source_after_sha256", {})
    fail(set(runtime) == RUNTIME_KEYS, "RUNTIME_KEYSET")
    fail(all(SHA_RE.fullmatch(value or "") for value in runtime.values()), "RUNTIME_SHA")
    install_public = installer.get("public_http_sha256", {})
    fail(set(install_public) == set(EXPECTED_URLS.values()),
         "INSTALL_PUBLIC_KEYSET")
    fail(all(SHA_RE.fullmatch(value or "") for value in install_public.values()), "INSTALL_PUBLIC_SHA")

    fail(health.get("schema_version") == "UAART-UA0022-FRESH-HEALTH-1", "HEALTH_SCHEMA")
    fail(health.get("main") == MAIN and health.get("production_write_performed") is False,
         "HEALTH_SCOPE")
    started = utc(health["started_at"])
    finished = utc(health["finished_at"])
    fail(started <= finished <= reconciled, "HEALTH_TIME_ORDER")
    fail((reconciled - finished).total_seconds() <= 3600, "HEALTH_STALE")
    fail(health.get("status") == "healthy" and health.get("exit_code") == 0, "HEALTH_MONITOR")
    routes = health.get("routes", {})
    fail(set(routes) == HTTP_KEYS, "HEALTH_ROUTE_KEYS")
    for name, item in routes.items():
        fail(item.get("http_status") == 200, "HEALTH_HTTP:" + name)
        fail(SHA_RE.fullmatch(item.get("sha256", "")) is not None, "HEALTH_SHA:" + name)
        fail(item.get("final_url") == EXPECTED_URLS[name], "HEALTH_URL:" + name)
    changed = sorted(name for name in ("ua0022_card", "ua0022_diagnostic")
                     if routes[name]["sha256"] != install_public[EXPECTED_URLS[name]])
    fail(health.get("public_bytes_changed_after_install_observation") == changed,
         "HEALTH_CHANGED_BYTES_BINDING")

    receipt = {
        "schema_version": "UA-ART-MANUAL-FORWARD-RECEIPT-2",
        "task_id": TASK, "run_id": RUN, "request_sha256": REQ_SHA,
        "transaction_id": TXID, "status": "FINISHED", "task_class": "CRITICAL",
        "target_environment": "production", "production_required": True,
        "tests": "PASS", "tests_scope": "HASH_BOUND_INSTALL_POST_CHECK_AND_CURRENT_FIVE_ROUTE_HEALTH",
        "unexpected_changes": 0,
        "unexpected_changes_scope": "INSTALL_EVIDENCE_PROTECTED_PAGES_OTHER_ROWS_MEDIA_AND_UA_GE_VALUES",
        "production": "PASS", "live_verify": "PASS",
        "installation_verify": "PASS", "live_availability": "PASS", "backup": "PASS",
        "rollback": "NOT_PERFORMED", "rollback_ready": True, "backup_available": True,
        "canonical_rollback_execution_ready": False,
        "canonical_rollback_blocker": "AUTOSTART_NONCE_RESERVATION_MISSING / TRANSACTION_LEDGER_INVALID",
        "backup_manifest_sha256": backup["backup_manifest_sha256"],
        "install_evidence_sha256": sha(install_raw),
        "install_evidence_path": INSTALL_EVIDENCE_PATH,
        "install_evidence_blob_sha": INSTALL_EVIDENCE_BLOB,
        "install_evidence_source_commit": INSTALL_EVIDENCE_COMMIT,
        "health_evidence_sha256": sha(health_raw),
        "health_evidence_path": HEALTH_EVIDENCE_PATH,
        "health_evidence_blob_sha": HEALTH_EVIDENCE_BLOB,
        "health_evidence_source_commit": HEALTH_EVIDENCE_COMMIT,
        "persistence": "MANUAL_FORWARD_RECONCILIATION", "reconciled_at": reconciled_at,
        "reconciliation_path": RECON_REL, "availability_evidence_path": EVIDENCE_REL,
    }
    receipt_bytes = canonical(receipt)

    tx.update({"status": "FINISHED", "closed_at": reconciled_at, "reconciliation_path": RECON_REL})
    checks = [{"name": name, "http_status": routes[name]["http_status"], "status": "PASS"}
              for name in sorted(HTTP_KEYS)]
    claim.update({
        "post_health_status": "PASS",
        "post_health": {"status": "PASS", "checked_at": health["finished_at"],
                        "checks": checks, "evidence_path": EVIDENCE_REL},
        "receipt_validation_status": "PASS", "receipt_path": RECEIPT_REL,
        "receipt_sha256": sha(receipt_bytes), "task_execution_status": "FINISHED",
        "production_transaction_status": "FINISHED", "updated_at": reconciled_at,
        "finished_at": reconciled_at, "heartbeat_at": reconciled_at,
        "heartbeat_sequence": int(claim["heartbeat_sequence"]) + 1,
        "reconciliation_path": RECON_REL,
    })

    evidence = {
        "schema_version": "UA-ART-UA0022-AVAILABILITY-EVIDENCE-2",
        "task_id": TASK, "run_id": RUN, "transaction_id": TXID,
        "install_evidence_sha256": sha(install_raw),
        "install_evidence_path": INSTALL_EVIDENCE_PATH,
        "install_evidence_blob_sha": INSTALL_EVIDENCE_BLOB,
        "install_evidence_source_commit": INSTALL_EVIDENCE_COMMIT,
        "health_evidence_sha256": sha(health_raw),
        "health_evidence_path": HEALTH_EVIDENCE_PATH,
        "health_evidence_blob_sha": HEALTH_EVIDENCE_BLOB,
        "health_evidence_source_commit": HEALTH_EVIDENCE_COMMIT,
        "observed_window_utc": {"started_at": health["started_at"], "finished_at": health["finished_at"]},
        "routes": routes, "installed_runtime_sha256": runtime,
        "installation_verify": "PASS", "rollback_performed": False,
        "public_bytes_changed_after_install_observation": health.get("public_bytes_changed_after_install_observation"),
        "production_write_by_reconciliation": False,
    }
    evidence_bytes = canonical(evidence)
    result = {
        "schema_version": "UA-ART-MANUAL-FORWARD-RECONCILIATION-3",
        "task_id": TASK, "run_id": RUN, "request_sha256": REQ_SHA, "transaction_id": TXID,
        "reconciled_at": reconciled_at, "decision": "ACCEPT_HASH_BOUND_INSTALL_AND_CURRENT_AVAILABILITY",
        "transaction_before": "ROLLING_BACK", "transaction_after": "FINISHED",
        "automatic_rollback_retried": False, "rollback_performed": False, "halt_removed": True,
        "scope": "ATOMIC_REPOSITORY_STATE_RECONCILIATION_ONLY",
        "production_runtime_changed": False, "site_reloaded": False, "preview_changed": False,
        "receipt_path": RECEIPT_REL, "receipt_sha256": sha(receipt_bytes),
        "availability_evidence_path": EVIDENCE_REL, "availability_evidence_sha256": sha(evidence_bytes),
        "input_manifest_sha256": sha(manifest_raw), "expected_parent": MAIN,
    }
    result_bytes = canonical(result)
    history_receipt = {**result, "reconciliation_payload_sha256": sha(result_bytes)}
    outputs = {
        TX_REL: canonical(tx), CLAIM_REL: canonical(claim), RECEIPT_REL: receipt_bytes,
        EVIDENCE_REL: evidence_bytes, RECON_REL: result_bytes,
        HISTORY_HALT_REL: raw[HALT_REL], HISTORY_RECEIPT_REL: canonical(history_receipt),
    }
    changes = [
        {"operation": "replace", "path": TX_REL, "expected_sha256": repo_manifest[TX_REL]["sha256"],
         "expected_blob": repo_manifest[TX_REL]["blob_sha"], "content_sha256": sha(outputs[TX_REL])},
        {"operation": "replace", "path": CLAIM_REL, "expected_sha256": repo_manifest[CLAIM_REL]["sha256"],
         "expected_blob": repo_manifest[CLAIM_REL]["blob_sha"], "content_sha256": sha(outputs[CLAIM_REL])},
        {"operation": "delete", "path": HALT_REL, "expected_sha256": repo_manifest[HALT_REL]["sha256"],
         "expected_blob": repo_manifest[HALT_REL]["blob_sha"]},
    ]
    for path in sorted(ADDITIONS):
        changes.append({"operation": "add", "path": path, "must_not_exist": True,
                        "content_sha256": sha(outputs[path])})
    plan = {
        "schema_version": "UA-ART-UA0022-FORWARD-RECONCILIATION-PLAN-2",
        "operation_id": "ua0022-forward-reconcile-v2-20260920T1109Z",
        "task_id": TASK, "run_id": RUN, "transaction_id": TXID,
        "expected_parent": MAIN, "ready": False, "review_required": True,
        "changes": changes, "application_writes": 0, "production_runtime_writes": 0,
        "one_atomic_commit_required": True, "force_allowed": False,
        "github_application_protocol": "create blobs -> one tree from exact parent -> one commit -> non-force ref update; fail if ref moved",
        "next_action": "Independent exact-candidate review, fresh ref/actions/health check, then one non-force exact-parent commit",
    }
    return plan, outputs
