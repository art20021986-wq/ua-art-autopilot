"""Kyiv campaign: cheaper clicks and more buyer searches (owner 2026-11-26: «расширь ассортимент, уменьши еще сумму за клик
до 10-5 гривен, до 7 гривен за переход на сайт, чтобы 300 гривен были максимально насыщенными переходами»).

- Maximize clicks ceiling 15 → 7 UAH.
- The «Корея під ключ» / «Корея под ключ» groups get more buyer phrasings (cars from Korea, order, delivery, bring,
  South Korea, gas, auction), phrase and exact.
- Two new groups «Будь-яка модель з Кореї» (uk) / «Любая модель из Кореи» (ru): popular Korean-market models beyond our
  five and the German brands asked yesterday («bmw из кореи»), to the «під ключ» page (with the form), the approved texts.
One googleAds:mutate with partialFailure (accepted parts are saved, refused ones listed); keywords already in a group are
skipped, a group is never created twice; state before and after in the report. No site, CRM or bot change.
"""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import urllib.request

import plan
import source_check as check

HERE = Path(__file__).resolve().parent
CEILING_UAH = 7
MATCHES = ('PHRASE', 'EXACT')
MORE = {
    'UA — Корея під ключ': ['машини з кореї', 'автомобілі з кореї', 'купити авто з кореї київ', 'замовити авто з кореї',
                           'доставка авто з кореї', 'привезти авто з кореї', 'авто з південної кореї', 'авто з кореї ціна',
                           'корейські авто під замовлення', 'авто з кореї на газу', 'авто з аукціону кореї'],
    'RU — Корея под ключ': ['машины из кореи', 'машины с кореи', 'автомобили из кореи', 'авто с кореи',
                           'купить авто с кореи', 'заказать авто из кореи', 'доставка авто из кореи',
                           'привезти авто из кореи', 'авто из южной кореи', 'авто из кореи цена',
                           'корейские авто под заказ', 'авто из кореи на газу', 'авто с аукциона кореи'],
}
OTHER_UK = ['kia sorento', 'kia carnival', 'kia k8', 'kia k3', 'kia niro', 'kia seltos', 'hyundai palisade',
            'hyundai grandeur', 'hyundai avante', 'hyundai kona', 'hyundai staria', 'genesis', 'kia', 'hyundai',
            'bmw', 'mercedes', 'audi']
OTHER_RU = OTHER_UK + ['киа соренто', 'киа карнивал', 'хендай палисад', 'хендай грандеур', 'генезис', 'киа', 'хендай',
                       'хюндай', 'мерседес', 'бмв', 'ауди']
NEW_GROUPS = [
    {'name': 'UA — Будь-яка модель з Кореї', 'url': plan.SITE + 'seo/ua/avto-z-korei-do-kyieva-pid-kluch.html',
     'keywords': ['%s з кореї' % m for m in OTHER_UK],
     'headlines': ['Будь-яка модель з Кореї', 'Авто з Кореї під ключ'] + plan.UK_HEAD, 'descriptions': plan.UK_DESC,
     'path': ('korea', 'kyiv')},
    {'name': 'RU — Любая модель из Кореи', 'url': plan.SITE + 'seo/ru/avto-iz-korei-v-kiev-pod-kluch.html',
     'keywords': ['%s из кореи' % m for m in OTHER_RU],
     'headlines': ['Любая модель из Кореи', 'Авто из Кореи под ключ'] + plan.RU_HEAD, 'descriptions': plan.RU_DESC,
     'path': ('korea', 'kiev')},
]
CAMPAIGN = ("SELECT campaign.resource_name, campaign.target_spend.cpc_bid_ceiling_micros FROM campaign "
            "WHERE campaign.name = '%s'" % plan.NAME)
GROUPS = "SELECT ad_group.resource_name, ad_group.name FROM ad_group WHERE campaign.name = '%s'" % plan.NAME
KEYWORDS = ("SELECT ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type "
            "FROM ad_group_criterion WHERE campaign.name = '%s' AND ad_group_criterion.type = 'KEYWORD' "
            "AND ad_group_criterion.negative = FALSE" % plan.NAME)


def read(customer, headers, query, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': query}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    return answer.get('results', [])


def state(customer, headers, opener=urllib.request.urlopen):
    rows = read(customer, headers, CAMPAIGN, opener)
    if len(rows) != 1:
        raise check.CheckError('CAMPAIGNS_%d' % len(rows))
    groups = {r['adGroup']['name']: r['adGroup']['resourceName'] for r in read(customer, headers, GROUPS, opener)}
    keywords = sorted({(r['adGroup']['name'], r['adGroupCriterion']['keyword']['text'],
                        r['adGroupCriterion']['keyword']['matchType']) for r in read(customer, headers, KEYWORDS, opener)})
    return {'campaign': rows[0]['campaign'], 'groups': groups, 'keywords': [list(k) for k in keywords]}


def keyword(ad_group, text, match):
    return {'adGroupCriterionOperation': {'create': {'adGroup': ad_group, 'status': 'ENABLED',
                                                     'keyword': {'text': text, 'matchType': match}}}}


def operations(customer, current):
    campaign = current['campaign']
    have = {tuple(k) for k in current['keywords']}
    ops = []
    if int(campaign.get('targetSpend', {}).get('cpcBidCeilingMicros', 0)) != CEILING_UAH * 1000000:
        ops.append({'campaignOperation': {'update': {'resourceName': campaign['resourceName'],
                                                     'targetSpend': {'cpcBidCeilingMicros': str(CEILING_UAH * 1000000)}},
                                          'updateMask': 'target_spend.cpc_bid_ceiling_micros'}})
    for name, words in MORE.items():
        if name in current['groups']:
            ops += [keyword(current['groups'][name], w, m) for w in words for m in MATCHES if (name, w, m) not in have]
    for n, group in enumerate(NEW_GROUPS):
        if group['name'] in current['groups']:
            ops += [keyword(current['groups'][group['name']], w, m) for w in group['keywords'] for m in MATCHES
                    if (group['name'], w, m) not in have]
            continue
        ad_group = 'customers/%s/adGroups/-%d' % (customer, 500 + n)
        ops.append({'adGroupOperation': {'create': {'resourceName': ad_group, 'name': group['name'],
                                                    'campaign': campaign['resourceName'], 'status': 'ENABLED',
                                                    'type': 'SEARCH_STANDARD'}}})
        ops += [keyword(ad_group, w, m) for w in group['keywords'] for m in MATCHES]
        ops.append({'adGroupAdOperation': {'create': {'adGroup': ad_group, 'status': 'ENABLED', 'ad': {
            'finalUrls': [group['url']], 'responsiveSearchAd': {
                'headlines': [{'text': h} for h in group['headlines'][:15]],
                'descriptions': [{'text': d} for d in group['descriptions']],
                'path1': group['path'][0], 'path2': group['path'][1]}}}}})
    return ops


def findings(failure):
    found = []
    for detail in (failure or {}).get('details', []) or []:
        for item in detail.get('errors', []) or []:
            path = item.get('location', {}).get('fieldPathElements', [])
            found.append({'index': path[0].get('index') if path else None, 'code': json.dumps(item.get('errorCode', {})),
                          'message': str(item.get('message', ''))[:160]})
    return found


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = state(customer, headers, opener)
    ops = operations(customer, before)
    value = {'before': {'ceiling': before['campaign'].get('targetSpend'), 'groups': sorted(before['groups']),
                        'keywords': len(before['keywords'])}, 'operation_count': len(ops)}
    if ops:
        status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                    json.dumps({'mutateOperations': ops, 'partialFailure': True}).encode(), headers, opener)
        if status != 200:
            value.update(status='FAIL', mutate={'http': status, **check.errors(answer)})
            return value
        value['refused'] = findings(answer.get('partialFailureError'))
    after = state(customer, headers, opener)
    value['after'] = {'ceiling': after['campaign'].get('targetSpend'), 'groups': sorted(after['groups']),
                      'keywords': len(after['keywords'])}
    value['left'] = len(operations(customer, after))
    value['status'] = 'PASS' if value['left'] == 0 else 'PARTIAL'
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
