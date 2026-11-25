"""Create the Kyiv Search campaign PAUSED (owner 2026-11-25; the content is plan.py).

One googleAds:mutate call builds the budget, the campaign (status PAUSED), its locations, languages, schedule and
negative keywords, the ad groups with keywords and one responsive search ad each, and the sitelink, callout and call
assets. APPLY False = Google checks everything without saving (validateOnly); True = saved. A campaign with the same
name is never created twice. A paused campaign shows no ads and spends nothing; turning it on is a separate step,
only with the owner's «да». No site, CRM or bot change; no key value in the report.
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
APPLY = False
DIAG = True  # R3: each Ukrainian text alone (all passed); R4: the full Ukrainian hub ad minus one text at a time


def variants():
    """(label, headlines, descriptions, path) of the Ukrainian hub ad: as is, without paths, and minus each text."""
    hub = plan.groups()[0]
    found = [('full', hub['headlines'], hub['descriptions'], hub['path']), ('no path', hub['headlines'], hub['descriptions'], None)]
    found += [('-' + h, [x for x in hub['headlines'] if x != h], hub['descriptions'], hub['path']) for h in hub['headlines']]
    found += [('-' + d, hub['headlines'], [x for x in hub['descriptions'] if x != d], hub['path']) for d in hub['descriptions']]
    return found


def candidates():
    return [v[0] for v in variants()]


def diag_operations(customer):
    """A paused test campaign: one ad group per variant of the Ukrainian hub ad (validate-only)."""
    ops = operations(customer)[:2]
    base = 'customers/%s/' % customer
    for n, (label, head, desc, path) in enumerate(variants()):
        ad_group = base + 'adGroups/-%d' % (100 + n)
        ops.append({'adGroupOperation': {'create': {'resourceName': ad_group, 'name': 'diag %d' % n,
                                                    'campaign': base + 'campaigns/-2', 'status': 'ENABLED',
                                                    'type': 'SEARCH_STANDARD'}}})
        rsa = {'headlines': [{'text': h} for h in head], 'descriptions': [{'text': d} for d in desc]}
        if path:
            rsa.update(path1=path[0], path2=path[1])
        ops.append({'adGroupAdOperation': {'create': {'adGroup': ad_group, 'status': 'ENABLED', 'ad': {
            'finalUrls': [plan.SITE + 'seo/ua/avto-z-korei-do-kyieva-pid-kluch.html'], 'responsiveSearchAd': rsa}}}})
    return ops


def operations(customer):
    """The mutate operations, in creation order, with temporary ids."""
    base = 'customers/%s/' % customer
    budget, campaign = base + 'campaignBudgets/-1', base + 'campaigns/-2'
    ops = [{'campaignBudgetOperation': {'create': {
        'resourceName': budget, 'name': plan.NAME + ' — бюджет', 'amountMicros': str(plan.BUDGET_UAH * 1000000),
        'deliveryMethod': 'STANDARD', 'explicitlyShared': False}}},
           {'campaignOperation': {'create': {
               'resourceName': campaign, 'name': plan.NAME, 'status': 'PAUSED', 'advertisingChannelType': 'SEARCH',
               'campaignBudget': budget, 'targetSpend': {'cpcBidCeilingMicros': str(plan.CPC_CEILING_UAH * 1000000)},
               'networkSettings': {'targetGoogleSearch': True, 'targetSearchNetwork': False,
                                   'targetContentNetwork': False, 'targetPartnerSearchNetwork': False},
               'geoTargetTypeSetting': {'positiveGeoTargetType': 'PRESENCE', 'negativeGeoTargetType': 'PRESENCE'},
               'containsEuPoliticalAdvertising': 'DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING'}}}]
    criteria = ([{'location': {'geoTargetConstant': g}} for g in plan.LOCATIONS]
                + [{'language': {'languageConstant': lang}} for lang in plan.LANGUAGES]
                + [{'adSchedule': {'dayOfWeek': d, 'startHour': plan.HOURS[0], 'startMinute': 'ZERO',
                                   'endHour': plan.HOURS[1], 'endMinute': 'ZERO'}} for d in plan.DAYS]
                + [{'negative': True, 'keyword': {'text': w, 'matchType': 'PHRASE'}} for w in plan.NEGATIVE])
    ops += [{'campaignCriterionOperation': {'create': dict(c, campaign=campaign)}} for c in criteria]
    for n, group in enumerate(plan.groups()):
        ad_group = base + 'adGroups/-%d' % (100 + n)
        ops.append({'adGroupOperation': {'create': {'resourceName': ad_group, 'name': group['name'], 'campaign': campaign,
                                                    'status': 'ENABLED', 'type': 'SEARCH_STANDARD'}}})
        ops += [{'adGroupCriterionOperation': {'create': {'adGroup': ad_group, 'status': 'ENABLED',
                                                          'keyword': {'text': k, 'matchType': m}}}}
                for k in group['keywords'] for m in ('PHRASE', 'EXACT')]
        ops.append({'adGroupAdOperation': {'create': {'adGroup': ad_group, 'status': 'ENABLED', 'ad': {
            'finalUrls': [group['url']], 'responsiveSearchAd': {
                'headlines': [{'text': h} for h in group['headlines']],
                'descriptions': [{'text': d} for d in group['descriptions']],
                'path1': group['path'][0], 'path2': group['path'][1]}}}}})
    assets = ([('SITELINK', {'sitelinkAsset': {'linkText': t, 'description1': d1, 'description2': d2}, 'finalUrls': [u]})
               for t, d1, d2, u in plan.SITELINKS]
              + [('CALLOUT', {'calloutAsset': {'calloutText': t}}) for t in plan.CALLOUTS]
              + [('CALL', {'callAsset': {'countryCode': 'UA', 'phoneNumber': plan.PHONE}})])
    for n, (field, body) in enumerate(assets):
        asset = base + 'assets/-%d' % (1000 + n)
        ops.append({'assetOperation': {'create': dict(body, resourceName=asset)}})
        ops.append({'campaignAssetOperation': {'create': {'campaign': campaign, 'asset': asset, 'fieldType': field}}})
    return ops


def findings(answer):
    """Every refused operation: its index, the policy topics and Google's evidence text."""
    found = []
    for detail in answer.get('error', {}).get('details', []) or []:
        for item in detail.get('errors', []) or []:
            path = item.get('location', {}).get('fieldPathElements', [])
            entries = item.get('details', {}).get('policyFindingDetails', {}).get('policyTopicEntries', [])
            found.append({'index': path[0].get('index') if path else None,
                          'code': json.dumps(item.get('errorCode', {})), 'message': str(item.get('message', ''))[:120],
                          'topics': [(e.get('type'), e.get('topic'),
                                      [t for ev in e.get('evidences', []) for t in ev.get('textList', {}).get('texts', [])])
                                     for e in entries]})
    return found


def existing(customer, headers, opener=urllib.request.urlopen):
    query = "SELECT campaign.resource_name, campaign.status FROM campaign WHERE campaign.name = '%s'" % plan.NAME
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': query}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    return [r['campaign'] for r in answer.get('results', [])]


def run(keys, apply=APPLY, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = existing(customer, headers, opener)
    value = {'apply': apply, 'existing_before': before, 'groups': [g['name'] for g in plan.groups()]}
    if before:
        value['status'] = 'ALREADY_THERE'
        return value
    ops = diag_operations(customer) if DIAG else operations(customer)
    if DIAG:
        apply = False
        value['candidates'] = candidates()
    value['operation_count'] = len(ops)
    status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                json.dumps({'mutateOperations': ops, 'validateOnly': not apply}).encode(), headers, opener)
    if status != 200:
        value.update(status='FAIL', mutate={'http': status, 'message': str(answer.get('error', {}).get('message'))[:200]},
                     findings=findings(answer))
        return value
    value['created'] = len(answer.get('mutateOperationResponses', []))
    value['after'] = existing(customer, headers, opener)
    value['status'] = 'PASS' if (not apply and not value['after']) or (
        apply and [c.get('status') for c in value['after']] == ['PAUSED']) else 'UNEXPECTED'
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
