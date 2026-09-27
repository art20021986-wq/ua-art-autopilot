"""Data-only manual reconciliation of the proven pre-write R4 failure.

No network, credentials, application writes, bot control or rollback replay.
The proposal is bound to one reviewed route and one exact main parent.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

TASK = 'CRM-PUBLISH-VIDEO-INSTALL-20260927-R4'
RUN = '36308311986'
REQUEST_SHA = '4ddae39cc7597018293b3d64b9c3f5d843662932be144a7b0b3ae45fd0c2b964'
BACKUP = '402585a2a17d3fd7ee6bd75c1d22cea23ef0ba071723611481b093daa7837fc3'
PLAN = 'a2c446d49dcc145a3d0e9e13790291fc0ba9dc8f39c070c9448b848890c7472f'
ORIGINAL = '4d1adb53cb659daa125c7480c289ad25e03a57e34d3d0c1f4e0989de1d7a8ac8'
VERIFIER = 'a4c3852479ea36d560e2bd2aeebcef3bfcb6dc2f5bcb21cf8a4f075850c3cc2b'
SOURCE = 'cloud/crm_latency_recovery_20260927/reconcile_r4.py'
REGISTRATION = 'state/manual_recovery_routes/' + TASK + '.' + RUN + '.json'
HALT = 'state/AUTOPILOT_HALT.json'
REQUEST = 'tasks/requests/' + TASK + '.json'
TX = 'state/transactions/' + TASK + '.' + REQUEST_SHA + '.' + RUN + '.json'
CLAIM = 'state/claims/' + TASK + '.' + REQUEST_SHA + '.' + RUN + '.json'
BASE = 'state/reconciliations/' + TASK + '.' + RUN
EVIDENCE = BASE + '.aborted.evidence.json'
DECISION = BASE + '.aborted.json'
HISTORY = 'state/halt_history/' + TASK + '.' + RUN
OWNER_COMMAND = 'Снова очень плохо работает бот CRM. Устрани!'


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def fresh(stamp, now):
    age = (now - dt.datetime.fromisoformat(stamp.replace('Z', '+00:00'))).total_seconds()
    require(0 <= age <= 180, 'STALE_OR_FUTURE_EVIDENCE')


def validate_observation(e, now):
    for name in ('server', 'queue', 'supervisor'):
        fresh(e[name]['observed_at'], now)
    server = e['server']
    require(server['verifier_sha256'] == VERIFIER, 'VERIFIER_DRIFT')
    require(server['backup_sha256'] == BACKUP and server['plan_sha256'] == PLAN, 'BACKUP_BINDING')
    require(server['publisher_sha256'] == ORIGINAL, 'SOURCE_DRIFT')
    require(server['backup_and_before_files_verified'] is True, 'BACKUP_OR_FILES_NOT_VERIFIED')
    require(server['protected_file_count'] == 19, 'PROTECTED_SCOPE')
    for mode, error in [('install', 'TransportError:HTTP_502'), ('rollback', 'TransportError:BOT_STATE_TIMEOUT')]:
        journal, receipt = server['journals'][mode], server['receipts'][mode]
        require(journal['stage'] == 'FINISHED' and journal['mode'] == mode, 'NONTERMINAL_JOURNAL')
        require(journal['backup_sha256'] == BACKUP and 'data_before' not in journal, 'WRITE_BOUNDARY_ENTERED')
        result = journal['result']
        require(result.get('status') == 'FAIL' and result.get('error') == error, 'FAILURE_IDENTITY')
        require(not result.get('installed') and not result.get('restored') and not result.get('rollback_error'), 'UNEXPECTED_WRITE_RESULT')
        require(result.get('crm_resume') == {'id': 266084, 'enabled': True, 'state': 'running'}, 'RESUME_NOT_CONFIRMED')
        require(receipt.get('run_id') == RUN and receipt.get('mode') == mode, 'RECEIPT_IDENTITY')
        require(receipt.get('backup_manifest_sha256') == BACKUP and receipt.get('plan_sha256') == PLAN, 'RECEIPT_BINDING')
        require(receipt.get('status') == 'FAIL' and receipt.get('error') == error and receipt.get('safe_to_stop') is True, 'RECEIPT_NOT_TERMINAL')
        require(receipt.get('crm_write') is False and receipt.get('crm_resume') == result['crm_resume'], 'RECEIPT_RESUME')
    require(e['queue']['statuses_checked'] == ['action_required', 'in_progress', 'pending', 'queued', 'waiting'], 'QUEUE_SCOPE')
    require(e['queue']['active_runs'] == [], 'ACTIVE_WORKFLOW')
    require(e['supervisor']['bot_id'] == 266084 and e['supervisor']['enabled'] is True and e['supervisor']['state'] == 'Running', 'BOT_NOT_RUNNING')
    require(e['supervisor']['active_processes'] == ['monitor', 'start_safe'], 'ACTIVE_WRITER')
    require(e['public']['urls'] == ['https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/katalog.html'], 'PUBLIC_SCOPE')
    fresh(e['public']['observed_at'], now)
    require(e['public']['status_codes'] == [200, 200], 'PUBLIC_HEALTH')


def propose(root: Path, evidence, expected_parent, now):
    """Return exact changed bytes. The caller must atomically compare-and-swap main."""
    def read(p):
        path = root / p
        require(path.is_file() and not path.is_symlink(), 'MISSING_OR_UNSAFE_STATE:' + p)
        return path.read_bytes()
    parsed = lambda p: json.loads(read(p))
    registration = parsed(REGISTRATION)
    require(registration['route_sha256'] == sha(read(SOURCE)), 'UNREGISTERED_ROUTE')
    require(registration['runtime_manifest_sha256'] == sha(read('state/AUTOPILOT_RUNTIME_MANIFEST.json')), 'RUNTIME_DRIFT')
    require(registration['task_id'] == TASK and registration['run_id'] == RUN, 'REGISTRATION_IDENTITY')
    require(registration['owner_command'] == OWNER_COMMAND and registration['application_writes'] is False, 'REGISTRATION_SCOPE')
    require(evidence['expected_parent'] == expected_parent, 'PARENT_DRIFT')
    require(sha(read(REQUEST)) == REQUEST_SHA, 'REQUEST_DRIFT')
    for p in (HALT, TX, CLAIM):
        require(sha(read(p)) == evidence['original_state_sha256'][p], 'STATE_DRIFT:' + p)
    halt, tx, claim = map(parsed, (HALT, TX, CLAIM))
    require(halt['status'] == 'EMERGENCY_HALT' and halt['task_id'] == TASK and halt['run_id'] == RUN, 'HALT_IDENTITY')
    require(tx['status'] == 'ROLLING_BACK' and tx['run_id'] == RUN and tx['request_sha256'] == REQUEST_SHA, 'TRANSACTION_IDENTITY')
    require(tx['backup_manifest_sha256'] == BACKUP and tx['transaction_id'] == 'tx-' + RUN + '-' + REQUEST_SHA[:16], 'TRANSACTION_BACKUP')
    require(claim['production_transaction_status'] == 'ROLLING_BACK' and claim['request_sha256'] == REQUEST_SHA, 'CLAIM_IDENTITY')
    validate_observation(evidence, now)
    # Legacy watchdog has two terminal states. Preserve the existing aborted
    # transaction convention, explicitly without a successful rollback receipt.
    stamp = now.isoformat()
    new_tx = {**tx, 'status': 'ROLLED_BACK', 'closed_at': stamp}
    new_claim = {**claim, 'production_transaction_status': 'ROLLED_BACK',
                 'task_execution_status': 'FAILED', 'updated_at': stamp,
                 'reconciliation_path': DECISION}
    decision = {
        'schema_version': 'UA-ART-PRODUCTION-RECONCILIATION-1', 'task_id': TASK,
        'run_id': RUN, 'request_sha256': REQUEST_SHA, 'transaction_id': tx['transaction_id'],
        'reconciled_at': stamp, 'expected_parent': expected_parent,
        'owner_instruction': OWNER_COMMAND, 'semantic_outcome': 'ABORTED_BEFORE_APPLICATION_WRITE',
        'metadata_terminal_status': 'ROLLED_BACK',
        'metadata_terminal_status_meaning': 'Watchdog-compatible aborted-attempt convention only; both real remote receipts remain FAIL.',
        'production_rollback_executed_successfully': False, 'application_installation_completed': False,
        'source_replacement_entered': False, 'crm_supervisor_pause_resume_performed': True,
        'original_failure_preserved': True, 'automatic_rollback_replayed': False,
        'application_data_written_by_reconciliation': False,
        'subsequent_operator_data_preserved': True, 'successor_authorized_by_record': False,
        'gates_workflows_runtime_ledger_nonce_unchanged': True,
        'evidence_path': EVIDENCE, 'evidence_sha256': sha(canonical(evidence)),
    }
    writes = {HISTORY + '/halt.json': read(HALT), HISTORY + '/transaction.json': read(TX),
              HISTORY + '/claim.json': read(CLAIM), EVIDENCE: canonical(evidence),
              DECISION: canonical(decision), TX: canonical(new_tx), CLAIM: canonical(new_claim), HALT: None}
    for p in (HISTORY + '/halt.json', HISTORY + '/transaction.json', HISTORY + '/claim.json', EVIDENCE, DECISION):
        require(not (root / p).exists(), 'RECONCILIATION_ALREADY_EXISTS')
    return writes
