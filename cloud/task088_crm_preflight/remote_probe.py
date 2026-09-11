#!/usr/bin/env python3
"""Single diagnostic collection; writes only this exact run's started/result JSON."""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import re
import tempfile

TASK_ID = 'TASK088-GE-PRICE-CRM-PREFLIGHT'
HERE = pathlib.Path(__file__).resolve().parent
REMOTE_ROOT = pathlib.Path('/home/Carix/autopilot_inbox/cloud/task088_crm_preflight/runs')
BINDINGS = ('task_id', 'run_id', 'request_sha256', 'transaction_id', 'manifest_sha256', 'backup_manifest_sha256')
SOURCES = ('remote_probe.py', 'owner_preflight.py', 'ui_patch.py', 'capacity_probe.py')


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def validate_plan(plan, here=HERE, remote_root=REMOTE_ROOT):
    if plan.get('task_id') != TASK_ID or not re.fullmatch(r'[0-9]{1,30}', str(plan.get('run_id', ''))) or not re.fullmatch(r'[A-Za-z0-9._-]{1,180}', str(plan.get('transaction_id', ''))):
        raise ValueError('IDENTITY')
    for key in ('request_sha256', 'manifest_sha256', 'backup_manifest_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}', str(plan.get(key, ''))):
            raise ValueError('SHA_IDENTITY')
    if here != remote_root / (plan['run_id'] + '-' + plan['request_sha256']) or here.is_symlink():
        raise ValueError('DIRECTORY_IDENTITY')
    pinned = plan.get('remote_source_sha256', {})
    if set(pinned) != set(SOURCES):
        raise ValueError('PACKAGE_IDENTITY')
    for name in SOURCES:
        path = here / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != pinned[name]:
            raise ValueError('PACKAGE_SHA')


def collect_once(plan, collector, here=HERE):
    started = here / 'started.json'
    try:
        descriptor = os.open(started, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(canonical({key: plan[key] for key in BINDINGS})); handle.flush(); os.fsync(handle.fileno())
    value = {key: plan[key] for key in BINDINGS}
    value.update({'collection_status': 'FAIL', 'crm_prices_acceptance': 'NOT_PERFORMED', 'business_source_writes': 0, 'db_writes': 0, 'site_changes': 0, 'bot_restarts': 0, 'live_modules_imported': False})
    try:
        discovery = collector()
        if not isinstance(discovery, dict) or discovery.get('read_only') is not True or discovery.get('crm_prices_acceptance') != 'NOT_PERFORMED':
            raise ValueError('DISCOVERY_SCOPE')
        if any(discovery.get(key) != 0 for key in ('db_writes', 'site_changes', 'bot_restarts')) or discovery.get('live_modules_imported') is not False:
            raise ValueError('DISCOVERY_MUTATION')
        value.update({'collection_status': 'PASS', 'discovery': discovery})
    except Exception as exc:
        value['error_type'] = type(exc).__name__
    payload = canonical(value)
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError('RESULT_BUDGET')
    descriptor, temporary = tempfile.mkstemp(prefix='.result-', dir=here)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.link(temporary, here / 'result.json')
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)
    return value


def main():
    plan = json.loads((HERE / 'plan.json').read_bytes())
    validate_plan(plan)
    # Only the hash-verified diagnostic module is imported; never live CRM modules.
    import owner_preflight
    result = collect_once(plan, owner_preflight.collect)
    return 0 if result is None or result.get('collection_status') == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
