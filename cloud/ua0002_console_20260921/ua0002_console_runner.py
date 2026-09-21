#!/usr/bin/env python3
"""Reviewed console authority around the unchanged UA-0002 retirement worker.

One CRM pause covers backup and retirement. An independent, source-bound
watchdog owns recovery if the console owner dies. No global HALT is modified.
"""
from __future__ import annotations
import argparse, ast, fcntl, hashlib, importlib, json, os, pathlib, re, shlex, signal, sqlite3, types
import subprocess, sys, time
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit
HERE=pathlib.Path(__file__).resolve().parent
def enc(v): return (json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()
def compact(v): return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def require(v,m):
 if not v: raise RuntimeError(m)
def atomic(path,v):
 path=pathlib.Path(path); tmp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
 fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'wb') as f: f.write(enc(v)); f.flush(); os.fsync(f.fileno())
 os.replace(tmp,path)
 fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try: os.fsync(fd)
 finally: os.close(fd)
def start_ticks(pid):
 try: return pathlib.Path('/proc/%d/stat'%pid).read_text().rsplit(')',1)[1].split()[19]
 except (FileNotFoundError,ProcessLookupError): return None
def bound(path,expected):
 path=pathlib.Path(path)
 require(path.is_absolute() and path.parent.resolve(strict=True)==HERE and not path.is_symlink(),'PRIVATE_PATH_SCOPE')
 raw=path.read_bytes(); require(sha(raw)==expected,'PLAN_SHA_MISMATCH'); return json.loads(raw)
def load(plan_path,plan_sha):
 plan=bound(plan_path,plan_sha); route=plan.get('console_route',{})
 require(route.get('kind')=='REVIEWED_DIRECT_CONSOLE_WITH_WATCHDOG','CONSOLE_ROUTE_REQUIRED')
 require(route.get('runner_path')==str(pathlib.Path(__file__).resolve()),'RUNNER_PATH')
 require(route.get('runner_sha256')==sha(pathlib.Path(__file__).read_bytes()),'RUNNER_SHA')
 require(plan['writers'].get('reviewed') is True,'INDEPENDENT_PLAN_REVIEW_REQUIRED')
 require(type(route.get('max_seconds')) is int and 60<=route['max_seconds']<=1500,'DURATION_SCOPE')
 require(route.get('watchdog_argv')==['python3.10','-I','-B',str(pathlib.Path(__file__).resolve()),'--watchdog',str(HERE/'console-context.json')],'WATCHDOG_ARGV_SCOPE')
 expected=plan.get('package_sha256',{}).get('remote_lifecycle.py')
 require(sha((HERE/'remote_lifecycle.py').read_bytes())==expected,'LIFECYCLE_SHA')
 if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))
 life=importlib.import_module('remote_lifecycle')
 require(pathlib.Path(life.__file__).resolve().parent==HERE,'LIFECYCLE_IMPORT')
 life.provider_admission=provider_admission
 life.child=child
 return plan,life
def provider_admission(api,plan,operation,plan_path,plan_sha,result_path,*,resume=False):
 require(operation=='install_verify','CONSOLE_OPERATION_SCOPE')
 writers=plan['writers']; require(writers['reviewed'] is True,'WRITER_REVIEW')
 reserve=1800 if resume else 1800+plan['console_route']['max_seconds']
 require(time.time()+reserve<writers['safe_window_end_epoch'],'QUIET_WINDOW_EXPIRED')
 def objects(v):
  if isinstance(v,dict): v=v.get('results',v.get('objects',v.get('tasks')))
  require(isinstance(v,list) and all(isinstance(r,dict) for r in v),'PROVIDER_LIST'); return v
 a=objects(api.request('GET','always_on/')); s=objects(api.request('GET','schedule/'))
 aa=[]
 for r in a:
  entry={'id':r.get('id'),'command_sha256':sha(str(r.get('command','')).encode()),'enabled':r.get('enabled')}
  if resume and entry['id']==266084 and entry['enabled'] is False: entry['enabled']=True
  aa.append(entry)
 ss=[{'id':r.get('id'),'command_sha256':sha(str(r.get('command','')).encode()),'hour':r.get('hour'),'minute':r.get('minute'),'interval':r.get('interval'),'enabled':r.get('enabled',True)} for r in s]
 sort=lambda v:sorted(v,key=lambda r:r['id'])
 require(sort(aa)==sort(writers['always_on']),'PROVIDER_ALWAYS_ON_DRIFT')
 require(sort(ss)==sort(writers['scheduled']),'PROVIDER_SCHEDULE_DRIFT')
 require(sha(compact({'always_on':sort(aa),'scheduled':sort(ss)}))==writers['provider_snapshot_sha256'],'PROVIDER_SNAPSHOT_SHA')
 now=datetime.now(timezone.utc)
 for row in ss:
  if row['enabled'] is False: continue
  h,m=row['hour'],row['minute']; require(type(m) is int and 0<=m<60,'SCHEDULE_MINUTE')
  if row['interval']=='daily' and type(h) is int and 0<=h<24:
   nxt=now.replace(hour=h,minute=m,second=0,microsecond=0)
   if nxt<=now:nxt+=timedelta(days=1)
  elif row['interval']=='hourly':
   nxt=now.replace(minute=m,second=0,microsecond=0)
   if nxt<=now:nxt+=timedelta(hours=1)
  else: raise RuntimeError('SCHEDULE_INTERVAL')
  require((nxt-now).total_seconds()>1800,'SCHEDULE_DUE')
 monitor=next((r for r in a if r.get('id')==270984),None); require(monitor is not None,'MONITOR_ABSENT')
 argv=shlex.split(monitor['command']); argv[0]=pathlib.Path(argv[0]).name
 expected=[sha(compact(argv)),sha(compact(plan['console_route']['watchdog_argv']))]
 require(sorted(writers['allowed_python_cmdline_sha256'])==sorted(expected),'PYTHON_ALLOWLIST_SCOPE')
 return {'route':'REVIEWED_DIRECT_CONSOLE_WITH_WATCHDOG','observed_epoch':int(time.time()),'provider_snapshot_sha256':writers['provider_snapshot_sha256']}
def worker(operation,plan_path,plan_sha):
 env=dict(os.environ); env.pop('API_TOKEN',None); env['PYTHONDONTWRITEBYTECODE']='1'
 r=subprocess.run([sys.executable,'-I','-B',str(HERE/'remote_stage_a.py'),'--operation',operation,'--plan',str(plan_path),'--plan-sha256',plan_sha],
  stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=600,env=env,check=False)
 try:v=json.loads(r.stdout.decode().strip())
 except Exception:raise RuntimeError('WORKER_RECEIPT_INVALID')
 require(v.get('plan_sha256')==plan_sha and v.get('operation')==operation,'WORKER_IDENTITY')
 require(r.returncode==0 and v.get('status')=='PASS','WORKER_PHASE_FAILED:'+str(v.get('error_code','UNKNOWN'))[:160])
 return v
def child(operation,plan_path,plan_sha):
 if operation=='install_verify':
  backup=worker('backup',plan_path,plan_sha)
  atomic(HERE/'console-backup-proof.json',backup)
  plan=json.loads(pathlib.Path(plan_path).read_bytes())
  folder_proof(plan,candidate_catalog(plan))
  result=worker('install_verify',plan_path,plan_sha)
  require(result['backup_manifest_sha256']==backup['backup_manifest_sha256'],'SAME_PAUSE_BACKUP_BINDING')
  result['crm_folder_proof']=folder_proof(json.loads(pathlib.Path(plan_path).read_bytes()))
  return result
 result=worker(operation,plan_path,plan_sha)
 if operation=='recover':result['crm_folder_proof']=folder_proof(json.loads(pathlib.Path(plan_path).read_bytes()))
 return result
def candidate_catalog(plan):
 """Recheck the current paused CRM against the exact proposed catalog before writes."""
 source_path=HERE/'uaart_price_sync_runtime.py'
 require(sha(source_path.read_bytes())==plan['package_sha256']['uaart_price_sync_runtime.py'],'CANDIDATE_PARSER_SHA')
 parser=importlib.import_module('uaart_price_sync_runtime')
 require(pathlib.Path(parser.__file__).resolve().parent==HERE,'CANDIDATE_PARSER_MODULE')
 source=(pathlib.Path(plan['root'])/'video/katalog.html').read_text(encoding='utf-8')
 parsed=parser._Anchors(source)
 links=[(a,b) for a,b,href in parsed.anchors if re.fullmatch(r'UA-0002(?:-diag)?(?:-[0-9a-f]{6,10})?\.html',urlsplit(href).path.rsplit('/',1)[-1])]
 articles=[(a,b) for a,b in parsed.articles if any(a<=x<y<=b for x,y in links)]
 spans=sorted(set(articles+[(a,b) for a,b in links if not any(x<=a<b<=y for x,y in articles)]))
 for a,b in reversed(spans):source=source[:a]+source[b:]
 return source
def folder_proof(plan, catalog_source=None):
 """Execute only the hash-bound pure folder parser; never import CRM startup."""
 root=pathlib.Path(plan['root']); source=(root/'ua_crm_catalog_folders.py').read_bytes()
 require(sha(source)==plan['source_sha256']['ua_crm_catalog_folders.py'],'FOLDER_SOURCE_CHANGED')
 tree=ast.parse(source)
 for node in tree.body:
  if isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):continue
  if isinstance(node,ast.Import):require(all(x.name=='re' for x in node.names),'PURE_FOLDER_IMPORT_SCOPE')
  elif isinstance(node,ast.ImportFrom):require(node.module in {'html.parser','typing'},'PURE_FOLDER_IMPORT_SCOPE')
  elif isinstance(node,(ast.FunctionDef,ast.ClassDef)):require(not node.decorator_list,'PURE_FOLDER_DECORATOR_SCOPE')
  elif isinstance(node,ast.Assign):require(all(isinstance(t,ast.Name) and t.id in {'_CAR_NUMBER','_BRAND','_STRUCTURAL'} for t in node.targets),'PURE_FOLDER_CONSTANT_SCOPE')
  else:raise RuntimeError('PURE_FOLDER_TOP_LEVEL_SCOPE')
 module=types.ModuleType('_ua0002_reviewed_folder_parser');exec(compile(tree,'ua_crm_catalog_folders.py','exec'),module.__dict__)
 conn=sqlite3.connect((root/'crm.db').as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
 try:cards=[dict(r) for r in conn.execute('SELECT * FROM cars ORDER BY id')]
 finally:conn.close()
 require(not any(r.get('id')==8 or r.get('auto_number')=='UA-0002' for r in cards),'TARGET_PRESENT_IN_FOLDER_DB')
 text=catalog_source if catalog_source is not None else (root/'video/katalog.html').read_text(encoding='utf-8')
 groups=module.partition_by_catalog(cards,module.parse_catalog(text))
 return {'status':'PASS','total':len(cards),'catalog':len(groups['catalog']),'unpublished':len(groups['unpublished']),'target_absent':True}
def watchdog(context_path):
 require(pathlib.Path(context_path)==HERE/'console-context.json','WATCHDOG_CONTEXT_SCOPE')
 with (HERE/'console-watchdog.lock').open('a+') as lock:
  fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  ctx=json.loads(pathlib.Path(context_path).read_bytes()); plan,life=load(ctx['plan_path'],ctx['plan_sha256'])
  require(ctx['owner_pid']==ctx['owner_pgid'] and ctx['owner_pid']>1,'OWNER_GROUP_IDENTITY')
  atomic(HERE/'console-watchdog-ready.json',{'context_sha256':sha(enc(ctx)),'pid':os.getpid(),'start_ticks':start_ticks(os.getpid())})
  deadline=ctx['started_epoch']+plan['console_route']['max_seconds']
  while True:
   result=pathlib.Path(ctx['result_path'])
   if result.exists():
    v=json.loads(result.read_bytes())
    if v.get('plan_sha256')==ctx['plan_sha256'] and v.get('safe_to_stop') is True:return
   alive=start_ticks(ctx['owner_pid'])==ctx['owner_start_ticks']
   if not alive or time.time()>deadline:break
   time.sleep(2)
  # The owner created this fresh process group before spawning any worker.
  # Terminate its remaining worker(s) before attempting the same locked journal.
  # Linux retains the PGID while group members live; an extant mismatching leader blocks.
  observed=start_ticks(ctx['owner_pid'])
  require(observed is None or observed==ctx['owner_start_ticks'],'OWNER_PID_REUSED')
  try:os.killpg(ctx['owner_pgid'],signal.SIGTERM)
  except ProcessLookupError:pass
  time.sleep(3)
  try:os.killpg(ctx['owner_pgid'],signal.SIGKILL)
  except ProcessLookupError:pass
  time.sleep(1)
  journal=pathlib.Path(ctx['result_path']).with_suffix('.journal.json')
  if not journal.exists():
   atomic(ctx['result_path'],{'status':'FAIL','operation':'install_verify','plan_sha256':ctx['plan_sha256'],
    'error':'OWNER_ENDED_BEFORE_PAUSE_INTENT','no_pause_intent':True,'safe_to_stop':True})
   return
  value=life.execute('install_verify',pathlib.Path(ctx['plan_path']),ctx['plan_sha256'],pathlib.Path(ctx['result_path']))
  atomic(HERE/'console-watchdog-recovery.json',value)
def owner(args):
 plan,life=load(args.plan,args.plan_sha256)
 require(args.result.parent.resolve(strict=True)==HERE and not args.result.is_symlink(),'RESULT_PATH_SCOPE')
 require(bool(os.environ.get('API_TOKEN','').strip()),'API_TOKEN_UNAVAILABLE')
 require(not (HERE/'console-context.json').exists(),'CONSOLE_CONTEXT_ALREADY_EXISTS_USE_OWNED_RECOVERY')
 try:os.setsid()
 except PermissionError:pass
 require(os.getpgrp()==os.getpid(),'DEDICATED_PROCESS_GROUP_REQUIRED')
 ctx={'plan_path':str(args.plan),'plan_sha256':args.plan_sha256,'result_path':str(args.result),
  'owner_pid':os.getpid(),'owner_pgid':os.getpgrp(),'owner_start_ticks':start_ticks(os.getpid()),'started_epoch':time.time()}
 atomic(HERE/'console-context.json',ctx)
 fd=os.open(HERE/'console-watchdog.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
 with os.fdopen(fd,'ab') as log:
  watcher=subprocess.Popen(plan['console_route']['watchdog_argv'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)
 ready=HERE/'console-watchdog-ready.json'; deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  if ready.exists():
   v=json.loads(ready.read_bytes())
   if v.get('context_sha256')==sha(enc(ctx)) and v.get('pid')==watcher.pid and start_ticks(watcher.pid)==v.get('start_ticks'):break
  require(watcher.poll() is None,'WATCHDOG_START_FAILED'); time.sleep(.1)
 else:raise RuntimeError('WATCHDOG_NOT_READY_NO_PAUSE')
 value=life.execute('install_verify',args.plan,args.plan_sha256,args.result)
 print(json.dumps(value,sort_keys=True,separators=(',',':')))
 return 0 if value.get('status')=='PASS' else 1
def main():
 p=argparse.ArgumentParser(); p.add_argument('--watchdog',type=pathlib.Path);p.add_argument('--plan',type=pathlib.Path)
 p.add_argument('--plan-sha256');p.add_argument('--result',type=pathlib.Path);args=p.parse_args()
 if args.watchdog:watchdog(args.watchdog);return 0
 require(args.plan is not None and args.plan_sha256 and args.result is not None,'OWNER_ARGS')
 return owner(args)
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:
  print(json.dumps({'status':'FAIL','error_type':type(exc).__name__,'error_code':str(exc)[:200] if isinstance(exc,RuntimeError) else 'CONSOLE_RUNNER_ERROR'}));raise SystemExit(1)
