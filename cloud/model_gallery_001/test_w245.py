#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import unittest
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect as c  # noqa: E402
import w245  # noqa: E402

c.PAUSE = 0
HITS = {'Mercedes-Benz W245 facelift front left': ['File:2010 Mercedes-Benz B 180 front.jpg',
                                                    'File:2014 Mercedes-Benz B 180 front.jpg',
                                                    'File:Mercedes-Benz B 200 (W245) front.jpg'],
        'Mercedes-Benz W245 facelift rear': ['File:2011 Mercedes-Benz B 180 rear.jpg',
                                             'File:2010 Mercedes-Benz B 180 front.jpg'],
        'Mercedes-Benz W245 trunk': ['File:Mercedes-Benz B 180 (W245) 2005 trunk.jpg']}


def fake(url):
    parts = urllib.parse.urlsplit(url)
    if parts.netloc == 'upload.wikimedia.org':
        return b'thumb'
    q = dict(urllib.parse.parse_qsl(parts.query))
    if q.get('list') == 'search':
        return json.dumps({'query': {'search': [{'title': t} for t in HITS.get(q['srsearch'][:-16], [])]}}).encode()
    pages = [{'title': t, 'imageinfo': [{'width': 2000, 'height': 1300, 'mime': 'image/jpeg',
              'thumburl': 'https://upload.wikimedia.org/x', 'descriptionurl': 'd',
              'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 3.0'}}}]} for t in q['titles'].split('|')]
    return json.dumps({'query': {'pages': pages}}).encode()


class W245Tests(unittest.TestCase):
    def test_facelift_years_views_and_no_repeats(self):
        found = w245.candidates(fake)
        titles = {view: [i['title'] for i in items] for view, items in found.items()}
        self.assertEqual(titles['front_left'], ['File:2010 Mercedes-Benz B 180 front.jpg',
                                                'File:Mercedes-Benz B 200 (W245) front.jpg'])
        self.assertEqual(titles['rear_left'], ['File:2011 Mercedes-Benz B 180 rear.jpg'])
        self.assertEqual(titles['boot'], [])
        self.assertEqual(list(found), ['front_left', 'front_right', 'rear_left', 'rear_right',
                                       'dash_driver', 'dash_passenger', 'rear_seats', 'boot'])

    def test_interior_round(self):
        def fake2(url):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
            if q.get('prop') == 'categories':
                return json.dumps({'query': {'pages': [{'categories': [
                    {'title': 'Category:Mercedes-Benz W245 interior'}, {'title': 'Category:Hatchbacks'}]}]}}).encode()
            if q.get('list') == 'categorymembers':
                files = {'Category:Mercedes-Benz W245 interior': ['File:B 200 (2010-10-16) 2.jpg',
                                                                  'File:2006 B 180 seats.jpg']}
                titles = files.get(q['cmtitle'], []) if q['cmtype'] == 'file' else []
                return json.dumps({'query': {'categorymembers': [{'title': t} for t in titles]}}).encode()
            if q.get('list') == 'search':
                hits = {'Mercedes B-Klasse Kofferraum': ['File:B-Klasse Kofferraum.jpg', 'File:B-Klasse front.jpg'],
                        'Mercedes-Benz W245 interior': ['File:B-Klasse front.jpg']}
                return json.dumps({'query': {'search': [{'title': t} for t in hits.get(q['srsearch'][:-16], [])]}}).encode()
            return fake(url)
        titles = [i['title'] for i in w245.interior(fake2)['interior']]
        # Every interior query hit is kept for the eye; a non-facelift year is not.
        self.assertEqual(titles, ['File:B 200 (2010-10-16) 2.jpg', 'File:B-Klasse Kofferraum.jpg',
                                  'File:B-Klasse front.jpg'])

    def test_identity_is_bound_to_the_task(self):
        with self.assertRaises(c.CollectError):
            w245.execute({'UAART_TASK_ID': 'MODEL-GALLERY-ANGLES-20261027'}, root='.', fetch=fake)


if __name__ == '__main__':
    unittest.main()
