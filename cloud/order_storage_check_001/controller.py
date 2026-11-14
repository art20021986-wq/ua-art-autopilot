#!/usr/bin/env python3
"""GET-only check of the «Order storage unavailable» bot error (BOT-ORDER-STORAGE-001).

Reads the CRM bot log and the ua_order sources through the PythonAnywhere files API.
Exports: every StorageUnavailable with its time and failing operation, grouped into
incidents; other MySQL error lines; the last tracebacks; the ua_order sources and the
lines around the bot's «Ошибка в боте» handler. Secrets and long numbers are redacted.
No write to the server, site, CRM or bot.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

PACKAGE = 'cloud/order_storage_check_001'
TASKS = ('ORDER-STORAGE-CHECK-20261114', 'ORDER-STORAGE-CHECK-20261114-R2')
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
LOG = '/var/log/alwayson-log-266084.log'
SOURCES = tuple('/home/Carix/ua_order/%s.py' % n for n in ('bindings', 'notifications', 'mysql_repository', 'storage'))
HOSTS = ('/home/Carix/start_safe.py', '/home/Carix/cars_ui.py', '/home/Carix/bot.py')
ALLOWED = (LOG,) + SOURCES + HOSTS
LIMIT = 64 * 1024 * 1024
GAP = 120  # seconds between failures that still belong to one incident
STAMP = re.compile(r'^([A-Z][a-z]{2} [ \d]\d \d\d:\d\d:\d\d) ')
FAILURE = re.compile(r'StorageUnavailable: Order storage unavailable')
OPERATION = re.compile(r'mysql_repository\.py", line \d+, in (\w+)')
MYSQL = re.compile(r'(?i)operationalerror|gone away|lost connection|max_user_connections|too many connections'
                   r"|can't connect to mysql|mysqldb\.|\(20\d\d,|\(1040|\(1226")
HANDLER = re.compile(r'Ошибка в боте|def error_handler|add_error_handler')
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization)\s*[:=]|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b'
                    r'|\b(gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{12,}')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def clean(line):
    if SECRET.search(line):
        return '[REDACTED_SENSITIVE_LINE]'
    return LONG_NUMBER.sub('[N]', line)[:400]


class Api:
    def __init__(self, token):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token

    def get(self, endpoint):
        if endpoint != 'cpu/' and not (endpoint.startswith('files/path') and endpoint[len('files/path'):] in ALLOWED):
            raise ProbeError('API_PATH_OUTSIDE_SCOPE')
        request = urllib.request.Request(API + urllib.parse.quote(endpoint), method='GET',
                                         headers={'Authorization': 'Token ' + self._token, 'User-Agent': 'uaart-order-storage-check/1'})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.status, response.read(LIMIT + 1)
        except urllib.error.HTTPError as error:
            error.close()
            return error.code, b''


def stamp(text, year):
    return dt.datetime.strptime('%d %s' % (year, re.sub(r'\s+', ' ', text)), '%Y %b %d %H:%M:%S')


def analyse_log(payload, year):
    lines = payload.decode('utf-8', errors='replace').splitlines()
    failures, mysql, last = [], [], None
    for index, line in enumerate(lines):
        match = STAMP.match(line)
        if match:
            last = match.group(1)
        if FAILURE.search(line) and last:
            operation = None
            for back in range(index - 1, max(-1, index - 60), -1):
                found = OPERATION.search(lines[back])
                if found and found.group(1) != '_run':
                    operation = found.group(1)
                    break
            failures.append({'line': index + 1, 'at': last, 'operation': operation})
        elif MYSQL.search(line):
            mysql.append('%d: %s' % (index + 1, clean(line)))
    incidents = []
    for item in failures:
        moment = stamp(item['at'], year)
        if incidents and (moment - incidents[-1]['_end']).total_seconds() <= GAP:
            incidents[-1]['_end'] = moment
            incidents[-1]['count'] += 1
        else:
            incidents.append({'_start': moment, '_end': moment, 'count': 1})
    for incident in incidents:
        incident['start'], incident['end'] = incident.pop('_start').isoformat(), incident.pop('_end').isoformat()
        incident['seconds'] = int((dt.datetime.fromisoformat(incident['end']) - dt.datetime.fromisoformat(incident['start'])).total_seconds())
    tracebacks = []
    for item in failures[-3:]:
        start = item['line'] - 1
        while start > 0 and start > item['line'] - 45 and 'Traceback' not in lines[start]:
            start -= 1
        tracebacks.append(['%d: %s' % (i + 1, clean(lines[i])) for i in range(start, item['line'])])
    first = STAMP.match(lines[0]) if lines else None
    final = next((STAMP.match(l) for l in reversed(lines) if STAMP.match(l)), None)
    operations = {}
    for item in failures:
        operations[item['operation'] or 'unknown'] = operations.get(item['operation'] or 'unknown', 0) + 1
    return {'bytes': len(payload), 'lines': len(lines), 'first_at': first.group(1) if first else None,
            'last_at': final.group(1) if final else None, 'failures': len(failures),
            'failures_by_operation': operations, 'failure_times': [f['at'] for f in failures][-200:],
            'incidents': incidents[-100:], 'incident_count': len(incidents),
            'longest_incident_seconds': max([i['seconds'] for i in incidents] or [0]),
            'mysql_lines': mysql[-80:], 'mysql_line_count': len(mysql), 'last_tracebacks': tracebacks}


def handler_context(payload):
    lines = payload.decode('utf-8', errors='replace').splitlines()
    keep = set()
    for index, line in enumerate(lines):
        if HANDLER.search(line):
            keep.update(range(max(0, index - 6), min(len(lines), index + 20)))
    return ['%d: %s' % (i + 1, clean(lines[i])) for i in sorted(keep)][:300]


def collect(api, year):
    result = {'status': {}, 'sources': {}, 'handlers': {}}
    status, cpu = api.get('cpu/')
    result['cpu'] = {'http': status, 'value': json.loads(cpu) if status == 200 and cpu else None}
    for path in ALLOWED:
        code, body = api.get('files/path' + path)
        result['status'][path] = code
        if code != 200:
            continue
        if len(body) > LIMIT:
            raise ProbeError('FILE_TOO_LARGE')
        if path == LOG:
            result['log'] = analyse_log(body, year)
        elif path in SOURCES:
            result['sources'][path] = {'sha256': sha(body), 'text': '\n'.join(clean(l) for l in body.decode('utf-8', 'replace').splitlines())}
        else:
            result['handlers'][path] = {'sha256': sha(body), 'lines': handler_context(body)}
    if result['status'].get(LOG) != 200:
        raise ProbeError('LOG_UNAVAILABLE:%s' % result['status'].get(LOG))
    return result


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') not in TASKS or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % env.get('UAART_TASK_ID') \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % env.get('UAART_TASK_ID'):
        raise ProbeError('IDENTITY')
    request = root/env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise ProbeError('BINDING')
    if json.loads(request.read_bytes()).get('production_required') is not False:
        raise ProbeError('SCOPE')
    return expected, env['UAART_RUN_ID']


def dump(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str)+'\n').encode()


def write(root, relative, data):
    target = root/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)


def execute(env, *, root=None, api=None, year=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    result = collect(api or Api(env.get('PYTHONANYWHERE_API_TOKEN', '')), year or dt.datetime.now(dt.timezone.utc).year)
    evidence = PACKAGE + '/evidence.json'
    write(root, evidence, dump({'task_id': task, 'run_id': run_id, **result}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'ORDER_STORAGE_CHECK',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_SITE_OR_CRM_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id, 'evidence_path': evidence}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('ORDER_STORAGE_CHECK_STOP:'+(str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
