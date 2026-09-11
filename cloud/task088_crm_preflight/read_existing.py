"""Read existing diagnostic evidence via API; never execute code on the server."""
from __future__ import annotations
import hashlib
import json
import re

import owner_preflight
import ui_patch


def safe_log(payload):
    value = payload[-16000:].decode('utf-8', 'replace')
    return {
        'bytes_observed': len(payload), 'raw_log_exported': False,
        'exception_types': re.findall(r'(?m)^([A-Za-z_]\w*(?:Error|Exception)):', value)[-8:],
        'known_messages': [text for text in ('command not found', 'Permission denied', 'No such file or directory', 'Traceback', 'tarpit') if text.lower() in value.lower()],
        'package_frames': [{'file': match[0], 'line': int(match[1])} for match in re.findall(r'/(remote_probe|owner_preflight|ui_patch|capacity_probe)\.py\", line ([0-9]{1,6})', value)[-8:]],
    }


def collect(api, snapshot):
    import controller
    prior = {}
    records = {}
    for name in ('plan', 'trigger', 'started', 'result'):
        raw = api.read(controller.PRIOR_DIRECTORY + '/' + name + '.json', missing=True)
        item = {'exists': raw is not None}
        if raw is not None:
            item['sha256'] = hashlib.sha256(raw).hexdigest()
            try:
                record = json.loads(raw)
                matches = isinstance(record, dict) and all(record.get(k) == v for k, v in controller.PRIOR_IDENTITY.items())
                item['identity_matches'] = matches
                if matches:
                    records[name] = record
                    for key in ('collection_status', 'error_type', 'crm_prices_acceptance'):
                        value = record.get(key)
                        if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', value):
                            item[key] = value
                    if name == 'trigger' and type(record.get('id')) is int:
                        item['id'] = record['id']
            except (ValueError, UnicodeDecodeError):
                item['json_valid'] = False
        prior[name] = item
    if 'trigger' in records:
        api.authorize_prior_log(records['trigger'])
        raw = api.read('/var/log/alwayson-log-' + str(api.prior_log_id) + '.log', missing=True)
        prior['task_log'] = {'exists': raw is not None, **(safe_log(raw) if raw is not None else {})}

    shapes, sources = {}, {}
    for name in controller.BUSINESS_FILES:
        raw = api.read('/home/Carix/' + name, missing=name != 'cars_ui.py')
        actual = {'absent': True} if raw is None else {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        if snapshot['sources'][name] != actual:
            raise controller.ControllerError('SOURCE_DRIFT_DURING_READ')
        if raw is not None:
            sources[name] = raw
            try:
                shapes[name] = owner_preflight.source_shape(raw, name)
            except Exception as exc:
                shapes[name] = {'status': 'NOT_VERIFIED', 'error_type': type(exc).__name__, **actual}
        else:
            shapes[name] = actual
    candidate = {'status': 'NOT_VERIFIED', 'live_bot_verified': False, 'ui_acceptance': 'NOT_PERFORMED'}
    try:
        proposed, _ = ui_patch.patch_text(sources['cars_ui.py'].decode('utf-8'))
        candidate.update(status='PASS_STATIC_ONLY', source_before_sha256=snapshot['sources']['cars_ui.py']['sha256'], source_after_sha256=hashlib.sha256(proposed.encode()).hexdigest())
    except Exception as exc:
        candidate['error_type'] = type(exc).__name__
        if isinstance(exc, ui_patch.PatchRefused):
            parts = str(exc).split(':', 1)
            if re.fullmatch(r'[A-Z_0-9]{1,80}', parts[0]):
                candidate['diagnostic_code'] = parts[0]
            if len(parts) == 2 and parts[1] in {'apply_value', 'auto_catch', 'catch_message', 'edit_menu', 'EDITABLE', 'MONEY', 'NUMERIC', 'LABELS_ALL'}:
                candidate['diagnostic_anchor'] = parts[1]
    comparison = {}
    old_sources = records.get('plan', {}).get('sources', {})
    if isinstance(old_sources, dict):
        comparison = {name: snapshot['sources'][name] == old_sources.get(name) for name in controller.BUSINESS_FILES}
    return {
        **controller.bindings(api.values), 'backup_manifest_sha256': api.values['UAART_BACKUP_MANIFEST_SHA256'],
        'collection_status': 'PASS', 'crm_prices_acceptance': 'NOT_PERFORMED',
        'business_source_writes': 0, 'db_writes': 0, 'site_changes': 0, 'bot_restarts': 0,
        'live_modules_imported': False,
        'discovery': {'mode': 'GET_ONLY_NO_REMOTE_PROCESS', 'read_only': True,
                      'prior_run': prior, 'sources': shapes, 'candidate': candidate,
                      'source_matches_prior_backup': comparison,
                      'database_acceptance': 'NOT_PERFORMED', 'remote_processes_created': 0},
    }
