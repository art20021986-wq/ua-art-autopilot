"""Campaign schedule and name (27.11: round the clock — every ad-schedule criterion removed, owner «Да давай включим,
включая 24/7») (owner 2026-11-26 via the coordinator: «по Украине с 9 утра до 2 часов ночи … Да,
переименуй»; «да» in this chat before the write).

Every day 09:00–24:00 and 00:00–02:00 (account time zone Kyiv) instead of 09:00–20:00; the campaign is renamed
«Пошук — Україна — Корея (UA ART)». One all-or-nothing googleAds:mutate (the old schedule removed, the new one added,
the name updated); state before and after in the report. The click ceiling, budget, keywords and places stay. No site,
CRM or bot change.
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
OLD_NAME = 'Пошук — Київ — Корея (UA ART)'
NEW_NAME = 'Пошук — Україна — Корея (UA ART)'
DAYS = ('MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY')
SLOTS = ()  # 2026-11-27: owner «включим, включая 24/7» — no ad schedule = all hours (was 09:00–24:00 + 00:00–02:00)


def query(name):
    return ("SELECT campaign.resource_name, campaign.name, campaign_criterion.resource_name, "
            "campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, "
            "campaign_criterion.ad_schedule.end_hour FROM campaign_criterion WHERE campaign.name = '%s' "
            "AND campaign_criterion.type = 'AD_SCHEDULE'" % name)


def campaign(name):
    return "SELECT campaign.resource_name, campaign.name, campaign.status FROM campaign WHERE campaign.name = '%s'" % name


def read(customer, headers, q, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': q}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    return answer.get('results', [])


def state(customer, headers, opener=urllib.request.urlopen):
    for name in (OLD_NAME, NEW_NAME):
        rows = read(customer, headers, campaign(name), opener)
        if rows:
            slots = sorted((r['campaignCriterion']['adSchedule']['dayOfWeek'], r['campaignCriterion']['adSchedule']['startHour'],
                            r['campaignCriterion']['adSchedule']['endHour'], r['campaignCriterion']['resourceName'])
                           for r in read(customer, headers, query(name), opener))
            return {'campaign': rows[0]['campaign'], 'slots': slots}
    raise check.CheckError('CAMPAIGN_NOT_FOUND')


def wanted():
    return sorted((d, a, b) for d in DAYS for a, b in SLOTS)


def operations(current):
    resource_name = current['campaign']['resourceName']
    have = [(d, a, b) for d, a, b, _ in current['slots']]
    ops = []
    if sorted(have) != wanted():
        ops += [{'campaignCriterionOperation': {'remove': r}} for _, _, _, r in current['slots']]
        ops += [{'campaignCriterionOperation': {'create': {'campaign': resource_name, 'adSchedule': {
            'dayOfWeek': d, 'startHour': a, 'startMinute': 'ZERO', 'endHour': b, 'endMinute': 'ZERO'}}}}
                for d, a, b in wanted()]
    if current['campaign']['name'] != NEW_NAME:
        ops.append({'campaignOperation': {'update': {'resourceName': resource_name, 'name': NEW_NAME},
                                          'updateMask': 'name'}})
    return ops


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = state(customer, headers, opener)
    ops = operations(before)
    value = {'before': {'name': before['campaign']['name'], 'slots': [s[:3] for s in before['slots']]},
             'operations': len(ops)}
    if ops:
        status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                    json.dumps({'mutateOperations': ops}).encode(), headers, opener)
        if status != 200:
            value.update(status='FAIL', mutate={'http': status, **check.errors(answer)})
            return value
    after = state(customer, headers, opener)
    value['after'] = {'name': after['campaign']['name'], 'slots': [s[:3] for s in after['slots']]}
    value['status'] = 'PASS' if not operations(after) else 'NOT_APPLIED'
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
