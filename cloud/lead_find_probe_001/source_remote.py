"""Read-only probe (owner 2026-11-25: the test enquiry OR-000008 «ТЕСТ реклама (Claude)» — «убери, мне она не нужна»).

Finds every place the enquiry is kept, so its removal can be exact: the order database (order_requests.db, found under
/home/Carix) and crm.db, both opened read-only. For each table: the row count and the rows that mention the request id
or the number OR-000008 — only their rowid, column names and the short key-like columns (no names, phones or payloads).
Nothing is written outside this run's own receipt.
"""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import sqlite3

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
REQUEST_ID = '43f45e8e-52f5-4eae-9569-550e38588988'
NUMBER = 'OR-000008'
SHORT = re.compile(r'^(?:id|.*_id|.*_key|key|state|status|stage|channel|owner|number|created_at|updated_at|recipient|'
                   r'sent_at|available_at|attempts|kind|folder|event)$')


def databases(home=HOME):
    found = sorted(p for p in home.glob('**/order_requests.db') if 'autopilot_inbox' not in p.parts
                   and 'backups' not in p.parts)[:5]
    crm = home / 'crm.db'
    return found + ([crm] if crm.is_file() else [])


def scan(path):
    con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        value = {}
        for table in tables:
            columns = [r[1] for r in con.execute('PRAGMA table_info("%s")' % table.replace('"', ''))]
            text = ' OR '.join('CAST("%s" AS TEXT) LIKE ?' % c.replace('"', '') for c in columns)
            hits = {}
            for needle in (REQUEST_ID, NUMBER):
                if columns:
                    for r in con.execute('SELECT rowid, * FROM "%s" WHERE %s' % (table.replace('"', ''), text),
                                         ['%' + needle + '%'] * len(columns)):
                        hits[r[0]] = r
            entry = {'rows': con.execute('SELECT count(*) FROM "%s"' % table.replace('"', '')).fetchone()[0]}
            if hits:
                entry['columns'] = columns
                entry['matches'] = [{'rowid': r[0], **{c: r[i + 1] for i, c in enumerate(columns) if SHORT.match(c)
                                                       and (r[i + 1] is None or len(str(r[i + 1])) <= 80)}}
                                    for r in hits.values()][:20]
            value[table] = entry
        return value
    finally:
        con.close()


def report(home=HOME):
    return {'status': 'PASS', 'databases': {str(p.relative_to(home)): scan(p) for p in databases(home)}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (60, 70))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:120]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
