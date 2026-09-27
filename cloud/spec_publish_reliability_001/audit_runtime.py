"""Read current specification code/state without importing live application modules."""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import zipfile

ROOT = Path('/home/Carix')
OUT = ROOT / 'spec_audit_20260928'
OUT.mkdir(mode=0o700, exist_ok=True)
NAMES = ('vin_spec_service.py', 'source_policy.py', 'profile_library.py',
         'ua_additional_spec.py', 'cars_ui.py', 'publikaciya.py',
         'ua_publish_requests.py', 'ua_crm_public_sync.py')
report = {'files': {}, 'databases': {}}
with zipfile.ZipFile(OUT / 'runtime.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in NAMES:
        path = ROOT / name
        if path.is_file():
            archive.write(path, name)
            report['files'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(ROOT.glob('*spec*.db')):
        with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True, timeout=5) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            report['databases'][path.name] = tables
            dest = OUT / path.name
            with sqlite3.connect(dest) as copy:
                db.backup(copy)
            os.chmod(dest, 0o600)
            archive.write(dest, path.name)
    with sqlite3.connect('file:' + str(ROOT / 'crm.db') + '?mode=ro', uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        columns = {r[1] for r in db.execute('PRAGMA table_info(cars)')}
        allowed = ('id','auto_number','vin','brand','make','model','year','engine','fuel','fuel_type',
                   'engine_cc','displacement','transmission','body','published','status')
        selected = [name for name in allowed if name in columns]
        rows = [dict(r) for r in db.execute('SELECT ' + ','.join(selected) + ' FROM cars')]
        archive.writestr('cars.json', json.dumps(rows, ensure_ascii=False, indent=2))
        report['cars'] = len(rows)
    archive.writestr('audit.json', json.dumps(report, ensure_ascii=False, indent=2))
os.chmod(OUT / 'runtime.zip', 0o600)
print('SPEC_AUDIT', json.dumps(report, ensure_ascii=False))
