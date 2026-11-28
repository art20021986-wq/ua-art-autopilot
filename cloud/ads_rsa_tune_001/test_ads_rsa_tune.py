#!/usr/bin/env python3
"""ADS-RSA-TUNE: old headlines replaced in place (pin kept), no duplicates, 3–15, one update per ad, nothing twice."""
import copy
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402

KEYS = {'developer_token': 'DEVTOKEN' + 'x' * 14, 'client_id': '1' * 12 + '-abc.apps.' + 'googleusercontent.com',
        'client_secret': 'GOC' + 'SPX-' + 'q' * 28, 'refresh_token': '1//' + 'r' * 40,
        'login_customer_id': '9054959760', 'customer_id': '4680747874'}
UK = ['Kia K5 з Кореї', 'Авто з Кореї під ключ', 'Пригон авто з Кореї', 'Передоплата в ціні авто',
      'Етап доставки онлайн', 'Офіційний договір']
RU = ['Kia K5 из Кореи', 'Купить авто из Кореи', 'Предоплата в цене авто', 'Этап доставки онлайн', 'Кредит и лизинг']


def heads(texts, pins=None):
    return [{'text': t, **({'pinnedField': pins[t]} if pins and t in pins else {}),
             'assetPerformanceLabel': 'PENDING'} for t in texts]


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Google:
    def __init__(self, refuse=()):
        self.campaign = {'resourceName': 'customers/1/campaigns/9', 'name': 'Пошук — Україна — Корея (UA ART)',
                         'status': 'ENABLED', 'biddingStrategyType': 'TARGET_SPEND',
                         'targetSpend': {'cpcBidCeilingMicros': '4550000'}}
        self.ads = {'customers/1/ads/1': ('UA — Kia K5', heads(UK, {'Передоплата в ціні авто': 'HEADLINE_2'})),
                    'customers/1/ads/2': ('RU — Kia K5', heads(RU)),
                    'customers/1/ads/3': ('UA — Інше', heads(['Офіційний договір', 'Кредит і лізинг', 'Послуга — 600 $'])),
                    'customers/1/ads/4': ('UA — Мало', heads(['Авто з Кореї під ключ Київ', 'Купити авто з Кореї',
                                                             'Етап доставки онлайн']))}
        self.refuse, self.calls = set(refuse), []

    def __call__(self, request, timeout=None):
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': 'ya' + '29.' + 'a' * 30}).encode())
        body = json.loads(request.data)
        self.calls.append((request.full_url, body))
        if request.full_url.endswith('googleAds:mutate'):
            errors = []
            for n, op in enumerate(body['mutateOperations']):
                update = op['adOperation']['update']
                assert op['adOperation']['updateMask'] == 'responsive_search_ad.headlines'
                assert set(update) == {'resourceName', 'responsiveSearchAd'}
                if update['resourceName'] in self.refuse:
                    errors.append({'errorCode': {'policyFindingError': 'POLICY_FINDING'}, 'message': 'policy',
                                   'location': {'fieldPathElements': [
                                       {'fieldName': 'mutate_operations', 'index': n}, {'fieldName': 'ad_operation'},
                                       {'fieldName': 'update'}, {'fieldName': 'responsive_search_ad'},
                                       {'fieldName': 'headlines', 'index': 0}, {'fieldName': 'text'}]},
                                   'details': {'policyFindingDetails': {'policyTopicEntries': [
                                       {'topic': 'GAMBLING', 'type': 'PROHIBITED',
                                        'evidences': [{'textList': {'texts': ['ключ']}}]}]}}})
                    continue
                group = self.ads[update['resourceName']][0]
                self.ads[update['resourceName']] = (group, update['responsiveSearchAd']['headlines'])
            answer = {'results': [{}] * len(body['mutateOperations'])}
            if errors:
                answer['partialFailureError'] = {'code': 3, 'details': [{'errors': errors}]}
            return Response(json.dumps(answer).encode())
        if 'FROM ad_group_ad' in body['query']:
            return Response(json.dumps({'results': [
                {'adGroup': {'name': g}, 'adGroupAd': {'status': 'ENABLED', 'policySummary': {'approvalStatus': 'APPROVED'},
                                                       'ad': {'resourceName': n, 'responsiveSearchAd': {'headlines': h}}}}
                for n, (g, h) in self.ads.items()]}).encode())
        return Response(json.dumps({'results': [{'campaign': self.campaign,
                                                 'campaignBudget': {'amountMicros': '300000000'}}]}).encode())


class RemoteTests(unittest.TestCase):
    def report(self, google):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'keys.json'
            path.write_text(json.dumps(KEYS))
            return json.loads(remote.report(path, google))

    def test_headlines_replaced_once(self):
        google = Google()
        first, second = self.report(google), self.report(google)
        self.assertEqual((first['status'], first['operations'], second['status'], second['operations']),
                         ('PASS', 2, 'PASS', 0))
        self.assertEqual([u for u, _ in google.calls if u.endswith(':mutate')], [remote.check.API +
                         'customers/4680747874/googleAds:mutate'])
        mutate = next(b for u, b in google.calls if u.endswith(':mutate'))
        self.assertTrue(mutate['partialFailure'])
        uk = first['ads']['customers/1/ads/1']
        self.assertEqual(uk['after'], ['Kia K5 з Кореї', 'Авто з Кореї під ключ', 'Пригон авто з Кореї',
                                       'Авто з Кореї під ключ Київ', 'Купити авто з Кореї', 'Офіційний договір'])
        self.assertEqual(uk['before'], UK)
        self.assertEqual(google.ads['customers/1/ads/1'][1][3], {'text': 'Авто з Кореї під ключ Київ',
                                                                 'pinnedField': 'HEADLINE_2'})
        ru = first['ads']['customers/1/ads/2']
        self.assertEqual(ru['after'], ['Kia K5 из Кореи', 'Купить авто из Кореи', 'Авто из Кореи под ключ Киев',
                                       'Кредит и лизинг'])  # «Купить…» was already there: the old one only dropped
        self.assertEqual(first['ads']['customers/1/ads/4']['result'], 'SKIPPED_COUNT_2')
        self.assertNotIn('customers/1/ads/3', first['ads'])
        self.assertEqual(first['counts'], {'SKIPPED_COUNT_2': 1, 'UPDATED': 2})
        self.assertTrue(first['settings_unchanged'])
        self.assertEqual(first['old_headlines_left'], 1)  # the skipped ad keeps its old headline; still PASS

    def test_refusal_with_policy_topic(self):
        google = Google(refuse={'customers/1/ads/2'})
        value = self.report(google)
        ad = value['ads']['customers/1/ads/2']
        self.assertEqual(ad['result'], 'REFUSED')
        self.assertEqual(ad['after'], RU)
        self.assertEqual(ad['refusals'][0]['topics'], [{'topic': 'GAMBLING', 'type': 'PROHIBITED', 'evidence': ['ключ']}])
        self.assertEqual(ad['refusals'][0]['text'], 'Kia K5 из Кореи')
        self.assertEqual(value['ads']['customers/1/ads/1']['result'], 'UPDATED')
        self.assertEqual(value['status'], 'PARTIAL')

    def test_rules(self):
        self.assertTrue(all(len(t) <= remote.MAX_LEN for t in remote.REPLACE.values()))
        self.assertIsNone(remote.new_headlines(heads(['А', 'Б', 'В'])))
        dup = remote.new_headlines(heads(['купити авто з кореї', 'Етап доставки онлайн', 'Б', 'В']))
        self.assertEqual([h['text'] for h in dup], ['купити авто з кореї', 'Б', 'В'])
        self.assertEqual(remote.problem(heads(['x'] * 3)), 'DUPLICATE')
        self.assertEqual(remote.problem(heads(['x%d' % n for n in range(16)])), 'COUNT_16')

    def test_too_many_ads_sends_nothing(self):
        google = Google()
        one = google.ads['customers/1/ads/1']
        google.ads.update({'customers/1/ads/%d' % n: copy.deepcopy(one) for n in range(10, 10 + remote.MAX_ADS)})
        value = self.report(google)
        self.assertEqual(value['status'], 'FAIL')
        self.assertFalse([u for u, _ in google.calls if u.endswith(':mutate')])

    def test_nightly_plan_uses_new_texts(self):
        sys.path.insert(0, str(HERE.parent / 'ads_bulk_001'))
        try:
            import plan
        finally:
            sys.path.pop(0)
        for old, new in remote.REPLACE.items():
            self.assertNotIn(old, plan.UK_HEAD + plan.RU_HEAD)
            self.assertIn(new, plan.UK_HEAD + plan.RU_HEAD)


class FakeAPI:
    def run(self, mode, run_id, bundle):
        return {'status': 'PASS'}


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-RSA-TUNE-20261128'

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
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_rsa_tune_001/20261128.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_prefix(self):
        text = Path(transport.__file__).read_text() + (HERE / 'bootstrap.py').read_text()
        self.assertIn('adsrsa-', text)
        self.assertNotIn('adsusa', text)

    def test_bundle_names(self):
        for path in HERE.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
