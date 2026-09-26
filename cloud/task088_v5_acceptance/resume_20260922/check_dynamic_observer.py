"""Targeted synthetic validation; never connects to or reads production."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile

HERE = Path(__file__).parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path, required=True,
                    help='Exact original observe_point4_core.py; its fixed SHA256 is verified.')
parser.add_argument('--validation-output', type=Path,
                    default=HERE / 'DYNAMIC_OBSERVER_VALIDATION.json',
                    help='New result path; an existing result is never overwritten.')
args = parser.parse_args()
BASELINE = args.baseline
EXPECTED_BASELINE = '8fe6380652bab23c3329088690d551f1cad82905de822b8f94aef16b87a62935'
OBSERVER = HERE / 'observe_point4_core_dynamic.py'
old = b"                if len(codes) != 22 or not NEW_CODES <= codes:\n                    raise Stop('EXPECTED_CURRENT_22_PUBLISHED_CARS_REQUIRED')\n"
new = b"                # The validated published set is dynamic after normal CRM edits.\n                # database() still rejects duplicate or malformed public codes.\n                if not codes:\n                    raise Stop('PUBLISHED_CARS_REQUIRED')\n"
baseline = BASELINE.read_bytes()
assert hashlib.sha256(baseline).hexdigest() == EXPECTED_BASELINE
assert baseline.count(old) == 1
assert OBSERVER.read_bytes() == baseline.replace(old, new)
compile(OBSERVER.read_bytes(), str(OBSERVER), 'exec')
spec = importlib.util.spec_from_file_location('dynamic_observer', OBSERVER)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
results = {'only_obsolete_count_guard_changed': 'PASS'}


def fixture(root, numbers, *, duplicate=False, invalid=False):
    (root / 'autopilot_inbox/cloud').mkdir(parents=True)
    for folder in ('site', 'video'):
        (root / folder / 'foto').mkdir(parents=True)
    for name in M.SOURCES | M.DEPENDENCIES | M.EXTRA | {'analitika_wsgi.py', 'uaart_bridge_wsgi.py'}:
        (root / name).write_text("raise RuntimeError('PRIVATE_SOURCE_MUST_NOT_IMPORT_OR_EXPORT')\n")
    (root / 'wsgi.txt').write_text('# synthetic WSGI')
    conn = sqlite3.connect(root / 'crm.db')
    conn.executescript('CREATE TABLE cars(id INTEGER,auto_number TEXT,published INTEGER,status TEXT,price_uah INTEGER,price_georgia INTEGER,secret TEXT); CREATE TABLE audit(id INTEGER,secret TEXT);')
    rows = [(n, 'UA-%04d' % n, 1, 'ua_arrived' if n == 18 else 'ge_waiting',
             22900 if n == 18 else 10000 + n, 8750 if n == 10 else None,
             'PRIVATE_ROW_NEVER_EXPORT') for n in numbers]
    if duplicate:
        rows.append((999, rows[0][1], 1, 'ge_waiting', 11111, None, 'PRIVATE_DUPLICATE'))
    if invalid:
        rows[0] = (rows[0][0], '../unsafe', *rows[0][2:])
    conn.executemany('INSERT INTO cars VALUES(?,?,?,?,?,?,?)', rows)
    conn.execute('INSERT INTO audit VALUES(1,?)', ('PRIVATE_AUDIT_NEVER_EXPORT',))
    conn.commit()
    conn.close()
    for folder in ('site', 'video'):
        for n in numbers:
            code = 'UA-%04d' % n
            (root / folder / (code + '.html')).write_text('<html><body>Авто ' + code +
                '<a class="mcf-diag-cta" href="' + code + '-diag.html">Діагностика</a>' +
                '<img src="foto/' + code + '.jpg"></body></html>')
            (root / folder / (code + '-diag.html')).write_text('<html>Діагностика ' + code + '</html>')
            (root / folder / 'foto' / (code + '.jpg')).write_bytes(b'NO_MEDIA_BYTES_READ')
        for name in ('index', 'katalog', 'info', 'podbor'):
            (root / folder / (name + '.html')).write_text('<html>Фікстура ' + name + '</html>')
    return {'observed_wsgi_config.py': root / 'wsgi.txt',
            **{n: root / n for n in ('analitika_wsgi.py', 'uaart_bridge_wsgi.py', 'video/index.html', 'site/index.html')}}


def execute_case(label, numbers, *, duplicate=False, invalid=False):
    with tempfile.TemporaryDirectory(prefix='dynamic-core-', dir=HERE) as temporary:
        root = Path(temporary)
        routing = fixture(root, numbers, duplicate=duplicate, invalid=invalid)
        before = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in root.rglob('*') if p.is_file()}
        output = root / 'autopilot_inbox/cloud' / label
        value = M.CoreObserver(root, output, routing=routing, capture=True,
            self_sha256=hashlib.sha256(OBSERVER.read_bytes()).hexdigest(),
            part_max_bytes=16 * 1024).run()
        assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
                   for name, digest in before.items()), 'fixture business files mutated'
        if duplicate or invalid:
            assert value['status'] == 'PARTIAL_NOT_ACCEPTED'
            assert 'PUBLISHED_IDENTITIES_INVALID' in value['blockers']
            results[label] = 'REJECTED_PUBLISHED_IDENTITIES_INVALID'
            return
        if not numbers:
            assert value['status'] == 'PARTIAL_NOT_ACCEPTED'
            assert 'PUBLISHED_CARS_REQUIRED' in value['blockers']
            results[label] = 'REJECTED_PUBLISHED_CARS_REQUIRED'
            return
        assert value['status'] == 'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION', value['blockers']
        assert value['export_completed'] is True
        assert all(v is True for v in value['stability'].values())
        assert len(value['core_html']) == 2 * len(numbers) + 4
        assert len(value['diagnostic_html']) == 2 * len(numbers)
        assert value['database']['published_codes'] == sorted('UA-%04d' % n for n in numbers)
        assert value['database'] == value['second_database']
        assert value['schema_sha256'] == value['second_schema_sha256']
        if 2 not in numbers:
            assert 'site/UA-0002.html' not in value['core_html']
            assert 'video/UA-0002.html' not in value['core_html']
        rows = {row['auto_number']: row for row in value['published_rows']}
        if 18 in numbers:
            assert rows['UA-0018']['price_uah'] == 22900
        if 10 in numbers:
            assert rows['UA-0010']['price_georgia'] == 8750
        terminal = json.loads((output / 'summary.json').read_bytes())
        assert terminal == value
        export = json.loads((output / 'export_manifest.json').read_bytes())
        assert export == value['plaintext_export']
        reconstructed, next_index = {}, 0
        for item in export['parts']:
            raw = (output / item['path']).read_bytes()
            assert len(raw) == item['bytes'] <= 16 * 1024
            assert hashlib.sha256(raw).hexdigest() == item['sha256']
            for secret in (b'PRIVATE_SOURCE_MUST_NOT_IMPORT_OR_EXPORT', b'PRIVATE_ROW_NEVER_EXPORT', b'PRIVATE_AUDIT_NEVER_EXPORT'):
                assert secret not in raw
            for row in json.loads(raw)['records']:
                assert row['index'] == next_index
                next_index += 1
                prior = reconstructed.setdefault(row['name'], '')
                assert len(prior) == row['offset_chars']
                reconstructed[row['name']] = prior + row['text']
        assert next_index == export['chunk_records']
        for name, item in export['artifacts'].items():
            raw = reconstructed[name].encode()
            assert len(raw) == item['bytes']
            assert hashlib.sha256(raw).hexdigest() == item['sha256']
        results[label] = 'PASS'


execute_case('current_21_without_deleted_ua0002', [n for n in range(1, 23) if n != 2])
execute_case('future_23_dynamic', [n for n in range(1, 25) if n != 2])
execute_case('historical_new_code_removed', [n for n in range(1, 23) if n not in (2, 22)])
execute_case('duplicate_public_code', [1, 10, 18], duplicate=True)
execute_case('invalid_public_code', [1, 10, 18], invalid=True)
execute_case('empty_public_set', [])
report = {'status': 'PASS_LOCAL_SYNTHETIC_ONLY', 'checks': results,
          'observer_sha256': hashlib.sha256(OBSERVER.read_bytes()).hexdigest(),
          'baseline_sha256': EXPECTED_BASELINE, 'production_read': False,
          'production_write': False, 'remote_execution': False,
          'unchanged_full_suites_repeated': False,
          'independent_review': 'PENDING'}
target = args.validation_output
with target.open('x') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(json.dumps(report, indent=2))
