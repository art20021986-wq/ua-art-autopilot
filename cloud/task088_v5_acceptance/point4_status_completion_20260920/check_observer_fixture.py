"""Small independent fixtures for new observer, never production imports/read."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import time

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('observer_fixture_target', HERE / 'observe_current_point4.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture(root):
    (root / 'autopilot_inbox/cloud').mkdir(parents=True)
    for folder in ('site', 'video'):
        (root / folder).mkdir()
    for name in mod.SOURCES | mod.DEPENDENCIES | mod.EXTRA | {'analitika_wsgi.py', 'uaart_bridge_wsgi.py'}:
        (root / name).write_text("raise RuntimeError('MUST_NOT_IMPORT_PRIVATE_FIXTURE')\n")
    routing = {name: root / name for name in ('analitika_wsgi.py', 'uaart_bridge_wsgi.py', 'video/index.html', 'site/index.html')}
    (root / 'wsgi.txt').write_text('# fixture-only routing bytes')
    routing['observed_wsgi_config.py'] = root / 'wsgi.txt'
    conn = sqlite3.connect(root / 'crm.db')
    conn.executescript('CREATE TABLE cars(id INTEGER, auto_number TEXT, published INTEGER, status TEXT, price_uah INTEGER, price_georgia INTEGER, private_note TEXT); CREATE TABLE audit(id INTEGER, detail TEXT);')
    for i in range(1, 23):
        conn.execute('INSERT INTO cars VALUES(?,?,?,?,?,?,?)', (i, 'UA-%04d' % i, 1, 'kr_bought', 1000+i, None if i==2 else 700+i, 'PRIVATE_NEVER_EXPORT'))
    conn.execute('INSERT INTO audit VALUES(1,?)', ('PRIVATE_AUDIT_NEVER_EXPORT',))
    conn.commit()
    cars = [dict(zip([x[0] for x in conn.execute('SELECT * FROM cars').description], row)) for row in conn.execute('SELECT * FROM cars ORDER BY rowid')]
    audit = [{'id':1,'detail':'PRIVATE_AUDIT_NEVER_EXPORT'}]
    expected = {'cars_sha256':mod.sha(mod.encoded(cars)), 'audit_sha256':mod.sha(mod.encoded(audit))}
    conn.close()
    for folder in ('site', 'video'):
        for name in ['UA-%04d'%i for i in range(1,23)] + ['index','katalog']:
            (root / folder / (name+'.html')).write_text('<html>Фікстура '+name+' 零</html>\n')
    return routing, expected


results = {}
with tempfile.TemporaryDirectory(prefix='observer-proof-', dir=HERE) as temporary:
    root = Path(temporary)
    routing, expected = fixture(root)
    out = root / 'autopilot_inbox/cloud/stable'
    value = mod.Observer(root, out, capture=True, routing=routing).run()
    assert value['status'] == 'PASS_DOUBLE_READ_STABLE_OBSERVATION', value
    assert len(value['published_rows']) == 22 and len(value['core_html']) == 48
    assert value['database']['cars_sha256'] == expected['cars_sha256']
    assert value['database']['audit_sha256'] == expected['audit_sha256']
    assert all(value['stability'].values())
    assert len(value['sources_dependencies_extra']) == 19
    payload = (out / 'public_inputs.jsonl').read_bytes()
    assert b'PRIVATE_NEVER_EXPORT' not in payload and b'PRIVATE_AUDIT_NEVER_EXPORT' not in payload
    lines = [json.loads(line) for line in payload.splitlines()]
    final = lines.pop()
    reconstructed = {}
    for i, row in enumerate(lines):
        assert row['index'] == i and len(row['text']) <= 3000
        text = reconstructed.setdefault(row['name'], '')
        assert len(text) == row['offset_chars']
        reconstructed[row['name']] += row['text']
    assert final['chunk_records'] == len(lines)
    for name, item in final['artifacts'].items():
        raw = reconstructed[name].encode()
        assert len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256']
        if name.startswith(('site/', 'video/')):
            assert raw == (root/name).read_bytes() == (out/'public_html'/name).read_bytes()
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in out.rglob('*') if p.is_file())
    results['stable_dynamic22_digest_compatibility_plaintext_roundtrip_private_output'] = 'PASS'
    old = hashlib.sha256((out/'summary.json').read_bytes()).hexdigest()
    try:
        mod.Observer(root, out, routing=routing).run()
        raise AssertionError('reused output')
    except mod.Stop as exc:
        assert str(exc) == 'OUTPUT_ALREADY_EXISTS_RECONCILE_DO_NOT_REPEAT'
    assert hashlib.sha256((out/'summary.json').read_bytes()).hexdigest() == old
    results['existing_output_refused_without_overwrite'] = 'PASS'
    class Drift(mod.Observer):
        calls = 0
        def database(self):
            self.calls += 1
            if self.calls == 2:
                c=sqlite3.connect(self.root/'crm.db');c.execute('UPDATE cars SET price_georgia=9999 WHERE id=1');c.commit();c.close()
            return super().database()
    value = Drift(root, root/'autopilot_inbox/cloud/drift', routing=routing).run()
    assert value['status'] == 'PARTIAL_NOT_ACCEPTED' and 'OBSERVATION_DRIFT_DO_NOT_REUSE_CANDIDATE' in value['blockers']
    c=sqlite3.connect(root/'crm.db');assert c.execute('SELECT price_georgia FROM cars WHERE id=1').fetchone()[0]==9999;c.close()
    results['operator_change_detected_and_preserved'] = 'PASS'
    (root/'cars_ui.py').unlink();(root/'cars_ui.py').symlink_to(root/'db.py')
    value = mod.Observer(root, root/'autopilot_inbox/cloud/symlink', routing=routing).run()
    assert value['status'] == 'PARTIAL_NOT_ACCEPTED' and 'REGULAR_BOUNDED_FILE_REQUIRED' in value['blockers']
    results['source_symlink_refused'] = 'PASS'
    (root/'cars_ui.py').unlink();(root/'cars_ui.py').write_text('# fixture')
    class Slow(mod.Observer):
        def inventory(self, number, core):
            self.phase='INVENTORY_PASS_'+str(number)
            time.sleep(3)
            return super().inventory(number,core)
    begin=time.monotonic()
    value = Slow(root,root/'autopilot_inbox/cloud/timeout',seconds=1,routing=routing).run()
    assert value['status']=='PARTIAL_NOT_ACCEPTED' and value['blockers']==['TIME_BOUND_EXCEEDED']
    assert time.monotonic()-begin < 2.5
    results['hard_collection_deadline_precise_partial_report'] = 'PASS'

report={'status':'PASS','checks':results,'production_read':False,'production_written':False,
        'observer_sha256':hashlib.sha256((HERE/'observe_current_point4.py').read_bytes()).hexdigest()}
(HERE/'OBSERVER_FIXTURE_VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
