#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import unittest
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect as c  # noqa: E402
import search as s  # noqa: E402

c.PAUSE = 0
HITS = {'Kia K5 DL3 interior filetype:bitmap': ['File:K5 dash.jpg', 'File:K5 portrait.jpg'],
        'Kia K5 2020 interior filetype:bitmap': ['File:K5 dash.jpg', 'File:K5 seats.jpg'],
        'Kia K5 DL3 rear filetype:bitmap': ['File:K5 rear.jpg', 'File:0 Kia K5 (DL3) 0.jpg']}


def fake(url):
    parts = urllib.parse.urlsplit(url)
    if parts.netloc == 'upload.wikimedia.org':
        return b'thumb'
    q = dict(urllib.parse.parse_qsl(parts.query))
    if q.get('list') == 'search':
        return json.dumps({'query': {'search': [{'title': t} for t in HITS.get(q['srsearch'], [])]}}).encode()
    pages = [{'title': t, 'imageinfo': [{'width': 2000, 'height': 3000 if 'portrait' in t else 1300,
              'mime': 'image/jpeg', 'thumburl': 'https://upload.wikimedia.org/x', 'descriptionurl': 'd',
              'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'}}}]} for t in q['titles'].split('|')]
    return json.dumps({'query': {'pages': pages}}).encode()


class SearchTests(unittest.TestCase):
    def test_every_model_has_searches(self):
        self.assertEqual(set(s.SEARCHES), set(c.MODELS))

    def test_model(self):
        found = s.model(fake, 'kia-k5')['candidates']
        self.assertEqual([i['title'] for i in found['interior']], ['File:K5 dash.jpg', 'File:K5 seats.jpg'])
        self.assertEqual([i['title'] for i in found['sides']], ['File:K5 rear.jpg'])
        self.assertEqual(found['interior'][0]['via'], 'search: Kia K5 DL3 interior')


if __name__ == '__main__':
    unittest.main()
