#!/usr/bin/env python3
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect as c  # noqa: E402

c.PAUSE = 0

MAIN = 'File:0_Kia_K5_(DL3)_0.jpg'
CATS = {MAIN: ['Category:Kia K5 (DL3) in Seoul', 'Category:Cars in Seoul'],
        'Category:Kia K5 (DL3) in Seoul': ['Category:Kia K5 (DL3)']}
SUBCATS = {'Category:Kia K5 (DL3)': ['Category:Interior of Kia K5 (DL3)', 'Category:Kia K5 (DL3) GT']}
FILES = {'Category:Kia K5 (DL3) in Seoul': ['File:K5 rear.jpg', MAIN],
         'Category:Interior of Kia K5 (DL3)': ['File:K5 dash.jpg', 'File:K5 nc.jpg'],
         'Category:Cars in Seoul': ['File:Other car.jpg']}
LICENSE = {'File:K5 nc.jpg': 'CC BY-NC 4.0'}


def fake(url):
    parts = urllib.parse.urlsplit(url)
    if parts.netloc == 'upload.wikimedia.org':
        return b'thumb:' + parts.path.encode()
    q = dict(urllib.parse.parse_qsl(parts.query))
    if q.get('prop') == 'categories':
        cats = CATS.get(q['titles'], [])
        return json.dumps({'query': {'pages': [{'categories': [{'title': t} for t in cats]}]}}).encode()
    if q.get('list') == 'categorymembers':
        found = (SUBCATS if q['cmtype'] == 'subcat' else FILES).get(q['cmtitle'], [])
        return json.dumps({'query': {'categorymembers': [{'title': t} for t in found]}}).encode()
    pages = [{'title': t, 'imageinfo': [{'width': 2000, 'height': 1300, 'mime': 'image/jpeg', 'sha1': 'x',
              'thumburl': 'https://upload.wikimedia.org/' + t.replace(' ', '_'), 'descriptionurl': 'd',
              'extmetadata': {'LicenseShortName': {'value': LICENSE.get(t, 'CC BY-SA 4.0')},
                              'Artist': {'value': '<a href="x">Me</a>'}}}]} for t in q['titles'].split('|')]
    return json.dumps({'query': {'pages': pages}}).encode()


class CollectTests(unittest.TestCase):
    def test_scope(self):
        with self.assertRaises(c.CollectError):
            c.get('https://www.example.com/x')

    def test_follow_stays_on_model(self):
        cats = c.follow(fake, MAIN, 'K5')
        self.assertEqual(cats, ['Category:Kia K5 (DL3) in Seoul', 'Category:Kia K5 (DL3)',
                                'Category:Interior of Kia K5 (DL3)'])

    def test_model_buckets_and_licences(self):
        found = c.model(fake, 'kia-k5')
        titles = {k: [i['title'] for i in v] for k, v in found['candidates'].items()}
        self.assertEqual(titles, {'interior': ['File:K5 dash.jpg'], 'sides': ['File:K5 rear.jpg'], 'other': []})
        item = found['candidates']['interior'][0]
        self.assertEqual(item['artist'], 'Me')
        self.assertEqual(base64.b64decode(item['thumb_b64']), b'thumb:/File:K5_dash.jpg')
        self.assertEqual(found['main']['title'], MAIN)

    def test_free_licences(self):
        for name in ('CC0', 'Public domain', 'CC BY 2.0', 'CC BY-SA 4.0', 'CC BY-SA 3.0 de'):
            self.assertTrue(c.FREE.match(name), name)
        for name in ('CC BY-NC 4.0', 'CC BY-ND 4.0', ''):
            self.assertFalse(c.FREE.match(name), name)

    def test_execute_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = c.TASKS[0]
            request = root/'tasks/requests'/(task + '.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task, 'UAART_RUN_ID': '1',
                   'UAART_REQUEST_SHA256': hashlib.sha256(request.read_bytes()).hexdigest()}
            with self.assertRaises(c.CollectError):
                c.execute({**env, 'UAART_REQUEST_SHA256': '0'}, root=root, fetch=fake)
            old = c.MODELS
            c.MODELS = {'kia-k5': ('korea', MAIN, 'K5')}
            try:
                receipt = c.execute(env, root=root, fetch=fake)
            finally:
                c.MODELS = old
            self.assertEqual(receipt['status'], 'FINISHED')
            data = json.loads((root/c.evidence_path('korea')).read_text())
            self.assertIn('kia-k5', data['models'])


if __name__ == '__main__':
    unittest.main()
