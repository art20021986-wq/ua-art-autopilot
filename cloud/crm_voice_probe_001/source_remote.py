"""Read-only probe on the server: the owner's last voice message in the CRM bot (CRM-VOICE-PROBE).

Reads only. Returns, sanitized: the voice path sources (cars_ui.py, ai.py, crm_voice_watchdog.py,
crm_online_guard.py) with sha256 and the sha256 of team_bot.py; today's bot log lines except the
card-publication retries; today's inbox rows and CRM audit rows as kinds, field names, sizes and
times only (no values). Nothing is written outside this run's own receipt.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sqlite3

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
FULL = ('cars_ui.py', 'ai.py', 'crm_voice_watchdog.py', 'crm_online_guard.py')
HASH_ONLY = ('team_bot.py', 'local_ocr.py', 'ai_fast_schema.py', 'ai_filter.py', 'db.py')
LOG = Path('/var/log/alwayson-log-266084.log')
LOG_TAIL = 8 * 1024 * 1024
# The card publisher retries every few seconds; its lines would hide everything else.
NOISE = re.compile(r'ua_crm_public_sync|BASE_PUBLISH_FAILED|raise RuntimeError\(str\(message\)')
MAX_SOURCE = 2 * 1024 * 1024
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN|\bsk-[A-Za-z0-9_-]{12,}')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org)(?:[/\'"\s]|$)')


def sanitized_line(line):
    if SECRET.search(line):
        return '[REDACTED]'
    line = URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)
    return LONG_NUMBER.sub('[N]', line)


def sources(home=None):
    home = home or HOME
    files = {}
    for name in FULL + HASH_ONLY:
        path = home / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_SOURCE:
            files[name] = None
            continue
        raw = path.read_bytes()
        files[name] = {'sha256': hashlib.sha256(raw).hexdigest()}
        if name in FULL:
            files[name]['source'] = '\n'.join(sanitized_line(x) for x in raw.decode('utf-8', 'replace').splitlines())
    return files


def bot_log(today, log=None):
    log = log or LOG
    if not log.is_file():
        return None
    with log.open('rb') as handle:
        handle.seek(max(0, log.stat().st_size - LOG_TAIL))
        lines = handle.read().decode('utf-8', 'replace').splitlines()
    marks = (today.strftime('%b %d'), today.strftime('%b ') + str(today.day).rjust(2))
    picked = []
    for number, line in enumerate(lines):
        following = lines[number + 1] if number + 1 < len(lines) else ''
        if not line.startswith(marks) or NOISE.search(line) or ('Traceback' in line and NOISE.search(following)):
            continue
        picked.append(sanitized_line(line)[:400])
    return {'today_lines': len(picked), 'lines': picked[-500:]}


def crm(today, database=None):
    path = database or HOME / 'crm.db'
    con = sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        day = today.isoformat()
        inbox = [{'id': i, 'kind': k, 'status': s, 'text_chars': len(t or ''), 'created_at': c}
                 for i, k, s, t, c in con.execute(
                     'SELECT id, kind, status, text, created_at FROM inbox WHERE created_at >= ? ORDER BY id', (day,))]
        numbers = dict(con.execute('SELECT id, auto_number FROM cars'))
        audit = [{'action': a, 'entity_type': e, 'auto_number': numbers.get(i) if e == 'cars' else None,
                  'field': f, 'old_chars': len(str(o or '')), 'new_chars': len(str(n or '')), 'created_at': c}
                 for a, e, i, f, o, n, c in con.execute(
                     'SELECT action, entity_type, entity_id, field, old_value, new_value, created_at '
                     'FROM audit WHERE created_at >= ? ORDER BY id', (day,))]
        return {'inbox': inbox, 'audit': audit}
    finally:
        con.close()


def report():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    value = {'status': 'PASS', 'files': sources()}
    for key, call in (('bot_log', lambda: bot_log(today)), ('crm', lambda: crm(today))):
        try:
            value[key] = call()
        except Exception as error:
            value[key] = {'error': type(error).__name__ + ':' + str(error)[:160]}
    return value


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
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
