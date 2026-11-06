#!/usr/bin/env python3
"""The one «Связаться с менеджером» button on a live card page (fixture: /video/UA-0018.html as published)."""
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ua_card_contact as contact  # noqa: E402

LIVE = (HERE / 'fixtures/video/UA-0018.html').read_text(encoding='utf-8')
BOT = 'https://t.me/UA_artcompany_LLC_bot?start=kupit_UA-0018'


def published(source):
    """What the generators' primary-action step now does: the canonical button, then finish()."""
    source = contact.PRIMARY.sub(lambda m: contact.button(4, BOT, 'UA-0018'), source, count=1)
    return contact.finish(source)


class CardContact(unittest.TestCase):
    def test_live_card_has_old_buttons(self):
        self.assertTrue(contact.QUESTION.search(LIVE) and contact.OLD_SCRIPT.search(LIVE))
        self.assertIn('contact dialog != 1', contact.errors(LIVE))

    def test_one_button_one_dialog(self):
        page = published(LIVE)
        self.assertEqual(contact.errors(page), [])
        button = contact.PRIMARY.search(page).group(0)
        self.assertIn('data-quick-lead-car="UA-0018"', button)
        self.assertIn('start=kupit_UA-0018', button)  # without JavaScript the address still reaches the manager
        self.assertEqual(re.sub(r'<[^>]+>', '', button), 'Связаться с менеджером')
        self.assertNotIn('Задать вопрос по этой машине', page)
        self.assertNotIn('cta-note', page)
        self.assertIn('id="ua-finance-link"', page)  # the finance link stays
        self.assertLess(page.index('<!--ua-card-contact-v1-->'), page.lower().rindex('</body>'))

    def test_idempotent(self):
        page = published(LIVE)
        self.assertEqual(contact.finish(page), page)
        self.assertEqual(published(page), page)

    def test_page_without_button_unchanged(self):
        self.assertEqual(contact.finish('<html><body>x</body></html>'), '<html><body>x</body></html>')

    def test_every_text_translated(self):
        page = published(LIVE)
        block = page[page.index('<!--ua-card-contact-v1-->'):]
        for node in re.finditer(r'<(span|button|a|p)\b([^>]*)>([^<]+)</\1>', block):
            if node.group(3).strip():
                self.assertIn('data-uk="', node.group(2), node.group(0))
        self.assertIn('data-uk="Зв&#x27;язатися з менеджером"', contact.PRIMARY.search(page).group(0))

    def test_dialog_matches_script_contract(self):
        page = published(LIVE)
        for needle in ('form class="ua-quick" data-ua-quick-lead', 'data-fields', 'data-status', 'data-consent',
                       'data-quick-close', 'data-quick-model-title', 'name="customer_name"', 'name="phone"',
                       'data-msg="ok"', 'data-msg="error"', 'data-msg="bad_phone"', 'data-msg="bad_name"',
                       '/video/order/quick-lead.js?v=', '/video/order/attribution.js?v=', '/video/order/quick-lead.css?v='):
            self.assertIn(needle, page)


if __name__ == '__main__':
    unittest.main()
