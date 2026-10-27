#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import unittest
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import angles as a  # noqa: E402
import collect as c  # noqa: E402
import years  # noqa: E402

c.PAUSE = 0
HITS = {'Kia K5 DL3 front left': ['File:2021 Kia K5 front.jpg', 'File:2025 Kia K5 front.jpg'],
        'Kia K5 DL3 rear': ['File:2021 Kia K5 rear.jpg', 'File:2021 Kia K5 front.jpg'],
        'Kia K5 DL3 trunk': ['File:2022 Kia K5 trunk.jpg']}


def fake(url):
    parts = urllib.parse.urlsplit(url)
    if parts.netloc == 'upload.wikimedia.org':
        return b'thumb'
    q = dict(urllib.parse.parse_qsl(parts.query))
    if q.get('list') == 'search':
        return json.dumps({'query': {'search': [{'title': t} for t in HITS.get(q['srsearch'][:-16], [])]}}).encode()
    pages = [{'title': t, 'imageinfo': [{'width': 2000, 'height': 1300, 'mime': 'image/jpeg',
              'thumburl': 'https://upload.wikimedia.org/x', 'descriptionurl': 'd',
              'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'}}}]} for t in q['titles'].split('|')]
    return json.dumps({'query': {'pages': pages}}).encode()


class AngleTests(unittest.TestCase):
    def test_eight_views_in_order(self):
        self.assertEqual([v for v, _ in a.VIEWS], ['front_left', 'front_right', 'rear_left', 'rear_right',
                                                   'dash_driver', 'dash_passenger', 'rear_seats', 'boot'])

    def test_model_views_years_and_no_repeats(self):
        found = a.model(fake, 'kia-k5')['candidates']
        titles = {view: [i['title'] for i in items] for view, items in found.items()}
        self.assertEqual(titles['front_left'], ['File:2021 Kia K5 front.jpg'])
        self.assertEqual(titles['rear_left'], ['File:2021 Kia K5 rear.jpg'])
        self.assertEqual(titles['boot'], ['File:2022 Kia K5 trunk.jpg'])
        self.assertEqual(set(found), {v for v, _ in a.VIEWS})


if __name__ == '__main__':
    unittest.main()
