"""Four sitelinks under the campaign ads (owner 2026-11-26 «Все да 4 пункта» in this chat).

One googleAds:mutate: a sitelink asset and its campaign link for each of the four below whose link text is not on the
campaign yet; nothing is removed. State (the campaign's sitelink texts) before and after in the report. Budget, ceiling,
keywords and ads stay. No site, CRM or bot change.
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
SITE = 'https://www.uaart.com.ua/video/'
SITELINKS = [('Лоти аукціону', 'Сотні авто на торгах Кореї', 'Фото, пробіг, VIN і ціна', SITE + 'korea.html'),
             ('Авто в наявності', 'Огляд в офісі в Києві', 'Фото, відео, VIN', SITE + 'katalog.html'),
             ('Під ключ до Києва', 'Послуга 600 $, договір', 'Доставка і розмитнення',
              SITE + 'seo/ua/avto-z-korei-do-kyieva-pid-kluch.html'),
             ('Підбір авто', 'Підберемо під ваш бюджет', 'Відповідь у Viber чи Telegram', SITE + 'podbor.html')]
NAMES = "'Пошук — Україна — Корея (UA ART)', 'Пошук — Київ — Корея (UA ART)'"
CAMPAIGN = "SELECT campaign.resource_name, campaign.name, campaign_budget.amount_micros FROM campaign WHERE campaign.name IN (%s)" % NAMES
LINKS = ("SELECT campaign.name, campaign_asset.resource_name, campaign_asset.status, campaign_asset.field_type, "
         "asset.sitelink_asset.link_text FROM campaign_asset "
         "WHERE campaign.name IN (%s) AND campaign_asset.field_type = 'SITELINK' AND campaign_asset.status != 'REMOVED'" % NAMES)


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
    texts = sorted(r.get('asset', {}).get('sitelinkAsset', {}).get('linkText', '') for r in read(customer, headers, LINKS, opener))
    return {'resource': rows[0]['campaign']['resourceName'], 'budget': rows[0].get('campaignBudget', {}).get('amountMicros'),
            'sitelinks': texts}


def operations(customer, current):
    ops = []
    for n, (text, d1, d2, url) in enumerate(s for s in SITELINKS if s[0] not in current['sitelinks']):
        temp = 'customers/%s/assets/-%d' % (customer, 900 + n)
        ops.append({'assetOperation': {'create': {'resourceName': temp, 'finalUrls': [url], 'sitelinkAsset': {
            'linkText': text, 'description1': d1, 'description2': d2}}}})
        ops.append({'campaignAssetOperation': {'create': {'campaign': current['resource'], 'asset': temp,
                                                          'fieldType': 'SITELINK'}}})
    return ops


def public(current):
    return {'budget': current['budget'], 'sitelinks': current['sitelinks']}


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = state(customer, headers, opener)
    ops = operations(customer, before)
    value = {'before': public(before), 'operations': len(ops)}
    if ops:
        status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                    json.dumps({'mutateOperations': ops}).encode(), headers, opener)
        if status != 200:
            value.update(status='FAIL', mutate={'http': status, **check.errors(answer)})
            return value
    after = state(customer, headers, opener)
    value['after'] = public(after)
    value['status'] = 'PASS' if not operations(customer, after) and after['budget'] == before['budget'] else 'NOT_APPLIED'
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
