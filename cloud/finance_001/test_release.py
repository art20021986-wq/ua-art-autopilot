#!/usr/bin/env python3
"""Release checks: the candidate from the live files (fixtures read by FINANCE-PROBE and earlier probes)."""
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
CLOUD = HERE.parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_order  # noqa: E402
import logo_assets  # noqa: E402
import order_assets  # noqa: E402
import ua_finance_partners as finance  # noqa: E402

FIXTURES = HERE / 'fixtures'
# cars_ui.py in full, as CRM-CLIENTS-PROBE-20261030 read it (sanitized); FINANCE-PROBE read the clients screen lines.
CARS_UI = json.loads((CLOUD / 'crm_clients_probe_001' / '20261030.json').read_text())['files']['cars_ui.py']['source'].encode()


def live():
    names = {'ua_seo_landings.py': 'ua_seo_landings.txt', 'analitika_yadro.py': 'analitika_yadro.txt',
             edit_order.PAGE: 'podbor.html', edit_order.SCRIPT: 'order.js', edit_order.STRINGS: 'order-strings.json'}
    source = {name: (FIXTURES / fixture).read_bytes() for name, fixture in names.items()}
    source['cars_ui.py'] = CARS_UI
    return source


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = candidate_builder.build(live(), {})

    def test_planned_files(self):
        self.assertEqual(sorted(self.result), sorted([
            'ua_seo_landings.py', 'analitika_yadro.py', 'cars_ui.py', edit_order.PAGE, edit_order.SCRIPT,
            edit_order.STRINGS, 'ua_finance_partners.py', 'ua_seo_finance.py', 'ua_finance_crm.py',
            'video/order/finance-link.css', 'video/finance/hapai-lizing.png']))
        for name, value in self.result.items():
            if name.endswith('.py') and name != 'cars_ui.py':  # the cars_ui fixture is sanitized (redacted lines)
                compile(value, name, 'exec')
        cars_ui = self.result['cars_ui.py'].decode()
        self.assertEqual(cars_ui.count('ua_finance_crm.BUTTON'), 1)
        self.assertLess(cars_ui.index('ua_finance_crm.BUTTON'), cars_ui.index('rows.append([InlineKeyboardButton("Заявки из бота"'))

    def test_order_page(self):
        script = self.result[edit_order.SCRIPT].decode()
        self.assertNotIn("t('calculate')", script)
        self.assertIn("node('a',t('finance'),'button finance-link')", script)
        self.assertIn("selectModel('')", script)  # the other-car form keeps its way in
        strings = json.loads(self.result[edit_order.STRINGS])
        for lang in ('uk', 'ru', 'ka'):
            self.assertEqual(strings[lang]['finance'], finance.BUTTON[lang])
            self.assertEqual(strings[lang]['finance_href'], finance.page_path(lang))
            self.assertNotIn('calculate', strings[lang])
        page = self.result[edit_order.PAGE].decode()
        self.assertIn(edit_order.CHECK_PAGE, page)
        self.assertIn('order/order.js?v=' + edit_order.VERSION, page)
        with self.assertRaisesRegex(ValueError, 'ORDER_'):
            edit_order.build(edit_order.SCRIPT, self.result[edit_order.SCRIPT])

    def test_logo_is_a_png_of_the_declared_size(self):
        data = logo_assets.FILES['video/finance/hapai-lizing.png']
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        width, height = int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
        self.assertEqual((width, height), finance.partner('hapai-leasing')['logo_size'])
        self.assertEqual(finance.partner('hapai-leasing')['logo'], '/video/finance/hapai-lizing.png')

    def test_link_style_targets_only_the_new_link(self):
        css = order_assets.FILES['video/order/finance-link.css']
        self.assertIn('.finance-link', css)
        self.assertIn('button.quick-offer:only-of-type', css)


if __name__ == '__main__':
    unittest.main()
