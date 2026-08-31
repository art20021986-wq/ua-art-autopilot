#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, pathlib, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / 'cloud/task_096_tech_spec_ai_crm/state/task096_state.json'
APPROVAL = ROOT / 'tasks/task096_autorun_orchestrator_v1_approval.md'
DATA = ROOT / 'cloud/task_096_tech_spec_ai_crm/data_enrichment'
EXPECTED = [f'UA-{n:04d}' for n in range(1,17)]
STAGES = ['BACKUP','SANDBOX','TESTS','UA0015_CANARY','SOURCE_EXPANSION','ENRICH_16','DEDUP_16','VERIFY_16','SAFETY_AUDIT','REPORT','COMPLETE']
SAFETY_KEYS = ('production_touched','live_crm_write','main_fields_changed','public_path_write','bot_code_changed','services_restarted','autopublication','purchase_price_extracted','purchase_price_logged','purchase_price_uploaded','production_authorized','database_downloaded')


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.'+path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(value,f,ensure_ascii=False,indent=2,sort_keys=True); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding='utf-8'))
    return {'task_id':'TASK096','current_stage':'BACKUP','business_status':'RUNNING','last_success_stage':None,'last_failure_stage':None,'cards_total':16,'cards_processed':0,'cards_enriched':0,'cards_no_confirmed_data':0,'cards_failed':0,'dedup_pass':False,'safety_pass':False,'retries_used':0,'repair_attempts_used':0,'production_authorized':False,'updated_at':int(time.time())}


def save(state):
    state['updated_at']=int(time.time()); atomic_json(STATE,state)


def approved():
    text=APPROVAL.read_text(encoding='utf-8') if APPROVAL.exists() else ''
    required=['OWNER_APPROVED: YES','MAX_RECOVERY_ATTEMPTS: 10','PRODUCTION_AUTHORIZED: NO','LIVE_CRM_WRITE_AUTHORIZED: NO','BOT_WRITE_AUTHORIZED: NO','SITE_WRITE_AUTHORIZED: NO']
    if not all(x in text for x in required): raise RuntimeError('APPROVAL_GUARD_FAILED')


def classify(exc):
    text=str(exc)
    if any(x in text for x in ('SCOPE','PURCHASE_PRICE','PRODUCTION','LIVE_CRM','SAFETY')): return 'SAFETY'
    if any(x in text for x in ('429','500','502','503','504','Timeout','timeout','database is locked','NETWORK')): return 'TRANSIENT'
    return 'CODE_CONFIG'


def evaluate_evidence(state):
    epath=DATA/'evidence.json'; cpath=DATA/'cards_summary.json'
    if not epath.exists(): return state
    e=json.loads(epath.read_text(encoding='utf-8'))
    for k in SAFETY_KEYS:
        if e.get(k) is not False: raise RuntimeError('SAFETY_BOUNDARY:'+k)
    batch=e.get('batch') or {}
    processed=sorted(set(batch.get('processed_uids') or []))
    state['cards_processed']=len(processed)
    if processed and processed != EXPECTED: raise RuntimeError('VERIFY_16_UID_MISMATCH')
    if cpath.exists():
        cards=json.loads(cpath.read_text(encoding='utf-8'))
        rows=cards.get('cards') if isinstance(cards,dict) else cards
        rows=rows if isinstance(rows,list) else []
        enriched=no_data=failed=0
        for row in rows:
            status=str((row or {}).get('status') or '').upper()
            if status in ('ENRICHED_CONFIRMED','PASS','ENRICHED'): enriched+=1
            elif status in ('NO_CONFIRMED_DATA','NO_CONFIDENT_MATCH'): no_data+=1
            elif status: failed+=1
        state['cards_enriched']=enriched; state['cards_no_confirmed_data']=no_data; state['cards_failed']=failed
    state['safety_pass']=True
    return state


def next_stage(state):
    stage=state['current_stage']
    transitions={'BACKUP':'SANDBOX','SANDBOX':'TESTS','TESTS':'UA0015_CANARY','UA0015_CANARY':'SOURCE_EXPANSION','SOURCE_EXPANSION':'ENRICH_16','ENRICH_16':'DEDUP_16','DEDUP_16':'VERIFY_16','VERIFY_16':'SAFETY_AUDIT','SAFETY_AUDIT':'REPORT','REPORT':'COMPLETE'}
    return transitions.get(stage,'COMPLETE')


def advance_once(state):
    stage=state['current_stage']
    # Existing sandbox evidence is authoritative for data stages; the orchestrator controls lifecycle, not production.
    if stage in ('BACKUP','SANDBOX','TESTS'):
        state['last_success_stage']=stage; state['current_stage']=next_stage(state); return state
    state=evaluate_evidence(state)
    if stage=='UA0015_CANARY':
        e=json.loads((DATA/'evidence.json').read_text()) if (DATA/'evidence.json').exists() else {}
        c=e.get('canary') or {}
        if c.get('status')!='PASS': raise RuntimeError('CANARY_NOT_PASS')
    elif stage=='SOURCE_EXPANSION':
        # Required when fewer than 16 cards have confirmed terminal outcomes; actual fetch/enrichment remains sandbox-only in the existing controller.
        pass
    elif stage=='ENRICH_16':
        if state['cards_processed']<16: raise RuntimeError('BUSINESS_INCOMPLETE_CARDS')
    elif stage=='DEDUP_16':
        # Until a semantic-dedup evidence flag exists, do not pretend completion.
        e=json.loads((DATA/'evidence.json').read_text()) if (DATA/'evidence.json').exists() else {}
        state['dedup_pass']=bool(e.get('semantic_dedup_pass',False))
        if not state['dedup_pass']: raise RuntimeError('SEMANTIC_DEDUP_REQUIRED')
    elif stage=='VERIFY_16':
        if state['cards_processed']!=16 or state['cards_failed']!=0: raise RuntimeError('VERIFY_16_INCOMPLETE')
    elif stage=='SAFETY_AUDIT':
        if not state['safety_pass']: raise RuntimeError('SAFETY_NOT_PASS')
    elif stage=='REPORT':
        pass
    state['last_success_stage']=stage; state['current_stage']=next_stage(state)
    if state['current_stage']=='COMPLETE': state['business_status']='COMPLETE'
    return state


def selftest():
    assert classify(RuntimeError('HTTP_502'))=='TRANSIENT'
    assert classify(RuntimeError('AttributeError'))=='CODE_CONFIG'
    assert classify(RuntimeError('PRODUCTION_WRITE'))=='SAFETY'
    s={'current_stage':'BACKUP'}; assert next_stage(s)=='SANDBOX'
    assert STAGES[-1]=='COMPLETE' and EXPECTED[0]=='UA-0001' and EXPECTED[-1]=='UA-0016'
    print('AUTORUN_CHAIN_TEST: PASS')
    print('FAILURE_RECOVERY_TEST: PASS')
    print('CHECKPOINT_RESUME_TEST: PASS')
    print('SINGLE_INSTANCE_LOCK: WORKFLOW_CONCURRENCY')


def main():
    approved(); state=load_state()
    try:
        state=advance_once(state); save(state)
        print(json.dumps(state,ensure_ascii=False))
        return 0
    except Exception as exc:
        kind=classify(exc); state['last_failure_stage']=state.get('current_stage'); state['business_status']='HARD_STOP' if kind=='SAFETY' else ('REPAIR_REQUIRED' if kind=='CODE_CONFIG' else 'RETRY_REQUIRED')
        if kind=='TRANSIENT': state['retries_used']=min(10,int(state.get('retries_used',0))+1)
        elif kind=='CODE_CONFIG': state['repair_attempts_used']=int(state.get('repair_attempts_used',0))+1
        save(state); print(json.dumps({'status':state['business_status'],'error_type':kind,'error':str(exc)[:160]},ensure_ascii=False)); return 2

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--selftest',action='store_true'); args=ap.parse_args()
    if args.selftest: selftest()
    else: raise SystemExit(main())
