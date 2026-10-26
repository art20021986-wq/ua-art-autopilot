#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import unittest
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect as c  # noqa: E402
import years as y  # noqa: E402

c.PAUSE = 0
DATES = {'File:2021 Kia K5 rear.jpg': '2021-05-01', 'File:2025 Kia K5.jpg': '2025-01-01',
         'File:Kia K5 DL3 interior.jpg': '2022:03:01', 'File:Kia K5 DL3 old photo.jpg': '2017:03:01',
         'File:2021 Kia K5 cargo.jpg': ''}


def fake(url):
    parts = urllib.parse.urlsplit(url)
    if parts.netloc == 'upload.wikimedia.org':
        return b'thumb'
    q = dict(urllib.parse.parse_qsl(parts.query))
    if q.get('list') == 'search':
        text = q['srsearch']
        hits = [t for t in DATES if ('trunk' in text or 'cargo' in text) == ('cargo' in t)]
        return json.dumps({'query': {'search': [{'title': t} for t in hits]}}).encode()
    pages = [{'title': t, 'imageinfo': [{'width': 2000, 'height': 1300, 'mime': 'image/jpeg',
              'thumburl': 'https://upload.wikimedia.org/x', 'descriptionurl': 'd',
              'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'},
                              'DateTimeOriginal': {'value': DATES.get(t, '')}}}]} for t in q['titles'].split('|')]
    return json.dumps({'query': {'pages': pages}}).encode()


class YearTests(unittest.TestCase):
    def test_targets_are_known_models(self):
        self.assertTrue(set(y.TARGETS) <= set(c.MODELS))
        for key in ('lexus-tx', 'toyota-tacoma-trailhunter', 'classics-1980-1990'):
            self.assertNotIn(key, y.TARGETS)

    def test_car_year(self):
        ok = y.car_year_ok
        self.assertTrue(ok({'title': 'File:2021 Kia K5.jpg', 'date': '2026-01-01'}, False))
        self.assertFalse(ok({'title': 'File:2025 Kia K5.jpg', 'date': '2022-01-01'}, True))
        self.assertFalse(ok({'title': 'File:2017 Audi Q5.jpg', 'date': ''}, False))
        self.assertTrue(ok({'title': 'File:Kia K5 DL3.jpg', 'date': '2022:03:01'}, True))
        self.assertFalse(ok({'title': 'File:Audi Q5 FY.jpg', 'date': '2022:03:01'}, False))
        self.assertFalse(ok({'title': 'File:Kia K5 DL3.jpg', 'date': ''}, True))

    def test_model(self):
        found = y.model(fake, 'kia-k5')['candidates']
        titles = {view: [i['title'] for i in items] for view, items in found.items()}
        self.assertEqual(titles['interior'], ['File:2021 Kia K5 rear.jpg', 'File:Kia K5 DL3 interior.jpg'])
        self.assertEqual(titles['trunk'], ['File:2021 Kia K5 cargo.jpg'])


if __name__ == '__main__':
    unittest.main()
