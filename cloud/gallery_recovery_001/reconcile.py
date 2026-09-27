"""Close only the verified gallery attempt aborted during read-only backup.

Manual, incident-specific repository reconciliation. No application writes,
credentials, network, workflow edits, or retry of the consumed transaction.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

TASK = 'GALLERY-DESKTOP-INSTALL-20260928'
RUN = '36352273461'
REQUEST_SHA = '0e863dd329ae5d2fb6c79aec2e1f029493c20fccadb16fd6d042af0b86693356'
LAUNCH_SHA = 'fea373b1d86baeb42879194d38ccf3e674cc7840'
SOURCE = 'cloud/gallery_recovery_001/reconcile.py'
REGISTRATION = 'state/manual_recovery_routes/'+TASK+'.'+RUN+'.json'
HALT = 'state/AUTOPILOT_HALT.json'
REQUEST = 'tasks/requests/'+TASK+'.json'
TX = 'state/transactions/'+TASK+'.'+REQUEST_SHA+'.'+RUN+'.json'
CLAIM = 'state/claims/'+TASK+'.'+REQUEST_SHA+'.'+RUN+'.json'
BASE = 'state/reconciliations/'+TASK+'.'+RUN
EVIDENCE = BASE+'.aborted-backup.evidence.json'
DECISION = BASE+'.aborted-backup.json'
HISTORY = 'state/halt_history/'+TASK+'.'+RUN
OWNER_COMMAND = 'По какой причине ты еще не завершил мою просьбу? немедленно ее заверши.'

def canonical(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()

def sha(value):
    return hashlib.sha256(value).hexdigest()

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def validate_observation(e):
    run=e['workflow_run']
    require(str(run['id'])==RUN and run['head_sha']==LAUNCH_SHA,'RUN_IDENTITY')
    require(run['status']=='completed' and run['conclusion']=='failure','RUN_NOT_TERMINAL')
    jobs=e['jobs']
    require(all(str(j['run_id'])==RUN and j['status']=='completed' for j in jobs),'JOB_IDENTITY')
    require(len({j['name'] for j in jobs})==len(jobs),'DUPLICATE_JOB')
    by_name={j['name']:j for j in jobs}
    backup=by_name['execute / critical / backup']
    require(backup['id']==108713544347 and backup['conclusion']=='failure','BACKUP_FAILURE')
    for name in ('open','controller_production','controller_nonproduction','rollback_execute','finalize'):
        require(by_name['execute / critical / '+name]['conclusion']=='skipped','WRITE_STAGE_EXECUTED:'+name)
    error='REMOTE_BACKUP:DeploymentError:LIVE_PLAN_DRIFT'
    require(e['backup_error']==error and any(error in line for line in e['backup_log_excerpt']),'BACKUP_ERROR')

def propose(root: Path, evidence, expected_parent, now):
    def read(path):
        p=root/path
        require(p.is_file() and not p.is_symlink(),'MISSING_OR_UNSAFE:'+path)
        return p.read_bytes()
    parsed=lambda p:json.loads(read(p))
    registration=parsed(REGISTRATION)
    require(registration['route_sha256']==sha(read(SOURCE)),'UNREGISTERED_ROUTE')
    require(registration['runtime_manifest_sha256']==sha(read('state/AUTOPILOT_RUNTIME_MANIFEST.json')),'RUNTIME_DRIFT')
    require(registration['task_id']==TASK and registration['run_id']==RUN,'REGISTRATION_IDENTITY')
    require(registration['owner_command']==OWNER_COMMAND and registration['application_writes'] is False,'REGISTRATION_SCOPE')
    require(evidence['expected_parent']==expected_parent,'PARENT_DRIFT')
    require(sha(read(REQUEST))==REQUEST_SHA,'REQUEST_DRIFT')
    request=parsed(REQUEST)
    execution=request['execution']
    require(execution['controller_sha256']=='738a249ae6607a91079134f073836761621657d3b8ca278433267bf49af8f327','CONTROLLER_IDENTITY')
    require(sha(read(execution['controller_path']))==execution['controller_sha256'],'CONTROLLER_DRIFT')
    remote='cloud/gallery_desktop_001/deployment_remote.py'
    require(sha(read(remote))=='c564d2b48fcc215523297d7d970cd35fa21078d755bd7af6661ce0be17774452','BACKUP_CODE_DRIFT')
    for path in (HALT,TX,CLAIM):
        require(sha(read(path))==evidence['original_state_sha256'][path],'STATE_DRIFT:'+path)
    halt,tx,claim=map(parsed,(HALT,TX,CLAIM))
    require(halt['status']=='EMERGENCY_HALT' and halt['task_id']==TASK and halt['run_id']==RUN,'HALT_IDENTITY')
    require(tx['status']=='PREPARING' and tx['run_id']==RUN and tx['request_sha256']==REQUEST_SHA,'TRANSACTION_IDENTITY')
    require(tx['transaction_id']=='tx-'+RUN+'-'+REQUEST_SHA[:16],'TRANSACTION_BINDING')
    require(all(tx[k] is None for k in ('backup_manifest_sha256','backup_receipt_sha256','opened_at')),'WRITE_CREDENTIAL_BOUNDARY_ENTERED')
    require(not (root/tx['backup_receipt_path']).exists(),'UNEXPECTED_BACKUP_RECEIPT')
    require(claim['production_transaction_status']=='PREPARING' and claim['task_execution_status']=='BLOCKED_ROOT_CAUSE','CLAIM_STATE')
    require(claim['request_sha256']==REQUEST_SHA,'CLAIM_IDENTITY')
    validate_observation(evidence)
    stamp=now.isoformat()
    decision={'schema_version':'UA-ART-PRODUCTION-RECONCILIATION-1','task_id':TASK,'run_id':RUN,
              'request_sha256':REQUEST_SHA,'transaction_id':tx['transaction_id'],'reconciled_at':stamp,
              'expected_parent':expected_parent,'owner_instruction':OWNER_COMMAND,
              'semantic_outcome':'ABORTED_DURING_BACKUP_BEFORE_APPLICATION_WRITE',
              'metadata_terminal_status':'ROLLED_BACK',
              'metadata_terminal_status_meaning':'Existing watchdog-compatible aborted-attempt convention; no installation or rollback PASS is claimed.',
              'application_writes':0,'production_install_controller_executed':False,
              'production_rollback_controller_executed':False,'service_pause_resume_executed':False,
              'original_failure_preserved':True,'automatic_rollback_replayed':False,
              'runtime_workflows_gates_ledger_nonce_unchanged':True,'successor_authorized_by_record':False,
              'fresh_plan_request_and_gate_b_required':True,'evidence_path':EVIDENCE,
              'evidence_sha256':sha(canonical(evidence))}
    writes={HISTORY+'/halt.json':read(HALT),HISTORY+'/transaction.json':read(TX),HISTORY+'/claim.json':read(CLAIM),
            EVIDENCE:canonical(evidence),DECISION:canonical(decision),
            TX:canonical({**tx,'status':'ROLLED_BACK','closed_at':stamp}),
            CLAIM:canonical({**claim,'production_transaction_status':'ROLLED_BACK','task_execution_status':'FAILED',
                             'updated_at':stamp,'reconciliation_path':DECISION}),HALT:None}
    for path in (HISTORY+'/halt.json',HISTORY+'/transaction.json',HISTORY+'/claim.json',EVIDENCE,DECISION):
        require(not (root/path).exists(),'RECONCILIATION_ALREADY_EXISTS')
    return writes
