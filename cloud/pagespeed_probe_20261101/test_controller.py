#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402


def report(performance):
    return {'lighthouseVersion': '13.5.0', 'finalDisplayedUrl': 'https://www.uaart.com.ua/video/index.html',
            'environment': {'hostUserAgent': 'HeadlessChrome', 'benchmarkIndex': 1500},
            'categories': {'performance': {'score': performance}, 'seo': {'score': 1}},
            'audits': {'largest-contentful-paint': {'numericValue': 3456.7, 'score': 0.5, 'scoreDisplayMode': 'numeric'},
                       'cumulative-layout-shift': {'numericValue': 0.01234, 'score': 1, 'scoreDisplayMode': 'numeric'},
                       'render-blocking-resources': {'score': 0.3, 'scoreDisplayMode': 'metricSavings',
                                                     'title': 'Render-blocking', 'displayValue': '600 ms',
                                                     'details': {'type': 'list', 'items': [{'type': 'table', 'items': [
                                                         {'url': 'https://x/a.css', 'wastedMs': 300},
                                                         {'url': 'https://x/b.js', 'wastedMs': 500, 'node': {}}]}]}},
                       'meta-description': {'score': 1, 'scoreDisplayMode': 'binary', 'title': 'Meta'},
                       'diagnostics': {'score': None, 'scoreDisplayMode': 'informative'},
                       'largest-contentful-paint-element': {'details': {'type': 'list', 'items': [
                           {'type': 'table', 'items': [{'node': {'snippet': '<img src="a.jpg">'}}]}]}}}}


class Fake:
    def __init__(self, node='v22.20.0'):
        self.node, self.calls, self.scores = node, [], iter([0.4, 0.9, 0.6] * len(c.PAGES))

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        out = self.node if argv[0] == 'node' else json.dumps(report(next(self.scores)))
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr='')


class ProbeTests(unittest.TestCase):
    def test_package_follows_node(self):
        self.assertEqual(c.package((22, 19)), 'lighthouse@13.5.0')
        self.assertEqual(c.package((20, 19)), 'lighthouse@12.8.2')

    def test_reduce(self):
        result = c.reduce(report(0.61))
        self.assertEqual((result['performance'], result['seo']), (61, 100))
        self.assertEqual((result['metrics']['lcp_ms'], result['metrics']['cls'], result['metrics']['tbt_ms']),
                         (3457, 0.012, None))
        self.assertEqual([item['id'] for item in result['failing']], ['render-blocking-resources'])
        self.assertEqual(result['lcp_element'], '<img src="a.jpg">')
        self.assertEqual([row['url'] for row in result['failing'][0]['resources']], ['https://x/b.js', 'https://x/a.css'])

    def test_execute(self):
        fake = Fake()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = 'PAGESPEED-PROBE-20261101'
            request = root / 'tasks/requests' / (task + '.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '1'}
            receipt = c.execute(env, root=root, run=fake)
            evidence = json.loads((root / receipt['evidence_path']).read_text())
            with self.assertRaises(c.ProbeError):
                c.execute({**env, 'UAART_REQUEST_SHA256': '0'}, root=root, run=fake)
        self.assertEqual(len(fake.calls), 1 + len(c.PAGES) * c.RUNS)
        self.assertTrue(all(call[2] == 'lighthouse@13.5.0' and call[3].startswith(c.SITE) for call in fake.calls[1:]))
        page = evidence['pages']['/video/index.html']
        self.assertEqual((page['performance'], page['runs_performance']), (60, [40, 90, 60]))
        self.assertEqual(evidence['environment']['lighthouse'], '13.5.0')
        self.assertEqual(receipt['evidence_path'], c.PACKAGE + '/evidence.json')


if __name__ == '__main__':
    unittest.main()
