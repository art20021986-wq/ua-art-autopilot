"""Campaign click ceiling 1 → 2 UAH (owner 2026-11-26 via the coordinator: «Давай сразу на 2 гривни переходи и сделай шаг …
Будем постепенно добавлять»; «да» in this chat before the write).

One googleAds:mutate that updates only campaign.target_spend.cpc_bid_ceiling_micros (Maximize clicks) to 2 UAH; state
before and after in the report. Budget, keywords, places, schedule and name stay. No site, CRM or bot change.
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
CEILING_UAH = 2
NAMES = "'Пошук — Україна — Корея (UA ART)', 'Пошук — Київ — Корея (UA ART)'"
QUERY = ("SELECT campaign.resource_name, campaign.name, campaign.status, campaign.target_spend.cpc_bid_ceiling_micros, "
         "campaign_budget.amount_micros FROM campaign WHERE campaign.name IN (%s)" % NAMES)


def state(customer, headers, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': QUERY}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    rows = answer.get('results', [])
    if len(rows) != 1:
        raise check.CheckError('CAMPAIGNS_%d' % len(rows))
    row = rows[0]
    return {'resource': row['campaign']['resourceName'], 'name': row['campaign']['name'],
            'status': row['campaign'].get('status'), 'budget': row.get('campaignBudget', {}).get('amountMicros'),
            'ceiling': int(row['campaign'].get('targetSpend', {}).get('cpcBidCeilingMicros', 0))}


def operations(current):
    if current['ceiling'] == CEILING_UAH * 1000000:
        return []
    return [{'campaignOperation': {'update': {'resourceName': current['resource'],
                                              'targetSpend': {'cpcBidCeilingMicros': str(CEILING_UAH * 1000000)}},
                                   'updateMask': 'target_spend.cpc_bid_ceiling_micros'}}]


def public(current):
    return {k: current[k] for k in ('name', 'status', 'budget', 'ceiling')}


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = state(customer, headers, opener)
    ops = operations(before)
    value = {'before': public(before), 'operations': len(ops)}
    if ops:
        status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                    json.dumps({'mutateOperations': ops}).encode(), headers, opener)
        if status != 200:
            value.update(status='FAIL', mutate={'http': status, **check.errors(answer)})
            return value
    after = state(customer, headers, opener)
    value['after'] = public(after)
    value['status'] = 'PASS' if not operations(after) and after['budget'] == before['budget'] else 'NOT_APPLIED'
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
