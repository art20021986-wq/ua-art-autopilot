#!/usr/bin/env python3
"""Run the offline planner and real Git proof on a disposable input copy."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import tempfile

import controller
from git_rehearsal import GitRehearsal


def run(root, inventory, queue):
    plan = controller.prepare_plan(root, inventory, queue)
    original = controller.inspect_inputs(root, inventory)
    with tempfile.TemporaryDirectory(prefix='uaart-recovery-local-proof-') as temporary:
        fixture = GitRehearsal.create(original, Path(temporary)/'owned-fixture')
        local_plan = fixture.make_plan(plan['code_hashes']['controller.py'], plan['base_commit'])
        simulated_approval = fixture.rehearsal_approval(local_plan)
        prepared = fixture.prepare(local_plan, simulated_approval, plan['code_hashes']['controller.py'])
        before = fixture.files()
        applied = fixture.commit(prepared)
        after = fixture.files()
        repeated = fixture.commit(prepared)
        expected = dict(original)
        expected.pop(controller.HALT)
        expected[controller.ARCHIVE] = original[controller.HALT]
        expected[controller.RECEIPT] = prepared.receipt_bytes
        controller.require(before == original and after == expected, 'REHEARSAL_FILE_SET_MISMATCH')
        controller.require(repeated['status'] == 'ALREADY_APPLIED'
                           and repeated['ref_writes_this_call'] == 0, 'REHEARSAL_REPLAY_FAILED')
    controller.require(controller.inspect_inputs(root, inventory) == original, 'SOURCE_CHANGED_AFTER_REHEARSAL')
    return {
        'schema_version': 'UA-ART-RECOVERY-SNAPSHOT-REHEARSAL-1',
        'task_id': controller.TASK, 'status': 'PASS_LOCAL_REHEARSAL_ONLY',
        'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'production_touched': False, 'execution_ready': False,
        'execution_blockers': plan['execution_blockers'],
        'owner_execution_authorization_proven': False,
        'authorization_kind': 'LOCAL_REHEARSAL_ONLY',
        'source_commit': plan['base_commit'], 'source_tree': plan['base_tree'],
        'source_file_count': len(original), 'source_files_unchanged': True,
        'source_halt_sha256': controller.sha(original[controller.HALT]),
        'source_halt_still_present': True,
        'preserved_fixture_file_count': len(original) - 1,
        'code_hashes': {**plan['code_hashes'],
                        'rehearse_snapshot.py': controller.sha(controller.read(Path(__file__)))},
        'offline_controller_plan_sha256': plan['plan_sha256'],
        'local_model_plan_sha256': local_plan['plan_sha256'],
        'plan_relationship': 'Separate local model; does not authorize execution of the offline controller plan',
        'offline_controller_plan': plan,
        'local_git_applied': applied, 'local_git_replayed': repeated,
        'temporary_fixture_removed': True, 'overall_specification_gate_b': 'NOT_EVALUATED',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.root, controller.json_object(controller.read(args.inventory)),
                 controller.json_object(controller.read(args.queue)))
    controller.write_plan(report, args.root, args.output)
    print(report['status'] + '; source HALT preserved; production execution NOT_READY')


if __name__ == '__main__':
    main()
