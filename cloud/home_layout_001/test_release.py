#!/usr/bin/env python3
"""Release-specific checks: planned files from the live home page and the owner's photo."""
import base64
import json
from pathlib import Path
import unittest

import candidate_builder
from release_constants import HOME, PHOTOS

HERE = Path(__file__).resolve().parent
LIVE = json.loads((HERE/'live_home.json').read_text())
SOURCE = base64.b64decode(LIVE['files'][LIVE['home']]['b64'])


class ReleaseTests(unittest.TestCase):
    def test_planned_files(self):
        result = candidate_builder.build({HOME: SOURCE}, {})
        self.assertEqual(sorted(result), sorted([HOME, *PHOTOS]))
        for name, asset in PHOTOS.items():
            self.assertEqual(result[name], (HERE/asset).read_bytes())
            self.assertEqual(result[name][8:12], b'WEBP')
        self.assertIn(b'class="hero ua-order-first"', result[HOME])
        for name in PHOTOS:
            self.assertIn(('/' + name).encode(), result[HOME])

    def test_changed_home_is_refused(self):
        with self.assertRaises(ValueError):
            candidate_builder.build({HOME: SOURCE.replace(b'order-feature', b'other')}, {})


if __name__ == '__main__':
    unittest.main()
