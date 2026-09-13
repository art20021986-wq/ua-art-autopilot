"""Prepare an explicit, side-effect-free bootstrap entrypoint; never install."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from .bootstrap import RUNTIME_PINS, read_regular

ENTRYPOINT = '''"""Called by the reviewed controller after actual verified runtime handoff."""
from spec_rebuild10.bootstrap import (CrmRows, ExactPlan, PublicReadback,
    WorkerService, LockedLifecycle, attach_public_sync, configure)

def install_runtime(controller):
    # No token, mutable environment flag or receipt's own PASS grants authority.
    rows = CrmRows(controller.crm_database)
    plan = ExactPlan(controller.runtime_plan_path, controller.runtime_plan_sha256,
        authenticate=controller.authenticate_current_owner_route,
        rows=rows, store_path=controller.spec_database)
    readback = PublicReadback(plan, controller.spec_database,
        transport=controller.approved_https_readback)
    worker = WorkerService(controller.spec_database, rows,
        controller.provisioned_collectors, controller.runtime_handoff_receipt,
        controller.verify_runtime_handoff, register=controller.register_existing_supervisor)
    lifecycle = LockedLifecycle(root=controller.application_root, rows=rows,
        plan=plan, readback=readback, lifecycle=controller.loaded_card_lifecycle,
        guard=controller.loaded_publish_transaction_guard,
        publisher=controller.loaded_publikaciya, ledger_path=controller.operation_ledger)
    attach_public_sync(worker, lifecycle, controller.spec_sync_outbox,
        authorize_sync=controller.authenticate_automatic_spec_sync,
        transport=controller.approved_https_readback)
    return configure(controller.spec_database, rows, plan, readback, worker,
        execute_lifecycle=lifecycle)
'''


def prepare(source_dir, output_dir):
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("NEW_PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    for name, expected in RUNTIME_PINS.items():
        raw = read_regular(source_dir / name)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("UNREVIEWED_RUNTIME_SOURCE:" + name)
        compile(raw, name, "exec")
    compile(ENTRYPOINT, "spec_rebuild10_bootstrap.py", "exec")
    output_dir.mkdir(mode=0o700, parents=True)
    target = output_dir / "spec_rebuild10_bootstrap.py"
    target.write_text(ENTRYPOINT, encoding="utf-8")
    target.chmod(0o600)
    report = {"status": "PREPARED_NOT_LOADED", "input_source_pins": RUNTIME_PINS,
        "entrypoint_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "imports_executed": False, "production_changed": False,
        "controller_runtime_authority": "REQUIRED_NOT_MANUFACTURED",
        "automatic_first_publication": False}
    (output_dir / "bootstrap-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_dir, args.output_dir), indent=2))
