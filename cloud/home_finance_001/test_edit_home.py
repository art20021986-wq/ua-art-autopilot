"""The home «Кредит і лізинг» block: placement, texts, links, logos; nothing else on the page changes."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

import edit_home
import finance_block
import finance_text as T

LIVE = (Path(__file__).resolve().parent/'fixtures'/'index_live.html').read_bytes()


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


class HomeFinanceTests(unittest.TestCase):
    def setUp(self):
        self.before = LIVE.decode('utf-8')
        self.after = edit_home.build(LIVE).decode('utf-8')

    def test_block_right_above_the_steps(self):
        block = finance_block.section()
        self.assertEqual(self.after.count(block), 1)
        self.assertIn(block + edit_home.STEPS, self.after)
        self.assertEqual(self.after.count(edit_home.CHECK), 1)

    def test_every_other_byte_stays(self):
        restored = self.after.replace(finance_block.section(), '', 1).replace(finance_block.CSS, '', 1)
        self.assertEqual(restored, self.before)

    def test_css_once_in_head(self):
        head = self.after[:self.after.index('</head>')]
        self.assertEqual(head.count(finance_block.CSS), 1)
        self.assertEqual(self.after.count('id="%s"' % finance_block.MARK), 1)

    def test_otp_advantage_on_the_way_or_under_order(self):
        otp = T.CARDS[0]
        self.assertEqual(otp['key'], 'otp')
        self.assertIn('в дорозі або під замовлення', otp['main'][1])
        self.assertIn('в пути или под заказ', otp['main'][0])
        self.assertIn('OTP', otp['badge'][1])
        block = finance_block.section()
        for words in (otp['badge'], otp['main']):
            self.assertIn('data-ru="%s" data-uk="%s" data-ka="%s">%s<' % (words + (words[1],)), block)

    def test_cards_open_their_section_with_logo(self):
        parser = Elements()
        parser.feed(finance_block.section())
        links = [a for tag, a in parser.items if tag == 'a']
        self.assertEqual([a['href'] for a in links],
                         [T.PAGE + '#kredyt', T.PAGE + '#lizynh'])
        logos = [a for tag, a in parser.items if tag == 'img']
        self.assertEqual([a['src'] for a in logos], ['/video/finance/otp-bank.png', '/video/finance/hapai-lizing.png'])
        for logo in logos:
            self.assertEqual(logo['translate'], 'no')
            self.assertTrue(logo['alt'] and logo['width'] and logo['height'])

    def test_every_text_has_three_languages(self):
        parser = Elements()
        parser.feed(finance_block.section())
        texts = [a for _, a in parser.items if 'data-uk' in a]
        self.assertEqual(len(texts), 2 + 4 + 3)
        for attrs in texts:
            self.assertTrue(attrs['data-ru'] and attrs['data-uk'] and attrs['data-ka'])

    def test_unsafe_text_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'HOME_FINANCE_TEXT'):
            finance_block.text('b', ('a', '<b>', 'c'))

    def test_already_live_or_missing_anchor_changes_nothing(self):
        with self.assertRaisesRegex(ValueError, 'HOME_FINANCE_ANCHOR'):
            edit_home.build(self.after.encode('utf-8'))
        with self.assertRaisesRegex(ValueError, 'HOME_FINANCE_ANCHOR'):
            edit_home.build(LIVE.replace(edit_home.STEPS.encode(), b'<section>'))
        with self.assertRaisesRegex(ValueError, 'HOME_FINANCE_ANCHOR'):
            edit_home.build(LIVE + edit_home.STEPS.encode())


if __name__ == '__main__':
    unittest.main()
