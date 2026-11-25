"""Read-only check of the Google Ads account on the server (ADS-API-001, owner 2026-11-25: «Хочу уже запустить эту рекламу»).

Uses the keys the owner sent to the CRM bot (/home/Carix/google_ads_api.json, never copied, never put in the report):
a fresh access token from the refresh token, then only reading calls of the official REST API:
- customers:listAccessibleCustomers;
- googleAds:search on the manager account (its client accounts) and on the advertiser account (account settings,
  campaigns, conversion actions, billing setup).
Nothing is created, changed or spent: no mutate call exists in this file. The report holds account names, statuses and
Google's error codes only; every key value is checked to be absent before the report is written.
"""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
KEYS_PATH = Path('/home/Carix/google_ads_api.json')
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
API = 'https://googleads.googleapis.com/v26/'
QUERIES = {
    'manager': ('login', 'SELECT customer_client.id, customer_client.descriptive_name, customer_client.manager, '
                         'customer_client.status, customer_client.level FROM customer_client'),
    'account': ('client', 'SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone, '
                          'customer.status, customer.auto_tagging_enabled, customer.test_account, '
                          'customer.conversion_tracking_setting.conversion_tracking_status FROM customer'),
    'campaigns': ('client', 'SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, '
                            'campaign_budget.amount_micros FROM campaign'),
    'conversions': ('client', 'SELECT conversion_action.id, conversion_action.name, conversion_action.status, '
                              'conversion_action.type, conversion_action.category, conversion_action.primary_for_goal '
                              'FROM conversion_action'),
    'billing': ('client', 'SELECT billing_setup.id, billing_setup.status FROM billing_setup'),
}
KEY_NAMES = ('developer_token', 'client_id', 'client_secret', 'refresh_token')


class CheckError(Exception):
    pass


def call(url, body=None, headers=None, opener=urllib.request.urlopen):
    """(status, parsed JSON) for one HTTPS call; Google's error answer is returned, not raised."""
    data = None if body is None else body
    request = urllib.request.Request(url, data=data, headers=headers or {}, method='POST' if data is not None else 'GET')
    try:
        with opener(request, timeout=40) as response:
            return response.status, json.loads(response.read(4 * 1024 * 1024) or b'{}')
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read(65536) or b'{}')
        except ValueError:
            return error.code, {}


def access_token(keys, opener=urllib.request.urlopen):
    body = urllib.parse.urlencode({'client_id': keys['client_id'], 'client_secret': keys['client_secret'],
                                   'refresh_token': keys['refresh_token'], 'grant_type': 'refresh_token'}).encode()
    status, answer = call(TOKEN_ENDPOINT, body, {'Content-Type': 'application/x-www-form-urlencoded'}, opener)
    if status != 200 or not answer.get('access_token'):
        raise CheckError('TOKEN_%s:%s' % (status, str(answer.get('error', ''))[:40]))
    return answer['access_token'], answer.get('scope', '')


def errors(answer):
    """Google's error codes and messages, short (no request data)."""
    error = answer.get('error', {}) if isinstance(answer, dict) else {}
    found = []
    for detail in error.get('details', []) or []:
        for item in detail.get('errors', []) or []:
            code = item.get('errorCode', {})
            found.append({'code': '.'.join('%s=%s' % pair for pair in sorted(code.items())),
                          'message': str(item.get('message', ''))[:200]})
    return {'status': error.get('status'), 'message': str(error.get('message', ''))[:200], 'errors': found[:5]}


def check(keys, opener=urllib.request.urlopen):
    token, scope = access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    value = {'token': 'PASS', 'scope': scope}
    status, answer = call(API + 'customers:listAccessibleCustomers',
                          headers={k: v for k, v in headers.items() if k != 'login-customer-id'}, opener=opener)
    value['accessible'] = answer.get('resourceNames', []) if status == 200 else {'http': status, **errors(answer)}
    for name, (who, query) in QUERIES.items():
        customer = keys['login_customer_id'] if who == 'login' else keys['customer_id']
        status, answer = call(API + 'customers/%s/googleAds:search' % customer, json.dumps({'query': query}).encode(),
                              headers, opener)
        value[name] = answer.get('results', []) if status == 200 else {'http': status, **errors(answer)}
    return value


def clean(value, keys):
    """The report text; stops if any key value would be in it."""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for name in KEY_NAMES:
        secret = str(keys.get(name) or '')
        if len(secret) >= 8 and secret in text:
            raise CheckError('KEY_IN_REPORT:' + name)
    if 'GOCSPX-' in text or 'ya29.' in text:
        raise CheckError('KEY_IN_REPORT')
    return text


def report(path=KEYS_PATH, opener=urllib.request.urlopen):
    keys = json.loads(Path(path).read_text(encoding='utf-8'))
    present = {name: bool(keys.get(name)) for name in KEY_NAMES + ('login_customer_id', 'customer_id')}
    value = {'status': 'PASS', 'keys_present': present, 'keys_mode': oct(Path(path).stat().st_mode & 0o777)}
    if not all(present.values()):
        value['status'] = 'KEYS_INCOMPLETE'
        return clean(value, keys)
    try:
        value['google_ads'] = check(keys, opener)
    except CheckError as error:
        value.update(status='FAIL', error=str(error))
    return clean(value, keys)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (120, 130))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = json.loads(report())
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:80]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
