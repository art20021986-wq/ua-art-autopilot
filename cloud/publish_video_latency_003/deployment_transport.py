"""Bounded PythonAnywhere transport for the delivery deployment only."""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

BASE = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
INBOX = '/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin'
BOT_ID = 266084
BOT_COMMAND = 'python3.10 /home/Carix/start_safe.py'
HERE = Path(__file__).resolve().parent


class TransportError(RuntimeError):
    pass


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class API:
    def __init__(self, token):
        if not token:
            raise TransportError('TOKEN_UNAVAILABLE')
        self.token = token

    def request(self, method, endpoint, data=None, content_type=None, allowed=(200,)):
        headers = {'Authorization': 'Token '+self.token}
        if content_type:
            headers['Content-Type'] = content_type
        for attempt in range(3):
            request = urllib.request.Request(BASE+endpoint, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=40) as response:
                    status, body = response.status, response.read(12*1024*1024+1)
            except urllib.error.HTTPError as error:
                status, body = error.code, error.read(4096)
            except (urllib.error.URLError, TimeoutError) as error:
                if method != 'GET' or attempt == 2:
                    raise TransportError('NETWORK_'+type(error).__name__) from error
                time.sleep(2**attempt)
                continue
            if len(body) > 12*1024*1024:
                raise TransportError('RESPONSE_SIZE')
            if status in allowed:
                return status, body
            if method != 'GET' or status not in (500, 502, 503, 504) or attempt == 2:
                raise TransportError('HTTP_'+str(status))
            time.sleep(2**attempt)

    def json(self, method, endpoint, fields=None, allowed=(200,)):
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        _, body = self.request(method, endpoint, data, 'application/x-www-form-urlencoded', allowed)
        return json.loads(body or b'{}')

    def bot(self):
        value = self.json('GET', 'always_on/%d/' % BOT_ID)
        if value.get('id') != BOT_ID or value.get('command') != BOT_COMMAND:
            raise TransportError('BOT_IDENTITY')
        return value

    def set_bot(self, enabled):
        observed = self.bot()
        if observed.get('enabled') is not enabled:
            self.json('PATCH', 'always_on/%d/' % BOT_ID, {'enabled': str(enabled).lower()})
        deadline = time.monotonic()+(480 if enabled else 120)
        while time.monotonic() < deadline:
            value = self.bot()
            state = str(value.get('state', '')).lower()
            if value.get('enabled') is enabled and (state == ('running' if enabled else 'stopped')):
                return {'id': BOT_ID, 'enabled': enabled, 'state': state}
            time.sleep(3)
        raise TransportError('BOT_STATE_TIMEOUT')

    def file(self, path, missing=False):
        if not str(path).startswith(INBOX+'/') or '..' in PurePosixPath(path).parts:
            raise TransportError('INBOX_SCOPE')
        status, content = self.request('GET', 'files/path'+urllib.parse.quote(path, safe='/'), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise TransportError('FILE_MISSING')
        return content

    def upload(self, path, payload):
        if not str(path).startswith(INBOX+'/') or '..' in PurePosixPath(path).parts:
            raise TransportError('INBOX_SCOPE')
        boundary = '----pubvideo-'+uuid.uuid4().hex
        content = ('--'+boundary+'\r\nContent-Disposition: form-data; name="content"; filename="'+PurePosixPath(path).name+'"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+payload+('\r\n--'+boundary+'--\r\n').encode()
        self.request('POST', 'files/path'+urllib.parse.quote(path, safe='/'), content,
                     'multipart/form-data; boundary='+boundary, (200, 201))
        if self.file(path) != payload:
            raise TransportError('UPLOAD_READBACK')

    def run(self, mode, run_id, bundle_sha, plan_sha='', backup_sha=''):
        if mode not in {'preview', 'backup', 'install', 'verify', 'rollback'} or not re.fullmatch(r'[0-9]+', run_id):
            raise TransportError('RUN_IDENTITY')
        for value in (bundle_sha, plan_sha, backup_sha):
            if value and not re.fullmatch(r'[0-9a-f]{64}', value):
                raise TransportError('RUN_HASH')
        receipt = INBOX+'/pubvideo-'+bundle_sha+'/runs/'+run_id+'/receipt-'+mode+'.json'
        prior = self.file(receipt, missing=True)
        if prior:
            return json.loads(prior)
        args = ['python3.10', INBOX+'/pubvideo_bootstrap.py', '--bundle', bundle_sha,
                '--run', run_id, '--mode', mode, '--plan', plan_sha, '--backup', backup_sha]
        trigger = self.json('POST', 'always_on/', {'command': shlex.join(args),
                   'description': 'Publication video latency '+mode+' '+run_id, 'enabled': 'true'}, (200, 201, 202))
        trigger_id = trigger.get('id')
        if type(trigger_id) is not int or trigger_id == BOT_ID:
            raise TransportError('TRIGGER_IDENTITY')
        deadline = time.monotonic()+780
        while time.monotonic() < deadline:
            raw = self.file(receipt, missing=True)
            if raw:
                value = json.loads(raw)
                if value.get('run_id') != run_id or value.get('mode') != mode or value.get('safe_to_stop') is not True:
                    raise TransportError('REMOTE_RECEIPT_BINDING')
                self.request('DELETE', 'always_on/%d/' % trigger_id, allowed=(200, 202, 204, 404))
                return value
            time.sleep(4)
        # The remote lifecycle retains ownership if the network disappears.
        if mode in ('preview', 'backup', 'verify'):
            self.request('DELETE', 'always_on/%d/' % trigger_id, allowed=(200, 202, 204, 404))
        raise TransportError('REMOTE_PENDING_TRIGGER_'+str(trigger_id))


def upload_package(api):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(HERE.iterdir()):
            if path.is_file() and path.suffix in ('.py', '.sql'):
                entry = zipfile.ZipInfo(path.name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, path.read_bytes())
    payload = output.getvalue()
    digest = sha(payload)
    api.upload(INBOX+'/pubvideo-'+digest+'.zip', payload)
    api.upload(INBOX+'/pubvideo_bootstrap.py', (HERE/'deployment_bootstrap.py').read_bytes())
    return digest
