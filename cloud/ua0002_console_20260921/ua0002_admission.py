#!/usr/bin/env python3
"""Read-only UA-0002 admission; optional private draft-plan output is explicit."""
from __future__ import annotations
import argparse, ast, hashlib, importlib, json, os, pathlib, re, shlex, sys, time
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path('/home/Carix')
SOURCE_NAMES = ('cars_ui.py','db.py','publication_fence.py','publikaciya.py',
 'publish_transaction_guard.py','run_all.py','start_safe.py','stranica.py',
 'ua_site_counters.py','ua_spec84_runtime.py','ua_spec_permanent.py','yadro.py',
 'uaart_connection_monitor.py','ua_crm_catalog_folders.py')
BASE='https://www.pythonanywhere.com/api/v0/user/Carix/'
def enc(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v): return hashlib.sha256(v).hexdigest()
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs): raise RuntimeError('API_REDIRECT_FORBIDDEN')
def api(endpoint):
 if endpoint not in ('always_on/','schedule/'): raise RuntimeError('GET_SCOPE')
 token=os.environ.get('API_TOKEN','').strip()
 if not token: raise RuntimeError('API_TOKEN_UNAVAILABLE')
 req=urllib.request.Request(BASE+endpoint,headers={'Authorization':'Token '+token},method='GET')
 with urllib.request.build_opener(NoRedirect()).open(req,timeout=40) as response:
  data=response.read(512*1024+1)
 if len(data)>512*1024: raise RuntimeError('PROVIDER_RESPONSE_SIZE')
 value=json.loads(data)
 if isinstance(value,dict): value=value.get('results',value.get('objects',value.get('tasks')))
 if not isinstance(value,list) or not all(isinstance(x,dict) for x in value): raise RuntimeError('PROVIDER_LIST_SHAPE')
 return value
def provider():
 always=api('always_on/'); scheduled=api('schedule/')
 a=sorted([{'id':r['id'],'command_sha256':sha(str(r.get('command','')).encode()),'enabled':r.get('enabled')} for r in always],key=lambda r:r['id'])
 s=sorted([{'id':r['id'],'command_sha256':sha(str(r.get('command','')).encode()),'hour':r.get('hour'),'minute':r.get('minute'),'interval':r.get('interval'),'enabled':r.get('enabled',True)} for r in scheduled],key=lambda r:r['id'])
 monitor=next(r for r in always if r.get('id')==270984)
 crm=next(r for r in always if r.get('id')==266084)
 if crm.get('command')!='python3.10 /home/Carix/start_safe.py' or crm.get('enabled') is not True or str(crm.get('state','')).lower()!='running': raise RuntimeError('CRM_SUPERVISOR_NOT_RUNNING')
 argv=shlex.split(monitor['command']); argv[0]=pathlib.Path(argv[0]).name
 if len(argv)<3 or argv[1:3]!=['-I','/home/Carix/uaart_connection_monitor.py']: raise RuntimeError('MONITOR_COMMAND_SCOPE')
 now=datetime.now(timezone.utc); next_times=[]
 for row in s:
  if row['enabled'] is False: continue
  minute,hour=row['minute'],row['hour']
  if type(minute) is not int or not 0<=minute<60: raise RuntimeError('SCHEDULE_MINUTE')
  if row['interval']=='daily' and type(hour) is int and 0<=hour<24:
   nxt=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
   if nxt<=now: nxt+=timedelta(days=1)
  elif row['interval']=='hourly':
   nxt=now.replace(minute=minute,second=0,microsecond=0)
   if nxt<=now: nxt+=timedelta(hours=1)
  else: raise RuntimeError('SCHEDULE_INTERVAL')
  next_times.append(nxt.timestamp())
 window=min(next_times or [time.time()+3600])
 if window-time.time()<=1800: raise RuntimeError('SCHEDULE_QUIET_WINDOW_TOO_SHORT')
 return {'reviewed':False,'provider_snapshot_sha256':sha(enc({'always_on':a,'scheduled':s})),
  'always_on':a,'scheduled':s,'safe_window_end_epoch':int(window),
  'allowed_python_cmdline_sha256':[sha(enc(argv))], 'provider_observed_epoch':int(time.time())}
def dry_run(plan, worker, package):
 """Pure candidate construction; never call retirement helpers that write journals."""
 from urllib.parse import urlsplit
 anchors=importlib.import_module('uaart_price_sync_runtime')._Anchors
 visibility=importlib.import_module('visibility_lifecycle')
 counters=importlib.import_module('ua_site_counters')
 proposed={}; records=None; target='UA-0002'
 for item in plan['shared_surfaces']:
  path=ROOT/item['path']; before=worker.read(path); source=before.decode('utf-8'); parsed=anchors(source)
  links=[(a,b) for a,b,href in parsed.anchors if re.fullmatch(re.escape(target)+r'(?:-diag)?(?:-[0-9a-f]{6,10})?\.html',urlsplit(href).path.rsplit('/',1)[-1])]
  articles=[(a,b) for a,b in parsed.articles if any(a<=x<y<=b for x,y in links)]
  spans=sorted(set(articles+[(a,b) for a,b in links if not any(x<=a<b<=y for x,y in articles)]))
  for a,b in reversed(spans): source=source[:a]+source[b:]
  if visibility.listing_present(source,target): raise RuntimeError('DRY_RUN_RESIDUAL_TARGET')
  if path.name=='katalog.html':
   original,_=counters.catalog_snapshot(before.decode('utf-8')); current,_=counters.catalog_snapshot(source)
   if current!={k:v for k,v in original.items() if k!=target}: raise RuntimeError('DRY_RUN_FOREIGN_CATALOG_CHANGE')
   if records is not None and records!=current: raise RuntimeError('DRY_RUN_CATALOG_MIRROR')
   records=current
  proposed[path]=(before,source)
 if records is None: raise RuntimeError('DRY_RUN_NO_CATALOG')
 counts={'all':len(records),**{s:0 for s in counters.STAGES}}
 for stage in records.values():
  if stage: counts[stage]+=1
 if sum(counts[s] for s in counters.STAGES)!=counts['all']: raise RuntimeError('DRY_RUN_UNKNOWN_STAGE')
 hashes={}
 for path,(before,source) in proposed.items():
  if path.name=='katalog.html': after=counters.patch_catalog(source,counts)
  elif plan['home_modes'][str(path.relative_to(ROOT))]=='MODERN_COUNTERS': after=counters.patch_home(source,counts)
  else:
   if 'stage-card' in source or 'outline-cta' in source: raise RuntimeError('DRY_RUN_HOME_MODE_DRIFT')
   after=source
  script=lambda s:re.findall(r'<script\b[^>]*>.*?</script\s*>',s,re.I|re.S)
  if script(before.decode('utf-8'))!=script(after): raise RuntimeError('DRY_RUN_SCRIPT_CHANGED')
  hashes[str(path.relative_to(ROOT))]=sha(after.encode())
 for rel in plan['sitemaps']: hashes[rel]=sha(worker.retire_sitemap(worker.read(ROOT/rel)))
 runner=importlib.import_module('ua0002_console_runner')
 if pathlib.Path(runner.__file__).resolve()!=pathlib.Path(plan['console_route']['runner_path']): raise RuntimeError('RUNNER_IMPORT_SCOPE')
 folder=runner.folder_proof(plan,proposed[ROOT/'video/katalog.html'][1])
 return {'status':'PASS','counter_proof':counts,'shared_after_sha256':hashes,'crm_folder_candidate_proof':folder}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--package',required=True,type=pathlib.Path); p.add_argument('--nonce',required=True)
 p.add_argument('--runner',required=True,type=pathlib.Path); p.add_argument('--plan-output',type=pathlib.Path)
 args=p.parse_args(); package=args.package.resolve(strict=True); runner=args.runner.resolve(strict=True)
 if not re.fullmatch(r'[A-Za-z0-9_-]{8,96}',args.nonce): raise RuntimeError('NONCE')
 if str(ROOT) in sys.path: raise RuntimeError('PRODUCTION_IMPORT_PATH_FORBIDDEN')
 sys.path.insert(0,str(package)); worker=importlib.import_module('remote_stage_a')
 if pathlib.Path(worker.__file__).parent!=package: raise RuntimeError('WORKER_MODULE_COLLISION')
 sources={}
 for name in SOURCE_NAMES:
  data=worker.read(ROOT/name); ast.parse(data,filename=name); sources[name]=sha(data)
 state=worker.db_state(); structure=worker.db_structure()
 if structure['card_delete'].get('observed') is not True: raise RuntimeError('TARGET_DELETE_AUDIT_EVENT_REQUIRED')
 if worker.VIN not in worker.read(ROOT/'video/UA-0002.html').decode().upper(): raise RuntimeError('HISTORICAL_VIN_MISMATCH')
 surfaces=[{'path':f'{folder}/{name}','kind':'CATALOG' if name=='katalog.html' else 'HOME'} for folder in ('site','video') for name in ('index.html','katalog.html')]
 public={x['path']:worker.fingerprint(ROOT/x['path']) for x in surfaces}; sitemaps=[]
 for folder in ('site','video'):
  root=ROOT/folder
  if root.resolve(strict=True)!=root: raise RuntimeError('PUBLIC_ROOT_SYMLINK')
  paths={root/'UA-0002.html',root/'UA-0002-diag.html',*root.glob('UA-0002*.html')}
  for path in paths:
   if not re.fullmatch(r'UA-0002(?:-diag)?(?:-[0-9a-f]{6,10})?\.html',path.name): raise RuntimeError('UNBOUND_ALIAS')
   f=worker.fingerprint(path); public[str(path.relative_to(ROOT))]=f if f['exists'] else {'exists':False}
  if (root/'sitemap.xml').exists():
   rel=f'{folder}/sitemap.xml'; sitemaps.append(rel); public[rel]=worker.fingerprint(root/'sitemap.xml')
 writers=provider()
 watchdog_argv=['python3.10','-B',str(runner),'--watchdog',str(package/'console-context.json')]
 writers['allowed_python_cmdline_sha256'].append(sha(enc(watchdog_argv)))
 plan={'contract':worker.CONTRACT,'version':1,'root':str(ROOT),'alwayson_id':266084,
  'target':{'id':8,'auto_number':'UA-0002','vin':worker.VIN},'nonce':args.nonce,
  'backup_dir':str(ROOT/'rezerv_publikacii'/('UA0002-delete-'+args.nonce)),
  'database_state_sha256':None,'package_sha256':{n:sha(worker.read(package/n)) for n in sorted(worker.PACKAGE)},
  'source_sha256':sources,'public_preimage':public,'shared_surfaces':surfaces,
  'home_modes':{'site/index.html':'LEGACY_TILES','video/index.html':'MODERN_COUNTERS'},'sitemaps':sitemaps,'writers':writers,
  'console_route':{'kind':'REVIEWED_DIRECT_CONSOLE_WITH_WATCHDOG','runner_path':str(runner),
   'runner_sha256':sha(worker.read(runner)),'watchdog_argv':watchdog_argv,'max_seconds':1500}}
 dry=dry_run(plan,worker,package)
 observed={'plan_draft_sha256':sha(enc(plan)+b'\n'),'target_absent':state['target_absent'],
  'cars_count':state['tables']['cars']['rows'],'integrity':state['integrity'],'delete_audit':structure['card_delete'],
  'provider':writers,'dry_run':dry,'processes':worker.process_inventory(),'source_hashes':sources,
  'public_preimage_sha256':sha(enc(public)),'public_route_count':len(public),'reviewed':False}
 if args.plan_output:
  out=args.plan_output
  if not out.is_absolute() or out.parent.resolve(strict=True)!=package: raise RuntimeError('DRAFT_PLAN_OUTPUT_SCOPE')
  fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as f: f.write(enc(plan)+b'\n'); f.flush(); os.fsync(f.fileno())
  observed['draft_plan_path']=str(out)
 else: observed['draft_plan']=plan
 print(json.dumps({'status':'ADMISSION_DRAFT_REQUIRES_REVIEW',**observed},sort_keys=True,separators=(',',':')))
if __name__=='__main__':
 try: main()
 except Exception as exc:
  error=str(exc) if isinstance(exc,RuntimeError) and re.fullmatch(r'[A-Z0-9_:.-]{1,160}',str(exc)) else type(exc).__name__
  print(json.dumps({'status':'FAIL','error_code':error})); raise SystemExit(1)
