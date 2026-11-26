"""Read-only check of the Google Ads account on the server (ADS-API-001, owner 2026-11-25: «Хочу уже запустить эту рекламу»).

Uses the keys the owner sent to the CRM bot (/home/Carix/google_ads_api.json, never copied, never put in the report):
a fresh access token from the refresh token, then only reading calls of the official REST API:
- customers:listAccessibleCustomers;
- googleAds:search on the manager account (its client accounts) and on the advertiser account (account settings,
  campaigns, conversion actions, billing setup).
R2 (owner 2026-11-25 «сделай мне аналитику, какая стоимость будет за лид»): the Keyword Planner (generateKeywordIdeas,
generateKeywordHistoricalMetrics, Ukrainian and Russian) and Google's forecast for one Search campaign
(generateKeywordForecastMetrics). Owner 2026-11-25: «начнем снимать сливки … с Киевской области»: the Kyiv city and
Kyiv Oblast locations are looked up in Google's location list and used for the planner and the forecast; the whole
of Ukraine only for the seed words, to compare — planning calls that only return numbers; no plan or campaign is saved.
Nothing is created, changed or spent: no mutate call exists in this file. The report holds account names, statuses and
Google's error codes only; every key value is checked to be absent before the report is written.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import resource
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
KEYS_PATH = Path('/home/Carix/google_ads_api.json')
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
API = 'https://googleads.googleapis.com/v26/'
CAMPAIGN = 'Пошук — Київ — Корея (UA ART)'
QUERIES = {
    'manager': ('login', 'SELECT customer_client.id, customer_client.descriptive_name, customer_client.manager, '
                         'customer_client.status, customer_client.level FROM customer_client'),
    'account': ('client', 'SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone, '
                          'customer.status, customer.auto_tagging_enabled, customer.test_account, '
                          'customer.conversion_tracking_setting.conversion_tracking_status FROM customer'),
    'campaigns': ('client', 'SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, '
                            'campaign_budget.amount_micros FROM campaign'),
    'conversions': ('client', 'SELECT conversion_action.id, conversion_action.name, conversion_action.status, '
                              'conversion_action.type, conversion_action.category, conversion_action.primary_for_goal '
                              'FROM conversion_action'),
    'billing': ('client', 'SELECT billing_setup.id, billing_setup.status FROM billing_setup'),
    # R3 (after ADS-ENABLE, coordinator 2026-11-25): the campaign, its ads' review and the auto-applied recommendations.
    'campaign': ('client', "SELECT campaign.name, campaign.status, campaign.serving_status, campaign.primary_status, "
                           "campaign.primary_status_reasons, campaign_budget.amount_micros FROM campaign "
                           "WHERE campaign.name = '%s'" % CAMPAIGN),
    'ads': ('client', "SELECT ad_group.name, ad_group_ad.status, ad_group_ad.policy_summary.approval_status, "
                      "ad_group_ad.policy_summary.review_status, ad_group_ad.primary_status FROM ad_group_ad "
                      "WHERE campaign.name = '%s'" % CAMPAIGN),
    'auto_apply': ('client', 'SELECT recommendation_subscription.type, recommendation_subscription.status '
                             'FROM recommendation_subscription'),
}
# R4 (owner 2026-11-25 «сколько показов, сколько зашло»): today's numbers of the campaign, its groups and searches.
QUERIES.update({
    'today': ('client', "SELECT campaign.name, metrics.impressions, metrics.clicks, metrics.cost_micros, "
                        "metrics.average_cpc, metrics.conversions, metrics.search_impression_share FROM campaign "
                        "WHERE campaign.name = '%s' AND segments.date DURING TODAY" % CAMPAIGN),
    'today_groups': ('client', "SELECT ad_group.name, metrics.impressions, metrics.clicks, metrics.cost_micros, "
                               "metrics.conversions FROM ad_group WHERE campaign.name = '%s' AND segments.date DURING TODAY "
                               "AND metrics.impressions > 0" % CAMPAIGN),
    'today_terms': ('client', "SELECT search_term_view.search_term, metrics.impressions, metrics.clicks, "
                              "metrics.cost_micros FROM search_term_view WHERE campaign.name = '%s' "
                              "AND segments.date DURING TODAY" % CAMPAIGN),
})
# R5 (owner 2026-11-25 «18 гривен это очень много… сэкономить цену за переход»): what sets the click price.
QUERIES.update({
    'today_keywords': ('client', "SELECT ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, "
                                 "ad_group_criterion.quality_info.quality_score, "
                                 "ad_group_criterion.quality_info.creative_quality_score, "
                                 "ad_group_criterion.quality_info.post_click_quality_score, "
                                 "ad_group_criterion.quality_info.search_predicted_ctr, "
                                 "ad_group_criterion.position_estimates.first_page_cpc_micros, "
                                 "ad_group_criterion.position_estimates.top_of_page_cpc_micros, "
                                 "metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.average_cpc "
                                 "FROM keyword_view WHERE campaign.name = '%s' AND segments.date DURING TODAY "
                                 "AND metrics.impressions > 0" % CAMPAIGN),
    'today_devices': ('client', "SELECT segments.device, metrics.impressions, metrics.clicks, metrics.cost_micros "
                                "FROM campaign WHERE campaign.name = '%s' AND segments.date DURING TODAY" % CAMPAIGN),
    'today_hours': ('client', "SELECT segments.hour, metrics.impressions, metrics.clicks, metrics.cost_micros "
                              "FROM campaign WHERE campaign.name = '%s' AND segments.date DURING TODAY" % CAMPAIGN),
    'today_share': ('client', "SELECT metrics.search_impression_share, metrics.search_rank_lost_impression_share, "
                              "metrics.search_budget_lost_impression_share, metrics.search_top_impression_share, "
                              "metrics.search_absolute_top_impression_share, metrics.ctr, metrics.conversions, "
                              "metrics.interactions FROM campaign WHERE campaign.name = '%s' "
                              "AND segments.date DURING TODAY" % CAMPAIGN),
    'today_locations': ('client', "SELECT user_location_view.country_criterion_id, metrics.impressions, metrics.clicks "
                                  "FROM user_location_view WHERE campaign.name = '%s' AND segments.date DURING TODAY"
                                  % CAMPAIGN),
})
# R7 (owner via the coordinator 2026-11-26: full feedback on the ads, from the live account): totals since the launch,
# the campaign settings, keywords, negatives, locations, languages, schedule, ads.
QUERIES.update({
    'since_launch': ('client', "SELECT metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.average_cpc, "
                               "metrics.conversions FROM campaign WHERE campaign.name = '%s' "
                               "AND segments.date BETWEEN '2026-11-25' AND '2026-12-31'" % CAMPAIGN),
    'settings': ('client', "SELECT campaign.status, campaign.serving_status, campaign.primary_status, "
                           "campaign.target_spend.cpc_bid_ceiling_micros, campaign.network_settings.target_search_network, "
                           "campaign.network_settings.target_content_network, "
                           "campaign.geo_target_type_setting.positive_geo_target_type, campaign_budget.amount_micros "
                           "FROM campaign WHERE campaign.name = '%s'" % CAMPAIGN),
    'criteria': ('client', "SELECT campaign_criterion.type, campaign_criterion.negative, "
                           "campaign_criterion.location.geo_target_constant, campaign_criterion.language.language_constant, "
                           "campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, "
                           "campaign_criterion.ad_schedule.end_hour FROM campaign_criterion "
                           "WHERE campaign.name = '%s'" % CAMPAIGN),
    'keywords': ('client', "SELECT ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.status "
                           "FROM ad_group_criterion WHERE campaign.name = '%s' AND ad_group_criterion.type = 'KEYWORD' "
                           "AND ad_group_criterion.negative = FALSE" % CAMPAIGN),
})
PLANNING = False  # R2: the Keyword Planner needs Basic access (DEVELOPER_TOKEN_NOT_APPROVED); R3 skips it
UKRAINE = 'geoTargetConstants/2804'
LANGUAGES = {'uk': 'languageConstants/1036', 'ru': 'languageConstants/1031'}
SEEDS = {
    'uk': ['авто з кореї під ключ', 'авто з кореї', 'пригон авто з кореї', 'авто з кореї під замовлення', 'авто з кореї київ',
           'kia k5 з кореї', 'hyundai sonata з кореї', 'hyundai tucson з кореї', 'kia sportage з кореї',
           'hyundai santa fe з кореї', 'аукціон авто корея', 'авто з сша під ключ', 'пригон авто'],
    'ru': ['авто из кореи под ключ', 'авто из кореи', 'пригон авто из кореи', 'авто из кореи под заказ', 'авто из кореи киев',
           'киа к5 из кореи', 'хюндай соната из кореи', 'туссан из кореи', 'спортейдж из кореи', 'санта фе из кореи',
           'аукцион авто корея', 'авто из сша под ключ', 'пригон авто'],
}
FORECAST_KEYWORDS = SEEDS['uk'][:11] + SEEDS['ru'][:11]
FORECAST_BUDGETS = (300, 500, 1000)  # UAH a day, Maximize clicks; the account currency is checked first
KEY_NAMES = ('developer_token', 'client_id', 'client_secret', 'refresh_token')


class CheckError(Exception):
    pass


def call(url, body=None, headers=None, opener=urllib.request.urlopen):
    """(status, parsed JSON) for one HTTPS call; Google's error answer is returned, not raised."""
    data = None if body is None else body
    request = urllib.request.Request(url, data=data, headers=headers or {}, method='POST' if data is not None else 'GET')
    try:
        with opener(request, timeout=40) as response:
            return response.status, json.loads(response.read(4 * 1024 * 1024) or b'{}')
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read(65536) or b'{}')
        except ValueError:
            return error.code, {}


def access_token(keys, opener=urllib.request.urlopen):
    body = urllib.parse.urlencode({'client_id': keys['client_id'], 'client_secret': keys['client_secret'],
                                   'refresh_token': keys['refresh_token'], 'grant_type': 'refresh_token'}).encode()
    status, answer = call(TOKEN_ENDPOINT, body, {'Content-Type': 'application/x-www-form-urlencoded'}, opener)
    if status != 200 or not answer.get('access_token'):
        raise CheckError('TOKEN_%s:%s' % (status, str(answer.get('error', ''))[:40]))
    return answer['access_token'], answer.get('scope', '')


def errors(answer):
    """Google's error codes and messages, short (no request data)."""
    error = answer.get('error', {}) if isinstance(answer, dict) else {}
    found = []
    for detail in error.get('details', []) or []:
        for item in detail.get('errors', []) or []:
            code = item.get('errorCode', {})
            found.append({'code': '.'.join('%s=%s' % pair for pair in sorted(code.items())),
                          'message': str(item.get('message', ''))[:200]})
    return {'status': error.get('status'), 'message': str(error.get('message', ''))[:200], 'errors': found[:5]}


def check(keys, opener=urllib.request.urlopen):
    token, scope = access_token(keys, opener)
    headers = {'Authorization': 'Bearer ' + token, 'developer-token': keys['developer_token'],
               'login-customer-id': keys['login_customer_id'], 'Content-Type': 'application/json'}
    value = {'token': 'PASS', 'scope': scope}
    status, answer = call(API + 'customers:listAccessibleCustomers',
                          headers={k: v for k, v in headers.items() if k != 'login-customer-id'}, opener=opener)
    value['accessible'] = answer.get('resourceNames', []) if status == 200 else {'http': status, **errors(answer)}
    for name, (who, query) in QUERIES.items():
        customer = keys['login_customer_id'] if who == 'login' else keys['customer_id']
        status, answer = call(API + 'customers/%s/googleAds:search' % customer, json.dumps({'query': query}).encode(),
                              headers, opener)
        value[name] = answer.get('results', []) if status == 200 else {'http': status, **errors(answer)}
    if not PLANNING:
        return value
    geo, value['kyiv_locations'] = kyiv(keys['customer_id'], headers, opener)
    value['geo'] = geo = geo or [UKRAINE]
    value['planner'] = planner(keys['customer_id'], headers, geo, opener)
    today = datetime.date.today()
    value['forecast'] = forecast(keys['customer_id'], headers, geo, (today + datetime.timedelta(days=1)).isoformat(),
                                 (today + datetime.timedelta(days=30)).isoformat(), opener)
    return value


def metrics(item):
    m = item.get('keywordIdeaMetrics') or item.get('keywordMetrics') or {}
    micros = lambda name: round(int(m[name]) / 1e6, 2) if m.get(name) else None  # noqa: E731
    return {'text': item.get('text'), 'searches': int(m.get('avgMonthlySearches') or 0),
            'competition': m.get('competition'), 'low_bid': micros('lowTopOfPageBidMicros'),
            'high_bid': micros('highTopOfPageBidMicros'), 'avg_cpc': micros('averageCpcMicros')}


GEO_QUERY = ("SELECT geo_target_constant.resource_name, geo_target_constant.name, geo_target_constant.target_type, "
             "geo_target_constant.canonical_name, geo_target_constant.status FROM geo_target_constant "
             "WHERE geo_target_constant.country_code = 'UA' AND geo_target_constant.name LIKE '%Kyiv%'")


def kyiv(customer, headers, opener=urllib.request.urlopen):
    """(resource names, found rows): Kyiv region-level locations (city region and oblast), else the city."""
    status, answer = call(API + 'customers/%s/googleAds:search' % customer, json.dumps({'query': GEO_QUERY}).encode(),
                          headers, opener)
    rows = [r.get('geoTargetConstant', {}) for r in answer.get('results', [])] if status == 200 else []
    rows = [r for r in rows if r.get('status', 'ENABLED') == 'ENABLED']
    chosen = [r['resourceName'] for r in rows if r.get('targetType') == 'Region']
    chosen = chosen or [r['resourceName'] for r in rows if r.get('targetType') == 'City' and r.get('name') == 'Kyiv']
    found = rows if status == 200 else {'http': status, **errors(answer)}
    return chosen, found


def historical(customer, headers, lang, geo, opener=urllib.request.urlopen):
    body = {'language': LANGUAGES[lang], 'geoTargetConstants': geo, 'keywordPlanNetwork': 'GOOGLE_SEARCH',
            'historicalMetricsOptions': {'includeAverageCpc': True}, 'keywords': SEEDS[lang]}
    status, answer = call(API + 'customers/%s:generateKeywordHistoricalMetrics' % customer, json.dumps(body).encode(),
                          headers, opener)
    return [metrics(r) for r in answer.get('results', [])] if status == 200 else {'http': status, **errors(answer)}


def planner(customer, headers, geo, opener=urllib.request.urlopen):
    """Keyword Planner numbers for the given locations (seeds also for all Ukraine); nothing is saved."""
    value = {}
    for lang, constant in LANGUAGES.items():
        base = {'language': constant, 'geoTargetConstants': geo, 'keywordPlanNetwork': 'GOOGLE_SEARCH',
                'historicalMetricsOptions': {'includeAverageCpc': True}}
        exact = historical(customer, headers, lang, geo, opener)
        status, answer = call(API + 'customers/%s:generateKeywordIdeas' % customer,
                              json.dumps(dict(base, keywordSeed={'keywords': SEEDS[lang]}, pageSize=150,
                                              includeAdultKeywords=False)).encode(), headers, opener)
        ideas = sorted((metrics(r) for r in answer.get('results', [])), key=lambda x: -x['searches'])[:120] \
            if status == 200 else {'http': status, **errors(answer)}
        value[lang] = {'seeds': exact, 'ideas': ideas, 'seeds_ukraine': historical(customer, headers, lang, [UKRAINE], opener)}
    return value


def forecast(customer, headers, geo, start, end, opener=urllib.request.urlopen):
    """Google's 30-day forecast for one Search campaign at each daily budget (Maximize clicks); nothing saved."""
    value = {}
    for budget in FORECAST_BUDGETS:
        keywords = [{'keyword': {'text': text, 'matchType': 'PHRASE'}} for text in FORECAST_KEYWORDS]
        body = {'currencyCode': 'UAH', 'forecastPeriod': {'startDate': start, 'endDate': end},
                'campaign': {'languageConstants': list(LANGUAGES.values()), 'keywordPlanNetwork': 'GOOGLE_SEARCH',
                             'geoModifiers': [{'geoTargetConstant': g} for g in geo],
                             'biddingStrategy': {'maximizeClicksBiddingStrategy': {
                                 'dailyTargetSpendMicros': str(budget * 1000000)}},
                             'adGroups': [{'biddableKeywords': keywords}]}}
        status, answer = call(API + 'customers/%s:generateKeywordForecastMetrics' % customer,
                              json.dumps(body).encode(), headers, opener)
        m = answer.get('campaignForecastMetrics', {}) if status == 200 else None
        value[str(budget)] = ({k: m.get(k) for k in ('impressions', 'clicks', 'costMicros', 'averageCpcMicros',
                                                     'clickThroughRate', 'conversions', 'conversionRate',
                                                     'averageCpaMicros')}
                              if m is not None else {'http': status, **errors(answer)})
    return value


def clean(value, keys):
    """The report text; stops if any key value would be in it."""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for name in KEY_NAMES:
        secret = str(keys.get(name) or '')
        if len(secret) >= 8 and secret in text:
            raise CheckError('KEY_IN_REPORT:' + name)
    if 'GOCSPX-' in text or 'ya29.' in text:
        raise CheckError('KEY_IN_REPORT')
    return text


def report(path=KEYS_PATH, opener=urllib.request.urlopen):
    keys = json.loads(Path(path).read_text(encoding='utf-8'))
    present = {name: bool(keys.get(name)) for name in KEY_NAMES + ('login_customer_id', 'customer_id')}
    value = {'status': 'PASS', 'keys_present': present, 'keys_mode': oct(Path(path).stat().st_mode & 0o777)}
    if not all(present.values()):
        value['status'] = 'KEYS_INCOMPLETE'
        return clean(value, keys)
    try:
        value['google_ads'] = check(keys, opener)
    except CheckError as error:
        value.update(status='FAIL', error=str(error))
    return clean(value, keys)


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
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
