#!/usr/bin/env python3
"""Scoped local integration; synthetic SQLite/quota/receipts are NOT production evidence."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
PATCH = HERE / 'cloud/task088_price_sync'
REPO = Path('/workspace/scratch/ae8e0003d3b0/routefix')
CORE = Path('/workspace/scratch/38dfdd094ece/pr114-offline/current_core_capture')
PRIVATE = Path('/workspace/scratch/38dfdd094ece/pr114-offline/private_before_20260920')
EVIDENCE = Path('/workspace/scratch/38dfdd094ece/pr114-offline/current_candidate_evidence')
CANDIDATE = Path('/workspace/scratch/38dfdd094ece/pr114-offline/current_candidate')
sys.dont_write_bytecode = True
sys.path[:0] = [str(PATCH)] + [str(REPO/'cloud'/p) for p in ('task088_price_sync','task088_stage3_renderer','task088_autopilot_owner_policy','task088_v5_writer_fence')]
import preflight as P
import build_preflight_bundle as B
import stage_preflight as S
import install_package as E
import initial_html_prices as M
import bound_catalog_reconciliation as A

checks=[]
def checked(name, condition):
    assert condition, name
    checks.append(name)
def rejected(name, call, text):
    try: call()
    except Exception as exc:
        checked(name, text in str(exc))
    else: raise AssertionError(name+': accepted')

checked('default_package_closure_unchanged',set(B.package_mapping(REPO)) == P.MODULES|P.TOOLS)
checked('bound_package_closure_exact',set(B.package_mapping(REPO,catalog_reconciliation=True)) == P.MODULES|P.TOOLS|P.RECONCILIATION_TOOLS)
checked('stager_default_mapping_matches_builder',S.package_mapping() == {k:str(v.relative_to(REPO)) for k,v in B.package_mapping(REPO).items()})
checked('stager_bound_mapping_matches_builder',S.package_mapping(catalog_reconciliation=True) == {k:str(v.relative_to(REPO)) for k,v in B.package_mapping(REPO,catalog_reconciliation=True).items()})
checked('binding_constants_match',P.CATALOG_RECONCILIATION == B.CATALOG_RECONCILIATION == S.CATALOG_RECONCILIATION)
rows=json.loads((CORE/'published_price_rows.json').read_bytes())
observer=(CORE/'summary.json').read_bytes()
with tempfile.TemporaryDirectory(prefix='pr114-preflight-test-') as tmp:
    root=Path(tmp)
    for path in PRIVATE.iterdir(): shutil.copyfile(path,root/path.name)
    for folder in ('site','video'): shutil.copytree(CORE/folder,root/folder)
    routing=json.loads((EVIDENCE/'OFFLINE_ROUTING_INPUT.json').read_bytes())
    for key, original in E.validate_routing(routing).items():
        if key in ('site/index.html','video/index.html'): continue
        original=Path(original)
        path=root/(original.relative_to(E.LIVE_ROOT) if original.is_relative_to(E.LIVE_ROOT) else Path('routing_external')/original.name)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'# synthetic local routing fixture only\n')
        routing['source_sha256'][key]=E.sha(path.read_bytes())
    conn=sqlite3.connect(root/'crm.db')
    conn.execute('CREATE TABLE cars (id INTEGER PRIMARY KEY, auto_number TEXT, published INTEGER, status TEXT, price_uah NUMERIC, price_georgia NUMERIC)')
    fields=('id','auto_number','published','status','price_uah','price_georgia')
    conn.executemany('INSERT INTO cars VALUES (?,?,?,?,?,?)',[[row[k] for k in fields] for row in rows])
    conn.execute('CREATE TABLE audit (id INTEGER PRIMARY KEY)')
    conn.commit()
    snapshot=E.database_snapshot(conn)
    conn.close()
    relative='autopilot_inbox/cloud/task088_price_sync_reconciliation_test'
    package=root/relative
    package.mkdir(parents=True)
    mapping=B.package_mapping(REPO,catalog_reconciliation=True)
    for name,path in mapping.items():
        updated=PATCH/name
        shutil.copyfile(updated if updated.is_file() else path,package/name)
    (package/P.CATALOG_RECONCILIATION['observer_file']).write_bytes(observer)
    quota={'observed_at':datetime.now(timezone.utc).isoformat(),'source':'PYTHONANYWHERE_AUTHENTICATED_ACCOUNT','account':'Carix','used_bytes':1,'limit_bytes':10**12}
    stage2={'task_id':'TASK088-GE-PRICE-CRM-STAGE2','status':'FINISHED','stage1_prerequisite':'PASS','stage2_status':'PASS','stage3_allowed':True,'installed_source_sha256':E.sha((root/'cars_ui.py').read_bytes()),'test_only':True}
    bundle={'contract':P.CONTRACT,'package_sha256':{name:E.sha((package/name).read_bytes()) for name in mapping},
      'source_sha256':{name:E.sha((root/name).read_bytes()) for name in E.SOURCES},
      'dependency_sha256':{name:E.sha((root/name).read_bytes()) for name in E.DEPENDENCIES},
      'system_inventory':E.system_inventory(root),'expected_published_codes':snapshot['published_codes'],
      'expected_stage_counts':{'korea':5,'sea':4,'georgia':7,'kiev':5},'quota_evidence':quota,
      'stage2_receipt':stage2,'routing':routing,'routing_evidence_sha256':E.sha(E.encoded(routing)),
      'homepage_policy':{'site/index.html':'PROTECTED_LEGACY_NOT_SERVED'},
      'catalog_reconciliation':dict(P.CATALOG_RECONCILIATION)}
    def run(label,data):
        raw=E.encoded(data)
        (package/'preflight_bundle.json').write_bytes(raw)
        report,path=P.run('preflight-reconciliation-'+label,E.sha(raw),test_root=root,package_relative=relative)
        return report,path
    default=copy.deepcopy(bundle)
    default.pop('catalog_reconciliation')
    default['package_sha256'].pop('bound_catalog_reconciliation.py')
    baseline,_=run('default',default)
    checked('absent_binding_retains_strict_stale_catalog_rejection',baseline['candidate_verification']=='FAIL' and all(baseline['html'][n]['error']=='INITIAL_UA_PRICE_CRM_MISMATCH' for n in A.TARGETS))
    report,path=run('exact',bundle)
    checked('canonical_preflight_bound_candidate_passes',report['candidate_verification']=='PASS')
    checked('no_production_gate_fabricated',report['status']=='BLOCKED' and report['gate_b']=='NOT_CREATED' and report['blockers']==['CANONICAL_CONTROL_BRIDGE_GATE_B_AND_ACTIVATION_NOT_RUN'])
    checked('46_html_candidates_and_66_total',len(report['html'])==46 and len(report['candidate_files'])==66)
    checked('all_candidates_match_independent_offline_candidate',all((path.parent/'candidate_root'/name).read_bytes()==(CANDIDATE/name).read_bytes() for name in report['candidate_files']))
    checked('actual_catalog_before_hash_retained',all(report['candidate_files'][n]['before_sha256']==A.ORIGINAL_CATALOG_SHA256==report['html'][n]['before_sha256'] for n in A.TARGETS))
    checked('explicit_original_intermediate_strict_final_chain',all(report['html'][n]['strict_migration_before_sha256']==report['catalog_reconciliation']['pages'][n]['intermediate_sha256'] and report['html'][n]['catalog_reconciliation']['original_sha256']==A.ORIGINAL_CATALOG_SHA256 for n in A.TARGETS))
    checked('private_schema_test_preserves_cars_audit',report['offline_schema_test']=='PASS_CRM_AND_AUDIT_UNCHANGED')
    checked('live_fixture_sources_html_database_unchanged',E.system_inventory(root)==bundle['system_inventory'] and E.database_snapshot(sqlite3.connect(root/'crm.db'))==snapshot)
    for label,value in [('null',None),('unknown',dict(P.CATALOG_RECONCILIATION,extra=True))]:
        bad=copy.deepcopy(bundle);bad['catalog_reconciliation']=value
        failed,_=run(label,bad)
        checked(label+'_binding_rejected',failed['candidate_verification']=='FAIL' and any('EXACT_CATALOG_RECONCILIATION_BINDING_REQUIRED' in b for b in failed['blockers']))
    target=package/P.CATALOG_RECONCILIATION['observer_file']
    target.write_bytes(observer+b' ')
    failed,_=run('observerdrift',bundle)
    checked('observer_byte_drift_rejected',failed['candidate_verification']=='FAIL' and any('OBSERVER_HASH_MISMATCH' in b for b in failed['blockers']))
    target.write_bytes(observer)
    originals,prepared,proof=P._prepare_catalog_reconciliation(root,package,P.CATALOG_RECONCILIATION,rows)
    first=root/'site/katalog.html';raw=first.read_bytes();first.write_bytes(raw+b' ')
    rejected('catalog_byte_drift_rejected',lambda:P._prepare_catalog_reconciliation(root,package,P.CATALOG_RECONCILIATION,rows),'EXACT_ORIGINAL_CATALOG_REQUIRED')
    first.write_bytes(raw)
    conflicting=[dict(row,price_usd=19900) if row['auto_number']=='UA-0018' else dict(row) for row in rows]
    _,prepared,_=P._prepare_catalog_reconciliation(root,package,P.CATALOG_RECONCILIATION,conflicting)
    rejected('full_row_alias_conflict_rejected_by_unchanged_migrator',lambda:M.migrate_catalog(prepared['site/katalog.html'].decode(),conflicting),'LEGACY_CATALOG_UA_PRICE_REQUIRES_RECONCILIATION')
    drift=copy.deepcopy(rows);next(r for r in drift if r['auto_number']=='UA-0018')['price_uah']=23000
    rejected('new_crm_price_not_reconciled_using_old_observation',lambda:P._prepare_catalog_reconciliation(root,package,P.CATALOG_RECONCILIATION,drift),'ACTUAL_STABLE_ROWS_REQUIRED')
    # Exercise archive + canonical staging data closure with local mocked reads only.
    buildrepo=root/'test_repository'
    for name, source in mapping.items():
        dest=buildrepo/source.relative_to(REPO)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes((package/name).read_bytes())
    observed=dict(contract='TASK088-V5-INSTALL-OBSERVATION-1',status='PASS',read_only=True,
        observed_at=datetime.now(timezone.utc).isoformat(),source_sha256=bundle['source_sha256'],
        dependency_sha256=bundle['dependency_sha256'],database=snapshot,system_inventory=bundle['system_inventory'],
        stage_counts=bundle['expected_stage_counts'],quota_evidence=quota)
    observation_file=root/'test_observation.json'; observation_file.write_bytes(E.encoded(observed))
    stage2_file=root/'test_stage2.json'; stage2_file.write_bytes(E.encoded(stage2))
    built=B.build(buildrepo,observation=observation_file,stage2_receipt=stage2_file,
        output_directory=root/'test_archive',catalog_reconciliation_observer=target)
    with zipfile.ZipFile(built['archive']) as archive:
        packed={name:archive.read(name) for name in archive.namelist()}
    archive_bundle=json.loads(packed['preflight_bundle.json'])
    checked('builder_observer_data_exact_in_archive',packed[P.CATALOG_RECONCILIATION['observer_file']]==observer)
    checked('builder_code_pins_exclude_json_but_bind_exact_helper',set(archive_bundle['package_sha256'])==P.MODULES|P.TOOLS|P.RECONCILIATION_TOOLS)
    remote={S.REPO+'a'*40+'/cloud/task088_price_sync/preflight_bundle.json':packed['preflight_bundle.json']}
    remote.update({S.REPO+'a'*40+'/'+path:packed[name] for name,path in S.package_mapping(catalog_reconciliation=True).items()})
    remote[S.REPO+'a'*40+'/cloud/task088_price_sync/'+P.CATALOG_RECONCILIATION['observer_file']]=observer
    def mocked_open(url,timeout):
        return io.BytesIO(remote[url])
    S.ROOT=root/'staged';S.ROOT.mkdir()
    with patch.object(sys,'argv',['stage_preflight.py','a'*40,built['bundle_sha256'],'--staging-id','test-unique-20260922']), patch.object(S.urllib.request,'urlopen',mocked_open):
        S.main()
    staged=S.ROOT/'task088_price_sync_test-unique-20260922'
    checked('stager_exact_archive_payload_no_network',all((staged/name).read_bytes()==data for name,data in packed.items()))
result={'status':'PASS_LOCAL_SYNTHETIC_INTEGRATION_ONLY','checks':checks,'count':len(checks),
'production_changed':False,'canonical_preflight_executed_on_server':False,'gate_b':False,
'fixture':'Actual captured HTML/private source before-images; synthetic local SQLite, routing source bytes, quota and Stage2 receipt; no server invocation.',
'code_sha256':{p.name:E.sha(p.read_bytes()) for p in PATCH.glob('*.py')}}
(HERE/'SCOPED_INTEGRATION_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
