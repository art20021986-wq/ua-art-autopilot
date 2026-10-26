"""One-time Google Analytics setup on the server, where the service account key lives.

Finds the owner's «UA ART» property the service account was given, creates the web data stream for the site
when it is missing, sets event data retention to 14 months, marks the site leads as key events and registers the
event parameters reports need as custom dimensions. Nothing else is written; the key never leaves
the server. If the Analytics Admin API is off in the service account's project, it tries to turn it on once.
"""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
# Uploaded from an iPhone the extension may be dropped or become .txt.
KEYS = tuple(HOME/('uaart-autopilot-110fb4d36d23' + ext) for ext in ('.json', '', '.txt'))
SCOPES = ['https://www.googleapis.com/auth/analytics.edit', 'https://www.googleapis.com/auth/cloud-platform']
ADMIN = 'https://analyticsadmin.googleapis.com/v1beta/'
ENABLE = 'https://serviceusage.googleapis.com/v1/projects/%s/services/analyticsadmin.googleapis.com:enable'
PROPERTY_NAME = 'UA ART'
SITE = 'https://www.uaart.com.ua'
STREAM_NAME = 'Сайт www.uaart.com.ua'
# R3: leads the site tag sends (ua_google_tag.py), counted as key events.
KEY_EVENTS = ('generate_lead', 'contact')
# R4 (owner «Да», 2026-10-26): «placement» of the autoria_click event (home page AUTO.RIA links) as a report dimension.
CUSTOM_DIMENSIONS = ({'parameterName': 'placement', 'displayName': 'AUTO RIA click placement', 'scope': 'EVENT',
                      'description': 'Where the AUTO.RIA link was clicked: reviews_block or footer_badge'},)


def token(key):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    credentials = service_account.Credentials.from_service_account_file(str(key), scopes=SCOPES)
    credentials.refresh(Request())
    return credentials.service_account_email, credentials.project_id, credentials.token


def call(bearer, url, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method or ('POST' if body is not None else 'GET'), headers={
        'Authorization': 'Bearer ' + bearer, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        return error.code, {'error': error.read(600).decode('utf-8', 'replace')}


def summaries(bearer, project):
    status, value = call(bearer, ADMIN + 'accountSummaries')
    if status == 403 and 'SERVICE_DISABLED' in value.get('error', ''):
        enable_status, enable = call(bearer, ENABLE % project, {})
        value['enable_attempt'] = {'http': enable_status, **({'error': enable['error'][:300]} if 'error' in enable else {})}
    return status, value


def report():
    keys = [key for key in KEYS if key.is_file()]
    if not keys:
        return {'status': 'FAIL', 'error': 'KEY_MISSING'}
    try:
        email, project, bearer = token(keys[0])
    except Exception as error:
        return {'status': 'FAIL', 'error': 'TOKEN:' + type(error).__name__ + ':' + str(error)[:160]}
    status, value = summaries(bearer, project)
    if status != 200:
        return {'status': 'FAIL', 'error': 'ADMIN_API_HTTP_%d' % status, 'service_account': email, 'project': project,
                'detail': value}
    found = [{'account': a.get('account'), 'account_name': a.get('displayName'),
              'property': p.get('property'), 'property_name': p.get('displayName')}
             for a in value.get('accountSummaries', []) for p in a.get('propertySummaries', [])]
    named = [p for p in found if p['property_name'] == PROPERTY_NAME]
    result = {'service_account': email, 'visible_properties': found}
    if len(named) != 1:
        return {'status': 'FAIL', 'error': 'PROPERTY_NOT_FOUND' if not named else 'PROPERTY_AMBIGUOUS', **result}
    prop = named[0]['property']
    status, info = call(bearer, ADMIN + prop)
    result['property'] = {'http': status, **{k: info.get(k) for k in ('name', 'displayName', 'timeZone', 'currencyCode',
                                                                      'industryCategory', 'serviceLevel')}}
    status, streams = call(bearer, ADMIN + prop + '/dataStreams')
    if status != 200:
        return {'status': 'FAIL', 'error': 'STREAMS_HTTP_%d' % status, 'detail': streams, **result}
    web = [s for s in streams.get('dataStreams', []) if s.get('type') == 'WEB_DATA_STREAM'
           and s.get('webStreamData', {}).get('defaultUri', '').rstrip('/') in (SITE, SITE.replace('www.', ''))]
    writes = []
    if not web:
        status, created = call(bearer, ADMIN + prop + '/dataStreams', {
            'type': 'WEB_DATA_STREAM', 'displayName': STREAM_NAME, 'webStreamData': {'defaultUri': SITE}})
        if status != 200:
            return {'status': 'FAIL', 'error': 'STREAM_CREATE_HTTP_%d' % status, 'detail': created, **result}
        writes.append('data_stream_created')
        web = [created]
    stream = web[0]
    result['stream'] = {'name': stream.get('name'), 'displayName': stream.get('displayName'),
                        'defaultUri': stream.get('webStreamData', {}).get('defaultUri'),
                        'measurementId': stream.get('webStreamData', {}).get('measurementId')}
    status, retention = call(bearer, ADMIN + prop + '/dataRetentionSettings')
    if status == 200 and retention.get('eventDataRetention') != 'FOURTEEN_MONTHS':
        status, retention = call(bearer, ADMIN + prop + '/dataRetentionSettings?updateMask=eventDataRetention',
                                 {'eventDataRetention': 'FOURTEEN_MONTHS'}, 'PATCH')
        if status == 200:
            writes.append('retention_14_months')
    result['retention'] = {'http': status, 'eventDataRetention': retention.get('eventDataRetention'),
                           **({'error': retention['error'][:300]} if 'error' in retention else {})}
    status, existing = call(bearer, ADMIN + prop + '/keyEvents')
    names = {item.get('eventName') for item in existing.get('keyEvents', [])} if status == 200 else set()
    result['key_events'] = {'http': status}
    for name in KEY_EVENTS:
        if status == 200 and name not in names:
            created_status, created = call(bearer, ADMIN + prop + '/keyEvents',
                                           {'eventName': name, 'countingMethod': 'ONCE_PER_EVENT'})
            result['key_events'][name] = created_status
            if created_status == 200:
                writes.append('key_event_' + name)
        else:
            result['key_events'][name] = 'exists' if name in names else status
    status, existing = call(bearer, ADMIN + prop + '/customDimensions')
    names = {item.get('parameterName') for item in existing.get('customDimensions', [])} if status == 200 else set()
    result['custom_dimensions'] = {'http': status}
    for dimension in CUSTOM_DIMENSIONS:
        name = dimension['parameterName']
        if status == 200 and name not in names:
            created_status, created = call(bearer, ADMIN + prop + '/customDimensions', dimension)
            result['custom_dimensions'][name] = created_status
            if created_status == 200:
                writes.append('custom_dimension_' + name)
            else:
                result['custom_dimensions'][name + '_error'] = created.get('error', '')[:300]
        else:
            result['custom_dimensions'][name] = 'exists' if name in names else status
    measurement = result['stream']['measurementId'] or ''
    return {'status': 'PASS' if re.fullmatch(r'G-[A-Z0-9]+', measurement) else 'FAIL', 'analytics_writes': writes, **result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (20, 25))
    work = HERE/'runs'/args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work/'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work/'.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
