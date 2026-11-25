"""Turn on the Kyiv Search campaign at 300 UAH a day (owner «Первое да, второе да» 2026-11-25 to «Бюджет на тест — 300 грн
в день?» and «Включаем кампанию сразу после установки формы, тест 14 дней?»).

Reads «Пошук — Київ — Корея (UA ART)» (created PAUSED by ADS-CAMP-20261125-R6) and its budget, then one all-or-nothing
googleAds:mutate: the budget to 300 UAH a day and the campaign ENABLED. Reads both again after. Nothing else changes; the
state before is in the report (pausing again is one call). No site, CRM or bot change; no key value in the report.
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
BUDGET_UAH = 300
QUERY = ("SELECT campaign.resource_name, campaign.status, campaign_budget.resource_name, campaign_budget.amount_micros "
         "FROM campaign WHERE campaign.name = '%s'" % NAME)


def state(customer, headers, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': QUERY}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    rows = answer.get('results', [])
    if len(rows) != 1:
        raise check.CheckError('CAMPAIGNS_%d' % len(rows))
    return {'campaign': rows[0]['campaign'], 'budget': rows[0]['campaignBudget']}


def operations(current):
    ops = []
    if int(current['budget'].get('amountMicros', 0)) != BUDGET_UAH * 1000000:
        ops.append({'campaignBudgetOperation': {'update': {'resourceName': current['budget']['resourceName'],
                                                           'amountMicros': str(BUDGET_UAH * 1000000)},
                                                'updateMask': 'amount_micros'}})
    if current['campaign'].get('status') != 'ENABLED':
        ops.append({'campaignOperation': {'update': {'resourceName': current['campaign']['resourceName'],
                                                     'status': 'ENABLED'}, 'updateMask': 'status'}})
    return ops


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = state(customer, headers, opener)
    ops = operations(before)
    value = {'before': before, 'operations': ops}
    if ops:
        status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                    json.dumps({'mutateOperations': ops}).encode(), headers, opener)
        if status != 200:
            value.update(status='FAIL', mutate={'http': status, **check.errors(answer)})
            return value
    value['after'] = after = state(customer, headers, opener)
    ok = after['campaign'].get('status') == 'ENABLED' and int(after['budget'].get('amountMicros', 0)) == BUDGET_UAH * 1000000
    value['status'] = 'PASS' if ok else 'NOT_APPLIED'
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
