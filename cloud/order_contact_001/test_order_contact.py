"""Messenger last, then review; thank-you text: exact edits of the order page, script, form module and strings."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_contact_form as form  # noqa: E402
import edit_order_page as page  # noqa: E402
from release_constants import FORM, PAGE, SCRIPT, STRINGS  # noqa: E402

PROBES = HERE.parent / 'lead_desk_probe_001'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_sources():
    """Live files as installed by MAKE-SEARCH-INSTALL-20261106 and ORDER-FORM-INSTALL-20261105 (on sanitized probe copies)."""
    live = json.loads((PROBES / '20261106.json').read_text())['files']
    r3 = json.loads((PROBES / '20261105-R3.json').read_text())['files']
    search = HERE.parent / 'make_search_001'
    search_page = load(search / 'edit_order_page.py', 'search_page')
    sys.path.insert(0, str(search))
    search_form = load(search / 'edit_preferences_form.py', 'search_form')
    order_form = load(HERE.parent / 'order_form_001' / 'edit_order_page.py', 'order_form_page')
    return {PAGE: search_page.build(PAGE, live[PAGE]['source'].encode()),
            SCRIPT: search_page.build(SCRIPT, r3[SCRIPT]['source'].encode()),
            FORM: search_form.build(live[FORM]['source'].encode()),
            STRINGS: order_form.build(STRINGS, r3[STRINGS]['source'].encode())}


SOURCES = live_sources()


class OrderContactTests(unittest.TestCase):
    def setUp(self):
        self.result = {name: value.decode() for name, value in candidate_builder.build(SOURCES, {}).items()}

    def test_page_contact_container_after_consent_and_before_submit(self):
        html = self.result[PAGE]
        self.assertEqual(html.count(page.CHECK_PAGE), 1)
        self.assertLess(html.index('name="consent"'), html.index('id="contact-fields"'))
        self.assertLess(html.index('id="contact-fields"'), html.index('<button type="submit" data-label="review">'))
        self.assertIn('order/order.js?v=20261106.2', html)

    def test_receipt_thanks_number_and_reply_time(self):
        html = self.result[PAGE]
        self.assertIn('<h2 data-label="thanks">Дякуємо! Вашу заявку отримано</h2>', html)
        self.assertIn('<p>№ <span id="number"></span></p>', html)
        self.assertIn('data-label="reply_time">Ми зв\'яжемося з вами найближчим часом', html)
        self.assertEqual(html.count('id="number"'), 1)

    def test_strings_stay_valid_json_with_three_languages(self):
        data, before = json.loads(self.result[STRINGS]), json.loads(SOURCES[STRINGS])
        for lang in ('uk', 'ru', 'ka'):
            self.assertEqual(data[lang]['thanks'], page.THANKS[lang])
            self.assertEqual(data[lang]['reply_time'], page.REPLY[lang])
            self.assertIn('3', data[lang]['reply_time'])
            data[lang].pop('thanks')
            data[lang].pop('reply_time')
        self.assertEqual(data, before)

    def test_script_passes_container_and_submits_on_messenger(self):
        js = self.result[SCRIPT]
        self.assertIn("persist,$('contact-fields'));", js)
        self.assertIn("if(event.target.name==='contact_method'&&event.target.value)form.requestSubmit();", js)
        self.assertIn("./preferences-form.js?v=20261106.2'", js)

    def test_form_renders_contact_last_with_messenger_after_phone(self):
        js = self.result[FORM]
        self.assertIn(form.CHECK, js)
        self.assertNotIn("'customer_name','contact'];", js)
        self.assertIn("box.append(input,note,method);", js)
        self.assertIn("const method=this.label('contact_method',", js)

    def test_applied_edit_is_refused(self):
        with self.assertRaises(ValueError):
            form.build(self.result[FORM].encode())
        for name in (PAGE, SCRIPT, STRINGS):
            with self.assertRaises(ValueError):
                page.build(name, self.result[name].encode())


if __name__ == '__main__':
    unittest.main()
