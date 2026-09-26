"""Validate one already completed, immutable source transition.

This is historical continuity, never permission to write, retry an old task, or
mint a current Gate. The caller must still prove fresh live source/inventory,
current control state, all writer fences, backup, Preview and new authorization.
The original Stage 2 receipt is never changed or replaced by this evidence.
"""
import hashlib
import json
import re

SOURCE_SUCCESSOR_BINDING = {
    "contract": "TASK088-CANONICAL-SOURCE-SUCCESSOR-1",
    "file": "source_successor_20260920.json",
    "sha256": "3c8fe00c8f0ca37bd98d159f7c5acc8eb3bed5ebbd3f10d9af59841a286fd63d",
    "canonical_commit": "d6bb157288e3a3ea19ddc5d6f11a4c449b9b01eb",
}
TASK = "UA-ART-UA0022-PUBLISH-REPAIR-003"
RUN = "35490449348"
REQUEST_SHA = "334c361c22ebee11fd3d1fb8f8e1cd34178976966bb3011297e05ad51b4902ba"
TX = "tx-35490449348-334c361c22ebee11"
PREDECESSOR = "4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde"
SUCCESSOR = "d9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837"
STAGE2_PATH = "state/receipts/TASK088-GE-PRICE-CRM-STAGE2.json"
INSTALL_PATH = "cloud/task088_v5_acceptance/point4_status_completion_20260920/UA0022_ACTUAL_INSTALL_RECEIPT_OBSERVED.json"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError("SOURCE_SUCCESSOR_" + message)


def validate_source_successor(stage2, current_sha256, raw):
    """Reject all unreviewed histories; validate this exact accepted transition."""
    _require(type(raw) is bytes and _sha(raw) == SOURCE_SUCCESSOR_BINDING["sha256"], "EXACT_REVIEWED_CHAIN_REQUIRED")
    chain = json.loads(raw)
    _validate_chain(stage2, current_sha256, chain)
    return dict(SOURCE_SUCCESSOR_BINDING)


def _validate_chain(stage2, current_sha256, chain):
    """Semantic defense in depth after immutable reviewed artifact admission."""
    _require(chain.get("source_commit") == SOURCE_SUCCESSOR_BINDING["canonical_commit"], "CANONICAL_COMMIT_MISMATCH")
    entries = chain.get("artifacts", {})
    records, raw = {}, {}
    for path, entry in entries.items():
        data = entry["raw"].encode("utf-8")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        _require(entry["sha256"] == _sha(data) and entry["git_blob"] == blob, "ARTIFACT_HASH_MISMATCH")
        records[path], raw[path] = json.loads(data), data
    def record(path):
        _require(path in records, "MISSING_ARTIFACT:" + path)
        return records[path]
    def bound(holder, key, path):
        record(path)
        # The existing critical adapter hashes manifests as canonical JSON;
        # request/gate/approval/receipt links use their original file bytes.
        digest = (_sha((json.dumps(records[path], ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")) + "\n").encode())
                  if path.startswith("tasks/manifests/") else _sha(raw[path]))
        _require(holder.get(key) == digest, "BOUND_HASH_MISMATCH:" + key)
    accepted = record(STAGE2_PATH)
    _require(stage2 == accepted, "ORIGINAL_STAGE2_RECEIPT_REQUIRED")
    _require(accepted.get("task_id") == "TASK088-GE-PRICE-CRM-STAGE2"
             and accepted.get("status") == "FINISHED"
             and accepted.get("stage1_prerequisite") == "PASS"
             and accepted.get("stage2_status") == "PASS"
             and accepted.get("stage3_allowed") is True
             and accepted.get("independent_price_fields") == "PASS"
             and accepted.get("original_values_restored") is True
             and accepted.get("installed_source_sha256") == PREDECESSOR, "ACCEPTED_PREDECESSOR_REQUIRED")
    _require(current_sha256 == SUCCESSOR and re.fullmatch(r"[0-9a-f]{64}", current_sha256), "CURRENT_SOURCE_DRIFT")
    request_path = "tasks/requests/" + TASK + ".json"
    manifest_path = "tasks/manifests/" + TASK + ".json"
    gate_path = "tasks/gates/" + TASK + ".json"
    owner_path = "tasks/approvals/" + TASK + ".production.json"
    receipt_path = "state/receipts/" + TASK + ".json"
    backup_path = "state/receipts/" + TASK + "-BACKUP.json"
    transaction_path = "state/transactions/" + TASK + "." + REQUEST_SHA + "." + RUN + ".json"
    reconciliation_path = "state/reconciliations/" + TASK + "." + RUN + ".forward-reconciliation.json"
    availability_path = "state/reconciliations/" + TASK + "." + RUN + ".availability-evidence.json"
    request, manifest, gate, owner, receipt, backup, transaction, reconciliation, availability = (
        record(p) for p in (request_path, manifest_path, gate_path, owner_path, receipt_path,
                           backup_path, transaction_path, reconciliation_path, availability_path))
    _require(_sha(raw[request_path]) == REQUEST_SHA, "REQUEST_IDENTITY_MISMATCH")
    for obj in (request, manifest, gate, owner, receipt, backup, transaction, reconciliation, availability):
        _require(obj.get("task_id") == TASK, "TASK_IDENTITY_MISMATCH")
    for obj in (receipt, backup, transaction, reconciliation, availability):
        _require(obj.get("run_id") == RUN and obj.get("transaction_id") == TX, "TRANSACTION_IDENTITY_MISMATCH")
    for obj in (receipt, backup, transaction, reconciliation):
        _require(obj.get("request_sha256") == REQUEST_SHA, "REQUEST_BINDING_MISMATCH")
    critical = request.get("critical", {})
    for key, path in (("manifest_sha256", manifest_path), ("gate_a_sha256", gate_path), ("owner_approval_sha256", owner_path)):
        bound(critical, key, path)
    for obj in (gate, owner, backup):
        bound(obj, "manifest_sha256", manifest_path)
    bound(owner, "gate_a_sha256", gate_path)
    _require(gate.get("status") == "PASS" and gate.get("tests") == "PASS"
             and gate.get("unexpected_changes") == 0 and critical.get("gate_b_authorized") is True
             and owner.get("owner_authorized") is True and owner.get("production_allowed") is True
             and owner.get("authorized_environment") == "production", "HISTORICAL_AUTHORIZATION_REQUIRED")
    subject = json.loads(raw[request_path])
    subject["critical"]["owner_approval_sha256"] = "0" * 64
    subject_raw = (json.dumps(subject, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _require(owner.get("request_subject_sha256") == _sha(subject_raw), "OWNER_SUBJECT_MISMATCH")
    operations = [v for v in manifest.get("operations", []) if v.get("path") == "production/runtime/cars_ui.py"]
    _require(len(operations) == 1 and operations[0] == {
        "action": "replace", "path": "production/runtime/cars_ui.py",
        "expected_before_sha256": PREDECESSOR, "expected_after_sha256": SUCCESSOR}, "BEFORE_AFTER_CHAIN_REQUIRED")
    _require(manifest.get("deployment", {}).get("source_sha256", {}).get("cars_ui.py") == PREDECESSOR
             and gate.get("protected_snapshot", {}).get("live_source_sha256", {}).get("cars_ui.py") == PREDECESSOR,
             "APPROVED_BEFORE_IMAGE_MISMATCH")
    _require(transaction.get("status") == "FINISHED" and receipt.get("status") == "FINISHED"
             and receipt.get("production") == "PASS" and receipt.get("installation_verify") == "PASS"
             and receipt.get("live_verify") == "PASS" and receipt.get("unexpected_changes") == 0
             and receipt.get("rollback") == "NOT_PERFORMED", "ACCEPTED_TERMINAL_OUTCOME_REQUIRED")
    _require(receipt.get("reconciliation_path") == reconciliation_path
             and transaction.get("reconciliation_path") == reconciliation_path
             and reconciliation.get("transaction_after") == "FINISHED"
             and reconciliation.get("transaction_before") == "ROLLING_BACK"
             and reconciliation.get("rollback_performed") is False
             and reconciliation.get("halt_removed") is True
             and reconciliation.get("decision") == "ACCEPT_HASH_BOUND_INSTALL_AND_CURRENT_AVAILABILITY",
             "FORWARD_RECONCILIATION_REQUIRED")
    bound(reconciliation, "receipt_sha256", receipt_path)
    bound(reconciliation, "availability_evidence_sha256", availability_path)
    _require(availability.get("rollback_performed") is False
             and availability.get("installed_runtime_sha256", {}).get("cars_ui.py") == SUCCESSOR,
             "CANONICAL_INSTALLED_SOURCE_REQUIRED")
    install = record(INSTALL_PATH)
    for obj in (receipt, availability):
        _require(obj.get("install_evidence_path") == INSTALL_PATH, "INSTALL_EVIDENCE_PATH_MISMATCH")
        bound(obj, "install_evidence_sha256", INSTALL_PATH)
        _require(obj.get("install_evidence_blob_sha") == entries[INSTALL_PATH]["git_blob"], "INSTALL_GIT_BLOB_MISMATCH")
    installed = install.get("receipt", {}).get("installer", {})
    _require(install.get("source") == "AUTHENTICATED_PYTHONANYWHERE_FILE_EDITOR"
             and install.get("receipt", {}).get("status") == "PASS"
             and installed.get("task_id") == TASK and installed.get("status") == "PASS"
             and installed.get("source_after_sha256", {}).get("cars_ui.py") == SUCCESSOR
             and all(installed.get(k) is True for k in ("integrity_pass", "post_check_pass", "other_rows_unchanged", "ua_ge_prices_unchanged", "protected_pages_unchanged")),
             "ACTUAL_INSTALL_EVIDENCE_REQUIRED")
    bound(transaction, "backup_receipt_sha256", backup_path)
    _require(backup.get("status") == "PASS" and backup.get("backup") == "PASS"
             and len({obj.get("backup_manifest_sha256") for obj in (backup, transaction, receipt, installed)}) == 1
             and re.fullmatch(r"[0-9a-f]{64}", backup.get("backup_manifest_sha256", "")), "BACKUP_BINDING_MISMATCH")
