"""Google Ads lead conversions on (owner «Да» 2026-11-25 to «Включаю учёт заявок в рекламном кабинете (шаг 1)?»).

The GA4 events are already linked to the advertiser account but stay HIDDEN and secondary, so ads cannot learn which
click brought a lead. This turns on:
- «UA ART (web) generate_lead» (site enquiry forms): ENABLED, primary for the goal;
- «UA ART (web) contact» (phone / messenger buttons): ENABLED, secondary (counted, not used for bidding).
R1 (validate-only): Google refused counting_type for GA4 imports (IMMUTABLE_FIELD: counting follows GA4, one form
sent = one event), so R2 changes status and primary only, saved (APPLY True; the mutate is all-or-nothing).
The other GA4 actions (purchase, qualify_lead, close_convert_lead) stay as they are.
APPLY False = Google checks the change without saving it (validateOnly); True = the change is saved. Each run reads the
actions before and after; the before-state is in the report, so a rollback is one call back. No campaign, budget or
spending; no site, CRM or bot change; no key value in the report.
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
APPLY = True
QUERY = ('SELECT conversion_action.resource_name, conversion_action.name, conversion_action.status, '
         'conversion_action.type, conversion_action.category, conversion_action.primary_for_goal, '
         'conversion_action.counting_type FROM conversion_action')
WANT = {  # type -> wanted fields
    'GOOGLE_ANALYTICS_4_GENERATE_LEAD': {'status': 'ENABLED', 'primaryForGoal': True},
    'GOOGLE_ANALYTICS_4_CUSTOM': {'status': 'ENABLED', 'primaryForGoal': False},
}
CUSTOM_NAME = 'UA ART (web) contact'
MASK = {'status': 'status', 'primaryForGoal': 'primary_for_goal'}


def actions(customer, headers, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': QUERY}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    return [r['conversionAction'] for r in answer.get('results', [])]


def operations(rows):
    """Update operations for the two lead actions; only fields that differ."""
    found = []
    for row in rows:
        want = WANT.get(row.get('type'))
        if not want or (row['type'] == 'GOOGLE_ANALYTICS_4_CUSTOM' and row.get('name') != CUSTOM_NAME):
            continue
        change = {k: v for k, v in want.items() if row.get(k, False if k == 'primaryForGoal' else None) != v}
        if change:
            found.append({'update': dict(change, resourceName=row['resourceName']),
                          'updateMask': ','.join(MASK[k] for k in sorted(change))})
    return found


def run(keys, apply=APPLY, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = actions(customer, headers, opener)
    ops = operations(before)
    value = {'apply': apply, 'before': before, 'operations': ops}
    lead = [r for r in before if r.get('type') == 'GOOGLE_ANALYTICS_4_GENERATE_LEAD']
    if len(lead) != 1:
        raise check.CheckError('GENERATE_LEAD_ACTIONS_%d' % len(lead))
    if ops:
        status, answer = check.call(check.API + 'customers/%s/conversionActions:mutate' % customer,
                                    json.dumps({'operations': ops, 'validateOnly': not apply}).encode(), headers, opener)
        value['mutate'] = {'http': status, **(check.errors(answer) if status != 200 else
                                              {'results': answer.get('results', [])})}
        if status != 200:
            value['status'] = 'FAIL'
            return value
    value['after'] = actions(customer, headers, opener)
    left = operations(value['after'])
    value['status'] = 'PASS' if not apply or not left else 'NOT_APPLIED'
    value['left'] = left
    return value


def report(path=check.KEYS_PATH, apply=APPLY, opener=urllib.request.urlopen):
    keys = json.loads(Path(path).read_text(encoding='utf-8'))
    if not all(keys.get(n) for n in check.KEY_NAMES + ('login_customer_id', 'customer_id')):
        return json.dumps({'status': 'KEYS_INCOMPLETE'})
    try:
        value = run(keys, apply, opener)
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
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=1 if APPLY else 0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
