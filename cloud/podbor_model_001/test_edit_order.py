#!/usr/bin/env python3
"""The live order page files (PODBOR-PROBE-20261025-R3 copy) change only in the planned fragments."""
import base64
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import candidate_builder
import edit_order

HERE = Path(__file__).resolve().parent
LIVE = json.loads((HERE.parent/'podbor_probe_20261025/live_podbor_r3.json').read_text())['files']
URLS = {edit_order.PAGE: 'https://www.uaart.com.ua/video/podbor.html?strana=korea&lang=uk',
        edit_order.SCRIPT: 'https://www.uaart.com.ua/video/order/order.js?v=20261025.1',
        edit_order.STATE: 'https://www.uaart.com.ua/video/order/order-state.js'}
SOURCE = {name: base64.b64decode(LIVE[url]['b64']) for name, url in URLS.items()}


class EditTests(unittest.TestCase):
    def test_only_planned_fragments_change(self):
        result = candidate_builder.build(SOURCE, {})
        self.assertEqual(sorted(result), sorted(SOURCE))
        for name, after in result.items():
            restored = after.decode()
            for old, new in edit_order.EDITS[name]:
                restored = restored.replace(new, old)
            self.assertEqual(restored.encode(), SOURCE[name])

    def test_refuses_changed_files(self):
        for name in edit_order.EDITS:
            with self.assertRaises(ValueError):
                edit_order.build(name, edit_order.build(name, SOURCE[name]))

    def test_versions_match(self):
        page = edit_order.build(edit_order.PAGE, SOURCE[edit_order.PAGE]).decode()
        script = edit_order.build(edit_order.SCRIPT, SOURCE[edit_order.SCRIPT]).decode()
        self.assertIn('order/order.js?v=%s' % edit_order.VERSION, page)
        self.assertIn("from './order-state.js?v=%s';" % edit_order.VERSION, script)

    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_model_from_url(self):
        with tempfile.TemporaryDirectory() as temp:
            module = Path(temp)/'order-state.mjs'
            module.write_bytes(edit_order.build(edit_order.STATE, SOURCE[edit_order.STATE]))
            script = ("import {modelFromUrl} from %s;\n"
                      "const models=[{key:'hyundai-tucson'},{key:'kia-k5'}];\n"
                      "const base='https://www.uaart.com.ua/video/podbor.html?strana=korea&lang=uk';\n"
                      "console.log(JSON.stringify([modelFromUrl(base+'&model=hyundai-tucson',models),"
                      "modelFromUrl(base+'&model=audi-a6',models),modelFromUrl(base,models),"
                      "modelFromUrl(base+'&model=kia-k5',undefined)]));") % json.dumps(module.as_uri())
            output = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(output.stdout), ['hyundai-tucson', '', '', ''])


if __name__ == '__main__':
    unittest.main()
