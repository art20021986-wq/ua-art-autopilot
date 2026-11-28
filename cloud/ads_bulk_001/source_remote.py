"""Kyiv campaign at 1 UAH a click with thousands of buyer searches (owner 2026-11-26 via the coordinator: «гривню одну мне
сделай … поисковых запросов 5000 … все, что связано непосредственно с автомобилями … на украинском и русском»).

1. One googleAds:mutate (partialFailure): Maximize clicks ceiling → 1 UAH, the extra negative phrases, the missing brand
   groups with one responsive ad each (approved texts, «під ключ» page of the same language).
2. Today's part of keywords.plan() (keywords.today: up to PER_DAY, phrase match, skipping any already in the group) in
   chunks of CHUNK operations, partialFailure; refused ones are listed (the Explorer API level allows ~2 880
   operations a day — the rest goes in the next run).
3. 2026-11-26 (owner «Все да»): «model + year from Korea» groups «UA — Аукціон — <brand>» / «RU — Аукцион — <brand>»
   to the auction lots page korea.html, headlines about the lots first; ceiling 2 UAH.
State before and after in the report; budget and other settings unchanged. No site, CRM or bot change.
"""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import urllib.request

import keywords
import plan
import source_check as check

HERE = Path(__file__).resolve().parent
CEILING_MICROS = 4550000  # 4,55 UAH (owner 2026-11-27 «став тогда 4 гривни 55 копеек»; was 3,50)
# 2026-11-26: the campaign may be renamed «Пошук — Україна — Корея (UA ART)» (owner «Да, переименуй»).
NAMES = "'%s', 'Пошук — Україна — Корея (UA ART)'" % plan.NAME
CHUNK = 600
AUCTION_PAGE = plan.SITE + 'korea.html'  # the lots of the coming Korean auctions (filters by make, model, year)
# 2026-11-27: «Ставка онлайн …» removed (owner «Да»): 7 of 32 auction ads were refused as PROHIBITED (read as gambling).
AUCTION_HEAD = {'uk': ['Лоти аукціонів Кореї щодня', 'Ціни та фото кожного лоту', 'Фільтр: марка, модель, рік',
                       'Курс НБУ щодня'],
                'ru': ['Лоты аукционов Кореи ежедневно', 'Цены и фото каждого лота', 'Фильтр: марка, модель, год',
                       'Курс НБУ каждый день']}
HUB = {'uk': plan.SITE + 'seo/ua/avto-z-korei-do-kyieva-pid-kluch.html',
       'ru': plan.SITE + 'seo/ru/avto-iz-korei-v-kiev-pod-kluch.html'}
CAMPAIGN = ("SELECT campaign.resource_name, campaign.target_spend.cpc_bid_ceiling_micros, campaign_budget.amount_micros "
            "FROM campaign WHERE campaign.name IN (%s)" % NAMES)
GROUPS = "SELECT ad_group.resource_name, ad_group.name FROM ad_group WHERE campaign.name IN (%s)" % NAMES
KEYWORDS = ("SELECT ad_group.name, ad_group_criterion.keyword.text FROM ad_group_criterion WHERE campaign.name IN (%s) "
            "AND ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.negative = FALSE" % NAMES)
ADS = ("SELECT ad_group.name, ad_group_ad.status FROM ad_group_ad WHERE campaign.name IN (%s) "
       "AND ad_group_ad.status != 'REMOVED'" % NAMES)
NEGATIVES = ("SELECT campaign_criterion.keyword.text FROM campaign_criterion WHERE campaign.name IN (%s) "
             "AND campaign_criterion.negative = TRUE AND campaign_criterion.type = 'KEYWORD'" % NAMES)


def read(customer, headers, query, opener=urllib.request.urlopen):
    rows, token = [], None
    while True:
        body = {'query': query, **({'pageToken': token} if token else {})}
        status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer, json.dumps(body).encode(),
                                    headers, opener)
        if status != 200:
            raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
        rows += answer.get('results', [])
        token = answer.get('nextPageToken')
        if not token:
            return rows


def state(customer, headers, opener=urllib.request.urlopen):
    rows = read(customer, headers, CAMPAIGN, opener)
    if len(rows) != 1:
        raise check.CheckError('CAMPAIGNS_%d' % len(rows))
    return {'campaign': rows[0]['campaign'], 'budget': rows[0].get('campaignBudget', {}),
            'groups': {r['adGroup']['name']: r['adGroup']['resourceName'] for r in read(customer, headers, GROUPS, opener)},
            'keywords': {(r['adGroup']['name'], r['adGroupCriterion']['keyword']['text'])
                         for r in read(customer, headers, KEYWORDS, opener)},
            'negatives': {r['campaignCriterion']['keyword']['text'] for r in read(customer, headers, NEGATIVES, opener)},
            'with_ads': {r['adGroup']['name'] for r in read(customer, headers, ADS, opener)}}


def ad_texts(group):
    lang = 'uk' if group.startswith('UA') else 'ru'
    auction = group.startswith(tuple(keywords.AUCTION.values()))
    brand = group.rsplit(' — ', 1)[1] if auction else group.split(' — ', 1)[1]
    first = {'Інші марки з Кореї': 'Будь-яка марка з Кореї', 'Другие марки из Кореи': 'Любая марка из Кореи'}.get(
        brand, '%s %s' % (brand, 'з Кореї' if lang == 'uk' else 'из Кореи'))
    head = ([first, 'Авто з Кореї під ключ'] + plan.UK_HEAD) if lang == 'uk' else \
        ([first, 'Авто из Кореи под ключ'] + plan.RU_HEAD)
    if auction:
        head = [first] + AUCTION_HEAD[lang] + head[1:]
    head = [h for n, h in enumerate(head) if len(h) <= 30 and h not in head[:n]][:15]
    return lang, head, plan.UK_DESC if lang == 'uk' else plan.RU_DESC


def first_operations(customer, current):
    campaign = current['campaign']
    ops = []
    if int(campaign.get('targetSpend', {}).get('cpcBidCeilingMicros', 0)) != CEILING_MICROS:
        ops.append({'campaignOperation': {'update': {'resourceName': campaign['resourceName'],
                                                     'targetSpend': {'cpcBidCeilingMicros': str(CEILING_MICROS)}},
                                          'updateMask': 'target_spend.cpc_bid_ceiling_micros'}})
    ops += [{'campaignCriterionOperation': {'create': {'campaign': campaign['resourceName'], 'negative': True,
                                                       'keyword': {'text': w, 'matchType': 'PHRASE'}}}}
            for w in keywords.NEGATIVE_MORE if w not in current['negatives']]
    def ad(group, ad_group):
        lang, head, desc = ad_texts(group)
        auction = group.startswith(tuple(keywords.AUCTION.values()))
        return {'adGroupAdOperation': {'create': {'adGroup': ad_group, 'status': 'ENABLED', 'ad': {
            'finalUrls': [AUCTION_PAGE if auction else HUB[lang]],
            'responsiveSearchAd': {'headlines': [{'text': h} for h in head],
                                   'descriptions': [{'text': d} for d in desc],
                                   'path1': 'korea', 'path2': 'kyiv' if lang == 'uk' else 'kiev'}}}}}
    for n, group in enumerate(g for g in keywords.plan() if g not in current['groups']):
        temp = 'customers/%s/adGroups/-%d' % (customer, 700 + n)
        ops.append({'adGroupOperation': {'create': {'resourceName': temp, 'name': group, 'status': 'ENABLED',
                                                    'campaign': campaign['resourceName'], 'type': 'SEARCH_STANDARD'}}})
        ops.append(ad(group, temp))
    # 2026-11-27: groups that exist without an ad (the refused ones) get one.
    ops += [ad(g, current['groups'][g]) for g in keywords.plan()
            if g in current['groups'] and g not in current.get('with_ads', set(current['groups']))]
    return ops


def keyword_operations(current, limit=None):
    return [{'adGroupCriterionOperation': {'create': {'adGroup': current['groups'][g], 'status': 'ENABLED',
                                                      'keyword': {'text': k, 'matchType': 'PHRASE'}}}}
            for g, k in keywords.today(current['keywords'], limit or keywords.PER_DAY) if g in current['groups']]


def findings(failure):
    found = []
    for detail in (failure or {}).get('details', []) or []:
        for item in detail.get('errors', []) or []:
            entry = {'code': json.dumps(item.get('errorCode', {})), 'message': str(item.get('message', ''))[:120]}
            # 2026-11-28: which policy and which text Google refused (4 «Аукціон» ads, PROHIBITED).
            policy = item.get('details', {}).get('policyFindingDetails', {}).get('policyTopicEntries', [])
            if policy:
                entry['policy'] = [{'topic': t.get('topic'), 'type': t.get('type'),
                                    'evidence': json.dumps(t.get('evidences', []), ensure_ascii=False)[:300]} for t in policy]
            path = item.get('location', {}).get('fieldPathElements', [])
            if path:
                entry['field'] = '.'.join('%s%s' % (e.get('fieldName'), '[%s]' % e['index'] if 'index' in e else '')
                                         for e in path)
            found.append(entry)
    return found


KEYWORD_ROWS = ("SELECT ad_group.name, ad_group_criterion.resource_name, ad_group_criterion.keyword.text, "
                "ad_group_criterion.keyword.match_type FROM ad_group_criterion WHERE campaign.name IN (%s) "
                "AND ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.negative = FALSE "
                "AND ad_group_criterion.status != 'REMOVED'" % NAMES)
GENERIC = ('UA — Будь-яка модель з Кореї', 'RU — Любая модель из Кореи', 'UA — Корея під ключ', 'RU — Корея под ключ')


def redundant(rows):
    """Resource names of duplicate keywords (Google's «remove redundant keywords», owner «сделай все, как хочет Google»):
    an exact keyword whose text is also a phrase keyword in the same group, and the same text and match type in more than
    one group (the copy kept: the group the plan puts it in, else a specific group over a generic one)."""
    plan_group = {k: g for g, ks in keywords.plan().items() for k in ks}
    by_group, by_text = {}, {}
    for r in rows:
        g, c = r['adGroup']['name'], r['adGroupCriterion']
        text, match = c['keyword']['text'], c['keyword']['matchType']
        by_group.setdefault((g, text), {})[match] = c['resourceName']
        by_text.setdefault((text, match), []).append((g, c['resourceName']))
    gone = {kinds['EXACT'] for kinds in by_group.values() if 'EXACT' in kinds and 'PHRASE' in kinds}
    for (text, match), places in by_text.items():
        places = [p for p in places if p[1] not in gone]
        if len(places) < 2:
            continue
        keep = next((p for p in places if p[0] == plan_group.get(text)), None) or \
            sorted(places, key=lambda p: (p[0] in GENERIC, p[0]))[0]
        gone.update(r for _, r in places if r != keep[1])
    return sorted(gone)


def mutate(customer, headers, ops, opener):
    status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                json.dumps({'mutateOperations': ops, 'partialFailure': True}).encode(), headers, opener)
    if status != 200:
        return {'http': status, **check.errors(answer)}
    refused = findings(answer.get('partialFailureError'))
    return {'sent': len(ops), 'refused': len(refused), 'codes': sorted({r['code'] for r in refused})[:8],
            'examples': refused[:8]}


def summary(current):
    groups = sorted(current['groups'])
    kws = current['keywords']
    return {'ceiling': current['campaign'].get('targetSpend'), 'budget': current['budget'].get('amountMicros'),
            'groups': len(groups), 'keywords': len(kws),
            'keywords_uk': sum(1 for g, _ in kws if g.startswith('UA')), 'keywords_ru': sum(1 for g, _ in kws if g.startswith('RU')),
            'negatives': len(current['negatives']), 'groups_without_ad': sorted(set(groups) - current.get('with_ads', set(groups)))}


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = state(customer, headers, opener)
    value = {'before': summary(before), 'steps': []}
    first = first_operations(customer, before)
    if first:
        value['steps'].append({'first': mutate(customer, headers, first, opener)})
    remove = redundant(read(customer, headers, KEYWORD_ROWS, opener))
    value['duplicates_removed'] = 0
    for start in range(0, len(remove), CHUNK):
        result = mutate(customer, headers, [{'adGroupCriterionOperation': {'remove': r}}
                                            for r in remove[start:start + CHUNK]], opener)
        value['steps'].append({'duplicates_%d' % start: result})
        if 'http' in result:
            break
        value['duplicates_removed'] += result['sent'] - result['refused']
    middle = state(customer, headers, opener)
    ops = keyword_operations(middle)
    for start in range(0, len(ops), CHUNK):
        result = mutate(customer, headers, ops[start:start + CHUNK], opener)
        value['steps'].append({'keywords_%d' % start: result})
        if 'http' in result:
            break
    after = state(customer, headers, opener)
    value['after'] = summary(after)
    value['added_now'] = value['after']['keywords'] - value['before']['keywords'] + value['duplicates_removed']
    value['plan_total'] = sum(map(len, keywords.plan().values()))
    value['left_for_next_run'] = len(keyword_operations(after, limit=10 ** 6))
    value['status'] = 'PASS' if value['after']['ceiling'] == {'cpcBidCeilingMicros': str(CEILING_MICROS)} \
        and value['added_now'] > 0 else 'PARTIAL'
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
    resource.setrlimit(resource.RLIMIT_CPU, (240, 250))
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
