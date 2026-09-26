"""New risk: real retirement saved plan across partial replace and later edit."""
import hashlib,json,sys,tempfile,types
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).parent; PUBLIC=HERE.parent/'pr114_review/cloud'; SOURCE=HERE.parent/'private_combined_candidate_v2'
for folder in ('task088_price_sync','task088_stage3_renderer','task088_autopilot_owner_policy','task088_v5_writer_fence'):
    sys.path.insert(0,str(PUBLIC/folder))
sys.path.insert(0,str(HERE.parent/'private_counter_candidate'))
import outbox
sys.modules['uaart_price_sync_outbox']=outbox
import visibility_lifecycle as V
import ua_site_counters as C
sha=lambda raw:hashlib.sha256(raw).hexdigest()
with tempfile.TemporaryDirectory(dir=HERE,prefix='plan-recovery-') as tmp:
    root=Path(tmp)
    for folder in ('video','site'):
        (root/folder).mkdir()
        for name in ('katalog.html','index.html'):
            (root/folder/name).write_bytes((SOURCE/folder/name).read_bytes())
    journal=root/'journal';(journal/'visibility').mkdir(parents=True,mode=0o700)
    binding=types.SimpleNamespace(db_path=root/'crm.db',journal_root=journal,
        resolve_visibility_surfaces=lambda code:[types.SimpleNamespace(kind='HOME',path=root/'video/index.html')])
    key=sha(b'independent-real-plan-crash'); original=V.atomic_bytes; switched=[]; interrupted=[]
    def atomic(path,data,mode,**kw):
        if kw.get('forward',True):
            if switched:
                interrupted.append(Path(path));raise KeyboardInterrupt()
            switched.append(Path(path))
        return original(path,data,mode,**kw)
    with patch.object(V,'atomic_bytes',atomic):
        try:V.retire_lists(binding,'UA-0001',key)
        except KeyboardInterrupt:pass
        else:raise AssertionError('Expected one isolated interruption')
    assert len(switched)==len(interrupted)==1
    plan=json.loads((journal/'visibility'/(key+'.retirement')).read_bytes())
    assert sha(switched[0].read_bytes())==plan['files'][str(switched[0])]['after_sha256']
    pending=interrupted[0]; exact_before=pending.read_bytes()
    pending.write_bytes(exact_before+b'\n<!-- NEWER_OPERATOR_EDIT -->\n')
    files=[Path(name) for name in plan['files']]
    preserved={str(p):p.read_bytes() for p in files}
    try:V.retire_lists(binding,'UA-0001',key)
    except V.VisibilityError as exc:assert str(exc)=='NEWER_PUBLIC_LIST_PRESERVED'
    else:raise AssertionError('Unknown operator write must block')
    assert preserved=={str(p):p.read_bytes() for p in files}
    # Fixture-only branch: restore the known pending preimage, then prove saved
    # afterimage resumes; production never automatically removes this conflict.
    pending.write_bytes(exact_before)
    V.retire_lists(binding,'UA-0001',key)
    assert all(sha(p.read_bytes())==plan['files'][str(p)]['after_sha256'] for p in files)
    assert all(not V.listing_present(p.read_text(),'UA-0001') for p in files)
    report={'status':'PASS','scope':'SAVED_REAL_HTML_ISOLATED_COPY_NO_LIVE_PASS',
        'reason':'Persisted retirement pre/postimage CAS after partial write and newer pending-file edit.',
        'checks':['ONE_PARTIAL_SWITCH_RECORDED','NEWER_OPERATOR_BYTES_PRESERVED_NO_REPLAY_WRITES','EXACT_SAVED_PLAN_RESUMES_WHEN_PREIMAGES_MATCH'],
        'lifecycle_sha256':sha(Path(V.__file__).read_bytes()),'counter_sha256':sha(Path(C.__file__).read_bytes()),
        'unchanged_suites_rerun':False}
    (HERE/'RETIREMENT_PLAN_RECOVERY_PROBE.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))
