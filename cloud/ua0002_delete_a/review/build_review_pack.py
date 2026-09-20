#!/usr/bin/env python3
"""Build a review-only exact-hash draft. Never creates a launch or readiness PASS."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil

TASK='UA-ART-UA0002-CRITICAL-DELETE-A-001'
PACKAGE='cloud/ua0002_delete_a'
FILES=('remote_stage_a.py','remote_lifecycle.py','publication_fence.py','visibility_lifecycle.py',
       'ua_site_counters.py','uaart_price_sync_runtime.py','provenance.json')
TESTS=('test_controller.py','test_stage_a.py','test_remote_lifecycle.py')
ROOT=Path(__file__).resolve().parent

def encoded(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()

def digest(data):return hashlib.sha256(data).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encoded(value));return digest(encoded(value))

def build(worker,probe_one,probe_two):
    package=ROOT/PACKAGE
    package.mkdir(parents=True,exist_ok=True)
    for name in (*FILES,'test_stage_a.py','test_remote_lifecycle.py'):
        shutil.copyfile(worker/name,package/name)
    shutil.copytree(worker/'fixtures',package/'fixtures',dirs_exist_ok=True)
    plan=json.loads((worker/'plan.template.NOT_READY.json').read_bytes())
    one=json.loads(probe_one.read_bytes());two=json.loads(probe_two.read_bytes())
    pins={}
    for evidence in (one,two):
        for path,fact in evidence.get('source_facts',{}).items():
            if path.startswith('/home/Carix/') and Path(path).parent==Path('/home/Carix'):
                pins[Path(path).name]=fact['sha256']
    plan['source_sha256']=pins
    plan['stage_a_requires_target_absent']=True
    plan['package_sha256']={name:digest((package/name).read_bytes()) for name in FILES}
    # Inputs are recorded faithfully; review/runtime admission remains unfinished.
    plan['writers']['reviewed']=False
    plan['writers']['safe_window_end_epoch']=None
    blockers=[
      'FRESH_ACCOUNT_QUOTA_UNAVAILABLE_NO_HOST_DISK_SUBSTITUTION',
      'PROVIDER_WRITER_REVIEW_AND_FUTURE_QUIET_WINDOW_NOT_APPROVED',
      'LIVE_DATABASE_TARGET_ABSENCE_DELETE_AUDIT_AND_INTEGRITY_NOT_OBSERVED',
      'EXACT_ALIAS_INVENTORY_NOT_OBSERVED',
      'INDEPENDENT_FINAL_PACKAGE_REVIEW_NOT_COMPLETED',
      'GENERIC_WORKFLOW_NONCE_RESERVATION_ROLLBACK_LIMITATION_REQUIRES_ACCEPTED_RECOVERY_ROUTE',
    ]
    changes=['production/card-retirement/UA-0002','production/catalog/UA-0002',
             'production/homepage/UA-0002','production/sitemap/UA-0002']
    manifest={'contract_id':'UA-ART-CRITICAL-ADAPTER-V1.0','task_id':TASK,'task_class':'CRITICAL',
      'readiness':'NOT_READY','blockers':blockers,'production_write':True,'explicit_crm_vehicle_approval':True,
      'backup_required':True,'rollback_required':True,'live_verify_required':True,
      'backup_scope':changes+['production/crm-readonly-snapshot'], 'rollback_scope':changes,
      'protected_paths':['production/runtime','production/prices','production/non-target-cards','production/media','production/CRM-records'],
      'operations':[{'action':'noop','path':path,'operation_kind':'EXACT_TARGET_RETIREMENT_WITH_EXPLICIT_PRODUCTION_MUTATION',
        'postcondition':{'target_retired':True,'other_vehicle_data_unchanged':True,'crm_write':False,'media_write':False}}
        for path in changes],
      'recovery_semantics':'RESTORE_SAFE_INVARIANTS_KEEP_SOLD_TARGET_RETIRED',
      'restored_field_definition':'Canonical rollback restored=true attests verified safe non-target invariants and continued target retirement. It never means restoration of the original listing or CRM record.',
      'forbidden_recovery':['restore_sold_listing','restore_whole_database','overwrite_new_operator_changes'],
      'dynamic_operation_contract':'Logical-artifact noop declares scope; worker makes explicitly authorized bounded public-file mutations. Actual postimage hashes come only from verified execution.',
      'deployment':plan,
      'source_evidence':[{'path':'cloud/ua0002_delete_probe/evidence.json','sha256':digest(probe_one.read_bytes()),'run_id':one['run_id'],'finished_at':one['finished_at']},
                         {'path':'cloud/ua0002_delete_probe2/evidence.json','sha256':digest(probe_two.read_bytes()),'run_id':two['run_id'],'finished_at':two['finished_at']}],
      'owner_authorization':{'scope_approved':True,'source':'Current conversation; user approved UA-ART-UA0002-CRITICAL-DELETE-001 v1.0 stages A and B','quoted_verbatim':False,'additional_owner_approval_required':False}}
    mh=write(ROOT/'tasks/manifests'/f'{TASK}.json',manifest)
    report_path=ROOT/'LOCAL_VALIDATION.json'
    report=json.loads(report_path.read_bytes()) if report_path.exists() else {'status':'NOT_RUN'}
    gate={'contract_id':'UA-ART-CRITICAL-ADAPTER-V1.0','task_id':TASK,'status':'NOT_READY','manifest_sha256':mh,
      'tests':report.get('status','NOT_RUN'),'local_validation':report,'blockers':blockers,
      'backup_plan_ready':True,'rollback_plan_ready':True,'production_write':False,'live_installation_acceptance':'NOT_PERFORMED',
      'unexpected_changes':0,'owner_scope_approved':True,'independent_review':'NOT_COMPLETED'}
    gh=write(ROOT/'tasks/gates'/f'{TASK}.json',gate)
    approval={'schema_version':'UA-ART-PRODUCTION-AUTHORIZATION-1','task_id':TASK,'owner_authorized':True,'production_allowed':True,
      'authorized_environment':'production','approval_scope':'UA-ART-UA0002-CRITICAL-DELETE-001 v1.0 stages A/B',
      'authorization_record_status':'OWNER_SCOPE_APPROVED_EXACT_LAUNCH_BINDING_PENDING',
      'owner_instruction_source':'Current conversation; exact quote can be added by root from visible approved user message.',
      'quoted_verbatim':False,'request_path':f'tasks/requests/{TASK}.json','manifest_sha256':mh,'gate_a_sha256':gh,
      'mode_epoch':'auto-20260904T174904Z-global-guard-04','launch_nonce':None,'approved_at':None,'expires_at':None,
      'request_subject_sha256':None,'authorization_id':None,'owner':'Artem / UA ART COMPANY LLC'}
    ah=write(ROOT/'tasks/approvals'/f'{TASK}.production.json',approval)
    deps=[PACKAGE+'/'+name for name in FILES]
    deps += [str(path.relative_to(ROOT)) for path in sorted((package/'fixtures').rglob('*.html'))]
    tests=[PACKAGE+'/'+name for name in TESTS]
    files={rel:digest((ROOT/rel).read_bytes()) for rel in deps+tests}
    execution={'controller_path':PACKAGE+'/controller.py','controller_sha256':digest((package/'controller.py').read_bytes()),
      'backup_controller_path':PACKAGE+'/backup_controller.py','backup_controller_sha256':digest((package/'backup_controller.py').read_bytes()),
      'rollback_controller_path':PACKAGE+'/rollback_controller.py','rollback_controller_sha256':digest((package/'rollback_controller.py').read_bytes()),
      'backup_receipt_path':f'state/receipts/{TASK}-BACKUP.json','rollback_receipt_path':f'state/receipts/{TASK}-ROLLBACK.json',
      'receipt_path':f'state/receipts/{TASK}.json','production_required':True,'timeout_seconds':1800,
      'dependency_paths':deps,'test_paths':tests,'file_sha256':files,
      'evidence_paths':[f'state/receipts/{TASK}{suffix}.json' for suffix in ('','-BACKUP','-ROLLBACK','-FORWARD-RECOVERY')]}
    request={'task_id':TASK,'title':'Critical retirement of sold UA-0002 only; preserve safe invariants',
      'description':'Approved UA-ART-UA0002-CRITICAL-DELETE-001 v1.0 Stage A. Existing target CRM row must be absent with matching deletion audit. Retire only exact sold listing and known aliases, update associated catalog/home/sitemap. Preserve all other data, prices, media, scripts and new operator edits. Worker recovery is forward retirement only, never restoration of sold vehicle. REVIEW DRAFT NOT_READY: fresh account quota, current admission facts and final independent review are missing.',
      'changed_paths':changes,'control_plane_version':'TASK107-R2','requested_min_class':'CRITICAL','production_required':True,'read_only':False,
      'ai_requested':False,'complexity':4,'storage_required_bytes':2147483648,
      'storage_probe':{'evidence_path':f'state/storage/{TASK}.json','evidence_sha256':None,'status':'NOT_READY_FRESH_ACCOUNT_QUOTA_REQUIRED'},
      'health_checks':['https://www.uaart.com.ua/','https://www.uaart.com.ua/video/katalog.html'],
      'critical':{'allow_crm_vehicle_data':True,'gate_b_authorized':True,'manifest_path':f'tasks/manifests/{TASK}.json','manifest_sha256':mh,
        'gate_a_path':f'tasks/gates/{TASK}.json','gate_a_sha256':gh,'owner_approval_path':f'tasks/approvals/{TASK}.production.json','owner_approval_sha256':ah},
      'execution':execution}
    rh=write(ROOT/'tasks/requests'/f'{TASK}.json',request)
    result={'status':'NOT_READY','task_id':TASK,'request_sha256':rh,'manifest_sha256':mh,'gate_a_sha256':gh,
      'owner_scope_approved':True,'gate_b_authorized':True,'launch_created':False,'storage_evidence_created':False,
      'production_actions_performed':False,'blockers':blockers,'package_file_sha256':files}
    write(ROOT/'REVIEW_PACK.json',result)
    print(json.dumps({k:result[k] for k in ('status','task_id','request_sha256','manifest_sha256','launch_created')}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker-dir',type=Path,required=True)
    parser.add_argument('--probe-one',type=Path,required=True);parser.add_argument('--probe-two',type=Path,required=True)
    args=parser.parse_args();build(args.worker_dir,args.probe_one,args.probe_two)
