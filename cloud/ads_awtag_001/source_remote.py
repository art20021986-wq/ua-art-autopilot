"""Google Ads website conversion action for the Google tag on the site (owner 2026-11-27 «Да, поставь все как советует
Google» — Google's «Завершите настройку отслеживания конверсий»).

One googleAds:mutate creates «Заявка з сайту (тег Google Ads)»: WEBPAGE, category SUBMIT_LEAD_FORM, one per click,
secondary (the GA4 generate_lead import stays primary until the tag is seen recording, so nothing is counted twice).
Then it reads the action's tag snippets and reports the tag id (AW-…) and the event's send_to — public values that go
into the site's Google tag. Never twice: an action with this name is only read. No site, CRM or bot change.
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
NAME = 'Заявка з сайту (тег Google Ads)'
QUERY = ("SELECT conversion_action.resource_name, conversion_action.name, conversion_action.status, "
         "conversion_action.type, conversion_action.primary_for_goal, conversion_action.tag_snippets "
         "FROM conversion_action WHERE conversion_action.name = '%s'" % NAME)
SEND_TO = re.compile(r"""send_to['"]?\s*:\s*['"](AW-[0-9]+/[A-Za-z0-9_-]+)['"]""")
TAG_ID = re.compile(r"\b(AW-[0-9]+)\b")


def read(customer, headers, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': QUERY}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    return answer.get('results', [])


def operation():
    return {'conversionActionOperation': {'create': {
        'name': NAME, 'type': 'WEBPAGE', 'category': 'SUBMIT_LEAD_FORM', 'status': 'ENABLED',
        'countingType': 'ONE_PER_CLICK', 'primaryForGoal': False, 'clickThroughLookbackWindowDays': 30,
        'valueSettings': {'defaultValue': 0, 'alwaysUseDefaultValue': True}}}}


def tag(row):
    """(tag id, send_to) from the action's snippets."""
    snippets = row.get('conversionAction', {}).get('tagSnippets', [])
    text = ' '.join(str(v) for s in snippets for v in s.values()).replace('&#39;', "'").replace('&quot;', '"')
    send_to = SEND_TO.search(text)
    tag_id = TAG_ID.search(text)
    return (tag_id.group(1) if tag_id else None), (send_to.group(1) if send_to else None)


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    rows = read(customer, headers, opener)
    value = {'existed': bool(rows), 'operations': 0}
    if not rows:
        status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                    json.dumps({'mutateOperations': [operation()]}).encode(), headers, opener)
        if status != 200:
            value.update(status='FAIL', mutate={'http': status, **check.errors(answer)})
            return value
        value['operations'] = 1
        rows = read(customer, headers, opener)
    if len(rows) != 1:
        value.update(status='FAIL', error='ACTIONS_%d' % len(rows))
        return value
    action = rows[0]['conversionAction']
    tag_id, send_to = tag(rows[0])
    value.update(action={k: action.get(k) for k in ('name', 'status', 'type', 'primaryForGoal')},
                 tag_id=tag_id, send_to=send_to, snippet_types=[s.get('type') for s in action.get('tagSnippets', [])])
    value['status'] = 'PASS' if tag_id and send_to else 'NO_SNIPPET'
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
