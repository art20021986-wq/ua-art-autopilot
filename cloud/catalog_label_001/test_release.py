#!/usr/bin/env python3
"""Release-specific checks: the rare-car card label built from a catalogue in the live form (CATALOG-LABEL-PROBE)."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import candidate_builder
import deployment_controller as controller
import label

HERE = Path(__file__).resolve().parent
SOURCE = (HERE/'fixtures/country_models.json').read_bytes()


class ReleaseTests(unittest.TestCase):
    def test_only_the_card_texts_change(self):
        after = json.loads(candidate_builder.build({label.CATALOG: SOURCE}, {})[label.CATALOG])
        before = json.loads(SOURCE)
        card = label.card(after)
        self.assertEqual((card['name'], card['labels'], card['media']['alt']), (label.LABELS['uk'], label.LABELS, label.ALT))
        self.assertEqual(card['key'], 'classics-1980-1990')
        self.assertEqual(after['version'], before['version'])
        self.assertEqual(after['countries']['korea'], before['countries']['korea'])
        for text in label.LABELS.values():
            self.assertNotRegex(text, r'\d')

    def test_form_of_the_file_kept(self):
        result = candidate_builder.build({label.CATALOG: SOURCE}, {})[label.CATALOG].decode()
        self.assertEqual(len(result.splitlines()), len(SOURCE.decode().splitlines()))
        self.assertTrue(result.endswith('\n'))
        self.assertIn('"ru": "Раритетное авто",', result)

    def test_applied_or_changed_source_is_refused(self):
        result = candidate_builder.build({label.CATALOG: SOURCE}, {})[label.CATALOG]
        with self.assertRaises(ValueError):
            label.build(result)
        doubled = SOURCE.decode().replace('"country": "korea"', '"country": "korea", "uk": "Раритетні авто 1980-1990-х років"')
        with self.assertRaises(ValueError):
            label.build(doubled.encode())

    def test_live_labels_decide_the_reload(self):
        class API:
            def reload_webapp(self):
                pass
        with patch.object(controller, 'live_labels', return_value=label.LABELS):
            self.assertEqual(controller.reload_and_check(API(), label.LABELS), {'reload': 'PASS', 'labels': label.LABELS})

    def test_bundle_modules_fit(self):
        for path in HERE.glob('*.py'):
            self.assertLessEqual(path.stat().st_size, 1048576, path.name)
            # The server bootstrap unpacks only these names (deployment_bootstrap.py).
            self.assertRegex(path.name, r'^[a-z_]+\.py$')

    def test_server_paths_agree(self):
        # Upload, unpack and receipt use one package folder name on the server.
        bootstrap = (HERE/'deployment_bootstrap.py').read_text()
        transport = (HERE/'deployment_transport.py').read_text()
        self.assertIn("'cataloglabel-' + args.bundle", bootstrap)
        self.assertIn("INBOX+'/cataloglabel-'+bundle_sha+'/runs/'", transport)
        self.assertIn("INBOX+'/cataloglabel-'+digest+'.zip'", transport)
        self.assertIn("INBOX+'/cataloglabel_bootstrap.py'", transport)
        self.assertNotIn('modelcard-', bootstrap + transport)


if __name__ == '__main__':
    unittest.main()
