"""Scoped offline evidence for core observer; no production or network calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
from unittest.mock import patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('core_observer_fixture',HERE/'observe_point4_core.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)

def fixture(root):
    (root/'autopilot_inbox/cloud').mkdir(parents=True)
    for folder in ('video','site'):
        (root/folder/'foto').mkdir(parents=True)
    for name in M.SOURCES | M.DEPENDENCIES | M.EXTRA | {'analitika_wsgi.py','uaart_bridge_wsgi.py'}:
        (root/name).write_text("raise RuntimeError('PRIVATE_SOURCE_MUST_NOT_IMPORT_OR_EXPORT')\n")
    (root/'uaart_price_sync_outbox.py').write_text('# runtime present fixture')
    (root/'wsgi.txt').write_text('# routing fixture')
    routing={'observed_wsgi_config.py':root/'wsgi.txt',
        **{name:root/name for name in ('analitika_wsgi.py','uaart_bridge_wsgi.py','video/index.html','site/index.html')}}
    db=sqlite3.connect(root/'crm.db')
    db.executescript('CREATE TABLE cars(id INTEGER, auto_number TEXT,published INTEGER,status TEXT,price_uah INTEGER,price_georgia INTEGER,secret TEXT); CREATE TABLE audit(id INTEGER,secret TEXT);')
    for i in range(1,23):
        db.execute('INSERT INTO cars VALUES(?,?,?,?,?,?,?)',(i,'UA-%04d'%i,1,'kr_bought',10000+i,None,'PRIVATE_ROW_NEVER_EXPORT'))
    db.execute('INSERT INTO audit VALUES(1,?)',('PRIVATE_AUDIT_NEVER_EXPORT',));db.commit();db.close()
    for folder in ('site','video'):
        for i in range(1,23):
            code='UA-%04d'%i
            (root/folder/(code+'.html')).write_text('<html><body>Авто 零 '+code+
                '<a class="mcf-diag-cta" href="'+code+'-diag.html">Діагностика</a>'+
                '<img src="foto/'+code+'.jpg"></body></html>')
            (root/folder/(code+'-diag.html')).write_text('<html><body>Diagnostics '+code+
                '<img src="foto/'+code+'.jpg"></body></html>')
            (root/folder/'foto'/(code+'.jpg')).write_bytes(b'NOT_READ_MEDIA_BYTES')
        for name in ('index','katalog','info','podbor'):
            (root/folder/(name+'.html')).write_text('<html><body>'+('Фікстура 零 \"\n'*700)+'</body></html>')
    return routing

results={}
with tempfile.TemporaryDirectory(prefix='core-observer-check-',dir=HERE) as tmp:
    root=Path(tmp);routing=fixture(root)
    class NoMediaRead(M.CoreObserver):
        def read_file(self,path,**kwargs):
            assert Path(path).suffix!='.jpg','media bytes requested'
            return super().read_file(path,**kwargs)
    output=root/'autopilot_inbox/cloud/stable'
    with patch.object(M.os,'scandir',side_effect=AssertionError('recursive inventory forbidden')):
        value=NoMediaRead(root,output,routing=routing,part_max_bytes=16*1024).run()
    assert value['status']=='PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION',value['blockers']
    assert value['export_completed'] is True
    assert len(value['core_html'])==48 and len(value['diagnostic_html'])==44 and len(value['supporting_html'])==4
    assert value['captured_public_html_files']==96 and all(value['stability'].values())
    assert len(value['runtime_modules'])==11
    assert value['runtime_modules']['uaart_price_sync_outbox.py']['exists'] is True
    assert value['runtime_modules']['visibility_lifecycle.py']=={'exists':False}
    assert not value['full_inventory_observed'] and not value['gate_b'] and not value['backup']
    assert not value['media_bytes_hashed'] and 'system_inventory_sha256' not in value
    assert all(item['content_sha256'] is None for item in value['media_reference_metadata'].values())
    results['scoped48_core44_diagnostics4_supporting_no_scan_no_media_read']='PASS'
    files=value['plaintext_export']['parts'];assert len(files)>1
    reconstructed={};next_index=0
    for entry in files:
        raw=(output/entry['path']).read_bytes()
        assert len(raw)==entry['bytes']<=16*1024 and b'\n' not in raw
        assert hashlib.sha256(raw).hexdigest()==entry['sha256']
        for forbidden in (b'PRIVATE_SOURCE_MUST_NOT_IMPORT_OR_EXPORT',b'PRIVATE_ROW_NEVER_EXPORT',b'PRIVATE_AUDIT_NEVER_EXPORT'):
            assert forbidden not in raw
        part=json.loads(raw)
        for record in part['records']:
            assert record['index']==next_index;next_index+=1
            old=reconstructed.setdefault(record['name'],'')
            assert len(old)==record['offset_chars']
            reconstructed[record['name']]+=record['text']
    assert next_index==value['plaintext_export']['chunk_records']
    for name,item in value['plaintext_export']['artifacts'].items():
        raw=reconstructed[name].encode()
        assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']
        if name.startswith(('video/','site/')):
            assert raw==(root/name).read_bytes()==(output/'public_html'/name).read_bytes()
    assert stat.S_IMODE(output.stat().st_mode)==0o700
    assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in output.rglob('*') if p.is_file())
    results['one_line_parts_exact_byte_bound_roundtrip_private_data_excluded_private_modes']='PASS'
    before=(output/'summary.json').read_bytes()
    try:
        M.CoreObserver(root,output,routing=routing).run();raise AssertionError('reuse accepted')
    except M.Stop as exc:
        assert str(exc)=='OUTPUT_ALREADY_EXISTS_RECONCILE_DO_NOT_REPEAT'
    assert (output/'summary.json').read_bytes()==before
    results['existing_output_refused_without_overwrite']='PASS'
    class Drift(M.CoreObserver):
        def core_pass(self,number,names):
            if number==2:
                (self.root/'cars_ui.py').write_text('# actual operator successor')
            return super().core_pass(number,names)
    changed=Drift(root,root/'autopilot_inbox/cloud/drift',routing=routing).run()
    assert changed['status']=='PARTIAL_NOT_ACCEPTED'
    assert 'OBSERVATION_DRIFT_DO_NOT_REUSE_CANDIDATE' in changed['blockers']
    assert (root/'cars_ui.py').read_text()=='# actual operator successor'
    results['source_drift_detected_preserved_no_rollback']='PASS'
    class SQLDrift(M.CoreObserver):
        calls=0
        def database(self):
            self.calls+=1
            if self.calls==2:
                db=sqlite3.connect(self.root/'crm.db');db.execute('UPDATE cars SET price_georgia=8800 WHERE id=1');db.commit();db.close()
            return super().database()
    changed=SQLDrift(root,root/'autopilot_inbox/cloud/sql-drift',routing=routing).run()
    assert changed['status']=='PARTIAL_NOT_ACCEPTED' and not changed['stability']['database_and_published_rows']
    results['second_read_operator_price_drift_detected']='PASS'
    class InterruptAfterOne(M.CoreObserver):
        captures_started=0
        def read_file(self,path,**kwargs):
            if kwargs.get('collect'):
                self.captures_started+=1
                if self.captures_started==2: raise M.Stop('TIME_BOUND_EXCEEDED')
            return super().read_file(path,**kwargs)
    stopped=InterruptAfterOne(root,root/'autopilot_inbox/cloud/partial',routing=routing).run()
    assert stopped['status']=='PARTIAL_NOT_ACCEPTED' and stopped['captured_public_html_files']==1
    assert len(list((root/'autopilot_inbox/cloud/partial/public_html').rglob('*.html')))==1
    results['interrupted_core_pass_retains_completed_capture_and_partial_outcome']='PASS'
    class Slow(M.CoreObserver):
        def core_pass(self,number,names):
            self.phase='CORE_HTML_PASS_'+str(number)
            time.sleep(2)
            return super().core_pass(number,names)
    begin=time.monotonic();stopped=Slow(root,root/'autopilot_inbox/cloud/deadline',routing=routing,seconds=1).run()
    assert stopped['status']=='PARTIAL_NOT_ACCEPTED' and time.monotonic()-begin<2
    assert (root/'autopilot_inbox/cloud/deadline/partial_export_outcome.json').is_file()
    results['total_alarm_interrupts_collection_and_saves_partial_export_outcome']='PASS'
    (root/'cars_ui.py').unlink();(root/'cars_ui.py').symlink_to(root/'db.py')
    stopped=M.CoreObserver(root,root/'autopilot_inbox/cloud/symlink',routing=routing).run()
    assert stopped['status']=='PARTIAL_NOT_ACCEPTED' and 'REGULAR_BOUNDED_FILE_REQUIRED' in stopped['blockers']
    results['source_symlink_refused']='PASS'
    (root/'cars_ui.py').unlink();(root/'cars_ui.py').write_text('# fixture restored')
    (root/'visibility_lifecycle.py').symlink_to(root/'db.py')
    stopped=M.CoreObserver(root,root/'autopilot_inbox/cloud/runtime-symlink',routing=routing).run()
    assert stopped['status']=='PARTIAL_NOT_ACCEPTED' and 'REGULAR_BOUNDED_FILE_REQUIRED' in stopped['blockers']
    results['eleven_runtime_modules_explicit_presence_absence_and_symlink_refusal']='PASS'
report={'status':'PASS','scope':'LOCAL_SYNTHETIC_ONLY','checks':results,
    'observer_sha256':hashlib.sha256((HERE/'observe_point4_core.py').read_bytes()).hexdigest(),
    'production_read':False,'production_write':False,'remote_execution':False}
(HERE/'CORE_OBSERVER_FIXTURE_VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
