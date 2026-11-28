"""Kyiv campaign at 1 UAH a click with thousands of buyer searches (owner 2026-11-26 via the coordinator: «гривню одну мне
сделай … поисковых запросов 5000 … все, что связано непосредственно с автомобилями … на украинском и русском»).

1. One googleAds:mutate (partialFailure): Maximize clicks ceiling → 1 UAH, the extra negative phrases, the missing brand
   groups with one responsive ad each (approved texts, «під ключ» page of the same language).
2. Today's part of keywords.plan() (keywords.today: up to PER_DAY, phrase match, skipping any already in the group) in
   chunks of CHUNK operations, partialFailure; refused ones are listed (the Explorer API level allows ~2 880
   operations a day — the rest goes in the next run).
3. 2026-11-26 (owner «Все да»): «model + year from Korea» groups «UA — Аукціон — <brand>» / «RU — Аукцион — <brand>»
   to the auction lots page korea.html, headlines about the lots first; ceiling 2 UAH.
4. 2026-11-28 (owner «да»): the same every night for the existing campaign «Пошук — США (UA ART)» (usa.py): up to
   usa.MAX_NEW_GROUPS missing groups with one ad each, then its keywords; keywords.split shares PER_DAY between Korea and
   USA (half each, all to one when the other has nothing left). Its budget, ceiling and negatives are not touched.
5. 2026-11-28 (Basic access): the night's limit is a parameter of the run (--limit, default keywords.PER_DAY; the
   request's keyword_limit, up to MAX_LIMIT). Above PER_DAY all missing USA groups are created in the same run. The API
   does not tell the developer token level, so a quota answer (HTTP 429 / RESOURCE_EXHAUSTED / quotaError) stops all
   sending at once, without a failure: status PASS_PARTIAL, access_level_hint EXPLORER_LIMIT_REACHED.
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
import usa

HERE = Path(__file__).resolve().parent
CEILING_MICROS = 4550000  # 4,55 UAH (owner 2026-11-27 «став тогда 4 гривни 55 копеек»; was 3,50)
# 2026-11-26: the campaign may be renamed «Пошук — Україна — Корея (UA ART)» (owner «Да, переименуй»).
NAMES = "'%s', 'Пошук — Україна — Корея (UA ART)'" % plan.NAME
CHUNK = 600
MAX_LIMIT = 12000  # keywords a run: with ~230 group/ad operations and ~40 reads the run stays under ~14 000 of 15 000
EXPLORER_OPS = 2880  # the Explorer level's daily operations on a production account
AUCTION_PAGE = plan.SITE + 'korea.html'  # the lots of the coming Korean auctions (filters by make, model, year)
# 2026-11-27: «Ставка онлайн …» removed (owner «Да»): 7 of 32 auction ads were refused as PROHIBITED (read as gambling).
AUCTION_HEAD = {'uk': ['Лоти аукціонів Кореї щодня', 'Ціни та фото кожного лоту', 'Фільтр: марка, модель, рік',
                       'Курс НБУ щодня'],
                'ru': ['Лоты аукционов Кореи ежедневно', 'Цены и фото каждого лота', 'Фильтр: марка, модель, год',
                       'Курс НБУ каждый день']}
HUB = {'uk': plan.SITE + 'seo/ua/avto-z-korei-do-kyieva-pid-kluch.html',
       'ru': plan.SITE + 'seo/ru/avto-iz-korei-v-kiev-pod-kluch.html'}
CAMPAIGN = ("SELECT campaign.resource_name, campaign.target_spend.cpc_bid_ceiling_micros, campaign_budget.amount_micros "
            "FROM campaign WHERE campaign.name IN (%s)")
GROUPS = "SELECT ad_group.resource_name, ad_group.name FROM ad_group WHERE campaign.name IN (%s)"
KEYWORDS = ("SELECT ad_group.name, ad_group_criterion.keyword.text FROM ad_group_criterion WHERE campaign.name IN (%s) "
            "AND ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.negative = FALSE")
ADS = ("SELECT ad_group.name, ad_group_ad.status FROM ad_group_ad WHERE campaign.name IN (%s) "
       "AND ad_group_ad.status != 'REMOVED'")
NEGATIVES = ("SELECT campaign_criterion.keyword.text FROM campaign_criterion WHERE campaign.name IN (%s) "
             "AND campaign_criterion.negative = TRUE AND campaign_criterion.type = 'KEYWORD'")


class QuotaStop(check.CheckError):
    """Google refused for the daily quota: nothing more is sent tonight."""


def quota(status, answer):
    """True for a quota answer: HTTP 429, RESOURCE_EXHAUSTED or any QuotaError (RESOURCE_EXHAUSTED,
    RESOURCE_TEMPORARILY_EXHAUSTED, ...)."""
    info = check.errors(answer)
    return status == 429 or info['status'] == 'RESOURCE_EXHAUSTED' or \
        any(e['code'].startswith('quotaError=') for e in info['errors'])


def read(customer, headers, query, opener=urllib.request.urlopen):
    rows, token = [], None
    while True:
        body = {'query': query, **({'pageToken': token} if token else {})}
        status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer, json.dumps(body).encode(),
                                    headers, opener)
        if status != 200:
            raise (QuotaStop if quota(status, answer) else check.CheckError)(
                'READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
        rows += answer.get('results', [])
        token = answer.get('nextPageToken')
        if not token:
            return rows


def state(customer, headers, opener=urllib.request.urlopen, names=NAMES):
    rows = read(customer, headers, CAMPAIGN % names, opener)
    if len(rows) != 1:
        raise check.CheckError('CAMPAIGNS_%d' % len(rows))
    return {'campaign': rows[0]['campaign'], 'budget': rows[0].get('campaignBudget', {}),
            'groups': {r['adGroup']['name']: r['adGroup']['resourceName']
                       for r in read(customer, headers, GROUPS % names, opener)},
            'keywords': {(r['adGroup']['name'], r['adGroupCriterion']['keyword']['text'])
                         for r in read(customer, headers, KEYWORDS % names, opener)},
            'negatives': {r['campaignCriterion']['keyword']['text']
                          for r in read(customer, headers, NEGATIVES % names, opener)},
            'with_ads': {r['adGroup']['name'] for r in read(customer, headers, ADS % names, opener)}}


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


def keyword_operations(current, limit=None, groups=None):
    """Korea by default; for USA groups=usa.waiting(current) limited to the groups that exist (nothing twice by text)."""
    have = current['keywords'] if groups is None else frozenset()
    if groups is not None:
        groups = {g: ks for g, ks in groups.items() if g in current['groups']}
    return [{'adGroupCriterionOperation': {'create': {'adGroup': current['groups'][g], 'status': 'ENABLED',
                                                      'keyword': {'text': k, 'matchType': 'PHRASE'}}}}
            for g, k in keywords.today(have, keywords.PER_DAY if limit is None else limit, groups)
            if g in current['groups']]


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def _path(item):
    return [e for e in _list(_dict(item.get('location')).get('fieldPathElements')) if isinstance(e, dict)]


def findings(failure):
    found = []
    for detail in _list(_dict(failure).get('details')):
        for item in _list(_dict(detail).get('errors')):
            entry = {'code': json.dumps(item.get('errorCode', {})), 'message': str(item.get('message', ''))[:120]}
            path = _path(item)
            if path:
                entry['field'] = '.'.join('%s%s' % (e.get('fieldName'), '[%s]' % e['index'] if 'index' in e else '')
                                         for e in path)
            found.append(entry)
    return found


def _camel(name):
    return re.sub(r'_([a-z])', lambda m: m.group(1).upper(), str(name))


def _text_at(op, path):
    """The text the field path points to inside the sent operation (e.g. a headline), or None."""
    node = op
    for e in path:
        if not isinstance(node, dict):
            return None
        node = node.get(_camel(e.get('fieldName')), node.get(e.get('fieldName')))
        if 'index' in e:
            node = node[e['index']] if isinstance(node, list) and isinstance(e['index'], int) \
                and 0 <= e['index'] < len(node) else None
    return node if isinstance(node, str) else None


def policy_refusals(failure, ops, names=None):
    """2026-11-28: per refused operation with policy findings (GoogleAdsFailure.errors[].details.policyFindingDetails.
    policyTopicEntries): the group, the refused field and its text, each topic with its type and evidence texts."""
    names = dict(names or {})
    names.update({_dict(o.get('adGroupOperation')).get('create', {}).get('resourceName'):
                  _dict(o.get('adGroupOperation')).get('create', {}).get('name')
                  for o in ops if 'create' in _dict(o.get('adGroupOperation'))})
    found = []
    for detail in _list(_dict(failure).get('details')):
        for item in _list(_dict(detail).get('errors')):
            topics = _list(_dict(_dict(item.get('details')).get('policyFindingDetails')).get('policyTopicEntries'))
            if not topics:
                continue
            path = _path(item)
            index = path[0].get('index') if path else None
            op = ops[index] if isinstance(index, int) and 0 <= index < len(ops) else {}
            target = next((_dict(v).get('create', {}) for v in op.values() if 'create' in _dict(v)), {})
            group = target.get('name') or names.get(target.get('adGroup'), target.get('adGroup'))
            entry = {'operation': index, 'group': group,
                     'field': '.'.join('%s%s' % (e.get('fieldName'), '[%s]' % e['index'] if 'index' in e else '')
                                       for e in path[1:]) or None,
                     'text': _text_at(op, path[1:]), 'topics': []}
            for t in topics:
                t = _dict(t)
                evidence = []
                for ev in _list(t.get('evidences')):
                    ev = _dict(ev)
                    evidence += _list(_dict(ev.get('textList')).get('texts'))
                    evidence += _list(_dict(ev.get('destinationTextList')).get('destinationTexts'))
                    evidence += _list(_dict(ev.get('websiteList')).get('websites'))
                entry['topics'].append({'topic': t.get('topic'), 'type': t.get('type'),
                                        'evidence': [str(x)[:120] for x in evidence][:10]})
            found.append(entry)
    return found


KEYWORD_ROWS = ("SELECT ad_group.name, ad_group_criterion.resource_name, ad_group_criterion.keyword.text, "
                "ad_group_criterion.keyword.match_type FROM ad_group_criterion WHERE campaign.name IN (%s) "
                "AND ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.negative = FALSE "
                "AND ad_group_criterion.status != 'REMOVED'")
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


def mutate(customer, headers, ops, opener, names=None):
    status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                json.dumps({'mutateOperations': ops, 'partialFailure': True}).encode(), headers, opener)
    if status != 200:
        return {'http': status, **check.errors(answer), **({'quota': True} if quota(status, answer) else {})}
    refused = findings(answer.get('partialFailureError'))
    result = {'sent': len(ops), 'refused': len(refused), 'codes': sorted({r['code'] for r in refused})[:8],
              'examples': refused[:8]}
    policy = policy_refusals(answer.get('partialFailureError'), ops, names)
    if policy:
        result['policy_refusals'] = policy
    return result


def summary(current):
    groups = sorted(current['groups'])
    kws = current['keywords']
    return {'ceiling': current['campaign'].get('targetSpend'), 'budget': current['budget'].get('amountMicros'),
            'groups': len(groups), 'keywords': len(kws),
            'keywords_uk': sum(1 for g, _ in kws if g.startswith('UA')), 'keywords_ru': sum(1 for g, _ in kws if g.startswith('RU')),
            'negatives': len(current['negatives']), 'groups_without_ad': sorted(set(groups) - current.get('with_ads', set(groups)))}


def run(keys, opener=urllib.request.urlopen, limit=None):
    limit = keywords.PER_DAY if limit is None else limit
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = state(customer, headers, opener)
    value = {'limit': limit, 'before': summary(before), 'steps': [], 'duplicates_removed': 0,
             'usa': {'steps': []}}
    sent = {'korea': [0, 0], 'usa': [0, 0]}  # [operations sent, refused by Google] of the keywords
    try:
        first = first_operations(customer, before)
        if first:
            stop(value['steps'], 'first', mutate(customer, headers, first, opener,
                                                  {r: n for n, r in before['groups'].items()}))
        remove = redundant(read(customer, headers, KEYWORD_ROWS % NAMES, opener))
        for start in range(0, len(remove), CHUNK):
            result = stop(value['steps'], 'duplicates_%d' % start, mutate(
                customer, headers, [{'adGroupCriterionOperation': {'remove': r}} for r in remove[start:start + CHUNK]],
                opener))
            if 'http' in result:
                break
            value['duplicates_removed'] += result['sent'] - result['refused']
        usa_before = state(customer, headers, opener, usa.NAMES)
        value['usa']['before'] = summary(usa_before)
        # Above the default night (Basic access) every missing USA group is created now, with its ad.
        new_groups = usa.group_operations(customer, usa_before, None if limit <= keywords.PER_DAY else len(usa.plan()))
        if new_groups:
            stop(value['usa']['steps'], 'groups', mutate(customer, headers, new_groups, opener,
                                                          {r: n for n, r in usa_before['groups'].items()}))
        middle, usa_middle = state(customer, headers, opener), state(customer, headers, opener, usa.NAMES)
        korea_part, usa_part = keywords.split(len(keyword_operations(middle, 10 ** 6)),
                                              len(keyword_operations(usa_middle, 10 ** 6, usa.waiting(usa_middle))),
                                              limit)
        value['split'] = {'korea': korea_part, 'usa': usa_part}
        send(customer, headers, keyword_operations(middle, korea_part), value['steps'], opener, sent['korea'])
        send(customer, headers, keyword_operations(usa_middle, usa_part, usa.waiting(usa_middle)),
             value['usa']['steps'], opener, sent['usa'])
    except QuotaStop as error:
        value['quota_stop'] = str(error)[:300]
    operations = sum(r.get('sent', 0) for step in value['steps'] + value['usa']['steps'] for r in step.values())
    value['operations_accepted'] = operations
    value['access_level_hint'] = ('EXPLORER_LIMIT_REACHED' if operations <= EXPLORER_OPS else 'BASIC_LIMIT_REACHED') \
        if 'quota_stop' in value else ('BASIC_OR_HIGHER' if operations > EXPLORER_OPS else 'NOT_TESTED_BELOW_2880')
    value['policy_refusals'] = [r for step in value['steps'] + value['usa']['steps'] for result in step.values()
                                for r in result.pop('policy_refusals', [])]
    try:
        after, usa_after = state(customer, headers, opener), state(customer, headers, opener, usa.NAMES)
    except QuotaStop as error:  # the reads of this quota day are used up too: what was sent is what is known
        value['after_unreadable'] = str(error)[:300]
        value['countries'] = {c: {'added_tonight': n - r, 'refused_by_google': r} for c, (n, r) in sent.items()}
        value['status'] = 'PARTIAL'
        return value
    value['after'], value['usa']['after'] = summary(after), summary(usa_after)
    usa_start = value['usa'].get('before', value['usa']['after'])
    value['added_now'] = value['after']['keywords'] - value['before']['keywords'] + value['duplicates_removed']
    value['plan_total'] = sum(map(len, keywords.plan().values()))
    value['left_for_next_run'] = len(keyword_operations(after, limit=10 ** 6))
    usa_added = value['usa']['after']['keywords'] - usa_start['keywords']
    value['countries'] = {
        'korea': {'added_tonight': value['added_now'], 'refused_by_google': sent['korea'][1],
                  'total_in_campaign': value['after']['keywords'], 'left_in_plan': value['left_for_next_run']},
        'usa': {'added_tonight': usa_added, 'refused_by_google': sent['usa'][1],
                'total_in_campaign': value['usa']['after']['keywords'],
                'left_in_plan': sum(map(len, usa.waiting(usa_after).values())),
                'groups_left_to_create': sum(1 for g in usa.plan() if g not in usa_after['groups'])}}
    usa_same = all(usa_start[k] == value['usa']['after'][k] for k in ('ceiling', 'budget', 'negatives'))
    safe = value['after']['ceiling'] == {'cpcBidCeilingMicros': str(CEILING_MICROS)} and usa_same
    if 'quota_stop' in value:
        value['status'] = 'PASS_PARTIAL' if safe else 'PARTIAL'
        return value
    done = not value['left_for_next_run'] and not value['countries']['usa']['left_in_plan']
    value['status'] = 'PASS' if safe and (value['added_now'] + usa_added > 0 or done) else 'PARTIAL'
    return value


def stop(steps, name, result):
    """Record one mutate result; a quota answer ends the run's sending (QuotaStop)."""
    steps.append({name: result})
    if result.get('quota'):
        raise QuotaStop('MUTATE_%s:%s' % (result['http'], json.dumps(
            {k: result[k] for k in ('status', 'message', 'errors') if k in result}, ensure_ascii=False)[:250]))
    return result


def send(customer, headers, ops, steps, opener, counts):
    """Keyword operations in chunks of CHUNK (partialFailure); counts gets [sent, refused] added."""
    for start in range(0, len(ops), CHUNK):
        result = stop(steps, 'keywords_%d' % start, mutate(customer, headers, ops[start:start + CHUNK], opener))
        if 'http' in result:
            break
        counts[0] += result['sent']
        counts[1] += result['refused']


def report(path=check.KEYS_PATH, opener=urllib.request.urlopen, limit=None):
    keys = json.loads(Path(path).read_text(encoding='utf-8'))
    if not all(keys.get(n) for n in check.KEY_NAMES + ('login_customer_id', 'customer_id')):
        return json.dumps({'status': 'KEYS_INCOMPLETE'})
    try:
        value = run(keys, opener, limit)
    except QuotaStop as error:  # the quota answered the first read: nothing was sent, nothing changed
        value = {'status': 'PASS_PARTIAL', 'limit': limit or keywords.PER_DAY, 'quota_stop': str(error)[:300],
                 'operations_accepted': 0, 'access_level_hint': 'EXPLORER_LIMIT_REACHED'}
    except check.CheckError as error:
        value = {'status': 'FAIL', 'error': str(error)}
    return check.clean(value, keys)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    if args.limit is not None and not 1 <= args.limit <= MAX_LIMIT:
        raise SystemExit('LIMIT')
    resource.setrlimit(resource.RLIMIT_CPU, (240, 250))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = json.loads(report(limit=args.limit))
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
