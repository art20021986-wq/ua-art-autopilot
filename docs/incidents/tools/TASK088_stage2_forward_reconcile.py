#!/usr/bin/env python3
"""One-shot factual reconciliation for run 34734575941.

This changes repository state only. It never contacts PythonAnywhere, changes
CRM data, restarts a process, or retries the consumed rollback.
"""
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent
TASK = "TASK088-GE-PRICE-CRM-STAGE2-INSTALL"
RUN = "34734575941"
REQ_SHA = "f9cf3ff6cfaba7e1f785c1520a668590cc8f7577a798237c83fd8fc35858b29e"
TXID = "tx-34734575941-f9cf3ff6cfaba7e1"
MANIFEST_SHA = "dbd31f0675c792f9e4ebf3c2f6b7f82d1121946ddc4454d3401955bebe1ceb46"
BACKUP_SHA = "c7fec58b1b43d076e866f78f4ac1f6a1377cc04b114b3767f21a2e1a426562bf"
STAMP = "2026-09-13T05:26:23Z"
EVIDENCE_REL = "state/reconciliations/TASK088-GE-PRICE-CRM-STAGE2-INSTALL.34734575941.observed-installation.evidence.json"
RESULT_REL = "state/reconciliations/TASK088-GE-PRICE-CRM-STAGE2-INSTALL.34734575941.forward-reconciliation.json"
TX_REL = f"state/transactions/{TASK}.{REQ_SHA}.{RUN}.json"
CLAIM_REL = f"state/claims/{TASK}.{REQ_SHA}.{RUN}.json"
RECEIPT_REL = f"state/receipts/{TASK}.json"
HALT_REL = "state/AUTOPILOT_HALT.json"
HISTORY = f"state/halt_history/{TASK}.{RUN}"


def read(relative):
    return json.loads((ROOT / relative).read_text())


def write(relative, value):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def digest(relative):
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


halt, tx, claim, evidence = map(read, (HALT_REL, TX_REL, CLAIM_REL, EVIDENCE_REL))
assert halt == evidence["observed_state"]["halt"]
assert tx == evidence["observed_state"]["transaction"]
assert tx["status"] == "ROLLING_BACK" and claim["production_transaction_status"] == "ROLLING_BACK"
assert claim["task_execution_status"] == "BLOCKED_ROOT_CAUSE"
assert evidence["remote_verify_observation"]["status"] == "INSTALLATION_VERIFIED"
assert evidence["remote_verify_observation"]["source_installed"] is True
assert evidence["remote_verify_observation"]["database_unchanged"] is True
assert evidence["remote_verify_observation"]["site_write"] is False
assert evidence["remote_verify_observation"]["live_price_writes"] is False
assert evidence["live_source_observation"]["matches_approved_candidate"] is True

receipt = {
    "task_id": TASK, "parent_task_id": "TASK088-GE-PRICE-CRM-STAGE2",
    "run_id": RUN, "request_sha256": REQ_SHA, "transaction_id": TXID,
    "manifest_sha256": MANIFEST_SHA, "contract_id": "UA-ART-CRITICAL-ADAPTER-V1.0",
    "status": "FINISHED", "task_class": "CRITICAL", "target_environment": "production",
    "production_required": True, "tests": "PASS",
    "tests_scope": "INSTALLATION_AND_SOURCE_DB_READONLY_VERIFY", "backup": "PASS",
    "production": "PASS", "live_verify": "PASS",
    "live_verify_scope": "INSTALLATION_AND_SOURCE_DB_READONLY_VERIFY",
    "rollback": "PASS", "rollback_scope": "BACKUP_AND_RESTORE_READINESS_VERIFIED",
    "rollback_ready": True, "backup_manifest_sha256": BACKUP_SHA,
    "unexpected_changes": 0, "protected_files_unchanged": True, "crm_unchanged": True,
    "crm_unchanged_scope": "DATABASE_SCHEMA_AND_VEHICLE_VALUES_EXCLUDING_APPROVED_UI_SOURCE_REPLACEMENT",
    "stage2_acceptance": "PENDING_TELEGRAM_CHECKS", "telegram_ui": "NOT_PERFORMED",
    "bot_restart": "NOT_PERFORMED", "code_activation": "PENDING_PROCESS_VERIFICATION",
    "stage3_allowed": False, "finished_at": "2026-09-13T03:16:31.774779Z",
    "persistence": "MANUAL_FORWARD_RECONCILIATION",
    "reconciled_at": STAMP, "reconciliation_evidence_path": EVIDENCE_REL,
}
write(RECEIPT_REL, receipt)
receipt_sha = digest(RECEIPT_REL)

tx["status"] = "FINISHED"
tx["closed_at"] = STAMP
write(TX_REL, tx)

claim.update({
    "post_health_status": "PASS",
    "post_health": {"status": "PASS", "checked_at": STAMP,
                    "checks": [{"url": "https://www.uaart.com.ua/", "http_status": 200,
                                "final_url": "https://www.uaart.com.ua/video/index.html", "status": "PASS"}]},
    "receipt_validation_status": "PASS", "receipt_path": RECEIPT_REL,
    "receipt_sha256": receipt_sha, "task_execution_status": "FINISHED",
    "production_transaction_status": "FINISHED", "updated_at": STAMP,
    "finished_at": STAMP, "heartbeat_at": STAMP,
    "heartbeat_sequence": int(claim["heartbeat_sequence"]) + 1,
    "reconciliation_path": RESULT_REL,
})
write(CLAIM_REL, claim)

history_halt = f"{HISTORY}/halt.json"
history_receipt = f"{HISTORY}/receipt.json"
write(history_halt, halt)

result = {
    "schema_version": "UA-ART-MANUAL-FORWARD-RECONCILIATION-1",
    "task_id": TASK, "run_id": RUN, "request_sha256": REQ_SHA,
    "transaction_id": TXID, "reconciled_at": STAMP,
    "owner_instruction": "Remove the unfinished emergency transaction block, complete Stage 2, then proceed to Stage 3.",
    "decision": "ACCEPT_VERIFIED_INSTALLED_SOURCE",
    "automatic_rollback_retried": False, "rollback_performed": False,
    "source_installed": True, "installed_sha256": evidence["live_source_observation"]["sha256"],
    "database_unchanged_at_install_verify": True, "site_write_during_install": False,
    "transaction_before": "ROLLING_BACK", "transaction_after": "FINISHED",
    "install_receipt_path": RECEIPT_REL, "install_receipt_sha256": receipt_sha,
    "incident_evidence_path": EVIDENCE_REL, "archived_halt_path": history_halt,
    "halt_removed": True, "autopilot_mode": "AUTOMATIC",
    "scope": "REPOSITORY_STATE_RECONCILIATION_ONLY",
    "bot_activation": "PENDING_SEPARATE_VERIFICATION",
    "parent_stage2_acceptance": "PENDING_TELEGRAM_CHECKS",
    "stage3_allowed": False,
}
write(RESULT_REL, result)
result["reconciliation_sha256"] = digest(RESULT_REL)
write(history_receipt, result)

(ROOT / HALT_REL).unlink()

assert not (ROOT / HALT_REL).exists()
assert read(TX_REL)["status"] == "FINISHED"
assert read(CLAIM_REL)["task_execution_status"] == "FINISHED"
assert read(CLAIM_REL)["production_transaction_status"] == "FINISHED"
assert read(RECEIPT_REL)["status"] == "FINISHED"
print(json.dumps({"status": "RECONCILED", "receipt_sha256": receipt_sha,
                  "halt_removed": True, "rollback_retried": False}, sort_keys=True))
