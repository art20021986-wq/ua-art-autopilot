#!/usr/bin/env python3
"""ADS-BULK: 1 UAH ceiling, buyer keywords uk+ru only, in parts, nothing twice, ads within Google limits."""
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import keywords  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402

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
    def __init__(self):
        self.campaign = {'resourceName': 'customers/1/campaigns/9', 'targetSpend': {'cpcBidCeilingMicros': '7000000'}}
        self.groups = {'UA — Корея під ключ': 'customers/1/adGroups/1', 'RU — Корея под ключ': 'customers/1/adGroups/2'}
        self.keywords, self.negatives, self.mutates = {('UA — Корея під ключ', 'авто з кореї')}, {'olx'}, []
        self.ads = {'UA — Корея під ключ', 'RU — Корея под ключ'}

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
                    self.campaign['targetSpend'] = op['campaignOperation']['update']['targetSpend']
                elif 'campaignCriterionOperation' in op:
                    self.negatives.add(op['campaignCriterionOperation']['create']['keyword']['text'])
                elif 'adGroupOperation' in op:
                    new = op['adGroupOperation']['create']
                    temp[new['resourceName']] = 'customers/1/adGroups/%d' % (10 + len(self.groups))
                    self.groups[new['name']] = temp[new['resourceName']]
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
        if 'FROM campaign_criterion' in query:
            rows = [{'campaignCriterion': {'keyword': {'text': t}}} for t in self.negatives]
        elif 'FROM ad_group_criterion' in query:
            rows = [{'adGroup': {'name': g}, 'adGroupCriterion': {'resourceName': 'kw|%s|%s' % (g, t),
                                                                  'keyword': {'text': t, 'matchType': 'PHRASE'}}}
                    for g, t in self.keywords]
        elif 'FROM ad_group_ad' in query:
            rows = [{'adGroup': {'name': g}, 'adGroupAd': {'status': 'ENABLED'}} for g in self.ads]
        elif 'FROM ad_group ' in query:
            rows = [{'adGroup': {'name': n, 'resourceName': r}} for n, r in self.groups.items()]
        else:
            rows = [{'campaign': self.campaign, 'campaignBudget': {'amountMicros': '300000000'}}]
        return Response(json.dumps({'results': rows}).encode())


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
        self.assertEqual(first['after']['ceiling'], {'cpcBidCeilingMicros': '4550000'})
        self.assertEqual(first['added_now'], 1000)
        self.assertEqual(first['after']['budget'], '300000000')
        self.assertEqual(second['added_now'], 1000)
        self.assertEqual(len(google.keywords), 2001)
        self.assertTrue(all(m['partialFailure'] for m in google.mutates))
        self.assertTrue(all(len(m['mutateOperations']) <= remote.CHUNK for m in google.mutates[1:]))
        self.assertEqual(first['after']['groups'], len(keywords.plan()))


class FakeAPI:
    def run(self, mode, run_id, bundle):
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
            receipt = c.execute(env, root=temp, api=FakeAPI(), upload=lambda a: 'b' * 64)
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_bulk_001/20261126.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_prefix(self):
        self.assertIn('adsbulk-', Path(transport.__file__).read_text())

    def test_bundle_names(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
