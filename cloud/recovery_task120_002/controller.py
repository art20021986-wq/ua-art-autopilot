#!/usr/bin/env python3
"""Inert TASK120 recovery planner. No network, application import or live apply.

The existing pinned control-plane validator is used only for read-only policy
inspection. It does not authorize a writer or create a recovery exception for
another production task. A live runner is deliberately not registered here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import types
from functools import wraps

TASK = 'UA-ART-RECOVERY-TASK120-002'
REPOSITORY = 'art20021986-wq/ua-art-autopilot'
# This inert revision proves one reviewed preparation snapshot. It is not a
# general live-ref verifier. A changed main requires a fresh reviewed revision.
REVIEWED_COMMIT = '2ce0c3a886f124c5865c564a7073ef1805861f1c'
REVIEWED_TREE = '6f9914b2f742ff4fb4001a5046f86408ad4ecc65'
FAILED_TASK = 'TASK120-PUBLISH-UA-0017-UA-0018'
FAILED_RUN = '34134692609'
EPOCH = 'auto-20260904T174904Z-global-guard-04'
REQUEST_SHA = 'a4662a876b037595742a31e34394b27d3e40bcbb75e2915df1ecdc0cb01b4442'
HALT = 'state/AUTOPILOT_HALT.json'
HALT_SHA = '35c8f42ec20d33f259cbf87aaaa193c86c4d5ae469fa4a8e67e6d049ce0091e9'
RECON = 'state/reconciliations/' + FAILED_TASK + '.' + FAILED_RUN + '.no-production-write.evidence-v2.json'
RECON_SHA = 'ce4f04f5fad0c1dc61544a029e4301868433b1a50c9ffaae93dce206bc6c4b3b'
CP_SHA = '93790a6422eba5b0b5f6b2920927d473cd0dd71950f8c1a2364892b83bbfff02'
REQUEST = 'tasks/requests/' + FAILED_TASK + '.json'
TRANSACTION = 'state/transactions/' + FAILED_TASK + '.' + REQUEST_SHA + '.' + FAILED_RUN + '.json'
CLAIM = 'state/claims/' + FAILED_TASK + '.' + REQUEST_SHA + '.' + FAILED_RUN + '.json'
LEDGER = 'state/autostart_consumed/' + FAILED_TASK + '.' + REQUEST_SHA + '.json'
ARCHIVE = 'state/halt_history/' + TASK + '/halt.json'
RECEIPT = 'state/halt_history/' + TASK + '/receipt.json'
SCOPES = ('state/claims', 'state/transactions', 'state/autostart_consumed',
          'state/autostart_nonces', 'tasks/launch', 'tasks/requests', '.github/workflows')
FIXED = (HALT, 'state/EXECUTION_MODE.json', 'state/AUTOPILOT_RUNTIME_MANIFEST.json',
         'state/MANUAL_MODE.md', 'state/receipts/TASK107-R2.json',
         'tasks/approvals/TASK107-R2-AUTOMATIC-MODE.json',
         'tasks/approvals/' + FAILED_TASK + '.production.json', RECON,
         'CLAUDE.md', 'tasks/task_107.md')
QUEUE_STATUSES = frozenset({'pending', 'queued', 'in_progress', 'requested', 'waiting'})
MAX_QUEUE_AGE = 600
PACKAGE = Path(__file__).resolve().parent


class RecoveryError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise RecoveryError(code)


def filesystem_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except OSError as exc:
            raise RecoveryError('FILESYSTEM_REFUSED:' + type(exc).__name__) from exc
    return wrapped


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def utc(value):
    require(isinstance(value, str), 'INVALID_TIMESTAMP')
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise RecoveryError('INVALID_TIMESTAMP') from exc
    require(parsed.tzinfo is not None, 'TIMESTAMP_REQUIRES_TIMEZONE')
    return parsed.astimezone(dt.timezone.utc)


def relative(value):
    require(isinstance(value, str) and bool(value), 'INVALID_REPOSITORY_PATH')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and str(path) == value
            and '\\' not in value and not any(ord(c) < 32 for c in value), 'INVALID_REPOSITORY_PATH')
    return value


def clean_path(path):
    path = Path(os.path.abspath(path))
    for parent in (*reversed(path.parents), path):
        require(not parent.is_symlink(), 'SYMLINK_REFUSED')
    return path


@filesystem_errors
def read(path, maximum=8 * 1024 * 1024):
    path = clean_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        before = os.fstat(handle.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'INPUT_TYPE_OR_SIZE')
        data = handle.read(maximum + 1)
        after = os.fstat(handle.fileno())
    current = path.stat(follow_symlinks=False)
    require(len(data) <= maximum and all(getattr(before, key) == getattr(after, key) == getattr(current, key)
                for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_mode')), 'INPUT_CHANGED_DURING_READ')
    clean_path(path)
    return data


def json_object(data):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    try:
        value = json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise RecoveryError('INVALID_JSON') from exc
    require(isinstance(value, dict), 'JSON_OBJECT_REQUIRED')
    return value


def verify_tree(tree, expected_root):
    children = {'': []}
    kinds = {'040000': 'tree', '100644': 'blob', '100755': 'blob',
             '120000': 'blob', '160000': 'commit'}
    for name, entry in tree.items():
        require(entry.get('type') == kinds.get(entry.get('mode'))
                and re.fullmatch('[0-9a-f]{40}', str(entry.get('sha', ''))), 'INVALID_GIT_TREE_ENTRY')
        parent, _, basename = name.rpartition('/')
        require(not parent or parent in tree and tree[parent].get('type') == 'tree', 'GIT_TREE_PARENT_MISSING')
        children.setdefault(parent, []).append((basename, entry))
        if entry['type'] == 'tree':
            children.setdefault(name, [])
    for directory in sorted(children, key=lambda path: path.count('/') + bool(path), reverse=True):
        entries = sorted(children[directory], key=lambda item: item[0].encode() +
                         (b'/' if item[1]['type'] == 'tree' else b''))
        payload = b''.join(entry['mode'].lstrip('0').encode() + b' ' + basename.encode() +
                           b'\0' + bytes.fromhex(entry['sha']) for basename, entry in entries)
        actual = hashlib.sha1(b'tree ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
        expected = tree[directory]['sha'] if directory else expected_root
        require(actual == expected, 'GIT_TREE_CONTENT_MISMATCH:' + (directory or 'ROOT'))


def inspect_inputs(root, inventory):
    root = clean_path(root)
    require(inventory.get('schema_version') == 'UA-ART-RECOVERY-INPUT-INVENTORY-1'
            and inventory.get('repository') == REPOSITORY, 'INVENTORY_IDENTITY')
    require(inventory.get('source_commit') == REVIEWED_COMMIT
            and inventory.get('source_tree') == REVIEWED_TREE, 'UNREVIEWED_SOURCE_REVISION')
    entries = inventory.get('tree_entries')
    require(isinstance(entries, list) and len(entries) <= 25000, 'INVENTORY_TREE_REQUIRED')
    tree = {}
    for entry in entries:
        name = relative(entry['path'])
        require(name not in tree, 'DUPLICATE_TREE_PATH')
        tree[name] = entry
    verify_tree(tree, REVIEWED_TREE)
    names = inventory.get('materialized_files')
    require(isinstance(names, list) and len(set(names)) == len(names), 'MATERIALIZED_INPUT_LIST')
    data = {}
    for name in names:
        relative(name)
        entry = tree.get(name, {})
        require(entry.get('type') == 'blob' and entry.get('mode') in ('100644', '100755'), 'INPUT_BLOB_REQUIRED')
        payload = read(root/name)
        require(len(payload) == entry.get('size') and git_blob(payload) == entry.get('sha'), 'SOURCE_BLOB_MISMATCH:' + name)
        data[name] = payload
    manifest = json_object(data.get('state/AUTOPILOT_RUNTIME_MANIFEST.json', b'{}'))
    pins = manifest.get('files')
    require(isinstance(pins, dict), 'RUNTIME_PIN_SET_REQUIRED')
    expected = set(FIXED) | set(pins)
    for scope in SCOPES:
        listed = {name for name in tree if name.startswith(scope + '/') and tree[name]['type'] == 'blob'}
        expected.update(listed)
        directory = clean_path(root/scope)
        actual = set()
        require(directory.is_dir(), 'INPUT_DIRECTORY_MISSING:' + scope)
        for path in directory.rglob('*'):
            clean_path(path)
            if path.is_file():
                actual.add(path.relative_to(root).as_posix())
        require(actual == listed, 'INPUT_DIRECTORY_SET_CHANGED:' + scope)
    require(set(data) == expected, 'MATERIALIZED_INPUT_SET_MISMATCH')
    for name in (ARCHIVE, RECEIPT):
        require(name not in tree and not (root/name).exists() and not (root/name).is_symlink(), 'RECOVERY_HISTORY_ALREADY_EXISTS')
    return data


def verify_pinned_policy(root, data):
    source = data.get('automation/control_plane.py', b'')
    require(sha(source) == CP_SHA, 'CONTROL_PLANE_REVIEWED_SHA_REQUIRED')
    # This is a pinned, pure metadata validation call. No claim, dispatch,
    # writer or recovery exception is passed to an executable task.
    module = types.ModuleType('uaart_recovery_policy_readonly')
    module.__file__ = str(root/'automation/control_plane.py')
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    try:
        result = module.verify_execution_mode(root=root, required_mode='AUTOMATIC', allow_halt_for_recovery=True)
    except module.ControlPlaneError as exc:
        raise RecoveryError('PINNED_POLICY_REFUSED:' + str(exc)) from exc
    require(result.get('mode_epoch') == EPOCH, 'MODE_EPOCH_MISMATCH')
    return {'status': result['status'], 'pinned_runtime_files': len(module.RUNTIME_PINNED_PATHS),
            'active_workflows': len(module.ACTIVE_WORKFLOW_EVENT_POLICY),
            'validator_sha256': CP_SHA, 'read_only_inspection': True,
            'execution_authorization_granted': False}


def verify_identity(data):
    require(sha(data[HALT]) == HALT_SHA, 'HALT_IDENTITY_MISMATCH')
    require(sha(data[RECON]) == RECON_SHA, 'RECONCILIATION_IDENTITY_MISMATCH')
    require(sha(data[REQUEST]) == REQUEST_SHA, 'REQUEST_IDENTITY_MISMATCH')
    halt, recon = json_object(data[HALT]), json_object(data[RECON])
    expected = {'status': 'EMERGENCY_HALT', 'task_id': FAILED_TASK, 'run_id': FAILED_RUN,
                'mode_epoch': EPOCH, 'request_path': REQUEST, 'request_sha256': REQUEST_SHA}
    require(all(halt.get(k) == v for k, v in expected.items()), 'HALT_FIELDS_MISMATCH')
    transaction, claim, ledger = (json_object(data[name]) for name in (TRANSACTION, CLAIM, LEDGER))
    require(transaction.get('transaction_id') == 'tx-' + FAILED_RUN + '-' + REQUEST_SHA[:16]
            and transaction.get('status') == 'ROLLED_BACK'
            and transaction.get('run_id') == FAILED_RUN
            and transaction.get('request_sha256') == REQUEST_SHA, 'TARGET_TRANSACTION_MISMATCH')
    require(recon.get('semantic_outcome') == 'ABORTED_NO_PRODUCTION_WRITE'
            and recon.get('original_run_id') == FAILED_RUN
            and recon.get('transaction_path') == TRANSACTION
            and recon.get('halt_snapshot', {}).get('sha256') == HALT_SHA, 'RECONCILIATION_MISMATCH')
    require(recon['state_anchors']['terminal_transaction_sha256'] == sha(data[TRANSACTION])
            and recon['state_anchors']['terminal_claim_sha256'] == sha(data[CLAIM]), 'TERMINAL_RECONCILIATION_BINDING')
    require(claim.get('task_execution_status') == 'FAILED', 'TARGET_CLAIM_NOT_TERMINAL')
    require(ledger.get('task_id') == FAILED_TASK and ledger.get('request_sha256') == REQUEST_SHA,
            'CONSUMED_IDENTITY_MISMATCH')
    return {k: expected[k] for k in ('task_id', 'run_id', 'mode_epoch', 'request_path', 'request_sha256')}


def inspect_queue_records(data, now):
    counts = {'claims': Counter(), 'transactions': Counter(), 'launch_markers': Counter()}
    for name, payload in data.items():
        if name.startswith('state/claims/'):
            value = json_object(payload).get('task_execution_status')
            require(value in {'FINISHED', 'FAILED', 'ROLLED_BACK'}, 'ACTIVE_OR_UNKNOWN_CLAIM:' + name)
            counts['claims'][value] += 1
        elif name.startswith('state/transactions/'):
            value = json_object(payload).get('status')
            require(value in {'FINISHED', 'ROLLED_BACK'}, 'PENDING_OR_UNKNOWN_TRANSACTION:' + name)
            counts['transactions'][value] += 1
        elif name.startswith('tasks/launch/AUTO-'):
            value = json_object(payload)
            require(value.get('schema_version') == 'UA-ART-AUTOSTART-LAUNCH-1', 'LAUNCH_SCHEMA_UNKNOWN')
            expiry = utc(value.get('expires_at'))
            require(expiry <= now, 'UNREVIEWED_UNEXPIRED_AUTO_LAUNCH:' + name)
            counts['launch_markers']['expired_auto'] += 1
        elif name.startswith('tasks/launch/'):
            counts['launch_markers']['legacy_not_in_autostart_trigger'] += 1
    return {key: dict(value) for key, value in counts.items()}


def verify_actions(queue, inventory, now):
    require(queue.get('schema_version') == 'UA-ART-RECOVERY-QUEUE-REVIEW-1'
            and queue.get('task_id') == TASK and queue.get('repository') == REPOSITORY
            and queue.get('source_commit') == inventory['source_commit'], 'QUEUE_BINDING_MISMATCH')
    statuses = queue.get('actions', {}).get('statuses')
    require(isinstance(statuses, list) and len(statuses) == len(QUEUE_STATUSES)
            and {item.get('status') for item in statuses} == QUEUE_STATUSES, 'INCOMPLETE_ACTIONS_INVENTORY')
    oldest = now
    for item in statuses:
        observed = utc(item.get('observed_at'))
        age = (now - observed).total_seconds()
        require(0 <= age <= MAX_QUEUE_AGE, 'STALE_OR_FUTURE_ACTIONS_INVENTORY')
        oldest = min(oldest, observed)
        expected_url = ('https://api.github.com/repos/' + REPOSITORY + '/actions/runs?status='
                        + item['status'] + '&per_page=100&page=1')
        require(item.get('url') == expected_url and item.get('page') == 1
                and item.get('per_page') == 100 and item.get('all_pages_read') is True,
                'ACTIONS_INVENTORY_SCOPE_OR_PAGINATION')
        raw = item.get('raw_body')
        require(isinstance(raw, str) and sha(raw.encode()) == item.get('raw_body_sha256'), 'ACTIONS_RESPONSE_HASH_MISMATCH')
        response = json_object(raw)
        require(response.get('total_count') == 0 and response.get('workflow_runs') == []
                and item.get('total_count') == 0 and item.get('returned_count') == 0, 'ACTIVE_OR_PENDING_ACTIONS')
    return {'status': 'EMPTY_AT_OBSERVATION', 'statuses_checked': sorted(QUEUE_STATUSES),
            'oldest_observation': oldest.isoformat(), 'maximum_age_seconds': MAX_QUEUE_AGE,
            'raw_responses_bound_by_sha256': True, 'external_writers': 'UNVERIFIED'}


def prepare_plan(root: Path, inventory: dict, queue: dict, now: dt.datetime | None = None) -> dict:
    root = clean_path(root)
    now = now or dt.datetime.now(dt.timezone.utc)
    require(now.tzinfo is not None, 'NOW_REQUIRES_TIMEZONE')
    now = now.astimezone(dt.timezone.utc)
    data = inspect_inputs(root, inventory)
    identity = verify_identity(data)
    policy = verify_pinned_policy(root, data)
    records = inspect_queue_records(data, now)
    actions = verify_actions(queue, inventory, now)
    code_hashes = {name: sha(read(PACKAGE/name)) for name in ('controller.py', 'git_rehearsal.py')}
    # Re-run directory/blob checks after all parsing and pinned policy reads.
    after = inspect_inputs(root, inventory)
    require(data == after, 'INPUT_CHANGED_DURING_PREFLIGHT')
    plan = {'schema_version': 'UA-ART-HALT-RECOVERY-PLAN-1', 'task_id': TASK,
            'repository': REPOSITORY, 'base_commit': inventory['source_commit'],
            'base_tree': inventory['source_tree'], 'generated_at': now.isoformat(),
            'snapshot_binding': 'REVIEWED_COMMIT_AND_RECONSTRUCTED_FULL_GIT_TREE',
            'live_ref_verification': 'NOT_PERFORMED_BY_OFFLINE_PLANNER',
            'expires_at': (now + dt.timedelta(minutes=5)).isoformat(),
            'scope': 'STAGE_A_READ_ONLY_PLAN_NOT_EXECUTION_AUTHORIZATION',
            'preflight_status': 'PASS', 'execution_ready': False,
            'execution_blockers': ['LIVE_RUNNER_NOT_REGISTERED', 'NO_SEPARATE_EXECUTION_COMMAND',
                                   'EXTERNAL_WRITERS_UNVERIFIED'],
            'halt_identity': identity, 'code_hashes': code_hashes,
            'inventory_sha256': sha(canonical(inventory)), 'queue_review_sha256': sha(canonical(queue)),
            'input_hashes': {name: sha(payload) for name, payload in sorted(data.items())},
            'pinned_policy': policy, 'durable_queue': records, 'actions': actions,
            'atomic_transition': 'one_git_commit_and_compare_and_swap_of_expected_main_ref',
            'required_writer_group': 'ua-art-production-writer',
            'mutation_plan': [
                {'operation': 'delete', 'path': HALT, 'expected_sha256': HALT_SHA},
                {'operation': 'add', 'path': ARCHIVE, 'content_sha256': HALT_SHA, 'must_not_exist': True},
                {'operation': 'add', 'path': RECEIPT, 'must_not_exist': True,
                 'content': 'execution receipt bound to this plan, separate owner command, base and code; not created by dry-run'}],
            'preserved': ['all prior request/claim/launch/nonce/consumed/transaction/reconciliation records',
                          'all current mode, runtime manifest and owner approval files',
                          'all CRM, site, VIN, card, price and media data'],
            'production_writes': 0, 'network_requests': 0, 'input_files_unchanged': True,
            'overall_specification_gate_b': 'NOT_EVALUATED'}
    plan['plan_sha256'] = sha(canonical(plan))
    return plan


@filesystem_errors
def write_plan(plan, root, output):
    root, output = clean_path(root), clean_path(output)
    allowed = root/'cloud/recovery_task120_002/evidence'
    require(output.parent == allowed and allowed.is_dir(), 'OUTPUT_MUST_BE_ISOLATED_EVIDENCE')
    require(output.name.endswith('.json'), 'OUTPUT_MUST_BE_JSON')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with os.fdopen(os.open(output, flags, 0o600), 'w', encoding='utf-8') as handle:
        json.dump(plan, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=('dry-run', 'execute'), default='dry-run')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--queue', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    require(args.action != 'execute', 'NOT_READY_LIVE_RUNNER_NOT_REGISTERED')
    require(all((args.root, args.inventory, args.queue, args.output)), 'DRY_RUN_ARGUMENTS_REQUIRED')
    inventory, queue = json_object(read(args.inventory)), json_object(read(args.queue))
    plan = prepare_plan(args.root, inventory, queue)
    write_plan(plan, args.root, args.output)
    print(json.dumps({key: plan[key] for key in ('task_id', 'preflight_status', 'execution_ready',
                     'execution_blockers', 'plan_sha256', 'production_writes')}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RecoveryError, OSError) as exc:
        print(json.dumps({'status': 'REFUSED', 'code': str(exc) if isinstance(exc, RecoveryError)
                          else type(exc).__name__, 'production_writes': 0}))
        raise SystemExit(2)
