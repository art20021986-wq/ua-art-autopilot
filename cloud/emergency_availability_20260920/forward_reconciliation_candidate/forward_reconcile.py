#!/usr/bin/env python3
"""Build a data-only forward-reconciliation proposal for UA0022 run 35490449348.

The builder never edits its input tree, contacts a service, removes HALT, or
retries publication/rollback.  It emits exact replacement/addition bytes and a
single-commit CAS plan for a separately reviewed writer.
"""
from __future__ import annotations

import argparse
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

INPUT_SHA256 = {
    TX_REL: "04eae89f483139d5d5500a9fceb3c648e7052c24cace2107c698379f3f13a205",
    CLAIM_REL: "f78b74b747d2255fcc89035a5b02565b87002e5e52176da96b797af7149c56b5",
    HALT_REL: "2629bf003f889d1ab47a7745ede754ff1c1405e95bdd114cba0fc4bb44d63cc0",
    BACKUP_REL: "2d5856cf31a1adf0eff7ad83b068ca28fdc6b340cad0096aacc8b3ed16fe065c",
    REQUEST_REL: "d8145cde2812a3c6969fd5bf7dc8abae68dfa4a2856699599810057025e159f1",
    "external/live.json": "7bb50cd3f9f924f19360efc2ad988b3311e31baf5f6304e74fd56ecbde0684e8",
}


class ReconcileError(RuntimeError):
    pass


def fail(condition: bool, code: str) -> None:
    if not condition:
        raise ReconcileError(code)


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_exact(path: pathlib.Path, expected: str) -> tuple[bytes, dict]:
    fail(path.is_file() and not path.is_symlink(), "INPUT_NOT_REGULAR:" + str(path))
    before = path.stat()
    payload = path.read_bytes()
    after = path.stat()
    fail((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "INPUT_CHANGED")
    fail(sha(payload) == expected, "INPUT_SHA256:" + str(path))
    try:
        value = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        raise ReconcileError("INPUT_JSON:" + str(path)) from exc
    fail(isinstance(value, dict), "INPUT_OBJECT:" + str(path))
    return payload, value


def load(root: pathlib.Path, live_path: pathlib.Path) -> tuple[dict, dict[str, bytes]]:
    mapping = {
        TX_REL: root / TX_REL,
        CLAIM_REL: root / CLAIM_REL,
        HALT_REL: root / HALT_REL,
        BACKUP_REL: root / BACKUP_REL,
        REQUEST_REL: root / REQUEST_REL,
        "external/live.json": live_path,
    }
    values: dict[str, dict] = {}
    raw: dict[str, bytes] = {}
    for key, path in mapping.items():
        raw[key], values[key] = read_exact(path, INPUT_SHA256[key])
    return values, raw


def build(root: pathlib.Path, live_path: pathlib.Path, reconciled_at: str) -> tuple[dict, dict[str, bytes]]:
    fail(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", reconciled_at) is not None,
         "RECONCILED_AT")
    dt.datetime.fromisoformat(reconciled_at.replace("Z", "+00:00"))
    values, raw = load(root, live_path)
    tx, claim, halt = (copy.deepcopy(values[x]) for x in (TX_REL, CLAIM_REL, HALT_REL))
    backup, request, live = values[BACKUP_REL], values[REQUEST_REL], values["external/live.json"]

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
    fail(live.get("operation_id") == "uaart-emergency-readback-20260920T0818Z", "LIVE_IDENTITY")
    install = live.get("ua0022_actual_installation", {})
    availability = live.get("live_availability", {})
    fail(install.get("task_id") == TASK and install.get("transaction_id") == TXID, "LIVE_BINDING")
    fail(install.get("install_verify_receipt") == "PASS" and install.get("publisher_result") is True,
         "LIVE_INSTALL")
    fail(install.get("rollback_execution") == "NOT_PERFORMED", "LIVE_ROLLBACK")
    fail(availability.get("availability_outcome") ==
         "RESTORED_OBSERVED_FROM_MANAGED_BROWSER_AND_SERVER", "LIVE_AVAILABILITY")
    fail(all(availability.get("http", {}).get(k) == 200 for k in
             ("apex_home", "www_home", "catalog", "ua0022_card", "ua0022_diagnostic")),
         "LIVE_HTTP")
    fail(all(availability.get("public_local_sha256_matches", {}).values()), "LIVE_BYTES")

    receipt = {
        "schema_version": "UA-ART-MANUAL-FORWARD-RECEIPT-1",
        "task_id": TASK, "run_id": RUN, "request_sha256": REQ_SHA,
        "transaction_id": TXID, "status": "FINISHED", "task_class": "CRITICAL",
        "target_environment": "production", "production_required": True,
        "tests": "PASS", "backup": "PASS", "production": "PASS", "live_verify": "PASS",
        "live_verify_scope": "INSTALLED_RUNTIME_HASHES_AND_CURRENT_PUBLIC_BYTE_MATCH",
        "rollback": "NOT_PERFORMED", "rollback_ready": True,
        "backup_manifest_sha256": backup["backup_manifest_sha256"], "unexpected_changes": 0,
        "persistence": "MANUAL_FORWARD_RECONCILIATION", "reconciled_at": reconciled_at,
        "reconciliation_path": RECON_REL, "availability_evidence_path": EVIDENCE_REL,
    }
    receipt_bytes = canonical(receipt)

    tx["status"] = "FINISHED"
    tx["closed_at"] = reconciled_at
    tx["reconciliation_path"] = RECON_REL

    checks = [
        {"name": "apex_home", "http_status": 200, "status": "PASS"},
        {"name": "www_home", "http_status": 200, "status": "PASS"},
        {"name": "catalog", "http_status": 200, "status": "PASS"},
        {"name": "ua0022_card", "http_status": 200, "status": "PASS"},
        {"name": "ua0022_diagnostic", "http_status": 200, "status": "PASS"},
    ]
    claim.update({
        "post_health_status": "PASS",
        "post_health": {"status": "PASS", "checked_at": availability["connection_monitor"]["finished_at"],
                        "checks": checks, "evidence_path": EVIDENCE_REL},
        "receipt_validation_status": "PASS", "receipt_path": RECEIPT_REL,
        "receipt_sha256": sha(receipt_bytes), "task_execution_status": "FINISHED",
        "production_transaction_status": "FINISHED", "updated_at": reconciled_at,
        "finished_at": reconciled_at, "heartbeat_at": reconciled_at,
        "heartbeat_sequence": int(claim["heartbeat_sequence"]) + 1,
        "reconciliation_path": RECON_REL,
    })

    evidence = {
        "schema_version": "UA-ART-UA0022-AVAILABILITY-EVIDENCE-1",
        "task_id": TASK, "run_id": RUN, "transaction_id": TXID,
        "source_evidence_sha256": INPUT_SHA256["external/live.json"],
        "observed_window_utc": availability["observed_window_utc"],
        "availability_outcome": availability["availability_outcome"],
        "http": availability["http"], "public_local_sha256_matches": availability["public_local_sha256_matches"],
        "installed_runtime_sha256": install["installed_runtime_sha256"],
        "install_verify_receipt": install["install_verify_receipt"],
        "publisher_result": install["publisher_result"], "rollback_performed": False,
        "production_write_by_reconciliation": False,
    }
    evidence_bytes = canonical(evidence)

    result = {
        "schema_version": "UA-ART-MANUAL-FORWARD-RECONCILIATION-2",
        "task_id": TASK, "run_id": RUN, "request_sha256": REQ_SHA, "transaction_id": TXID,
        "reconciled_at": reconciled_at, "decision": "ACCEPT_VERIFIED_SUCCESSFUL_INSTALLATION",
        "transaction_before": "ROLLING_BACK", "transaction_after": "FINISHED",
        "automatic_rollback_retried": False, "rollback_performed": False,
        "halt_removed": True, "scope": "ATOMIC_REPOSITORY_STATE_RECONCILIATION_ONLY",
        "production_runtime_changed": False, "site_reloaded": False, "preview_changed": False,
        "receipt_path": RECEIPT_REL, "receipt_sha256": sha(receipt_bytes),
        "availability_evidence_path": EVIDENCE_REL, "availability_evidence_sha256": sha(evidence_bytes),
        "input_sha256": INPUT_SHA256, "expected_parent": MAIN,
    }
    result_bytes = canonical(result)
    history_receipt = {**result, "reconciliation_payload_sha256": sha(result_bytes)}

    outputs = {
        TX_REL: canonical(tx), CLAIM_REL: canonical(claim), RECEIPT_REL: receipt_bytes,
        EVIDENCE_REL: evidence_bytes, RECON_REL: result_bytes,
        HISTORY_HALT_REL: raw[HALT_REL], HISTORY_RECEIPT_REL: canonical(history_receipt),
    }
    changes = [
        {"operation": "replace", "path": TX_REL, "expected_sha256": INPUT_SHA256[TX_REL],
         "content_sha256": sha(outputs[TX_REL])},
        {"operation": "replace", "path": CLAIM_REL, "expected_sha256": INPUT_SHA256[CLAIM_REL],
         "content_sha256": sha(outputs[CLAIM_REL])},
        {"operation": "delete", "path": HALT_REL, "expected_sha256": INPUT_SHA256[HALT_REL]},
    ]
    for path in (RECEIPT_REL, EVIDENCE_REL, RECON_REL, HISTORY_HALT_REL, HISTORY_RECEIPT_REL):
        changes.append({"operation": "add", "path": path, "must_not_exist": True,
                        "content_sha256": sha(outputs[path])})
    plan = {
        "schema_version": "UA-ART-UA0022-FORWARD-RECONCILIATION-PLAN-1",
        "operation_id": "ua0022-forward-reconcile-prep-20260920T0857Z",
        "task_id": TASK, "run_id": RUN, "transaction_id": TXID,
        "expected_parent": MAIN, "ready": False, "review_required": True,
        "changes": changes, "application_writes": 0, "production_runtime_writes": 0,
        "one_atomic_commit_required": True, "force_allowed": False,
        "next_action": "Independent review, then exact-parent atomic commit and full readback",
    }
    return plan, outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--live-evidence", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--reconciled-at", required=True)
    args = parser.parse_args()
    plan, outputs = build(args.root.resolve(), args.live_evidence.resolve(), args.reconciled_at)
    fail(not args.output.exists(), "OUTPUT_EXISTS")
    args.output.mkdir(parents=True)
    for relative, payload in outputs.items():
        path = args.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    plan["output_sha256"] = {path: sha(payload) for path, payload in sorted(outputs.items())}
    (args.output / "PLAN.json").write_bytes(canonical(plan))
    print(json.dumps({"status": "PLAN_READY_FOR_INDEPENDENT_REVIEW", "files": len(outputs),
                      "plan_sha256": sha(canonical(plan))}, sort_keys=True))


if __name__ == "__main__":
    main()
