"""Campaign geography (owner 2026-11-26 via the coordinator, final: «Запорожье город, Херсон, Днепропетровский город
показывать. И все, что ближе ко Львову … В сторону Донецка … не показывать»; «Да» — Харьков и Сумы, только города).

R2: R1 stopped safely (Crimea, Sevastopol, Donetsk and Luhansk were not found under those names), so nothing is
excluded: only the wanted places are targeted. The campaign now targets exactly: 18 central and western regions in full, and only the cities of
Zaporizhzhia, Kherson, Dnipro, Kharkiv and Sumy; every other location criterion is removed. Each name must be found
exactly once in Google's list, or nothing changes. One all-or-nothing googleAds:mutate; people located there only.
State before and after in the report. No site, CRM or bot change.
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
# Region stems (Google's English names; spelling variants) — whole regions.
REGIONS_IN = {'Kyiv city': ('Kyiv city',), 'Kyiv Oblast': ('Kyiv Oblast',), 'Zhytomyr': ('Zhytomyr',),
              'Vinnytsia': ('Vinnyts',), 'Cherkasy': ('Cherkas',), 'Kirovohrad': ('Kirovohrad', 'Kirovograd', 'Kropyvnyts'),
              'Poltava': ('Poltav',), 'Chernihiv': ('Chernih',), 'Mykolaiv': ('Mykolai', 'Nikolaev'),
              'Odesa': ('Odes',), 'Khmelnytskyi': ('Khmelnyts',), 'Rivne': ('Rivne', 'Rovno'), 'Volyn': ('Volyn',),
              'Lviv': ('Lviv',), 'Ternopil': ('Ternopil',), 'Ivano-Frankivsk': ('Ivano-Frankivsk',),
              'Zakarpattia': ('Zakarpat', 'Transcarpath'), 'Chernivtsi': ('Chernivts',)}
# Only the city (its region stays out).
CITIES_IN = {'Zaporizhzhia': ('Zaporizhzhia', 'Zaporizhia', 'Zaporozhye'), 'Kherson': ('Kherson',),
             'Dnipro': ('Dnipro', 'Dnipropetrovsk'), 'Kharkiv': ('Kharkiv',), 'Sumy': ('Sumy',)}


def plain(name):
    return name.replace("'", '').replace('’', '')
CAMPAIGN = "SELECT campaign.resource_name FROM campaign WHERE campaign.name = '%s'" % NAME
LOCATIONS = ("SELECT campaign_criterion.resource_name, campaign_criterion.location.geo_target_constant, "
             "campaign_criterion.negative FROM campaign_criterion WHERE campaign.name = '%s' "
             "AND campaign_criterion.type = 'LOCATION'" % NAME)
REGIONS = ("SELECT geo_target_constant.resource_name, geo_target_constant.name, geo_target_constant.target_type, "
           "geo_target_constant.canonical_name, geo_target_constant.status FROM geo_target_constant "
           "WHERE geo_target_constant.country_code = 'UA'")
WIDE = ('Region', 'Autonomous Republic', 'Province', 'State', 'Territory')


def read(customer, headers, query, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': query}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    return answer.get('results', [])


def wanted(rows):
    """({resource: name} to target, [missing]): each region stem must match one whole region, each city one city."""
    live = [r['geoTargetConstant'] for r in rows if r['geoTargetConstant'].get('status', 'ENABLED') == 'ENABLED']
    found, missing = {}, []
    for label, stems in REGIONS_IN.items():
        hits = [g for g in live if g.get('targetType') in WIDE and any(plain(g['name']).startswith(s) for s in stems)]
        if label == 'Kyiv city':
            hits = [g for g in live if g['name'] == 'Kyiv city']
        if label == 'Kyiv Oblast':
            hits = [g for g in live if g['name'] == 'Kyiv Oblast']
        if len(hits) == 1:
            found[hits[0]['resourceName']] = hits[0]['name']
        else:
            missing.append('%s:%d' % (label, len(hits)))
    for label, stems in CITIES_IN.items():
        hits = [g for g in live if g.get('targetType') == 'City' and plain(g['name']) in stems]
        if len(hits) == 1:
            found[hits[0]['resourceName']] = '%s (%s)' % (hits[0]['name'], hits[0].get('canonicalName', ''))
        else:
            missing.append('%s:%s' % (label, [h['name'] for h in hits][:4]))
    return found, missing


def state(customer, headers, opener=urllib.request.urlopen):
    rows = read(customer, headers, CAMPAIGN, opener)
    if len(rows) != 1:
        raise check.CheckError('CAMPAIGNS_%d' % len(rows))
    locations = [r['campaignCriterion'] for r in read(customer, headers, LOCATIONS, opener)]
    return {'campaign': rows[0]['campaign']['resourceName'],
            'positive': {c['location']['geoTargetConstant']: c['resourceName'] for c in locations if not c.get('negative')},
            'negative': {c['location']['geoTargetConstant']: c['resourceName'] for c in locations if c.get('negative')}}


def operations(current, target):
    ops = [{'campaignCriterionOperation': {'remove': name}} for geo, name in current['positive'].items() if geo not in target]
    ops += [{'campaignCriterionOperation': {'remove': name}} for name in current['negative'].values()]
    ops += [{'campaignCriterionOperation': {'create': {'campaign': current['campaign'], 'location': {'geoTargetConstant': geo}}}}
            for geo in sorted(target) if geo not in current['positive']]
    return ops


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    target, missing = wanted(read(customer, headers, REGIONS, opener))
    value = {'target': target}
    if missing:
        value.update(status='FAIL', error='LOCATIONS_NOT_FOUND', missing=missing)
        return value
    before = state(customer, headers, opener)
    value['before'] = before
    ops = operations(before, target)
    if ops:
        status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                    json.dumps({'mutateOperations': ops}).encode(), headers, opener)
        if status != 200:
            value.update(status='FAIL', mutate={'http': status, **check.errors(answer)})
            return value
    after = state(customer, headers, opener)
    value['after'] = after
    value['status'] = 'PASS' if set(after['positive']) == set(target) and not after['negative'] else 'NOT_APPLIED'
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
