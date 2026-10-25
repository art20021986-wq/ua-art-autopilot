#!/usr/bin/env python3
import base64
import json
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_home as b  # noqa: E402

LIVE = json.loads((HERE/'live_home.json').read_text())
SOURCE = base64.b64decode(LIVE['files'][LIVE['home']]['b64'])


class BuildTests(unittest.TestCase):
    def test_layout(self):
        old, new = SOURCE.decode(), b.build(SOURCE).decode()
        self.assertEqual(new.count('<h1'), 1)
        self.assertNotIn('order-feature', new)
        self.assertLess(new.index('<section class="hero ua-order-first'), new.index('<section class="confidence-strip'))
        self.assertLess(new.index('<section class="confidence-strip'), new.index('<section class="ua-how'))
        self.assertLess(new.index('<section class="ua-how'), new.index('id="stages"'))
        self.assertEqual(new.count('data-order-country='), 8)
        self.assertIn(b.TELEGRAM, new)
        self.assertIn(b.VIBER, new)

    def test_kept(self):
        old, new = SOURCE.decode(), b.build(SOURCE).decode()
        stages = re.compile(r'<section id="stages".*?</section>', re.S)
        self.assertEqual(stages.search(old).group(), stages.search(new).group())
        self.assertEqual(old[:old.index('</head>')], new[:new.index('<style id="%s">' % b.MARK)])
        self.assertEqual(old[old.index('</main>'):], new[new.index('</main>'):])

    def test_once(self):
        with self.assertRaises(ValueError):
            b.build(b.build(SOURCE))


if __name__ == '__main__':
    unittest.main()
