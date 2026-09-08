#!/usr/bin/env python3
import tempfile
from pathlib import Path
from eco_budget import EcoBudgetError, block, complete, load, progress, reconcile, reserve, save
def expect_error(fn,marker):
 try: fn()
 except EcoBudgetError as exc: assert marker in str(exc),(marker,str(exc)); return
 raise AssertionError('expected '+marker)
def main():
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp); d=load('T1','a'*64,root); reserve(d,12000); reconcile(d,1000); save(d,root)
  d2=load('T1','a'*64,root); assert d2['model_calls']==1 and d2['pending_reservation']==0
  reserve(d2,12000); reconcile(d2,900); save(d2,root)
  d3=load('T1','a'*64,root); expect_error(lambda:reserve(d3,1),'MODEL_CALL_BUDGET_EXHAUSTED')
  progress(d3,'VERIFY'); complete(d3,applied=True); save(d3,root)
  d4=load('T1','a'*64,root); assert d4['completed'] and d4['stage']=='COMPLETE'; expect_error(lambda:reserve(d4,1),'DUPLICATE_COMPLETE')
  fresh=load('T1','b'*64,root); assert fresh['model_calls']==0 and fresh['fingerprint']!=d4['fingerprint']
  q=load('T2','c'*64,root); block(q,'QUOTA'); save(q,root); q2=load('T2','c'*64,root); expect_error(lambda:reserve(q2,100),'ECO_BLOCKED:QUOTA')
  t=load('T3','d'*64,root); expect_error(lambda:reserve(t,24001),'TOKEN_BUDGET_EXHAUSTED')
  u=load('T4','e'*64,root); reserve(u,500); save(u,root); u2=load('T4','e'*64,root); expect_error(lambda:reserve(u2,1),'UNKNOWN_PAID_OUTCOME'); assert u2['pending_reservation']==500
 print('ECO_BUDGET_TESTS_PASS')
if __name__=='__main__': main()
