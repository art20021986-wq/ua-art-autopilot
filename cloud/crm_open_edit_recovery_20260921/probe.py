"""Bounded read-only CRM diagnosis. Only its own evidence JSON is written."""
import collections
import datetime
import hashlib
import json
import pathlib
import re
import sqlite3
import time

root = pathlib.Path('/home/Carix')
result = {'task': 'CRM-CARD-RECOVERY-20260921', 'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'business_writes': False}
result['sources'] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ('cars_ui.py', 'db.py', 'start_safe.py')}
log = pathlib.Path('/var/log/alwayson-log-266084.log')
if log.exists():
    with log.open('rb') as stream:
        stream.seek(max(0, log.stat().st_size - 120000))
        lines = stream.read(120000).decode('utf-8', 'replace').splitlines()
    patterns = ('database is locked', 'message is too long', "can't parse entities", 'timedout', 'conflict', 'badrequest', 'traceback', 'application started', 'photos opening timeout', 'videos opening timeout')
    text = '\n'.join(lines).lower()
    result['log'] = {'modified_at': log.stat().st_mtime, 'sample_bytes_max': 120000, 'counts': {p: text.count(p) for p in patterns}}
    # Only exception class names and application stack frames; never log message values.
    result['log']['exception_classes'] = dict(collections.Counter(re.findall(r'\b([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|TimedOut|BadRequest|Conflict)):', text)))
    frames = [line.strip() for line in lines if re.search(r'File "/home/Carix/[^"\n]+", line \d+, in [A-Za-z_]', line)]
    result['log']['last_application_frames'] = frames[-16:]
    result['log']['last_timestamps'] = re.findall(r'20\d\d-\d\d-\d\d[ T]\d\d:\d\d:\d\d', '\n'.join(lines))[-5:]
else:
    result['log'] = {'visible': False}

try:
    started = time.monotonic()
    conn = sqlite3.connect('file:/home/Carix/crm.db?mode=ro', uri=True, timeout=2.0)
    conn.execute('PRAGMA query_only=ON')
    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + 4.0
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    result['db'] = {'journal_mode': conn.execute('PRAGMA journal_mode').fetchone()[0], 'quick_check': conn.execute('PRAGMA quick_check').fetchone()[0]}
    cols = {row[1] for row in conn.execute('PRAGMA table_info(cars)')}
    fields = [name for name in ('id', 'auto_number', 'condition_text', 'description', 'brand', 'model', 'vin', 'gearbox') if name in cols]
    rows = conn.execute('SELECT ' + ','.join(fields) + ' FROM cars').fetchall()
    result['db']['cars_count'] = len(rows)
    result['db']['read_seconds'] = round(time.monotonic() - started, 4)
    result['db']['display_risks'] = []
    for row in rows:
        risks = [{'field': name, 'characters': len(str(row[name] or '')), 'html_metacharacters': any(c in str(row[name] or '') for c in '<>&')} for name in fields if name not in ('id', 'auto_number') and (len(str(row[name] or '')) > 2500 or any(c in str(row[name] or '') for c in '<>&'))]
        if risks:
            result['db']['display_risks'].append({'id': row['id'], 'auto_number': row['auto_number'] if 'auto_number' in fields else None, 'fields': risks})
    conn.close()
except Exception as error:
    result['db'] = {'error_class': type(error).__name__, 'error': str(error)[:160]}

out = pathlib.Path(__file__).with_suffix('.json')
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
print('CRM_READONLY_PROBE_FINISHED', str(out))
