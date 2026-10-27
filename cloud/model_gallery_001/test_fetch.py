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
import angles  # noqa: E402
import fetch as f  # noqa: E402

c.PAUSE = 0
LICENSE = {'File:K5 nc.jpg': 'CC BY-NC 4.0'}


def fake(url):
    parts = urllib.parse.urlsplit(url)
    if parts.netloc == 'upload.wikimedia.org':
        return b'photo:' + parts.path.encode()
    q = dict(urllib.parse.parse_qsl(parts.query))
    pages = [{'title': t, 'imageinfo': [{'width': 2000, 'height': 1300, 'mime': 'image/jpeg',
              'thumburl': 'https://upload.wikimedia.org/' + t.replace(' ', '_'), 'descriptionurl': 'd',
              'extmetadata': {'LicenseShortName': {'value': LICENSE.get(t, 'CC BY-SA 4.0')}}}]}
             for t in q['titles'].split('|')]
    return json.dumps({'query': {'pages': pages}}).encode()


def env_for(root):
    task = f.TASKS[0]
    request = root/'tasks/requests'/(task + '.json')
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps({'read_only': True, 'production_required': False}))
    return {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
            'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task, 'UAART_RUN_ID': '1',
            'UAART_REQUEST_SHA256': hashlib.sha256(request.read_bytes()).hexdigest()}


class FetchTests(unittest.TestCase):
    def test_picks_cover_known_models(self):
        picks = f.chosen.PICKS
        self.assertTrue(set(picks) <= set(c.MODELS))
        order = [view for view, _ in angles.VIEWS]
        for views in picks.values():
            self.assertEqual(list(views), [view for view in order if view in views])
            self.assertTrue(all(len(titles) == 1 for titles in views.values()))

    def test_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            picks = {'kia-k5': {'exterior': ['File:K5 rear.jpg'], 'interior': ['File:K5 dash.jpg']}}
            receipt = f.execute(env_for(root), root=root, fetch=fake, picks=picks)
            self.assertEqual(receipt['evidence_path'], [f.evidence_path('korea', f.TASKS[0])])
            data = json.loads((root/f.evidence_path('korea', f.TASKS[0])).read_text())['models']['kia-k5']
            self.assertEqual(base64.b64decode(data['interior'][0]['b64']), b'photo:/File:K5_dash.jpg')

    def test_non_free_pick_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            picks = {'kia-k5': {'exterior': ['File:K5 nc.jpg'], 'interior': []}}
            with self.assertRaises(c.CollectError):
                f.execute(env_for(root), root=root, fetch=fake, picks=picks)


if __name__ == '__main__':
    unittest.main()
