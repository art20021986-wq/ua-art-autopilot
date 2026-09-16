#!/usr/bin/env python3
"""Pure reviewable maintenance inventory; no authority creation or live calls.

Missing observation != absent file. This output is preparation for the upstream
verified route, not an executable owner command or an external-writer receipt.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import code_handoff_v4 as handoff
import platform_control

HERE = Path(__file__).resolve().parent
DOMAIN = 'www.uaart.com.ua'
REQUIRED_EVIDENCE = {
    'fresh_main_and_execution_identity': 'Current main, unique existing run/nonce/epoch and exact plan binding',
    'authenticated_live_preconditions': 'All 17 live path hashes or explicitly proven absence, plus three dependency hashes',
    'platform_pause_ownership': 'Fresh account readback of four original task IDs/settings and original webapp enabled state',
    'all_prior_writer_drain': 'Provider-confirmed termination of prior Always On, cron/manual and old WSGI writers, including waiters',
    'loaded_new_runtime': 'Verified handoff and loaded WSGI/worker hashes, health readback before resume',
    'exact_owner_authorization': 'Separate exact-plan command required by the verified recovery route',
    'current_runtime_canary': 'Versioned canary for changed runtime; historical v1 PASS is not reused',
    'overall_gate_b_and_source10': 'Actual final17v3 execution plus permitted source10 evidence and remaining full Gate B checks',
    'account_quota': 'Fresh authenticated PA account used/quota bytes, bound receipt; 70% warning, 80% deployment stop, 90% emergency stop; shared statvfs is only absolute free bytes',
}

def digest(value): return hashlib.sha256(handoff.canonical(value)).hexdigest()

def prepare(candidate, inventory, live=None):
    manifest, _ = handoff.inspect_candidate(candidate)
    if inventory.get('webapp',{}).get('domain') != DOMAIN:
        raise RuntimeError('EXACT_WEBAPP_REQUIRED')
    rows = platform_control.normalize_inventory({k: inventory[k] for k in ('always_on','schedule')})
    live = live or {}
    if isinstance(live, dict) and live.get('schema') == 'UA-ART-LIVE17-PRECONDITIONS-1':
        if (set(live) != {'schema','root','hashes','observed_at','read_only','application_imported'}
                or live['root'] != '/home/Carix' or live['read_only'] is not True
                or live['application_imported'] is not False or type(live['hashes']) is not dict
                or set(live['hashes']) != set(manifest['files'])):
            raise RuntimeError('LIVE17_CAPTURE_SCOPE')
        for name, value in live['hashes'].items():
            if value is not None and not (isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)):
                raise RuntimeError('LIVE17_CAPTURE_HASH:'+name)
        live = {'capture_receipt_sha256': digest(live), 'captured_at': live['observed_at'],
                'files': {name: {'state': 'ABSENT' if value is None else 'PRESENT', 'sha256': value}
                          for name, value in live['hashes'].items()}}
    if not isinstance(live, dict) or set(live) - {'capture_receipt_sha256','captured_at','files','dependencies'}:
        raise RuntimeError('LIVE_OBSERVATION_SCHEMA')
    observed = live.get('files', {})
    if not isinstance(observed, dict) or set(observed) - set(manifest['files']):
        raise RuntimeError('LIVE_FILE_SCOPE')
    writes, missing = [], []
    for name, output in sorted(manifest['files'].items()):
        value = observed.get(name)
        if value is None:
            before = {'state':'UNOBSERVED','sha256':None}
            missing.append('/home/Carix/'+name)
        elif type(value) is dict and set(value) == {'state','sha256'}:
            if value['state'] == 'ABSENT' and value['sha256'] is None:
                before = value
            elif value['state'] == 'PRESENT' and isinstance(value['sha256'],str) and re.fullmatch('[0-9a-f]{64}',value['sha256']):
                before = value
            else: raise RuntimeError('LIVE_HASH_OR_EXPLICIT_ABSENCE_REQUIRED:'+name)
        else: raise RuntimeError('LIVE_PRECONDITION_SCHEMA:'+name)
        writes.append({'path':'/home/Carix/'+name,'before':before,'after_sha256':output['after_sha256'],
                       'backup':'EXCLUSIVE_SESSION_BACKUP_BEFORE_WRITE','mutation':'HASH_CONDITIONAL_CODE_FILE_ONLY'})
    evidence = [{'id':key,'requirement':value,'status':'UPSTREAM_VERIFICATION_REQUIRED'} for key,value in REQUIRED_EVIDENCE.items()]
    if missing:
        evidence[1]['missing_paths'] = missing
    evidence[3]['current_exact_blocker'] = 'No documented PA API proves full old-process drain; UI task/console process lists and Kill exist, old WSGI termination remains unproven.'
    pins = {name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in
            ('code_handoff_v4.py','server_fence.py','platform_control.py')}
    historical_path = HERE / 'evidence/handoff-v3-server-result.json'
    historical = json.loads(historical_path.read_bytes())
    historical_sha = hashlib.sha256(historical_path.read_bytes()).hexdigest()
    if (historical_sha != 'd4de16383b4b5afba0bebb6cd16e7d1bb13c51f98bb9967cad7f61a0401e2fe2'
            or historical['status'] != 'PASS' or historical['tests'] != 30):
        raise RuntimeError('HISTORICAL_V3_EVIDENCE_CHANGED')
    local_path = HERE / 'evidence/handoff-v4-actual17-local-result.json'
    local = json.loads(local_path.read_bytes())
    if (local.get('status') != 'PASS' or local.get('candidate_manifest_sha256') != handoff.MANIFEST_SHA256
            or local.get('installer_sha256') != pins['code_handoff_v4.py']
            or local.get('candidate_pin_was_patched_for_test') is not False
            or local.get('algorithm_byte_identical_after_three_admission_literal_substitutions') is not True):
        raise RuntimeError('EXACT_LOCAL_V4_ADMISSION_EVIDENCE_REQUIRED')
    validation = {
        'historical_v3_server': {
            'path': 'evidence/handoff-v3-server-result.json', 'sha256': historical_sha,
            'status': historical['status'], 'tests': historical['tests'],
            'finished_at': historical['finished_at'],
            'scope': 'UNCHANGED_V3_ALGORITHM; SYNTHETIC_FILES_FAKE_AUTHORITY; NOT_A_V4_SERVER_RUN',
            'rerun_for_version_label_only': False,
        },
        'current_v4_local': {
            'path': 'evidence/handoff-v4-actual17-local-result.json',
            'sha256': hashlib.sha256(local_path.read_bytes()).hexdigest(),
            'status': local['status'], 'finished_at': local['finished_at'],
            'scope': local['validation_scope'],
            'fixture_authority_quota_and_session': local['fixture_authority_quota_and_session'],
            'fixture_legacy_bytes': local['fixture_legacy_bytes'],
            'production_authority_provided': False,
        },
    }
    plan = {'schema':'UA-ART-MAINTENANCE-READINESS-V3','status':'BLOCKED_BEFORE_EXACT_EXECUTION_PLAN',
            'candidate_id':manifest['candidate_id'],'candidate_manifest_sha256':handoff.MANIFEST_SHA256,
            'observed_main':inventory.get('main_sha'),'current_main_verified':False,'execution_identity':'UNASSIGNED',
            'observation_only':True,'inventory_sha256':digest(inventory),'live_observation':live,
            'tasks':[{**row,'maintenance_action':'TEMPORARILY_DISABLE_SAME_ID','restore_enabled':row['enabled']} for row in rows],
            'webapp':{'domain':DOMAIN,'source_directory':inventory['webapp'].get('source_directory'),
                      'wsgi_path':inventory['webapp'].get('wsgi_path'),
                      'original_enabled':inventory['webapp'].get('enabled','UNOBSERVED'),
                      'maintenance_action':'DISABLE_DURING_REVIEWED_WINDOW_THEN_RESTORE_EXACT_ORIGINAL_STATE',
                      'impact':'Webapp service is temporarily unavailable during the window; disabling does not prove old WSGI drain.'},
            'code_writes':writes,'unchanged_dependencies':manifest['execution_dependency_pins'],
            'terminal_source_pins':pins,'validation_evidence':validation,'required_evidence':evidence,
            'rollback':{'mode':'EXACT_OWNED_BACKUP_BYTES_MODES_MTIME','foreign_write':'STOP_DO_NOT_OVERWRITE',
                        'crash':'KEEP_TASKS_PAUSED_REACQUIRE_VERIFIED_OWNERSHIP_THEN_ROLLBACK_ONLY',
                        'terminal_readback':'CodeHandoff.read_terminal; old filenames or prior PASS are not current proof',
                        'resume':'Only upstream verified terminal and fresh loaded-runtime health allow original task/webapp restoration'},
            'crm_html_media_writes':0,'application_imports':False,'owner_command':None,
            'no_repeat':'Use same existing recovery session and exact plan; no new TASK120 or production task',
            'overall_gate_b':'NOT_EVALUATED'}
    return {**plan,'readiness_sha256':digest(plan)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--inventory',type=Path,required=True);p.add_argument('--live-observation',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    plan=prepare(a.candidate,json.loads(a.inventory.read_bytes()),json.loads(a.live_observation.read_bytes()) if a.live_observation else None)
    handoff._exclusive(a.output.absolute(),json.dumps(plan,sort_keys=True,indent=2,ensure_ascii=False).encode()+b'\n')
    print(json.dumps({'status':plan['status'],'code_write_count':len(plan['code_writes']),
                      'missing_precondition_count':len(plan['required_evidence'][1].get('missing_paths',[])),
                      'owner_command':None,'production_changed':False,'readiness_sha256':plan['readiness_sha256']}))

if __name__=='__main__':main()
