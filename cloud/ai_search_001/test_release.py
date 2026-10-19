#!/usr/bin/env python3
"""Release-specific checks: exact installed inputs, planned files, home page edit."""
import hashlib
import json
from pathlib import Path
import unittest

import build_home
import candidate_builder
import ua_indexnow

HERE = Path(__file__).resolve().parent
HOME = json.loads((HERE.parent / 'ai_search_source_probe_20261019/public_pages.json').read_text())['/video/index.html']['body'].encode()


def installed():
    return {name: (HERE.parent / 'seo_growth_001' / name).read_bytes() for name in candidate_builder.SOURCE_SHA256}


class ReleaseTests(unittest.TestCase):
    def test_pins_match_probe_and_previous_release(self):
        probe = json.loads((HERE.parent / 'ai_search_source_probe_20261019/evidence.json').read_text())['modules']
        for name, digest in candidate_builder.SOURCE_SHA256.items():
            self.assertEqual(probe[name]['sha256'], digest)
            self.assertEqual(hashlib.sha256(installed()[name]).hexdigest(), digest)

    def test_builder_refuses_unexpected_inputs(self):
        with self.assertRaises(ValueError):
            candidate_builder.build({**installed(), 'ua_seo_index.py': b'other', 'video/index.html': HOME}, {})

    def test_planned_files(self):
        result = candidate_builder.build({**installed(), 'video/index.html': HOME}, {})
        self.assertEqual(sorted(result), sorted(['ua_indexnow.py', 'ua_seo_landings.py', 'ua_seo_schema.py',
                                                 'ua_seo_index.py', ua_indexnow.KEY_FILE, 'video/index.html']))
        self.assertEqual(result[ua_indexnow.KEY_FILE], ua_indexnow.KEY.encode())
        for name in ('ua_indexnow.py', 'ua_seo_landings.py', 'ua_seo_schema.py', 'ua_seo_index.py'):
            compile(result[name], name, 'exec')

    def test_home_only_gains_one_schema_block(self):
        after = build_home.build(HOME)
        block = after[HOME.index(b'</head>'):after.index(b'</head>')]
        self.assertEqual(after.replace(block, b''), HOME)
        data = json.loads(block[block.index(b'>') + 1:block.rindex(b'</script>')])
        dealer = data['@graph'][0]
        self.assertEqual((dealer['@type'], dealer['telephone'], dealer['address']['streetAddress']),
                         ('AutoDealer', '+380992222002', 'вул. Перемоги, 20'))
        self.assertEqual(build_home.build(after), after)

    def test_home_with_foreign_schema_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'HOME_HEAD'):
            build_home.build(HOME.replace(b'</head>', b'<script type="application/ld+json">{}</script></head>'))


if __name__ == '__main__':
    unittest.main()
