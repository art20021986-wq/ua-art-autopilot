"""Search campaign «Пошук — США (UA ART)» (owner 2026-11-27 «Запусти, пожалуйста, рекламу, чтобы она работала. США,
бюджет, да, 50 гривен в день»; 27.11 «можно начать с 2 гривен»; «да» on the texts in this chat before the write).

One all-or-nothing googleAds:mutate: budget 50 UAH/day, the campaign (Search only, Maximize clicks with a 2 UAH ceiling,
ENABLED), the same places, languages and schedule as the Korea campaign (read from it), the Korea campaign's negative
phrases, four groups (uk/ru «з США під ключ», «аукціони США») with one responsive ad each to usa.html and phrase
keywords, six sitelinks (three of the Korea campaign's, three new). Never twice: a campaign with this name stops the run. The Korea campaign is not changed. No site, CRM or bot
change.
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
NAME = 'Пошук — США (UA ART)'
KOREA = "'Пошук — Україна — Корея (UA ART)'"
BUDGET_MICROS = 50000000
CEILING_MICROS = 2000000
PAGE = 'https://www.uaart.com.ua/video/usa.html'
UK_HEAD = ['Авто з США під ключ', 'Аукціони США: Copart', 'Послуга — 600 $', 'Звіт Carfax — 0 $',
           'Доступ до Copart безкоштовно', 'Офіс у Києві, Перемоги 20', 'Офіційний договір', 'Особистий кабінет 24/7',
           'Страхування авто в дорозі']
UK_DESC = ['Обираєте авто на аукціонах США — викуповуємо, страхуємо й веземо до Києва.',
           'Послуга 600 $ за договором. Звіт Carfax — 0 $, доступ до аукціонів безкоштовно.',
           'Залиште заявку — менеджер напише у Viber або Telegram.']
RU_HEAD = ['Авто из США под ключ', 'Аукционы США: Copart', 'Услуга — 600 $', 'Отчёт Carfax — 0 $',
           'Доступ к Copart бесплатно', 'Офис в Киеве, Победы 20', 'Официальный договор', 'Личный кабинет 24/7',
           'Страховка авто в пути']
RU_DESC = ['Выбираете авто на аукционах США — выкупаем, страхуем и везём в Киев.',
           'Услуга 600 $ по договору. Отчёт Carfax — 0 $, доступ к аукционам бесплатно.',
           'Оставьте заявку — менеджер напишет в Viber или Telegram.']
GROUPS = [
    ('UA — США під ключ', UK_HEAD, UK_DESC, ['авто з сша під ключ', 'пригон авто з сша', 'купити авто з сша',
                                             'авто з сша до києва', 'авто з америки під ключ', 'пригон авто з америки',
                                             'авто з сша ціни під ключ', 'електромобіль з сша', 'гібрид з сша',
                                             'авто з сша під замовлення']),
    ('RU — США под ключ', RU_HEAD, RU_DESC, ['авто из сша под ключ', 'пригон авто из сша', 'купить авто из сша',
                                             'авто с сша под ключ', 'авто из сша в киев', 'авто из америки под ключ',
                                             'пригон авто из америки', 'авто из сша цены под ключ', 'электромобиль из сша',
                                             'гибрид из сша', 'авто из сша под заказ']),
    ('UA — Аукціони США', ['Аукціони США: Copart'] + [h for h in UK_HEAD if h != 'Аукціони США: Copart'], UK_DESC,
     ['авто з аукціону copart', 'авто з copart під ключ', 'авто з iaai під ключ', 'аукціон copart україна',
      'купити авто на copart', 'авто з аукціонів сша']),
    ('RU — Аукционы США', ['Аукционы США: Copart'] + [h for h in RU_HEAD if h != 'Аукционы США: Copart'], RU_DESC,
     ['авто с аукциона copart', 'авто с copart под ключ', 'авто с iaai под ключ', 'аукцион copart украина',
      'купить авто на copart', 'авто с аукционов сша']),
]
# Six sitelinks (Google's recommendation applied by the owner, coordinator 04:45Z): three of the Korea campaign's own assets
# (reused as they are) and three new ones. Link text -> page.
SITE = 'https://www.uaart.com.ua/video/'
SITELINKS_REUSED = ('Авто в наявності', 'Підбір авто', 'Аукціони Кореї')
SITELINKS_NEW = [('Аукціони США', PAGE), ('Авто з Японії', SITE + 'japan.html'),
                 ('Кредит і лізинг', SITE + 'seo/ua/kredyt-lizynh-avto.html')]
KOREA_SITELINKS = ("SELECT campaign.name, campaign_asset.field_type, campaign_asset.status, asset.resource_name, "
                   "asset.sitelink_asset.link_text FROM campaign_asset WHERE campaign.name = %s "
                   "AND campaign_asset.field_type = 'SITELINK' AND campaign_asset.status = 'ENABLED'" % KOREA)
EXISTING = "SELECT campaign.resource_name, campaign.status FROM campaign WHERE campaign.name = '%s'" % NAME
KOREA_CRITERIA = ("SELECT campaign.name, campaign_criterion.type, campaign_criterion.negative, "
                  "campaign_criterion.location.geo_target_constant, campaign_criterion.language.language_constant, "
                  "campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, "
                  "campaign_criterion.ad_schedule.end_hour, campaign_criterion.keyword.text, "
                  "campaign_criterion.keyword.match_type FROM campaign_criterion WHERE campaign.name = %s" % KOREA)
STATE = ("SELECT campaign.name, campaign.status, campaign.target_spend.cpc_bid_ceiling_micros, "
         "campaign_budget.amount_micros FROM campaign WHERE campaign.name IN ('%s', %s)" % (NAME, KOREA))


def read(customer, headers, query, opener=urllib.request.urlopen):
    status, answer = check.call(check.API + 'customers/%s/googleAds:search' % customer,
                                json.dumps({'query': query}).encode(), headers, opener)
    if status != 200:
        raise check.CheckError('READ_%s:%s' % (status, json.dumps(check.errors(answer))[:200]))
    return answer.get('results', [])


def copied(criteria, campaign):
    """The Korea campaign's places, languages, schedule and negative phrases for the new campaign."""
    ops = []
    for row in criteria:
        c = row['campaignCriterion']
        kind = c.get('type')
        body = {'campaign': campaign}
        if kind == 'LOCATION' and not c.get('negative'):
            body['location'] = {'geoTargetConstant': c['location']['geoTargetConstant']}
        elif kind == 'LANGUAGE':
            body['language'] = {'languageConstant': c['language']['languageConstant']}
        elif kind == 'AD_SCHEDULE':
            a = c['adSchedule']
            body['adSchedule'] = {'dayOfWeek': a['dayOfWeek'], 'startHour': a['startHour'], 'endHour': a['endHour'],
                                  'startMinute': 'ZERO', 'endMinute': 'ZERO'}
        elif kind == 'KEYWORD' and c.get('negative'):
            body.update(negative=True, keyword={'text': c['keyword']['text'], 'matchType': c['keyword']['matchType']})
        else:
            continue
        ops.append({'campaignCriterionOperation': {'create': body}})
    return ops


def sitelinks(customer, korea_assets, campaign):
    by_text = {r['asset']['sitelinkAsset']['linkText']: r['asset']['resourceName'] for r in korea_assets}
    ops, assets = [], [by_text[t] for t in SITELINKS_REUSED if t in by_text]
    for n, (text, url) in enumerate(SITELINKS_NEW):
        temp = 'customers/%s/assets/-%d' % (customer, 300 + n)
        ops.append({'assetOperation': {'create': {'resourceName': temp, 'finalUrls': [url],
                                                  'sitelinkAsset': {'linkText': text}}}})
        assets.append(temp)
    ops += [{'campaignAssetOperation': {'create': {'campaign': campaign, 'asset': a, 'fieldType': 'SITELINK'}}}
            for a in assets]
    return ops


def operations(customer, criteria, korea_assets=()):
    base = 'customers/%s/' % customer
    budget, campaign = base + 'campaignBudgets/-1', base + 'campaigns/-2'
    ops = [{'campaignBudgetOperation': {'create': {'resourceName': budget, 'name': NAME + ' — бюджет',
                                                   'amountMicros': str(BUDGET_MICROS), 'deliveryMethod': 'STANDARD',
                                                   'explicitlyShared': False}}},
           {'campaignOperation': {'create': {
               'resourceName': campaign, 'name': NAME, 'status': 'ENABLED', 'advertisingChannelType': 'SEARCH',
               'campaignBudget': budget, 'targetSpend': {'cpcBidCeilingMicros': str(CEILING_MICROS)},
               'networkSettings': {'targetGoogleSearch': True, 'targetSearchNetwork': False,
                                   'targetContentNetwork': False},
               'geoTargetTypeSetting': {'positiveGeoTargetType': 'PRESENCE', 'negativeGeoTargetType': 'PRESENCE'},
               'containsEuPoliticalAdvertising': 'DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING'}}}]
    ops += copied(criteria, campaign)
    ops += sitelinks(customer, korea_assets, campaign)
    for n, (name, head, desc, words) in enumerate(GROUPS):
        group = base + 'adGroups/-%d' % (10 + n)
        lang = 'uk' if name.startswith('UA') else 'ru'
        ops.append({'adGroupOperation': {'create': {'resourceName': group, 'name': name, 'campaign': campaign,
                                                    'status': 'ENABLED', 'type': 'SEARCH_STANDARD'}}})
        ops += [{'adGroupCriterionOperation': {'create': {'adGroup': group, 'status': 'ENABLED',
                                                          'keyword': {'text': w, 'matchType': 'PHRASE'}}}} for w in words]
        ops.append({'adGroupAdOperation': {'create': {'adGroup': group, 'status': 'ENABLED', 'ad': {
            'finalUrls': [PAGE], 'responsiveSearchAd': {'headlines': [{'text': h} for h in head],
                                                        'descriptions': [{'text': d} for d in desc],
                                                        'path1': 'usa', 'path2': 'kyiv' if lang == 'uk' else 'kiev'}}}}})
    return ops


def run(keys, opener=urllib.request.urlopen):
    token, _ = check.access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    customer = keys['customer_id']
    before = read(customer, headers, STATE, opener)
    value = {'before': before}
    if read(customer, headers, EXISTING, opener):
        value['status'] = 'ALREADY_THERE'
        return value
    criteria = read(customer, headers, KOREA_CRITERIA, opener)
    ops = operations(customer, criteria, read(customer, headers, KOREA_SITELINKS, opener))
    value['operations'] = len(ops)
    value['copied'] = {k: sum(1 for o in ops if k in o.get('campaignCriterionOperation', {}).get('create', {}))
                       for k in ('location', 'language', 'adSchedule', 'keyword')}
    value['sitelinks'] = sum(1 for o in ops if 'campaignAssetOperation' in o)
    status, answer = check.call(check.API + 'customers/%s/googleAds:mutate' % customer,
                                json.dumps({'mutateOperations': ops}).encode(), headers, opener)
    if status != 200:
        value.update(status='FAIL', mutate={'http': status, **check.errors(answer)})
        return value
    after = read(customer, headers, STATE, opener)
    value['after'] = after
    usa = [r for r in after if r['campaign']['name'] == NAME]
    korea_same = [r for r in after if r['campaign']['name'] != NAME] == [r for r in before if r['campaign']['name'] != NAME]
    value['status'] = 'PASS' if len(usa) == 1 and usa[0]['campaign'].get('status') == 'ENABLED' and korea_same \
        else 'UNEXPECTED'
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
