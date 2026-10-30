#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import unittest
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import classics2000  # noqa: E402
import collect as c  # noqa: E402

c.PAUSE = 0
HITS = {'BMW Z8 interior': ['File:BMW Z8 2001 interior.jpg', 'File:BMW Z8 1999 interior.jpg'],
        'BMW Z8': ['File:BMW Z8 2001 interior.jpg', 'File:BMW Z8 (2002) front.jpg', 'File:BMW Z8 front.jpg',
                   'File:BMW Z8 2005 rear.jpg'],
        'BMW E52': ['File:BMW Z8 front.jpg']}


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


class Classics2000Tests(unittest.TestCase):
    def test_years_kinds_and_no_repeats(self):
        found = classics2000.model(fake, classics2000.MODELS['bmw-z8'])['candidates']
        titles = {kind: [i['title'] for i in items] for kind, items in found.items()}
        self.assertEqual(titles['interior'], ['File:BMW Z8 2001 interior.jpg'])
        self.assertEqual(titles['outside'], ['File:BMW Z8 (2002) front.jpg', 'File:BMW Z8 front.jpg'])

    def test_thumbs_are_640(self):
        urls = []
        classics2000.model(lambda url: urls.append(url) or fake(url), ('BMW Z8',))
        self.assertTrue(any('iiurlwidth=640' in u for u in urls))

    def test_identity_is_checked(self):
        with self.assertRaises(c.CollectError):
            classics2000.execute({'UAART_TASK_ID': 'OTHER'}, root='.', fetch=fake)

    def test_every_model_in_one_part(self):
        keys = list(classics2000.MODELS)
        parts = [keys[n::classics2000.PARTS] for n in range(classics2000.PARTS)]
        self.assertEqual(sorted(k for part in parts for k in part), sorted(keys))
        self.assertEqual(len(classics2000.EVIDENCE), classics2000.PARTS)


if __name__ == '__main__':
    unittest.main()
