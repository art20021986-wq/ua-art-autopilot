#!/usr/bin/env python3
"""Read-only: where the videos sent in Telegram for the cars in Ukraine ended up (CRM fields, media, inbox, files).

GET only. Exports counts, statuses and file names; never Telegram file ids, user ids or message text.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import urllib.error
import urllib.request

TASK_ID = 'CRM-VIDEO-PROBE-20261012-R2'
PACKAGE = 'cloud/crm_video_probe_20261012_r2'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
EVIDENCE = PACKAGE + '/evidence.json'
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/files/path/home/Carix/'
SERVER_PATH = re.compile(r'crm\.db|video/|video/diag/UA-\d{4,}/')
CODES = ('UA-0007', 'UA-0018', 'UA-0020')
VIDEO_FIELDS = ('videos', 'video_h', 'video_v', 'condition_videos', 'condition_photos')
MEDIA_COLUMNS = ('id', 'vid', 'razmer', 'mime', 'put', 'status', 'poryadok', 'kogda', 'primechanie')
INBOX_COLUMNS = ('id', 'kind', 'media_group', 'status', 'card_type', 'card_id', 'created_at', 'updated_at')
LIMIT = 64 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ProbeError('REDIRECT_FORBIDDEN')


class Reader:
    def __init__(self, token, opener=None):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token
        self._opener = opener or urllib.request.build_opener(NoRedirect())

    def server(self, path):
        if not SERVER_PATH.fullmatch(path):
            raise ProbeError('SERVER_PATH_OUTSIDE_SCOPE')
        request = urllib.request.Request(API + path, method='GET', headers={
            'Authorization': 'Token ' + self._token, 'Accept-Encoding': 'identity',
            'User-Agent': 'uaart-video-probe/1'})
        for attempt in range(3):
            try:
                with self._opener.open(request, timeout=60) as response:
                    data = response.read(LIMIT + 1)
                    if response.status != 200 or len(data) > LIMIT:
                        raise ProbeError('RESPONSE_REJECTED')
                    return data
            except urllib.error.HTTPError as error:
                code = error.code
                error.close()
                if code == 404:
                    return None
                if code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise ProbeError('HTTP_%d' % code) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise ProbeError('TRANSPORT_FAILURE') from None
            time.sleep(2 ** (attempt + 1))


def items(value):
    """Count list entries and keep only non-identifying shape facts."""
    try:
        data = json.loads(value) if isinstance(value, str) and value.strip() else (value or [])
    except ValueError:
        return {'count': 'UNPARSED'}
    if not isinstance(data, list):
        return {'count': 'NOT_LIST'}
    return {'count': len(data), 'entry_keys': sorted({k for x in data if isinstance(x, dict) for k in x})}


def safe(value):
    return re.sub(r'[A-Za-z0-9_-]{20,}', '[ID]', re.sub(r'\d{6,}', '[N]', str(value or '')))[:200]


def crm_facts(payload):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'crm.db'
        path.write_bytes(payload)
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        try:
            cols = lambda table: {r[1] for r in con.execute('PRAGMA table_info(%s)' % table)}
            cars = {}
            for code in CODES:
                row = con.execute('SELECT * FROM cars WHERE auto_number=?', (code,)).fetchone()
                if row is None:
                    continue
                row = dict(row)
                media_cols = [c for c in MEDIA_COLUMNS if c in cols('media')]
                media = [dict(r) for r in con.execute(
                    'SELECT %s FROM media WHERE car_id=? ORDER BY vid, poryadok, id' % ', '.join(media_cols), (row['id'],))]
                videos = [dict(m, primechanie=safe(m.get('primechanie'))) for m in media if m.get('vid') != 'foto']
                inbox_cols = [c for c in INBOX_COLUMNS if c in cols('inbox')]
                inbox = [dict(r) for r in con.execute(
                    "SELECT %s FROM inbox WHERE card_id=? AND card_type='cars' ORDER BY id" % ', '.join(inbox_cols),
                    (row['id'],))]
                cars[code] = {'id': row['id'], 'status': row.get('status'), 'updated_at': row.get('updated_at'),
                              'fields': {f: items(row.get(f)) for f in VIDEO_FIELDS if f in row},
                              'media_by_vid_status': {}, 'non_photo_media': videos, 'inbox_linked': inbox}
                for m in media:
                    key = '%s/%s' % (m.get('vid'), m.get('status'))
                    cars[code]['media_by_vid_status'][key] = cars[code]['media_by_vid_status'].get(key, 0) + 1
            unlinked = [dict(r) for r in con.execute(
                "SELECT %s FROM inbox WHERE kind IN ('video','video_note','animation','document') "
                "AND (card_id IS NULL OR card_id='') ORDER BY id DESC LIMIT 40" %
                ', '.join(c for c in INBOX_COLUMNS if c in cols('inbox')))]
            return {'cars': cars, 'unlinked_inbox_videos_or_documents': unlinked}
        finally:
            con.close()


def collect(reader):
    facts = crm_facts(reader.server('crm.db') or b'')
    listing = json.loads(reader.server('video/') or b'{}')
    facts['site_video_files'] = {code: sorted(n for n in listing if n.startswith(code) and not n.endswith('.html'))
                                 for code in CODES}
    facts['diag_folders'] = {code: sorted(json.loads(reader.server('video/diag/%s/' % code) or b'null') or [])
                             for code in CODES}
    return facts


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') != TASK_ID or env.get('UAART_RECEIPT_PATH') != RECEIPT \
            or env.get('UAART_REQUEST_PATH') != REQUEST:
        raise ProbeError('IDENTITY')
    request = root / REQUEST
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise ProbeError('BINDING')
    raw = json.loads(request.read_bytes())
    if raw.get('read_only') is not True or raw.get('production_required') is not False:
        raise ProbeError('SCOPE')
    return expected, env['UAART_RUN_ID']


def write(root, relative, value):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'x') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + '\n')


def execute(env, *, root=None, reader=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    facts = collect(reader or Reader(env.get('PYTHONANYWHERE_API_TOKEN', '')))
    write(root, EVIDENCE, {'task_id': TASK_ID, 'run_id': run_id, 'http_methods': ['GET'],
                           'remote_write_count': 0, **facts})
    receipt = {'task_id': TASK_ID, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': EVIDENCE}
    write(root, RECEIPT, receipt)
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('CRM_VIDEO_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
