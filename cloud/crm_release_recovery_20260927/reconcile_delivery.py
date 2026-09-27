"""Propose one evidence-bound, manual reconciliation; never write live state.

The operator must persist the exact proposal against its expected Git parent in
one commit. This is not the automatic close/rollback route and cannot be replayed.
Application acceptance remains pending for the separate corrective release.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re


TASK = 'DELIVERY-STATUS-INSTALL-20260927'
RUN = '36268504600'
REQ_SHA = '54c3be3cfc4dd0dab6f508524499715a6844011f4aa9520cc6e09f51f8c132ff'
TXID = 'tx-36268504600-54c3be3cfc4dd0da'
BACKUP_SHA = '7debcda6ef2ab08f87abeed07123c8c6c4e81b8dd6b96d4b043ad114a0564ac7'
PLAN_SHA = '67279c4ec97fd9652db7af262562c3d0dd54e38b35d8f6651b539980a0cf4a66'
MANIFEST_SHA = '04bed14bb530b1c42d56fe37e6a0661dbc57a5d94adf54257a5e4e69fd660a58'
COMMAND = 'Убери блоки и установи'
IDENTITY = TASK + '.' + REQ_SHA + '.' + RUN + '.json'
REQUEST = 'tasks/requests/' + TASK + '.json'
TRANSACTION = 'state/transactions/' + IDENTITY
CLAIM = 'state/claims/' + IDENTITY
HALT = 'state/AUTOPILOT_HALT.json'
RECEIPT = 'state/receipts/' + TASK + '.json'
HISTORY = 'state/halt_history/DELIVERY-STATUS-INSTALL-20260927.36268504600'
RESULT = 'state/reconciliations/DELIVERY-STATUS-INSTALL-20260927.36268504600.forward.json'
EVIDENCE = 'state/reconciliations/DELIVERY-STATUS-INSTALL-20260927.36268504600.forward.evidence.json'
REGISTRATION = 'state/manual_recovery_routes/DELIVERY-STATUS-INSTALL-20260927.36268504600.json'
SOURCE = 'cloud/crm_release_recovery_20260927/reconcile_delivery.py'
BOT = 'python3.10 /home/Carix/start_safe.py'
MONITOR = ('python3.10 -I /home/Carix/uaart_connection_monitor.py --watch --interval 300 '
           '--evidence /home/Carix/uaart-monitor/latest.json')
QUEUE_STATES = {'pending', 'queued', 'in_progress', 'requested', 'waiting'}


class ReconciliationError(ValueError):
    pass


def require(condition, error):
    if not condition:
        raise ReconciliationError(error)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def read(root, relative):
    path = root / relative
    require(path.resolve() == path and path.is_file() and path.stat().st_size <= 2*1024*1024,
            'UNSAFE_FILE:' + relative)
    return path.read_bytes()


def parsed(root, relative):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(read(root, relative), object_pairs_hook=unique)


def fresh(value, now):
    try:
        observed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(observed.tzinfo is not None, 'OBSERVATION_TIMEZONE')
        require(0 <= (now-observed).total_seconds() <= 120, 'STALE_OBSERVATION')
    except (TypeError, AttributeError, ValueError) as error:
        raise ReconciliationError('OBSERVATION_TIME:' + str(error)) from error


def bound_module(root, relative, name, runtime):
    payload = read(root, relative)
    require(sha(payload) == runtime['files'][relative], 'RUNTIME_CHANGED:' + relative)
    spec = importlib.util.spec_from_file_location(name, root/relative)
    module = importlib.util.module_from_spec(spec)
    exec(compile(payload, str(root/relative), 'exec'), module.__dict__)
    return module


def propose(root, evidence, expected_main, *, now, owner_command):
    """Return data-only changes; no subprocess, network, credentials or writes."""
    root = Path(root).resolve()
    require(re.fullmatch('[0-9a-f]{40}', expected_main) is not None, 'EXPECTED_MAIN')
    require(now.tzinfo is not None and owner_command == COMMAND, 'OWNER_COMMAND')
    registration = parsed(root, REGISTRATION)
    require(registration == {
        'schema_version': 'UA-ART-INCIDENT-MANUAL-ROUTE-1', 'task_id': TASK,
        'run_id': RUN, 'owner_command': COMMAND, 'owner_actor_id': '321059821',
        'scope': 'ACCEPT_VERIFIED_DELIVERY_INSTALLATION_ONLY',
        'route_path': SOURCE, 'route_sha256': sha(read(root, SOURCE)),
        'runtime_manifest_sha256': MANIFEST_SHA,
        'application_writes': False, 'automatic_rollback_replay': False,
    }, 'ROUTE_REGISTRATION')
    manifest_data = read(root, 'state/AUTOPILOT_RUNTIME_MANIFEST.json')
    require(sha(manifest_data) == MANIFEST_SHA, 'REVIEWED_RUNTIME_CHANGED')
    runtime = json.loads(manifest_data)
    for path, digest in runtime['files'].items():
        require(sha(read(root, path)) == digest, 'RUNTIME_CHANGED:' + path)
    cp = bound_module(root, 'automation/control_plane.py', 'delivery_reconcile_cp', runtime)
    cp.verify_execution_mode(root=root, required_mode='AUTOMATIC', allow_halt_for_recovery=True)
    watchdog = bound_module(root, 'automation/transaction_watchdog.py', 'delivery_reconcile_watchdog', runtime)
    pending = watchdog.discover(root=root)
    require((pending['pending_count'], pending['transaction_id'], pending['transaction_status'])
            == (1, TXID, 'ROLLING_BACK'), 'PENDING_TRANSACTION')
    before = {p: read(root,p) for p in (HALT, TRANSACTION, CLAIM, REQUEST)}
    halt, tx, claim, request = (json.loads(before[p]) for p in (HALT,TRANSACTION,CLAIM,REQUEST))
    require(sha(before[REQUEST]) == REQ_SHA, 'REQUEST_CHANGED')
    require(halt['status'] == 'EMERGENCY_HALT' and halt['task_id'] == TASK
            and halt['run_id'] == RUN and halt['request_sha256'] == REQ_SHA, 'HALT_IDENTITY')
    require(claim['task_execution_status'] == 'BLOCKED_ROOT_CAUSE'
            and claim['production_transaction_status'] == 'ROLLING_BACK', 'CLAIM_STATE')
    for path in (RECEIPT, RESULT, EVIDENCE, HISTORY+'/halt.json',
                 HISTORY+'/transaction.json', HISTORY+'/claim.json'):
        require(not (root/path).exists() and not (root/path).is_symlink(), 'ALREADY_RECONCILED')

    require(evidence['expected_main'] == expected_main, 'MAIN_OBSERVATION')
    require(evidence['owner_actor_id'] == '321059821', 'OWNER_IDENTITY')
    for section in ('remote', 'processes', 'github_queue', 'public_health'):
        fresh(evidence[section]['observed_at'], now)
    remote, processes, queue, health = (evidence[k] for k in
                                      ('remote','processes','github_queue','public_health'))
    require(remote['backup_manifest_sha256'] == BACKUP_SHA
            and remote['backup_database_matches'] is True
            and remote['backup_mismatches'] == [], 'BACKUP_INTEGRITY')
    require(remote['rollback_receipt_exists'] is False, 'ROLLBACK_OUTCOME_AMBIGUOUS')
    plan = parsed(root, 'cloud/delivery_status_001/deployment_plan.json')
    plan_canonical = (json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                 separators=(',', ':'))+'\n').encode()
    require(sha(plan_canonical) == PLAN_SHA, 'RECORDED_PLAN_CHANGED')
    expected_code = {p:v['after'] for p,v in plan['files'].items() if p.endswith('.py')}
    require(len(expected_code) == 11 and remote['code_sha256'] == expected_code
            and remote['protected_mismatches'] == [], 'LIVE_CODE_DRIFT')
    for operation in ('backup', 'install', 'verify'):
        receipt = remote['receipts'][operation]
        require(receipt.get('run_id') == RUN and receipt.get('mode') == operation
                and receipt.get('status') == 'PASS' and receipt.get('safe_to_stop') is True
                and receipt.get('crm_write') is False
                and receipt.get('backup_manifest_sha256') == BACKUP_SHA, 'REMOTE_RECEIPT:' + operation)
        if operation in ('backup', 'install'):
            require(receipt.get('plan_sha256') == PLAN_SHA, 'REMOTE_PLAN:' + operation)
        if operation in ('install', 'verify'):
            require(receipt.get('crm_unchanged') is True, 'CRM_CHANGED_DURING_INSTALL')
    installed = remote['receipts']['install']
    require(installed.get('installed') is True and installed.get('crm_resume',{}).get('enabled') is True,
            'INSTALL_NOT_COMPLETED')
    journal = remote['install_journal']
    require(journal.get('stage') == 'FINISHED' and journal.get('mode') == 'install'
            and journal.get('backup_sha256') == BACKUP_SHA
            and journal.get('result',{}).get('installed') is True
            and journal.get('result',{}).get('status') == 'PASS', 'INSTALL_JOURNAL')
    require(processes['commands'] == sorted([BOT, MONITOR])
            and processes['enabled_always_on_commands'] == sorted([BOT, MONITOR])
            and processes['bot_running'] is True, 'EXTERNAL_WRITER_OR_BOT_STATE')
    require(queue['statuses'] == sorted(QUEUE_STATES) and queue['complete'] is True
            and queue['runs'] == [], 'GITHUB_WRITER_QUEUE')
    require(health['checks'] == [
        {'url':'https://www.uaart.com.ua/video/index.html','status':200},
        {'url':'https://www.uaart.com.ua/video/katalog.html','status':200}], 'PUBLIC_HEALTH')
    require(evidence['full_crm_acceptance'] is False
            and evidence['publication_repair_installed'] is False, 'SCOPE_OVERCLAIM')

    stamp = now.isoformat()
    receipt = {
        'task_id':TASK, 'run_id':RUN, 'request_sha256':REQ_SHA, 'transaction_id':TXID,
        'manifest_sha256':request['critical']['manifest_sha256'],
        'contract_id':'UA-ART-CRITICAL-ADAPTER-V1.0', 'status':'FINISHED',
        'task_class':'CRITICAL', 'target_environment':'production', 'production_required':True,
        'tests':'PASS', 'tests_scope':'ORIGINAL_INSTALLATION_AND_CURRENT_SOURCE_READBACK',
        'production':'PASS', 'live_verify':'PASS',
        'live_verify_scope':'INSTALLED_SOURCE_AND_SERVICE_AVAILABILITY_ONLY',
        'backup':'PASS', 'backup_manifest_sha256':BACKUP_SHA,
        'rollback':'PASS', 'rollback_ready':True,
        'rollback_scope':'ORIGINAL_BACKUP_RESTORE_READINESS_AND_CORRECTED_NONCE_TRANSPORT',
        'rollback_performed':False, 'automatic_rollback_replay':False,
        'unexpected_changes':0, 'unexpected_changes_scope':'THIS_RECONCILIATION_ONLY',
        'protected_files_unchanged':True,
        'protected_files_unchanged_scope':'ORIGINAL_VERIFY_AND_CURRENT_PROTECTED_PYTHON_SOURCES',
        'crm_unchanged':True, 'crm_unchanged_scope':'DURING_ORIGINAL_INSTALL_AND_VERIFY_ONLY',
        'subsequent_operator_edits_preserved':True, 'full_crm_acceptance':False,
        'publication_repair_installed':False, 'remaining_task':'UA-ART-CRM-ONECLICK-PUBLISH-001',
        'persistence':'MANUAL_FORWARD_RECONCILIATION', 'reconciled_at':stamp,
        'reconciliation_evidence_path':EVIDENCE,
    }
    cp.validate_receipt(receipt, request, REQ_SHA, RUN)
    result = {'schema_version':'UA-ART-MANUAL-FORWARD-RECONCILIATION-1',
        'decision':'ACCEPT_VERIFIED_DELIVERY_INSTALLATION_ONLY', 'task_id':TASK,
        'run_id':RUN, 'transaction_id':TXID, 'request_sha256':REQ_SHA,
        'expected_parent':expected_main, 'owner_command':COMMAND, 'reconciled_at':stamp,
        'transaction_before':'ROLLING_BACK', 'transaction_after':'FINISHED',
        'rollback_performed':False, 'automatic_rollback_retried':False,
        'application_writes':False, 'full_crm_acceptance':False,
        'original_state_sha256':{p:sha(v) for p,v in before.items()},
        'receipt_path':RECEIPT, 'receipt_sha256':sha(encode(receipt)),
        'evidence_path':EVIDENCE, 'evidence_sha256':sha(encode(evidence)),
        'runtime_manifest_sha256':MANIFEST_SHA,
        'next_step':'Fresh gated corrective release; original launch remains consumed.'}
    updated_tx = dict(tx, status='FINISHED', closed_at=stamp)
    post_health = {'status':'PASS', 'checked_at':health['observed_at'], 'checks':[
        {'url':x['url'], 'final_url':x['url'], 'http_status':x['status'], 'status':'PASS'}
        for x in health['checks']]}
    updated_claim = dict(claim, task_execution_status='FINISHED',
        production_transaction_status='FINISHED', receipt_validation_status='PASS',
        receipt_path=RECEIPT, receipt_sha256=sha(encode(receipt)),
        post_health_status='PASS', post_health=post_health,
        reconciliation_path=RESULT, updated_at=stamp, finished_at=stamp,
        heartbeat_at=stamp, heartbeat_sequence=int(claim['heartbeat_sequence'])+1)
    changes = {HALT:None, TRANSACTION:encode(updated_tx), CLAIM:encode(updated_claim),
               RECEIPT:encode(receipt), RESULT:encode(result), EVIDENCE:encode(evidence),
               HISTORY+'/halt.json':before[HALT], HISTORY+'/transaction.json':before[TRANSACTION],
               HISTORY+'/claim.json':before[CLAIM]}
    require(all(read(root,p) == value for p,value in before.items()), 'SOURCE_DRIFT')
    return {'expected_parent':expected_main, 'changes':changes,
            'plan_sha256':sha(encode({p:sha(v) if v is not None else None
                                     for p,v in sorted(changes.items())}))}
