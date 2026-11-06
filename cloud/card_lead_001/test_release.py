#!/usr/bin/env python3
"""LEAD-FOLDERS-001 card button: the candidate built from the live sources (fixtures: the probe's sanitized copies)."""
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
import hashlib

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import card_lead_assets  # noqa: E402
import edit_generators  # noqa: E402
import edit_metadata  # noqa: E402

FILES = {'stranica.py': 'stranica.txt', 'master_card.py': 'master_card.txt', 'ua_seo_metadata.py': 'ua_seo_metadata.txt',
         'ua_order/contract.py': 'ua_order/contract.py', 'ua_order/crm.py': 'ua_order/crm.py',
         'video/order/quick-lead.js': 'quick-lead.js'}


def stubbed(text):
    """The probe replaced credential-like lines with [REDACTED]; compile them as `pass` at their indentation."""
    lines = text.split('\n')
    for index, line in enumerate(lines):
        if line.strip() == '[REDACTED]':
            following = next(item for item in lines[index + 1:] if item.strip())
            lines[index] = following[:len(following) - len(following.lstrip())] + 'pass'
    return '\n'.join(lines)


class CandidateTests(unittest.TestCase):
    def build(self):
        source = {name: (FIXTURES / path).read_bytes() for name, path in FILES.items()}
        pins = {name: hashlib.sha256(value).hexdigest() for name, value in source.items()}
        with patch.dict(candidate_builder.SOURCE_SHA256, pins), patch.dict(candidate_builder.DEPENDENCY_SHA256, clear=True):
            return candidate_builder.build(source, {})

    def test_files(self):
        result = self.build()
        self.assertEqual(sorted(result), sorted(list(FILES) + ['ua_card_contact.py', 'ua_order/card_lead.py']))
        for name, value in result.items():
            if name.endswith('.py'):
                compile(stubbed(value.decode()), name, 'exec')
        self.assertEqual(result['video/order/quick-lead.js'], card_lead_assets.JS.encode())
        self.assertIn("SEO_REVISION = 'CARD-CONTACT-001'", result['ua_seo_metadata.py'].decode())

    def test_generators_take_the_button_from_one_module(self):
        result = self.build()
        for name in edit_generators.NAMES:
            text = result[name].decode()
            self.assertNotIn('"Купить" if stage == 4 else "Задаток 500 $"', text)
            self.assertEqual(text.count("label = _ua_card_contact.LABEL['ru']"), 2)
            self.assertEqual(text.count('canonical = _ua_card_contact.button(stage, href, str(kod))'), 1)
            self.assertEqual(text.count('return _ua_card_contact.finish(source)'), 1)
            self.assertEqual(text.count('errors.extend(_ua_card_contact.errors(source))'), 1)
            # The stage and the bot address of the action stay as they were.
            self.assertIn('action = "kupit" if stage == 4 else "bron"', text)
            self.assertIn('if ("start=%s_%s" % (expected_action, kod)) not in node:', text)

    def test_edits_refused_twice(self):
        result = self.build()
        for name in edit_generators.NAMES:
            with self.assertRaises(ValueError):
                edit_generators.build(name, result[name])
        with self.assertRaises(ValueError):
            edit_metadata.build(result['ua_seo_metadata.py'])

    def test_wrong_source_refused(self):
        source = {name: (FIXTURES / path).read_bytes() for name, path in FILES.items()}
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build(source, {})

    def test_dialog_script_keeps_order_page_contract(self):
        js = card_lead_assets.JS
        live = (FIXTURES / 'quick-lead.js').read_text()
        for needle in ("'[data-quick-lead-model],[data-quick-lead-car]'", "'ua_order_request.card.v1'",
                       'payload.car_code = car', "fetch('/api/orders/submit'", "method: 'quick_form'"):
            self.assertIn(needle, js)
        # Everything the order page used stays.
        for needle in re.findall(r"form\.querySelector\('[^']+'\)", live):
            self.assertIn(needle, js)


if __name__ == '__main__':
    unittest.main()
