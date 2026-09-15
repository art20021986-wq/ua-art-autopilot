#!/usr/bin/env python3
"""Read existing CRM bot identity/private-chat facts; never send a message.

Uses only the token file explicitly configured by the hash-pinned team_bot.py.
No deployed imports, token output, credential search, getUpdates, or CRM writes.
The result is an observation, not installation/delegation authority.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import urllib.parse
import urllib.request

ROOT = Path('/home/Carix')
SOURCE_SHA = 'aebe2c091fdf1f19a8a011784dd70e2d648dc04607ec64374e4ff9f402e995af'

def main():
    if Path.home() != ROOT or ROOT.is_symlink():
        raise RuntimeError('HOST_MISMATCH')
    source = ROOT / 'team_bot.py'
    if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA:
        raise RuntimeError('SOURCE_DRIFT')
    # This exact path is TEAM_TOKEN_FILE in the reviewed deployed source.
    token_path = ROOT / 'team_token.txt'
    if token_path.is_symlink() or not token_path.is_file():
        raise RuntimeError('EXISTING_CRM_TOKEN_FILE_UNAVAILABLE')
    if os.environ.get('TEAM_BOT_TOKEN', '').strip():
        raise RuntimeError('CONSOLE_ENV_OVERRIDE_REQUIRES_SEPARATE_BINDING')
    with sqlite3.connect((ROOT / 'crm.db').as_uri() + '?mode=ro', uri=True, timeout=1) as conn:
        rows = conn.execute("SELECT user_id FROM staff WHERE role='owner' AND active=1").fetchall()
    if len(rows) != 1 or type(rows[0][0]) is not int:
        raise RuntimeError('UNIQUE_ACTIVE_OWNER_REQUIRED')
    owner_id = rows[0][0]
    token = token_path.read_text().strip()
    if not token or len(token) > 1024 or any(c.isspace() for c in token):
        raise RuntimeError('EXISTING_CRM_TOKEN_FORMAT')
    result = {'contract': 'PR114-READONLY-CRM-BOT-IDENTITY-FACTS-1',
              'observed_at': datetime.now(timezone.utc).isoformat(),
              'team_bot_sha256': SOURCE_SHA, 'credential_source': str(token_path),
              'production_written': False, 'messages_sent': False,
              'updates_consumed': False, 'credential_value_recorded': False,
              'running_process_environment_binding': 'NOT_OBSERVED',
              'owner_staff_id': owner_id}
    try:
        for method, params in [('getMe', {}), ('getChat', {'chat_id': owner_id})]:
            # Both operations read Telegram metadata; no messaging endpoint is used.
            suffix = '?' + urllib.parse.urlencode(params) if params else ''
            request = urllib.request.Request('https://api.telegram.org/bot' + token + '/' + method + suffix)
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise RuntimeError('RESPONSE_TOO_LARGE')
            payload = json.loads(raw)
            if payload.get('ok') is not True or not isinstance(payload.get('result'), dict):
                raise RuntimeError('API_RESULT_NOT_OK')
            value = payload['result']
            if method == 'getMe':
                if value.get('is_bot') is not True or type(value.get('id')) is not int:
                    raise RuntimeError('BOT_IDENTITY_INVALID')
                result['getMe'] = {'id': value['id'], 'is_bot': True, 'username': value.get('username')}
            else:
                if value.get('id') != owner_id or value.get('type') != 'private':
                    raise RuntimeError('OWNER_PRIVATE_CHAT_NOT_CONFIRMED')
                result['getChat'] = {'id': value['id'], 'type': value['type']}
            result[method + '_response_sha256'] = hashlib.sha256(raw).hexdigest()
        result['status'] = 'AUTHENTICATED_BOT_AND_OWNER_PRIVATE_CHAT_OBSERVED'
    finally:
        token = None
    result['finished_at'] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Never print exception messages or tracebacks: they may contain request URLs.
        print(json.dumps({'status': 'FACTS_UNAVAILABLE', 'error_type': type(error).__name__,
                          'messages_sent': False, 'updates_consumed': False}))
        raise SystemExit(1)
