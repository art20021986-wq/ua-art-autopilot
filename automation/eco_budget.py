#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, tempfile, time
from pathlib import Path
from typing import Any
MAX_MODEL_CALLS=2; MAX_TOTAL_TOKENS=24_000; STATE_DIR=Path('state/eco_budget')
BLOCKING_CLASSES={'BILLING','QUOTA','ACCESS','UNKNOWN_PAID_OUTCOME'}
class EcoBudgetError(RuntimeError): pass
def _atomic_json(path:Path,value:dict[str,Any])->None:
 path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.'+path.name,dir=str(path.parent))
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as h: json.dump(value,h,ensure_ascii=False,indent=2,sort_keys=True); h.flush(); os.fsync(h.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def fingerprint(task_id:str,input_sha256:str)->str: return hashlib.sha256(f'{task_id}\0{input_sha256}'.encode()).hexdigest()
def ledger_path(task_id:str,input_sha256:str,root:Path=STATE_DIR)->Path:
 safe=''.join(c if c.isalnum() or c in '._-' else '_' for c in task_id); return root/f'{safe}-{fingerprint(task_id,input_sha256)[:20]}.json'
def load(task_id:str,input_sha256:str,root:Path=STATE_DIR)->dict[str,Any]:
 path=ledger_path(task_id,input_sha256,root)
 if path.exists():
  data=json.loads(path.read_text(encoding='utf-8'))
  if data.get('fingerprint')!=fingerprint(task_id,input_sha256): raise EcoBudgetError('ECO_FINGERPRINT_MISMATCH')
  return data
 return {'task_id':task_id,'input_sha256':input_sha256,'fingerprint':fingerprint(task_id,input_sha256),'model_calls':0,'reserved_tokens':0,'actual_tokens':0,'pending_reservation':0,'stage':'INTAKE','completed':False,'applied':False,'blocked':None,'history':[]}
def save(data:dict[str,Any],root:Path=STATE_DIR)->Path:
 path=ledger_path(data['task_id'],data['input_sha256'],root); _atomic_json(path,data); return path
def reserve(data:dict[str,Any],max_tokens:int)->None:
 if data.get('completed'): raise EcoBudgetError('ECO_DUPLICATE_COMPLETE')
 if data.get('blocked'): raise EcoBudgetError('ECO_BLOCKED:'+str(data['blocked']))
 if data.get('pending_reservation'): raise EcoBudgetError('ECO_UNKNOWN_PAID_OUTCOME')
 if max_tokens<0: raise EcoBudgetError('ECO_INVALID_TOKEN_RESERVATION')
 if data['model_calls']+1>MAX_MODEL_CALLS: raise EcoBudgetError('ECO_MODEL_CALL_BUDGET_EXHAUSTED')
 if data['reserved_tokens']+max_tokens>MAX_TOTAL_TOKENS: raise EcoBudgetError('ECO_TOKEN_BUDGET_EXHAUSTED')
 data['model_calls']+=1; data['reserved_tokens']+=max_tokens; data['pending_reservation']=max_tokens
 data['history'].append({'at':int(time.time()),'event':'MODEL_BUDGET_RESERVED','max_tokens':max_tokens})
def reconcile(data:dict[str,Any],actual_tokens:int)->None:
 if actual_tokens<0: raise EcoBudgetError('ECO_INVALID_ACTUAL_USAGE')
 if not data.get('pending_reservation'): raise EcoBudgetError('ECO_NO_PENDING_RESERVATION')
 data['actual_tokens']+=actual_tokens; data['pending_reservation']=0
 data['history'].append({'at':int(time.time()),'event':'MODEL_USAGE_RECONCILED','actual_tokens':actual_tokens})
def block(data:dict[str,Any],error_class:str)->None:
 kind=error_class.upper()
 if kind not in BLOCKING_CLASSES: raise EcoBudgetError('ECO_UNKNOWN_BLOCK_CLASS')
 data['blocked']=kind; data['pending_reservation']=0; data['history'].append({'at':int(time.time()),'event':'BLOCKED','class':kind})
def progress(data:dict[str,Any],stage:str)->None: data['stage']=stage; data['history'].append({'at':int(time.time()),'event':'STAGE','stage':stage})
def complete(data:dict[str,Any],applied:bool=False)->None:
 if data.get('pending_reservation'): raise EcoBudgetError('ECO_UNKNOWN_PAID_OUTCOME')
 data['stage']='COMPLETE'; data['completed']=True; data['applied']=bool(applied); data['history'].append({'at':int(time.time()),'event':'COMPLETE','applied':bool(applied)})
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument('task_id'); p.add_argument('input_sha256'); p.add_argument('--reserve',type=int); p.add_argument('--actual',type=int); p.add_argument('--stage'); p.add_argument('--block',choices=sorted(BLOCKING_CLASSES)); p.add_argument('--complete',action='store_true'); a=p.parse_args(); d=load(a.task_id,a.input_sha256)
 try:
  if a.reserve is not None: reserve(d,a.reserve)
  if a.actual is not None: reconcile(d,a.actual)
  if a.stage: progress(d,a.stage)
  if a.block: block(d,a.block)
  if a.complete: complete(d)
 except EcoBudgetError as exc:
  if str(exc)=='ECO_UNKNOWN_PAID_OUTCOME': block(d,'UNKNOWN_PAID_OUTCOME'); save(d)
  raise
 path=save(d); print(json.dumps({'status':'OK','ledger':str(path),'data':d},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
