"""Build an offline, exact-incident DATA ONLY recovery proposal; never apply it.

Caller must supply reviewed fresh authenticated observations. Hash bindings
prove integrity, not the truth/authentication of caller-supplied evidence.
No subprocess, network, production path writes, Git operation or control bypass.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent
INPUT_SHA = '7d72329f249bbfd9b2fa47c252f0ac7e877c8ac40e69781a1e8eb855a1c071b4'
MAIN = '79c6aaccbfdc2decf7bf39d26738a2c38bde91f4'
TASK = 'SEO-DAILY-PODBOR-CANONICAL-20260921'
RUN = '35552076762'
REQUEST = 'd89fd9b950e5c72a01828a153c9fe57d460750aba9ed7db82f6c3b97819520d4'
IDENTITY = TASK + '.' + REQUEST + '.' + RUN + '.json'
TX = 'state/transactions/' + IDENTITY
CLAIM = 'state/claims/' + IDENTITY
HALT = 'state/AUTOPILOT_HALT.json'
ARCHIVE = 'state/halt_history/' + TASK + '.' + RUN
RECON = 'state/reconciliations/' + TASK + '.' + RUN + '.aborted-before-production.json'
EVIDENCE = 'state/reconciliations/' + TASK + '.' + RUN + '.authenticated-evidence.json'
SUMMARY_SHA = '07e07f499c20d5db62e0ae58cb4922be2cfacd4e8956879dbcd374322bb71454'
TARGET = '/home/Carix/video/podbor.html'

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def require(ok, code):
    if not ok:
        raise ValueError(code)

def time_value(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'AWARE_TIMESTAMP_REQUIRED')
    return parsed

def build(evidence, *, now, proof_root):
    raw = (HERE / 'canonical_inputs.json').read_bytes()
    require(sha(raw) == INPUT_SHA, 'CANONICAL_INPUT_DRIFT')
    source = json.loads(raw)
    files = {p: s.encode() for p, s in source['files'].items()}
    values = {p: json.loads(b) for p, b in files.items() if p.endswith('.json')}
    tx, claim, halt = values[TX], values[CLAIM], values[HALT]
    require(source['main_commit'] == MAIN == evidence['observed_main'], 'MAIN_DRIFT')
    require(evidence['contract'] == 'SEO-35552076762-AUTHENTICATED-READONLY-EVIDENCE-1', 'EVIDENCE_CONTRACT')
    require(evidence['task_id'] == TASK and str(evidence['run_id']) == RUN, 'EVIDENCE_IDENTITY')
    age = (now - time_value(evidence['observed_at_utc'])).total_seconds()
    require(0 <= age <= 300, 'FRESH_EVIDENCE_REQUIRED')
    server = evidence['server']
    require(server['account'] == 'Carix' and server['read_only'] is True, 'AUTHENTICATED_ACCOUNT_REQUIRED')
    require(server['process_matcher'] == 'seo_daily_podbor_canonical_20260921.py', 'EXACT_LOWERCASE_PROCESS_MATCHER_REQUIRED')
    require(all(type(server[k]) is int and server[k] == 0 for k in
        ('matching_process_count', 'matching_scheduled_task_count', 'matching_always_on_task_count')), 'REMOTE_WRITER_NOT_EXCLUDED')
    require(server['backup_manifest'] == server['upload_receipt'] == 'ABSENT', 'RECONCILE_CHANGED_REMOTE_OUTCOME')
    require(evidence['remote_backup_outcome'] == 'UNKNOWN', 'DO_NOT_INVENT_BACKUP_OUTCOME')
    require(set(evidence['active_github_runs']) == {'queued','in_progress','pending','requested','waiting'}, 'COMPLETE_QUEUE_OBSERVATION_REQUIRED')
    require(all(type(v) is int and v == 0 for v in evidence['active_github_runs'].values()), 'ACTIVE_GITHUB_WRITER')
    require(evidence['observer_summary_sha256'] == SUMMARY_SHA, 'CURRENT_OBSERVER_BINDING')
    target = evidence['current_target']
    require(target['path'] == TARGET and len(target['sha256']) == 64
        and all(c in '0123456789abcdef' for c in target['sha256'])
        and target['http_status'] == 200 and type(target['canonical_values']) is list, 'CURRENT_TARGET_OBSERVATION_REQUIRED')
    require(target['sha256'] == '1a8cc3d403151b48756f043c22b76ca8cd9f180f775f82a3d82e1b5f3ffd6be6', 'TARGET_CHANGED_REFRESH_OBSERVER_AND_REVIEW')
    require(evidence['owner_instruction'] and evidence['independently_reviewed_observations'] is True, 'REVIEWED_OWNER_AUTHORIZED_OBSERVATIONS_REQUIRED')
    required_proofs = {'server_processes_and_schedules', 'server_artifact_absence', 'current_target_and_http', 'github_active_runs'}
    require(set(evidence['proof_files']) == required_proofs, 'EXACT_PROOF_SET_REQUIRED')
    durable_proofs = {}
    for name, item in evidence['proof_files'].items():
        proof_age = (now - time_value(item['observed_at_utc'])).total_seconds()
        require(0 <= proof_age <= 300, 'FRESH_INDIVIDUAL_PROOF_REQUIRED')
        path = proof_root / item['path']
        require(path.is_relative_to(proof_root) and '..' not in Path(item['path']).parts
            and path.is_file() and not path.is_symlink(), 'LOCAL_PROOF_PATH')
        proof_raw = path.read_bytes()
        require(len(proof_raw) <= 128 * 1024, 'BOUNDED_SCOPED_TEXT_PROOF_REQUIRED')
        require(sha(proof_raw) == item['sha256'], 'LOCAL_PROOF_HASH')
        proof_text = proof_raw.decode('utf-8')
        require(proof_text.encode('utf-8') == proof_raw, 'EXACT_UTF8_PROOF_REQUIRED')
        durable_proofs[name] = {'sha256': item['sha256'], 'bytes': len(proof_raw),
            'observed_at_utc': item['observed_at_utc'], 'exact_utf8_content': proof_text}
    require(tx['status'] == 'PREPARING' and tx['opened_at'] is None
        and tx['backup_manifest_sha256'] is None and tx['backup_receipt_sha256'] is None, 'EXACT_ABORTED_PREPARING_ONLY')
    require(claim['task_execution_status'] == 'BLOCKED_ROOT_CAUSE' and claim['production_transaction_status'] == 'PREPARING', 'CLAIM_PHASE')
    require(halt['status'] == 'EMERGENCY_HALT' and halt['task_id'] == TASK
        and halt['run_id'] == RUN and halt['request_sha256'] == REQUEST, 'EXACT_HALT_ONLY')
    require(sha(files['tasks/requests/' + TASK + '.json']) == REQUEST, 'REQUEST_BINDING')
    for path, value in values.items():
        if path.startswith('state/transactions/') and path != TX:
            require(value['status'] in ('FINISHED', 'ROLLED_BACK'), 'OTHER_PENDING_TRANSACTION')
    jobs = {j['name']: j for j in source['workflow_jobs']}
    required_jobs = {'backup':'failure', 'open':'skipped', 'controller_production':'skipped',
        'rollback_execute':'skipped', 'finalize':'skipped'}
    for suffix, conclusion in required_jobs.items():
        job = jobs['execute / critical / ' + suffix]
        require(str(job['run_id']) == RUN and job['status'] == 'completed'
            and job['conclusion'] == conclusion, 'WORKFLOW_OUTCOME_BINDING')
    timestamp = now.isoformat()
    new_tx, new_claim = copy.deepcopy(tx), copy.deepcopy(claim)
    new_tx.update(status='ROLLED_BACK', closed_at=timestamp)
    new_claim.update(task_execution_status='FAILED', production_transaction_status='ROLLED_BACK', updated_at=timestamp)
    new_claim['failure_history'].append({'action':'MANUAL_RECONCILIATION','at':timestamp,
        'class':'ABORTED_BEFORE_PRODUCTION','message':'Exact backup-only attempt closed; installation never opened. Remote backup outcome UNKNOWN; no backup/rollback PASS claimed.',
        'retry_allowed':False,'retries_remaining':0,'evidence_path':EVIDENCE})
    durable_evidence = copy.deepcopy(evidence)
    durable_evidence['embedded_proofs'] = durable_proofs
    durable_evidence['completed_workflow_jobs'] = source['workflow_jobs']
    durable_evidence['workflow_run_url'] = 'https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/' + RUN
    durable_evidence['canonical_source_commit'] = MAIN
    durable_evidence['backup_only_source_sha256'] = {p: sha(b) for p, b in files.items()
        if p.startswith('cloud/seo_daily_podbor_canonical_20260921/')}
    writes = {ARCHIVE+'/halt.json':files[HALT], ARCHIVE+'/transaction.before.json':files[TX],
        ARCHIVE+'/claim.before.json':files[CLAIM], TX:encoded(new_tx), CLAIM:encoded(new_claim), EVIDENCE:encoded(durable_evidence)}
    recon = {'schema_version':'UA-ART-PRODUCTION-RECONCILIATION-1','task_id':TASK,
        'original_run_id':RUN,'request_sha256':REQUEST,'transaction_id':tx['transaction_id'],
        'base_main_commit':MAIN,'reconciled_at':timestamp,'semantic_outcome':'ABORTED_NO_PRODUCTION_WRITE',
        'production_write_scope':'Live podbor.html and other business files; excludes ephemeral transport, isolated receipts and possible backup outputs.',
        'metadata_terminal_status':'ROLLED_BACK','metadata_terminal_status_meaning':'Existing watchdog-compatible aborted-PREPARING convention only; no rollback execution or PASS.',
        'production_install_controller_executed':False,'production_rollback_executed':False,
        'remote_backup_outcome':'UNKNOWN','backup_pass_claimed':False,'historical_target_before_hash_available':False,
        'current_target_unchanged_since_original_run_claimed':False,
        'evidence_path':EVIDENCE,'evidence_sha256':sha(writes[EVIDENCE]),
        'before_sha256':{p:sha(files[p]) for p in (HALT,TX,CLAIM)},
        'after_sha256':{p:sha(writes[p]) for p in (TX,CLAIM)},
        'old_request_approval_ledger_nonce_marker_unchanged':True,
        'successor_installation_authorized_by_this_record':False,
        'original_failure_preserved':True,'runtime_workflows_gates_unchanged':True}
    writes[RECON] = encoded(recon)
    writes[ARCHIVE+'/receipt.json'] = encoded({'schema_version':'UA-ART-MANUAL-RECONCILIATION-1',
        'scope':'REPOSITORY_STATE_RECONCILIATION_ONLY','task_id':TASK,'run_id':RUN,
        'transaction_id':tx['transaction_id'],'request_sha256':REQUEST,'reconciled_at':timestamp,
        'archived_halt_path':ARCHIVE+'/halt.json','archived_halt_sha256':sha(files[HALT]),
        'reconciliation_path':RECON,'reconciliation_sha256':sha(writes[RECON]),
        'halt_removed':True,'application_writes':0,'rollback_performed':False,
        'backup_pass_claimed':False,'execution_mode_changed':False,'fresh_successor_gate_b_required':True})
    return files, writes, {'contract':'SEO-35552076762-OFFLINE-RECOVERY-PROPOSAL-1',
        'status':'PROPOSED_NOT_APPLIED_REQUIRES_INDEPENDENT_REVIEW_AND_EXACT_MAIN_READBACK',
        'expected_main':MAIN,'created_at':timestamp,'canonical_input_sha256':INPUT_SHA,
        'writes':{p:{'before_sha256':sha(files[p]) if p in files else None,'after_sha256':sha(b)} for p,b in writes.items()},
        'deletes':{HALT:sha(files[HALT])},'server_writes':False,'git_writes':False,
        'required_before_publish':['independent exact-diff review','unchanged pinned control-plane validators on complete proposed repository',
        'fresh actual main and active writers readback','single atomic commit and non-forced compare of expected parent; no mixed intermediate state'],
        'required_after_publish':['exact main commit/diff/readback','HALT absence and original archived bytes','zero pending production transactions','no old launch replay'],
        'not_authorized':['re-run old workflow','create backup/rollback/final PASS receipts','modify runtime or approvals','install prices before their own gates']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    evidence=json.loads(args.evidence.read_bytes())
    _,writes,plan=build(evidence,now=dt.datetime.now(dt.timezone.utc),proof_root=args.evidence.parent.resolve())
    args.output.mkdir(parents=False,exist_ok=False)
    for name,raw in writes.items():
        path=args.output/'proposed'/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)
    (args.output/'PLAN.json').write_bytes(encoded(plan))
    print(json.dumps({'status':plan['status'],'writes':len(writes),'deletes':1,'output':str(args.output)}))

if __name__=='__main__':
    main()
