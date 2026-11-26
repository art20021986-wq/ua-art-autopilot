"""Campaign geography (owner 2026-11-26: «на всю Украину теперь рекламу, кроме Крыма, Луганской, Донецкой и прифронтовых
зон»).

Targets Ukraine (geoTargetConstants/2804) instead of Kyiv city + Kyiv Oblast and excludes, as negative locations, the
regions found by name in Google's location list: Crimea, Sevastopol, Luhansk, Donetsk, Zaporizhzhia and Kherson oblasts
(EXCLUDE; Kharkiv and Sumy only if the owner says so). One all-or-nothing googleAds:mutate; people located there only
(the campaign's PRESENCE setting stays). State before and after in the report. No site, CRM or bot change.
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
NAME = 'Пошук — Київ — Корея (UA ART)'
UKRAINE = 'geoTargetConstants/2804'
EXCLUDE = ('Crimea', 'Sevastopol', 'Luhansk', 'Donetsk', 'Zaporiz', 'Kherson')
CAMPAIGN = "SELECT campaign.resource_name FROM campaign WHERE campaign.name = '%s'" % NAME
LOCATIONS = ("SELECT campaign_criterion.resource_name, campaign_criterion.location.geo_target_constant, "
             "campaign_criterion.negative FROM campaign_criterion WHERE campaign.name = '%s' "
             "AND campaign_criterion.type = 'LOCATION'" % NAME)
REGIONS = ("SELECT geo_target_constant.resource_name, geo_target_constant.name, geo_target_constant.target_type, "
           "geo_target_constant.status FROM geo_target_constant WHERE geo_target_constant.country_code = 'UA'")
WIDE = ('Region', 'Autonomous Republic', 'Province', 'State', 'Territory')


def read(customer, headers, query, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': query}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    return answer.get('results', [])


def excluded(rows):
    """Regions to exclude: every enabled region whose name has one of EXCLUDE (Sevastopol is a city-level region)."""
    found = {}
    for r in rows:
        g = r['geoTargetConstant']
        if g.get('status', 'ENABLED') != 'ENABLED':
            continue
        if any(word in g['name'] for word in EXCLUDE) and (g.get('targetType') in WIDE or 'Sevastopol' in g['name']):
            found[g['resourceName']] = g['name']
    return found


def state(customer, headers, opener=urllib.request.urlopen):
    rows = read(customer, headers, CAMPAIGN, opener)
    if len(rows) != 1:
        raise check.CheckError('CAMPAIGNS_%d' % len(rows))
    locations = [r['campaignCriterion'] for r in read(customer, headers, LOCATIONS, opener)]
    return {'campaign': rows[0]['campaign']['resourceName'],
            'positive': {c['location']['geoTargetConstant']: c['resourceName'] for c in locations if not c.get('negative')},
            'negative': {c['location']['geoTargetConstant']: c['resourceName'] for c in locations if c.get('negative')}}


def operations(current, exclude):
    ops = [{'campaignCriterionOperation': {'remove': name}} for geo, name in current['positive'].items() if geo != UKRAINE]
    if UKRAINE not in current['positive']:
        ops.append({'campaignCriterionOperation': {'create': {'campaign': current['campaign'],
                                                              'location': {'geoTargetConstant': UKRAINE}}}})
    ops += [{'campaignCriterionOperation': {'create': {'campaign': current['campaign'], 'negative': True,
                                                       'location': {'geoTargetConstant': geo}}}}
            for geo in sorted(exclude) if geo not in current['negative']]
    return ops


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    exclude = excluded(read(customer, headers, REGIONS, opener))
    value = {'exclude': exclude}
    names = ' '.join(exclude.values())
    if not all(word in names for word in EXCLUDE):
        value.update(status='FAIL', error='REGIONS_NOT_FOUND')
        return value
    before = state(customer, headers, opener)
    value['before'] = before
    ops = operations(before, exclude)
    if ops:
        status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                    json.dumps({'mutateOperations': ops}).encode(), headers, opener)
        if status != 200:
            value.update(status='FAIL', mutate={'http': status, **check.errors(answer)})
            return value
    after = state(customer, headers, opener)
    value['after'] = after
    value['status'] = 'PASS' if list(after['positive']) == [UKRAINE] and set(exclude) <= set(after['negative']) \
        else 'NOT_APPLIED'
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
