#!/usr/bin/env python3
"""MAPS-LINK-001: what is replaced, and that nothing else changes."""
import json
from pathlib import Path
import tempfile
import unittest

import candidate_builder as builder

HERE = Path(__file__).resolve().parent
PROBE = json.loads((HERE.parent/'card_lang_probe_001'/'20261031.json').read_text())['maps']


class ReleaseTests(unittest.TestCase):
    def test_old_link_is_the_one_the_probe_found_everywhere(self):
        counts = {}
        for links in PROBE.values():
            for url, n in links.items():
                counts[url] = counts.get(url, 0) + n
        self.assertEqual(max(counts, key=counts.get), builder.OLD)
        for name in builder.MODULES:
            self.assertIn(builder.OLD, PROBE[name], name)
        self.assertNotIn('?', builder.NEW)  # the share parameter is not part of the address

    def test_targets_and_exact_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('video', 'site'):
                (root/name).mkdir()
            for name in builder.MODULES:
                (root/name).write_text("MAP = '%s'\n" % builder.OLD if name != 'yadro.py' else 'x = 1\n')
            (root/'video/index.html').write_text('<a href="%s">Офіс</a> <a href="%s">2</a>' % (builder.OLD, builder.OLD))
            (root/'site/UA-0013.html').write_text('<a href="%s">x</a>' % builder.OLD)
            (root/'video/proba-index.html').write_text(builder.OLD)
            (root/'video/other.html').write_text('<p>no link</p>')
            names = builder.targets(root)
            source = {name: (root/name).read_bytes() for name in names}
        self.assertEqual(names, ('ua_seo_schema.py', 'card_html.py', 'stranica_klienta.py', 'client_ui.py',
                                 'site/UA-0013.html', 'video/index.html'))
        result = builder.build(source, {})
        self.assertEqual(result['video/index.html'].decode(),
                         '<a href="%s">Офіс</a> <a href="%s">2</a>' % (builder.NEW, builder.NEW))
        for name, value in result.items():
            self.assertEqual(value.replace(builder.NEW.encode(), builder.OLD.encode()), source[name])
        with self.assertRaises(ValueError):
            builder.build({'video/index.html': result['video/index.html']}, {})


if __name__ == '__main__':
    unittest.main()
