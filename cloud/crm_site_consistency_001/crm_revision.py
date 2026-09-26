"""Include related photo/download and specification state in sync revisions."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path


def snapshot(root='/home/Carix'):
    root = Path(root)
    journal = root / '.video_sinhron.json'
    raw = journal.read_bytes()
    ledger = json.loads(raw)
    if not isinstance(ledger, dict):
        raise RuntimeError('Invalid photo ledger')
    conn = sqlite3.connect((root / 'crm.db').resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    result = {}
    codes = set()
    try:
        conn.execute('BEGIN')
        for row in conn.execute('SELECT * FROM cars WHERE published=1 ORDER BY id').fetchall():
            row = dict(row)
            code = row.get('auto_number', '')
            if not isinstance(code, str) or not re.fullmatch(r'UA-\d{4,}', code) or code in codes:
                raise RuntimeError('Missing or duplicate published auto_number')
            codes.add(code)
            related = {
                'schema': 2, 'car': row, 'photos': ledger.get('foto:' + code),
                'media': [dict(r) for r in conn.execute('SELECT * FROM media WHERE car_id=? ORDER BY id', (row['id'],))],
                'specification': [dict(r) for r in conn.execute('SELECT * FROM additional_specification WHERE car_uid=? ORDER BY id', (code,))],
            }
            digest = hashlib.sha256(json.dumps(related, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
            result[str(row['id'])] = {'code': code, 'sha256': digest}
    finally:
        conn.close()
    if journal.read_bytes() != raw:
        raise RuntimeError('Photo ledger changed during revision snapshot')
    return result
