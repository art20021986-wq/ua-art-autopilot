"""Link the company's Google Business Profile to the ads (owner 2026-11-25: Oleg gave the owner access to the profile
«ТОВ "ЮА АРТ КОМПАНІ"»; the profile's «Связанные аккаунты» page shows no request yet).

Two creates (R2: googleAds:mutate has no customer asset set operation): a location asset set synced from the Business Profile of the owner's account
(BUSINESS_OWNER, by the profile manager's e-mail) and its link to the whole advertiser account, so every ad can show
the address, rating and route. Google then sends the link request to the profile («Запросы»), which the owner accepts.
Nothing is created twice; no campaign, budget or spending change; no site, CRM or bot change; no key value in the report.
"""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import urllib.request

import source_check as check

HERE = Path(__file__).resolve().parent
NAME = 'UA ART — профиль компании (Київ)'
PROFILE_EMAIL = 'borov20021986@gmail.com'  # the owner's Google account, a manager of the profile since 2026-11-25
QUERY = ("SELECT asset_set.resource_name, asset_set.name, asset_set.type, asset_set.status FROM asset_set "
         "WHERE asset_set.type = 'LOCATION_SYNC'")
LINKS = ("SELECT customer_asset_set.resource_name, customer_asset_set.asset_set, customer_asset_set.status "
         "FROM customer_asset_set")


def read(customer, headers, query, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': query}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    return answer.get('results', [])


def mutate(customer, headers, service, operation, opener=urllib.request.urlopen):
    """One create through the service's own mutate (googleAds:mutate has no customer asset set operation)."""
    status, answer = check.call(check.API + 'customers/%s/%s:mutate' % (customer, service),
                                json.dumps({'operations': [{'create': operation}]}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('%s_%s:%s' % (service.upper(), status, json.dumps(check.errors(answer))[:300]))
    return answer['results'][0]['resourceName']


def location_set():
    return {'name': NAME, 'type': 'LOCATION_SYNC',
            'locationSet': {'locationOwnershipType': 'BUSINESS_OWNER',
                            'businessProfileLocationSet': {'emailAddress': PROFILE_EMAIL}}}


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = read(customer, headers, QUERY, opener)
    value = {'before': before, 'created': []}
    live = [r['assetSet']['resourceName'] for r in before if r['assetSet'].get('status') != 'REMOVED']
    asset_set = live[0] if live else mutate(customer, headers, 'assetSets', location_set(), opener)
    if not live:
        value['created'].append('asset_set')
    linked = [r['customerAssetSet'] for r in read(customer, headers, LINKS, opener)
              if r['customerAssetSet'].get('assetSet') == asset_set and r['customerAssetSet'].get('status') != 'REMOVED']
    if not linked:
        mutate(customer, headers, 'customerAssetSets', {'assetSet': asset_set, 'customer': 'customers/%s' % customer},
               opener)
        value['created'].append('customer_link')
    value['after'] = read(customer, headers, QUERY, opener)
    value['links'] = read(customer, headers, LINKS, opener)
    value['status'] = 'PASS' if value['created'] else 'ALREADY_THERE'
    return value


def report(path=check.KEYS_PATH, opener=urllib.request.urlopen):
    keys = json.loads(Path(path).read_text(encoding='utf-8'))
    if not all(keys.get(n) for n in check.KEY_NAMES + ('login_customer_id', 'customer_id')):
        return json.dumps({'status': 'KEYS_INCOMPLETE'})
    try:
        value = run(keys, opener)
    except check.CheckError as error:
        value = {'status': 'FAIL', 'error': str(error)}
    return check.clean(value, keys)


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
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=1)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
