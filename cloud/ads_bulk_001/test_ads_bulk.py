#!/usr/bin/env python3
"""ADS-BULK: 1 UAH ceiling, buyer keywords uk+ru only, in parts, nothing twice, ads within Google limits; Korea + USA."""
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import keywords  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402
import usa  # noqa: E402

KEYS = {'developer_token': 'DEVTOKEN' + 'x' * 14, 'client_id': '1' * 12 + '-abc.apps.' + 'googleusercontent.com',
        'client_secret': 'GOC' + 'SPX-' + 'q' * 28, 'refresh_token': '1//' + 'r' * 40,
        'login_customer_id': '9054959760', 'customer_id': '4680747874'}


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Google:
    """Both campaigns: a query naming «США» reads the USA one, any other the Korea one."""
    def __init__(self):
        self.campaigns = {'korea': {'resourceName': 'customers/1/campaigns/9',
                                    'targetSpend': {'cpcBidCeilingMicros': '7000000'}},
                          'usa': {'resourceName': 'customers/1/campaigns/8',
                                  'targetSpend': {'cpcBidCeilingMicros': '2000000'}}}
        self.campaign = self.campaigns['korea']
        self.budgets = {'korea': '300000000', 'usa': '50000000'}
        self.groups = {'UA — Корея під ключ': 'customers/1/adGroups/1', 'RU — Корея под ключ': 'customers/1/adGroups/2',
                       'UA — США під ключ': 'customers/1/adGroups/3', 'RU — США под ключ': 'customers/1/adGroups/4',
                       'UA — Аукціони США': 'customers/1/adGroups/5', 'RU — Аукционы США': 'customers/1/adGroups/6'}
        self.country = {g: 'usa' if 'США' in g else 'korea' for g in self.groups}
        # «авто з сша» is in the USA plan's hub group but already sits in another group: never added again.
        self.keywords = {('UA — Корея під ключ', 'авто з кореї'), ('UA — США під ключ', 'авто з сша під ключ'),
                         ('UA — Аукціони США', 'авто з сша')}
        self.negatives, self.mutates = {'korea': {'olx'}, 'usa': {'olx', 'copart parts'}}, []
        self.ads = set(self.groups)

    def name(self, resource):
        return next(n for n, r in self.groups.items() if r == resource)

    def __call__(self, request, timeout=None):
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': 'ya' + '29.' + 'a' * 30}).encode())
        body = json.loads(request.data)
        if request.full_url.endswith('googleAds:mutate'):
            self.mutates.append(body)
            temp = {}
            for op in body['mutateOperations']:
                if 'campaignOperation' in op:
                    update = op['campaignOperation']['update']
                    self.of(update['resourceName'])['targetSpend'] = update['targetSpend']
                elif 'campaignCriterionOperation' in op:
                    create = op['campaignCriterionOperation']['create']
                    self.negatives[self.country_of(create['campaign'])].add(create['keyword']['text'])
                elif 'adGroupOperation' in op:
                    new = op['adGroupOperation']['create']
                    temp[new['resourceName']] = 'customers/1/adGroups/%d' % (10 + len(self.groups))
                    self.groups[new['name']] = temp[new['resourceName']]
                    self.country[new['name']] = self.country_of(new['campaign'])
                elif 'adGroupAdOperation' in op:
                    target = op['adGroupAdOperation']['create']['adGroup']
                    self.ads.add(self.name(temp.get(target, target)))
                elif 'remove' in op.get('adGroupCriterionOperation', {}):
                    _, g, t = op['adGroupCriterionOperation']['remove'].split('|')
                    self.keywords.discard((g, t))
                elif 'adGroupCriterionOperation' in op:
                    k = op['adGroupCriterionOperation']['create']
                    self.keywords.add((self.name(k['adGroup']), k['keyword']['text']))
            return Response(b'{}')
        query = body['query']
        country = 'usa' if 'США' in query else 'korea'
        if 'FROM campaign_criterion' in query:
            rows = [{'campaignCriterion': {'keyword': {'text': t}}} for t in self.negatives[country]]
        elif 'FROM ad_group_criterion' in query:
            rows = [{'adGroup': {'name': g}, 'adGroupCriterion': {'resourceName': 'kw|%s|%s' % (g, t),
                                                                  'keyword': {'text': t, 'matchType': 'PHRASE'}}}
                    for g, t in self.keywords if self.country[g] == country]
        elif 'FROM ad_group_ad' in query:
            rows = [{'adGroup': {'name': g}, 'adGroupAd': {'status': 'ENABLED'}} for g in self.ads
                    if self.country[g] == country]
        elif 'FROM ad_group ' in query:
            rows = [{'adGroup': {'name': n, 'resourceName': r}} for n, r in self.groups.items()
                    if self.country[n] == country]
        else:
            rows = [{'campaign': self.campaigns[country], 'campaignBudget': {'amountMicros': self.budgets[country]}}]
        return Response(json.dumps({'results': rows}).encode())

    def of(self, resource):
        return self.campaigns[self.country_of(resource)]

    def country_of(self, resource):
        return next(c for c, v in self.campaigns.items() if v['resourceName'] == resource)

    def texts(self, country):
        return [t for g, t in self.keywords if self.country[g] == country]


class PlanTests(unittest.TestCase):
    def test_keywords_valid_and_paired(self):
        groups = keywords.plan()
        words = [k for v in groups.values() for k in v]
        self.assertEqual(len(words), len(set(words)))
        self.assertGreater(len(words), 3000)
        self.assertTrue(all(len(k) <= 80 and len(k.split()) <= 10 and k == k.lower() for k in words))
        self.assertTrue(all(g.startswith(('UA — ', 'RU — ')) for g in groups))
        self.assertTrue(all(('коре' in k or 'під замовлення' in k) for g, v in groups.items()
                            if g.startswith('UA') for k in v))
        self.assertFalse([k for k in words if any(n in k.split() for n in keywords.NEGATIVE_MORE)])
        self.assertNotIn('lexus tiguan з кореї', words)

    def test_ad_texts_within_limits(self):
        for group in keywords.plan():
            lang, head, desc = remote.ad_texts(group)
            self.assertTrue(3 <= len(head) <= 15 and all(len(h) <= 30 for h in head), group)
            self.assertEqual(len(head), len(set(head)))
            self.assertFalse(any('Отримайте пропозицію' in h for h in head))


class DuplicateTests(unittest.TestCase):
    def test_redundant(self):
        def row(g, t, m):
            return {'adGroup': {'name': g}, 'adGroupCriterion': {'resourceName': '%s/%s/%s' % (g, t, m),
                                                                 'keyword': {'text': t, 'matchType': m}}}
        plan_group = next((g, k[0]) for g, k in keywords.plan().items() if g.startswith('UA — Аукціон'))
        rows = [row('UA — Корея під ключ', 'авто з кореї', 'PHRASE'), row('UA — Корея під ключ', 'авто з кореї', 'EXACT'),
                row('UA — Kia', 'kia з кореї', 'PHRASE'), row('UA — Будь-яка модель з Кореї', 'kia з кореї', 'PHRASE'),
                row('UA — Будь-яка модель з Кореї', plan_group[1], 'PHRASE'), row(plan_group[0], plan_group[1], 'PHRASE'),
                row('UA — Kia', 'kia k5 з кореї', 'EXACT')]
        gone = remote.redundant(rows)
        self.assertEqual(gone, sorted(['UA — Корея під ключ/авто з кореї/EXACT',
                                       'UA — Будь-яка модель з Кореї/kia з кореї/PHRASE',
                                       'UA — Будь-яка модель з Кореї/%s/PHRASE' % plan_group[1]]))


class AuctionTests(unittest.TestCase):
    def test_model_year_groups(self):
        groups = keywords.plan()
        auction = {g: v for g, v in groups.items() if g.startswith(tuple(keywords.AUCTION.values()))}
        self.assertEqual(len(auction), 2 * len(keywords.BRANDS))
        words = [k for v in auction.values() for k in v]
        self.assertGreater(len(words), 12000)
        self.assertIn('bmw 5 series 2017 з кореї', auction['UA — Аукціон — BMW'])
        self.assertIn('kia k5 2019 с кореи', auction['RU — Аукцион — Kia'])
        lang, head, _ = remote.ad_texts('UA — Аукціон — BMW')
        self.assertEqual(head[:2], ['BMW з Кореї', 'Лоти аукціонів Кореї щодня'])
        ops = remote.first_operations('1', {'campaign': {'resourceName': 'c/1', 'targetSpend': {
            'cpcBidCeilingMicros': '4550000'}}, 'negatives': set(keywords.NEGATIVE_MORE),
            'groups': {g: 'g' for g in groups if g not in auction}})
        urls = {o['adGroupAdOperation']['create']['ad']['finalUrls'][0] for o in ops if 'adGroupAdOperation' in o}
        self.assertEqual(urls, {remote.AUCTION_PAGE})
        self.assertEqual(len(ops), 2 * len(auction))


class MissingAdTests(unittest.TestCase):
    def test_ad_only_for_groups_without_one(self):
        groups = {g: 'customers/1/adGroups/%d' % n for n, g in enumerate(keywords.plan())}
        current = {'campaign': {'resourceName': 'c/1', 'targetSpend': {'cpcBidCeilingMicros': str(remote.CEILING_MICROS)}},
                   'negatives': set(keywords.NEGATIVE_MORE), 'groups': groups,
                   'with_ads': set(groups) - {'UA — Аукціон — BMW', 'RU — Аукцион — Kia'}}
        ops = remote.first_operations('1', current)
        self.assertEqual(len(ops), 2)
        self.assertEqual({o['adGroupAdOperation']['create']['adGroup'] for o in ops},
                         {groups['UA — Аукціон — BMW'], groups['RU — Аукцион — Kia']})
        heads = [h['text'] for o in ops for h in o['adGroupAdOperation']['create']['ad']['responsiveSearchAd']['headlines']]
        self.assertFalse([h for h in heads if 'Ставка' in h])


class PolicyRefusalTests(unittest.TestCase):
    """A partial failure as the REST API answers it: google.rpc.Status with GoogleAdsFailure in details."""
    def failure(self, index, headline):
        return {'code': 3, 'message': 'The resource has been disapproved ...', 'details': [{
            '@type': 'type.googleapis.com/google.ads.googleads.v19.errors.GoogleAdsFailure',
            'requestId': 'abc', 'errors': [{
                'errorCode': {'policyFindingError': 'POLICY_FINDING'},
                'message': 'The resource has been disapproved since the policy summary includes policy topics of '
                           'type PROHIBITED.',
                'trigger': {'stringValue': ''},
                'location': {'fieldPathElements': [
                    {'fieldName': 'mutate_operations', 'index': index}, {'fieldName': 'ad_group_ad_operation'},
                    {'fieldName': 'create'}, {'fieldName': 'ad'}, {'fieldName': 'responsive_search_ad'},
                    {'fieldName': 'headlines', 'index': headline}, {'fieldName': 'text'}]},
                'details': {'policyFindingDetails': {'policyTopicEntries': [{
                    'topic': 'GAMBLING', 'type': 'PROHIBITED',
                    'evidences': [{'textList': {'texts': ['Лоти аукціонів Кореї щодня']}}],
                    'constraints': [{'countryConstraintList': {'totalTargetedCountries': 1}}]}]}}}]}]}

    def test_group_topic_and_text_in_report(self):
        google = Google()
        google.ads -= {'UA — Корея під ключ'}
        group = google.groups['UA — Корея під ключ']
        answer = google.__call__

        def call(request, timeout=None):
            response = answer(request, timeout)
            if request.full_url.endswith('googleAds:mutate'):
                ops = json.loads(request.data)['mutateOperations']
                index = next((n for n, o in enumerate(ops)
                              if o.get('adGroupAdOperation', {}).get('create', {}).get('adGroup') == group), None)
                if index is not None:
                    return Response(json.dumps({'partialFailureError': self.failure(index, 1), 'results': []}).encode())
            return response
        with tempfile.TemporaryDirectory() as temp, patch.object(keywords, 'PER_DAY', 10), \
                patch.object(usa, 'MAX_NEW_GROUPS', 1):
            path = Path(temp) / 'keys.json'
            path.write_text(json.dumps(KEYS))
            night = json.loads(remote.report(path, call))
        self.assertEqual(night['policy_refusals'], [{
            'operation': night['policy_refusals'][0]['operation'], 'group': 'UA — Корея під ключ',
            'field': 'ad_group_ad_operation.create.ad.responsive_search_ad.headlines[1].text',
            'text': remote.ad_texts('UA — Корея під ключ')[1][1],
            'topics': [{'topic': 'GAMBLING', 'type': 'PROHIBITED', 'evidence': ['Лоти аукціонів Кореї щодня']}]}])
        self.assertNotIn('policy_refusals', night['steps'][0]['first'])
        self.assertEqual(night['steps'][0]['first']['refused'], 1)

    def test_new_group_named_and_odd_shapes_ignored(self):
        ops = [{'adGroupOperation': {'create': {'resourceName': 'customers/1/adGroups/-700',
                                                'name': 'UA — Аукціон — BMW'}}},
               {'adGroupAdOperation': {'create': {'adGroup': 'customers/1/adGroups/-700', 'ad': {}}}}]
        found = remote.policy_refusals(self.failure(1, 0), ops)
        self.assertEqual(found[0]['group'], 'UA — Аукціон — BMW')
        self.assertIsNone(found[0]['text'])
        self.assertEqual(remote.policy_refusals(self.failure(9, 0), ops)[0]['group'], None)
        for odd in (None, {}, {'details': None}, {'details': [{'errors': [{'details': {'policyFindingDetails': None}}]}]},
                    {'details': ['x', {'errors': 'x'}]}):
            self.assertEqual(remote.policy_refusals(odd, ops), [])


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(KEYS))
        return path

    def test_run_in_parts_and_never_twice(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp, patch.object(keywords, 'PER_DAY', 1000):
            first = json.loads(remote.report(self.keys_file(temp), google))
            second = json.loads(remote.report(self.keys_file(temp), google))
        self.assertEqual(first['status'], 'PASS')
        self.assertEqual(first['after']['ceiling'], {'cpcBidCeilingMicros': '4550000'})
        self.assertEqual(first['added_now'], 500)
        self.assertEqual(first['after']['budget'], '300000000')
        self.assertEqual(second['added_now'], 500)
        self.assertEqual(len(google.texts('korea')), 1001)
        self.assertEqual(first['countries']['usa']['added_tonight'], 500)
        self.assertEqual(second['countries']['usa']['added_tonight'], 500)
        self.assertEqual(len(google.texts('usa')), 1002)
        self.assertEqual(second['countries']['usa']['total_in_campaign'], 1002)
        self.assertEqual(second['countries']['korea']['total_in_campaign'], 1001)
        self.assertEqual(second['countries']['korea']['refused_by_google'], 0)
        self.assertEqual(second['countries']['usa']['left_in_plan'],
                         sum(map(len, usa.plan().values())) - 1000 - 2)  # the two already there count as done
        self.assertTrue(all(m['partialFailure'] for m in google.mutates))
        self.assertTrue(all(len(m['mutateOperations']) <= remote.CHUNK for m in google.mutates[1:]))
        self.assertEqual(first['after']['groups'], len(keywords.plan()))
        # USA: nothing twice (by text, across groups), at most MAX_NEW_GROUPS new groups a night, each with its ad.
        texts = google.texts('usa')
        self.assertEqual(len(texts), len(set(texts)))
        self.assertEqual(first['usa']['after']['groups'], 4 + usa.MAX_NEW_GROUPS)
        self.assertEqual(second['usa']['after']['groups'], 4 + 2 * usa.MAX_NEW_GROUPS)
        self.assertEqual(second['usa']['after']['groups_without_ad'], [])
        self.assertEqual(first['usa']['before']['ceiling'], first['usa']['after']['ceiling'])
        self.assertEqual(google.budgets['usa'], '50000000')
        self.assertEqual(google.campaigns['usa']['targetSpend'], {'cpcBidCeilingMicros': '2000000'})
        self.assertEqual(google.negatives['usa'], {'olx', 'copart parts'})
        place = {k: g for g, ks in usa.plan().items() for k in ks}
        self.assertFalse([(g, t) for g, t in google.keywords - Google().keywords
                          if google.country[g] == 'usa' and place.get(t) != g])

    def test_all_to_usa_when_korea_is_done(self):
        google = Google()
        done = {'UA — Корея під ключ': ['авто з кореї']}  # the whole Korea plan already in the campaign
        with tempfile.TemporaryDirectory() as temp, patch.object(keywords, 'PER_DAY', 1000), \
                patch.object(keywords, 'plan', lambda: done):
            night = json.loads(remote.report(self.keys_file(temp), google))
        self.assertEqual(night['countries']['korea']['added_tonight'], 0)
        self.assertEqual(night['countries']['korea']['left_in_plan'], 0)
        self.assertEqual(night['countries']['usa']['added_tonight'], 1000)
        self.assertEqual(night['status'], 'PASS')


class UsaTests(unittest.TestCase):
    def test_split(self):
        self.assertEqual(keywords.split(9000, 17000), (1200, 1200))
        self.assertEqual(keywords.split(0, 17000), (0, 2400))
        self.assertEqual(keywords.split(9000, 0), (2400, 0))
        self.assertEqual(keywords.split(300, 17000), (300, 2100))
        self.assertEqual(keywords.split(9000, 500), (1900, 500))
        self.assertEqual(keywords.split(10, 20), (10, 20))

    def test_plan(self):
        groups = usa.plan()
        words = [k for v in groups.values() for k in v]
        self.assertEqual((len(words), len(groups)), (17653, 114))
        self.assertEqual(len(words), len(set(words)))
        self.assertTrue(all(len(k) <= 80 and len(k.split()) <= 10 and k == k.lower() for k in words))
        self.assertEqual(list(groups)[:2], ['UA — США під ключ', 'RU — США под ключ'])

    def test_ads_within_limits(self):
        for group in usa.plan():
            ad = usa.ad(group, 'g')['adGroupAdOperation']['create']['ad']
            head = [h['text'] for h in ad['responsiveSearchAd']['headlines']]
            desc = [d['text'] for d in ad['responsiveSearchAd']['descriptions']]
            self.assertTrue(3 <= len(head) <= 15 and all(len(h) <= 30 for h in head), group)
            self.assertEqual(len(head), len(set(head)))
            self.assertTrue(2 <= len(desc) <= 4 and all(len(d) <= 90 for d in desc))
            self.assertFalse([h for h in head if 'Ставка' in h or 'Отримайте пропозицію' in h])
            self.assertEqual(ad['finalUrls'], [usa.PAGE])
            lang_uk = group.startswith('UA')
            self.assertTrue(head[0] in usa.UK_HEAD + usa.RU_HEAD or head[0].endswith('з США' if lang_uk else 'из США'))
            self.assertEqual(ad['responsiveSearchAd']['path2'], 'kyiv' if lang_uk else 'kiev')
        self.assertEqual(usa.ad('RU — США — Ford — годы', 'g')['adGroupAdOperation']['create']['ad'][
            'responsiveSearchAd']['headlines'][0]['text'], 'Ford из США')

    def test_new_groups_capped(self):
        current = {'campaign': {'resourceName': 'c/8'}, 'groups': {'UA — США під ключ': 'g/1', 'RU — США под ключ': 'g/2'},
                   'with_ads': {'UA — США під ключ'}}
        ops = usa.group_operations('1', current)
        self.assertEqual(sum(1 for o in ops if 'adGroupOperation' in o), usa.MAX_NEW_GROUPS)
        self.assertEqual(len(ops), 2 * usa.MAX_NEW_GROUPS + 1)  # + the ad of the existing group without one
        self.assertEqual(ops[-1]['adGroupAdOperation']['create']['adGroup'], 'g/2')


QUOTA = {'error': {'code': 429, 'message': 'Resource has been exhausted (e.g. check quota).', 'status': 'RESOURCE_EXHAUSTED',
                   'details': [{'@type': 'type.googleapis.com/google.ads.googleads.v19.errors.GoogleAdsFailure',
                                'errors': [{'errorCode': {'quotaError': 'RESOURCE_EXHAUSTED'},
                                            'message': 'Too many requests. Retry in 86400 seconds.',
                                            'details': {'quotaErrorDetails': {
                                                'rateScope': 'DEVELOPER', 'retryDelay': '86400s',
                                                'rateName': 'Number of operations for explorer access'}}}]}]}}


class Explorer(Google):
    """Google at the Explorer level: after `left` operations every mutate (with reads=True every read too) is 429."""
    def __init__(self, left, reads=False):
        super().__init__()
        self.left, self.reads, self.refused_after, self.tripped = left, reads, 0, left <= 0

    def __call__(self, request, timeout=None):
        if request.full_url != remote.check.TOKEN_ENDPOINT:
            mutate = request.full_url.endswith('googleAds:mutate')
            size = len(json.loads(request.data)['mutateOperations']) if mutate else 0
            if self.left < size or (self.tripped and self.reads):
                self.tripped = True
                self.refused_after += mutate
                raise urllib.error.HTTPError(request.full_url, 429, 'Too Many Requests', {},
                                             io.BytesIO(json.dumps(QUOTA).encode()))
            self.left -= size
        return super().__call__(request, timeout)


class BigRunTests(unittest.TestCase):
    """Basic access: one run with a large limit (owner 28.11: ~12 000 keywords at once, Japan not included)."""
    def report(self, google, limit):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'keys.json'
            path.write_text(json.dumps(KEYS))
            return json.loads(remote.report(path, google, limit))

    def test_split_12000(self):
        self.assertEqual(keywords.split(8976, 17600, 12000), (6000, 6000))  # half each, both have more left
        self.assertEqual(keywords.split(4000, 17600, 12000), (4000, 8000))  # Korea all it has, USA the rest
        self.assertEqual(keywords.split(8976, 1000, 12000), (8976, 1000))  # less left than the limit: all of it
        self.assertEqual(keywords.split(8976, 17600), (1200, 1200))  # the default night unchanged

    def test_big_run_all_usa_groups_and_basic_hint(self):
        google = Google()
        night = self.report(google, 5000)
        self.assertEqual(night['status'], 'PASS')
        self.assertEqual(night['limit'], 5000)
        self.assertEqual(night['split'], {'korea': 2500, 'usa': 2500})
        self.assertEqual(night['countries']['usa']['groups_left_to_create'], 0)
        self.assertEqual(night['usa']['after']['groups_without_ad'], [])
        self.assertEqual(night['countries']['korea']['added_tonight'], 2500)
        self.assertEqual(night['countries']['usa']['added_tonight'], 2500)
        self.assertEqual(night['access_level_hint'], 'BASIC_OR_HIGHER')
        self.assertGreater(night['operations_accepted'], remote.EXPLORER_OPS)
        self.assertTrue(all(len(m['mutateOperations']) <= remote.CHUNK for m in google.mutates
                            if 'adGroupCriterionOperation' in m['mutateOperations'][0]))
        texts = google.texts('usa')
        self.assertEqual(len(texts), len(set(texts)))
        self.assertEqual(google.budgets, {'korea': '300000000', 'usa': '50000000'})
        self.assertEqual(google.campaigns['usa']['targetSpend'], {'cpcBidCeilingMicros': '2000000'})
        self.assertEqual(google.negatives['usa'], {'olx', 'copart parts'})

    def test_usa_group_cap_only_with_big_limit(self):
        current = {'campaign': {'resourceName': 'c/8'}, 'groups': {}, 'with_ads': set()}
        night = self.report(Google(), keywords.PER_DAY)
        self.assertEqual(night['usa']['after']['groups'], 4 + usa.MAX_NEW_GROUPS)
        self.assertEqual(night['access_level_hint'], 'NOT_TESTED_BELOW_2880')
        self.assertEqual(night['split'], {'korea': 1200, 'usa': 1200})
        self.assertEqual(len(usa.group_operations('1', current)), 2 * usa.MAX_NEW_GROUPS)
        self.assertEqual(len(usa.group_operations('1', current, len(usa.plan()))), 2 * len(usa.plan()))

    def test_quota_mid_run_stops_cleanly(self):
        google = Explorer(2880)
        night = self.report(google, 12000)
        self.assertEqual(night['status'], 'PASS_PARTIAL')
        self.assertEqual(night['access_level_hint'], 'EXPLORER_LIMIT_REACHED')
        self.assertIn('RESOURCE_EXHAUSTED', night['quota_stop'])
        self.assertEqual(google.refused_after, 1)  # nothing sent after the quota answer
        added = night['countries']['korea']['added_tonight'] + night['countries']['usa']['added_tonight']
        self.assertEqual(added, len(google.keywords) - len(Google().keywords))
        self.assertGreater(added, 0)
        self.assertLessEqual(night['operations_accepted'], remote.EXPLORER_OPS)
        self.assertEqual(night['countries']['usa']['added_tonight'], 0)  # Korea goes first, the stop came in it
        self.assertEqual(night['after']['ceiling'], {'cpcBidCeilingMicros': '4550000'})
        self.assertEqual(google.budgets, {'korea': '300000000', 'usa': '50000000'})

    def test_quota_also_on_reads_reports_what_was_sent(self):
        google = Explorer(2880, reads=True)
        night = self.report(google, 12000)
        self.assertEqual(night['status'], 'PARTIAL')
        self.assertEqual(night['access_level_hint'], 'EXPLORER_LIMIT_REACHED')
        self.assertIn('after_unreadable', night)
        self.assertEqual(night['countries']['korea']['added_tonight'] + night['countries']['usa']['added_tonight'],
                         len(google.keywords) - len(Google().keywords))

    def test_quota_before_anything(self):
        night = self.report(Explorer(0, reads=True), 12000)
        self.assertEqual((night['status'], night['access_level_hint'], night['operations_accepted']),
                         ('PASS_PARTIAL', 'EXPLORER_LIMIT_REACHED', 0))

    def test_quota_shapes(self):
        self.assertTrue(remote.quota(429, {}))
        self.assertTrue(remote.quota(400, {'error': {'status': 'RESOURCE_EXHAUSTED'}}))
        temporary = json.loads(json.dumps(QUOTA))
        temporary['error']['status'] = 'INVALID_ARGUMENT'
        temporary['error']['details'][0]['errors'][0]['errorCode'] = {'quotaError': 'RESOURCE_TEMPORARILY_EXHAUSTED'}
        self.assertTrue(remote.quota(400, temporary))
        self.assertFalse(remote.quota(400, {'error': {'status': 'INVALID_ARGUMENT', 'details': [
            {'errors': [{'errorCode': {'requestError': 'INVALID_INPUT'}}]}]}}))


class FakeAPI:
    def __init__(self):
        self.limit = 'unset'

    def run(self, mode, run_id, bundle, limit=None):
        self.limit = limit
        return {'status': 'PASS'}


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-BULK-20261126'

    def test_report_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / 'tasks/requests' / (self.TASK + '.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'production_required': False}))
            env = {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}
            api = FakeAPI()
            receipt = c.execute(env, root=temp, api=api, upload=lambda a: 'b' * 64)
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_bulk_001/20261126.json')
        self.assertIsNone(api.limit)  # the default night: no limit passed on

    def test_limit_from_request(self):
        task = 'ADS-BULK-20261128-BIG'
        for limit, error in ((12000, None), (12001, 'LIMIT'), ('12000', 'LIMIT'), (True, 'LIMIT')):
            with tempfile.TemporaryDirectory() as temp:
                request = Path(temp) / 'tasks/requests' / (task + '.json')
                request.parent.mkdir(parents=True)
                request.write_text(json.dumps({'production_required': False, 'keyword_limit': limit}))
                env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                       'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task,
                       'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}
                api = FakeAPI()
                if error:
                    with self.assertRaisesRegex(c.ProbeError, error):
                        c.execute(env, root=temp, api=api, upload=lambda a: 'b' * 64)
                    continue
                receipt = c.execute(env, root=temp, api=api, upload=lambda a: 'b' * 64)
            self.assertEqual(api.limit, 12000)
            self.assertEqual(receipt['evidence_path'], 'cloud/ads_bulk_001/20261128-BIG.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_limit_in_command_only_when_given(self):
        for limit, tail in ((None, ['--run', '1']), (12000, ['--run', '1', '--limit', '12000'])):
            api = transport.API('test-token')
            receipt = json.dumps({'run_id': '1', 'mode': 'probe', 'safe_to_stop': True}).encode()
            with patch.object(api, 'file', side_effect=[None, receipt]), \
                    patch.object(api, 'json', return_value={'id': 5}) as start, patch.object(api, 'request'):
                api.run('probe', '1', 'a' * 64, limit)
            self.assertTrue(start.call_args[0][2]['command'].endswith(' '.join(tail)))
        with self.assertRaisesRegex(transport.TransportError, 'RUN_LIMIT'):
            transport.API('test-token').run('probe', '1', 'a' * 64, 20000)

    def test_own_prefix(self):
        self.assertIn('adsbulk-', Path(transport.__file__).read_text())

    def test_bundle_names(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
