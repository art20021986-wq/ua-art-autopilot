#!/usr/bin/env python3
"""ADS-GEO: Ukraine instead of Kyiv, the six regions excluded, nothing else; stops if a region is not found."""
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
import source_remote as remote  # noqa: E402
import transport  # noqa: E402

KEYS = {'developer_token': 'DEVTOKEN' + 'x' * 14, 'client_id': '1' * 12 + '-abc.apps.' + 'googleusercontent.com',
        'client_secret': 'GOC' + 'SPX-' + 'q' * 28, 'refresh_token': '1//' + 'r' * 40,
        'login_customer_id': '9054959760', 'customer_id': '4680747874'}
NAMES = ['Kyiv Oblast', 'Zhytomyr Oblast', 'Vinnytsia Oblast', 'Cherkasy Oblast', 'Kirovohrad Oblast', 'Poltava Oblast',
         "Chernihiv Oblast", 'Mykolaiv Oblast', 'Odesa Oblast', "Khmel'nyts'kyi Oblast", 'Rivne Oblast', 'Volyn Oblast',
         'Lviv Oblast', 'Ternopil Oblast', 'Ivano-Frankivsk Oblast', 'Zakarpattia Oblast', 'Chernivtsi Oblast',
         'Zaporizhia Oblast', 'Kherson Oblast', 'Kharkiv Oblast', 'Sumy Oblast', 'Dnipropetrovsk Oblast']
REGIONS = ([(str(100 + n), name, 'Region') for n, name in enumerate(NAMES)] + [('21118', 'Kyiv city', 'Region')]
           + [('900', 'Zaporizhzhia', 'City'), ('901', 'Kherson', 'City'), ('902', 'Dnipro', 'City'),
              ('903', 'Kharkiv', 'City'), ('904', 'Sumy', 'City'), ('905', 'Kyiv', 'City')])


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Google:
    def __init__(self, regions=REGIONS):
        self.regions = regions
        self.criteria = {'c/1': ('geoTargetConstants/21118', False), 'c/2': ('geoTargetConstants/2804', False),
                         'c/3': ('geoTargetConstants/121', True)}
        self.calls = []

    def __call__(self, request, timeout=None):
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': 'ya' + '29.' + 'a' * 30}).encode())
        body = json.loads(request.data)
        self.calls.append((request.full_url, body))
        if request.full_url.endswith('googleAds:mutate'):
            for op in body['mutateOperations']:
                o = op['campaignCriterionOperation']
                if 'remove' in o:
                    del self.criteria[o['remove']]
                else:
                    self.criteria['c/%d' % (len(self.criteria) + 10)] = (o['create']['location']['geoTargetConstant'],
                                                                        o['create'].get('negative', False))
            return Response(b'{}')
        q = body['query']
        if 'FROM geo_target_constant' in q:
            rows = [{'geoTargetConstant': {'resourceName': 'geoTargetConstants/' + i, 'name': n, 'targetType': t,
                                           'status': 'ENABLED'}} for i, n, t in self.regions]
        elif 'FROM campaign_criterion' in q:
            rows = [{'campaignCriterion': {'resourceName': k, 'location': {'geoTargetConstant': g}, 'negative': neg}}
                    for k, (g, neg) in self.criteria.items()]
        else:
            rows = [{'campaign': {'resourceName': 'customers/1/campaigns/9'}}]
        return Response(json.dumps({'results': rows}).encode())


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(KEYS))
        return path

    def test_exact_places(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            value = json.loads(remote.report(self.keys_file(temp), google))
            again = json.loads(remote.report(self.keys_file(temp), google))
        self.assertEqual((value['status'], again['status']), ('PASS', 'PASS'))
        names = set(value['target'].values())
        self.assertEqual(len(names), 23)
        for out in ('Zaporizhia Oblast', 'Kherson Oblast', 'Kharkiv Oblast', 'Sumy Oblast', 'Dnipropetrovsk Oblast'):
            self.assertNotIn(out, names)
        self.assertTrue({n.split(' (')[0] for n in names} >= {'Zaporizhzhia', 'Kherson', 'Dnipro', 'Kharkiv', 'Sumy',
                                                               "Khmel'nyts'kyi Oblast", 'Kyiv city'})
        self.assertEqual(value['after']['negative'], {})
        self.assertNotIn('geoTargetConstants/2804', value['after']['positive'])
        self.assertEqual(len([u for u, _ in google.calls if u.endswith(':mutate')]), 1)

    def test_missing_place_changes_nothing(self):
        google = Google([r for r in REGIONS if r[1] != 'Sumy'])
        with tempfile.TemporaryDirectory() as temp:
            value = json.loads(remote.report(self.keys_file(temp), google))
        self.assertEqual((value['status'], value['error']), ('FAIL', 'LOCATIONS_NOT_FOUND'))
        self.assertFalse([u for u, _ in google.calls if u.endswith(':mutate')])


class FakeAPI:
    def run(self, mode, run_id, bundle):
        return {'status': 'PASS'}


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-GEO-20261126'

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
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_geo_001/20261126.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_prefix(self):
        self.assertIn('adsgeo-', Path(transport.__file__).read_text())

    def test_bundle_names(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
