"""Make/model search: exact edits of the live order page, script and form module; the two new list files."""
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_order_page  # noqa: E402
import edit_preferences_form as form  # noqa: E402
import picker_assets  # noqa: E402
from release_constants import FORM, PAGE, PICKER_CSS, PICKER_JS, SCRIPT  # noqa: E402

# Live sources read by LEAD-DESK-PROBE-20261106 (page, form) and LEAD-DESK-PROBE-20261105-R3 (script); sanitized copies.
PROBES = HERE.parent / 'lead_desk_probe_001'
LIVE = json.loads((PROBES / '20261106.json').read_text())['files']
R3 = json.loads((PROBES / '20261105-R3.json').read_text())['files']
SOURCES = {PAGE: LIVE[PAGE]['source'].encode(), FORM: LIVE[FORM]['source'].encode(), SCRIPT: R3[SCRIPT]['source'].encode()}


class MakeSearchTests(unittest.TestCase):
    def setUp(self):
        self.result = {name: value.decode() for name, value in candidate_builder.build(SOURCES, {}).items()}

    def test_candidate_files(self):
        self.assertEqual(set(self.result), {PAGE, SCRIPT, FORM, PICKER_JS, PICKER_CSS})

    def test_page_links_styles_and_new_script_version(self):
        html = self.result[PAGE]
        self.assertEqual(html.count(edit_order_page.CHECK_PAGE), 1)
        self.assertIn('order/order.js?v=20261106.1', html)
        self.assertNotIn('order/order.js?v=20261105.1', html)
        self.assertLess(html.index('search-picker.css'), html.index('order/order.js'))

    def test_script_only_changes_the_form_module_version(self):
        before, after = SOURCES[SCRIPT].decode().splitlines(), self.result[SCRIPT].splitlines()
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertEqual(len(before), len(after))
        self.assertEqual(changed, [("import {PreferenceForm} from './preferences-form.js?v=20260927.10';",
                                    "import {PreferenceForm} from './preferences-form.js?v=20261106.1';")])

    def test_form_uses_the_list_for_make_and_models(self):
        js = self.result[FORM]
        self.assertEqual(js.count(form.CHECK), 1)
        self.assertIn("this.picker(key,v.make,", js)
        self.assertIn("row.select=this.picker(", js)
        # The separate «Як обрати модель» select is gone; «Інша модель» is the bottom entry of the model list.
        self.assertNotIn("this.select('model_mode'", js)
        self.assertIn("otherModelChoice(){return [['other',this.t('other_model')]];}", js)
        self.assertIn("document.getElementById('pref-other_model')?.focus();", js)
        # Field errors also mark and focus the list button.
        self.assertEqual(js.count("'select,input,textarea,.search-picker'"), 2)

    def test_mileage_presets_read_up_to(self):
        js = self.result[FORM]
        self.assertIn("{extra:{any:this.t('any')},prefix:this.t('to')}", js)
        self.assertIn("(prefix?prefix+' ':'')+Number(x).toLocaleString(", js)
        # Budget, year and engine presets keep their plain numbers.
        self.assertEqual(js.count('prefix:this.t('), 1)

    def test_list_files_are_self_contained(self):
        for text in (picker_assets.JS, picker_assets.CSS):
            self.assertNotIn('http', text)
            self.assertNotIn('import ', text)
        self.assertIn('export function searchPicker(', picker_assets.JS)
        self.assertIn("type:'search'", picker_assets.JS)
        self.assertIn('dialog.showModal()', picker_assets.JS)
        for selector in ('.ua-order .search-picker{', '.ua-order .search-picker-dialog{', '.search-picker-pinned{'):
            self.assertIn(selector, picker_assets.CSS)

    def test_applied_edit_is_refused(self):
        with self.assertRaises(ValueError):
            form.build(self.result[FORM].encode())
        with self.assertRaises(ValueError):
            edit_order_page.build(PAGE, self.result[PAGE].encode())


if __name__ == '__main__':
    unittest.main()
