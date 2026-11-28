"""Korea Search campaign: two headlines of every responsive search ad replaced in place (owner «Да» 2026-11-28 13:44Z,
event cff080ab-fc51-4e90-8f7c-9e888bc7211c).

uk: «Передоплата в ціні авто» → «Авто з Кореї під ключ Київ», «Етап доставки онлайн» → «Купити авто з Кореї»;
ru: «Предоплата в цене авто» → «Авто из Кореи под ключ Киев», «Этап доставки онлайн» → «Купить авто из Кореи».
A new headline already in the ad only drops the old one (no duplicates); each headline keeps its pin; 3–15 headlines
of ≤ 30 characters, otherwise the ad is skipped. Reads the ENABLED/PAUSED responsive search ads of the campaign, then one
googleAds:mutate (partialFailure) with one AdOperation update per ad that has an old headline (AdService: an ad's
responsive_search_ad fields are updated in place by resource name customers/{customer}/ads/{ad}; the update mask
responsive_search_ad.headlines replaces the whole headline list — official google-ads-python sample
update_responsive_search_ad.py). Per ad before, after, refusals with policy topics. Budget, bids, status and all other
fields are not sent; the campaign settings are compared before/after. No site, CRM or bot change.
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
# 2026-11-26 the campaign may carry its new name «Пошук — Україна — Корея (UA ART)» (owner «Да, переименуй»).
NAMES = "'Пошук — Україна — Корея (UA ART)', 'Пошук — Київ — Корея (UA ART)'"
REPLACE = {'Передоплата в ціні авто': 'Авто з Кореї під ключ Київ', 'Етап доставки онлайн': 'Купити авто з Кореї',
           'Предоплата в цене авто': 'Авто из Кореи под ключ Киев', 'Этап доставки онлайн': 'Купить авто из Кореи'}
MAX_LEN, MIN_HEAD, MAX_HEAD = 30, 3, 15
MAX_ADS = 400  # the campaign has ~70 ads; more would mean a wrong campaign filter — nothing is sent
MASK = 'responsive_search_ad.headlines'
CAMPAIGN = ("SELECT campaign.resource_name, campaign.name, campaign.status, campaign.bidding_strategy_type, "
            "campaign.target_spend.cpc_bid_ceiling_micros, campaign_budget.amount_micros FROM campaign "
            "WHERE campaign.name IN (%s)" % NAMES)
ADS = ("SELECT ad_group.name, ad_group_ad.status, ad_group_ad.ad.resource_name, "
       "ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.policy_summary.approval_status FROM ad_group_ad "
       "WHERE campaign.name IN (%s) AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD' "
       "AND ad_group_ad.status IN ('ENABLED', 'PAUSED')" % NAMES)


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
    campaigns = read(customer, headers, CAMPAIGN, opener)
    if len(campaigns) != 1:
        raise check.CheckError('CAMPAIGNS_%d' % len(campaigns))
    ads = {}
    for r in read(customer, headers, ADS, opener):
        ad = r['adGroupAd']['ad']
        ads[ad['resourceName']] = {'group': r['adGroup']['name'], 'status': r['adGroupAd'].get('status'),
                                   'approval': r['adGroupAd'].get('policySummary', {}).get('approvalStatus'),
                                   'headlines': ad.get('responsiveSearchAd', {}).get('headlines', [])}
    return {'campaign': {**campaigns[0]['campaign'], 'budget': campaigns[0].get('campaignBudget', {}).get('amountMicros')},
            'ads': ads}


def new_headlines(headlines):
    """The ad's headline list with the old texts replaced (pin kept) or dropped; None when nothing changes."""
    present = {h.get('text', '').casefold() for h in headlines}
    out, changed = [], False
    for h in headlines:
        text = h.get('text', '')
        if text in REPLACE:
            changed = True
            text = REPLACE[text]
            if text.casefold() in present:
                continue
            present.add(text.casefold())
        out.append({'text': text, **({'pinnedField': h['pinnedField']} if h.get('pinnedField') else {})})
    return out if changed else None


def problem(headlines):
    if not MIN_HEAD <= len(headlines) <= MAX_HEAD:
        return 'COUNT_%d' % len(headlines)
    if any(len(h['text']) > MAX_LEN for h in headlines):
        return 'TOO_LONG'
    if len({h['text'].casefold() for h in headlines}) != len(headlines):
        return 'DUPLICATE'
    return None


def plan(current):
    """(operations, per-ad records) — one AdOperation update per ad with an old headline."""
    ops, records = [], {}
    for name in sorted(current['ads']):
        ad = current['ads'][name]
        texts = [h.get('text') for h in ad['headlines']]
        wanted = new_headlines(ad['headlines'])
        if wanted is None:
            continue
        record = {'group': ad['group'], 'status': ad['status'], 'approval_before': ad['approval'], 'before': texts,
                  'planned': [h['text'] for h in wanted]}
        why = problem(wanted)
        if why:
            record['result'] = 'SKIPPED_' + why
        else:
            record['operation'] = len(ops)
            ops.append({'adOperation': {'update': {'resourceName': name, 'responsiveSearchAd': {'headlines': wanted}},
                                        'updateMask': MASK}})
        records[name] = record
    return ops, records


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def _path(item):
    return [e for e in _list(_dict(item.get('location')).get('fieldPathElements')) if isinstance(e, dict)]


def _field(path):
    return '.'.join('%s%s' % (e.get('fieldName'), '[%s]' % e['index'] if 'index' in e else '') for e in path) or None


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


def refusals(failure, ops):
    """Per refused operation (as cloud/ads_bulk_001/source_remote.py policy_refusals): its index, the error code and
    message, the refused field and its text, and each policy topic with its type and evidence texts."""
    found = []
    for detail in _list(_dict(failure).get('details')):
        for item in _list(_dict(detail).get('errors')):
            path = _path(item)
            index = path[0].get('index') if path else None
            op = ops[index] if isinstance(index, int) and 0 <= index < len(ops) else {}
            entry = {'operation': index, 'code': json.dumps(item.get('errorCode', {})),
                     'message': str(item.get('message', ''))[:120], 'field': _field(path[1:]),
                     'text': _text_at(op, path[1:]), 'topics': []}
            topics = _list(_dict(_dict(item.get('details')).get('policyFindingDetails')).get('policyTopicEntries'))
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


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = state(customer, headers, opener)
    if len(before['ads']) > MAX_ADS:
        return {'status': 'FAIL', 'error': 'TOO_MANY_ADS_%d' % len(before['ads'])}
    ops, records = plan(before)
    value = {'campaign_before': before['campaign'], 'ads_read': len(before['ads']), 'operations': len(ops)}
    by_index = {r['operation']: name for name, r in records.items() if 'operation' in r}
    if ops:
        status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                    json.dumps({'mutateOperations': ops, 'partialFailure': True}).encode(), headers,
                                    opener)
        if status != 200:
            value.update(status='FAIL', mutate={'http': status, **check.errors(answer)}, ads=records)
            return value
        for refusal in refusals(answer.get('partialFailureError'), ops):
            name = by_index.get(refusal.pop('operation'))
            if name:
                records[name].setdefault('refusals', []).append(refusal)
    after = state(customer, headers, opener)
    for name, record in records.items():
        ad = after['ads'].get(name, {})
        record['after'] = [h.get('text') for h in ad.get('headlines', [])]
        record['approval_after'] = ad.get('approval')
        record.pop('operation', None)
        if 'result' not in record:
            record['result'] = 'REFUSED' if record.get('refusals') else \
                'UPDATED' if record['after'] == record['planned'] else 'NOT_APPLIED'
    left = sorted(n for n, a in after['ads'].items() if new_headlines(a['headlines']) is not None)
    results = [r['result'] for r in records.values()]
    value.update(campaign_after=after['campaign'], ads=records, old_headlines_left=len(left),
                 counts={k: results.count(k) for k in sorted(set(results))},
                 settings_unchanged=before['campaign'] == after['campaign'])
    skipped = {n for n, r in records.items() if r['result'].startswith('SKIPPED_')}  # kept as is: 3–15 rule
    value['status'] = 'PASS' if set(left) <= skipped and value['settings_unchanged'] else 'PARTIAL'
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
