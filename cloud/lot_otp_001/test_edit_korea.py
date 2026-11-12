"""The OTP credit line in the Korea lot window: only a style and a script are added; texts, link, no list change."""
import json
from pathlib import Path
import re
import unittest

import edit_korea
import lot_otp

LIVE = (Path(__file__).resolve().parent/'fixtures'/'korea_live.html').read_bytes()


class LotOtpTests(unittest.TestCase):
    def setUp(self):
        self.before = LIVE.decode('utf-8')
        self.after = edit_korea.build(LIVE).decode('utf-8')

    def test_every_other_byte_stays(self):
        self.assertEqual(self.after.replace(lot_otp.CSS, '', 1).replace(lot_otp.SCRIPT, '', 1), self.before)

    def test_style_in_head_script_at_body_end(self):
        head, body = self.after.split('</head>')
        self.assertIn(lot_otp.CSS, head)
        self.assertTrue(body.rstrip().endswith(lot_otp.SCRIPT + '</body></html>') or
                        (lot_otp.SCRIPT + '</body>') in body)
        self.assertEqual(self.after.count(edit_korea.CHECK), 1)

    def test_owner_text_in_three_languages(self):
        self.assertEqual(lot_otp.TEXT['uk'], 'Перевага OTP: кредит на авто з аукціону або в дорозі')
        self.assertIn('с аукциона или в пути', lot_otp.TEXT['ru'])
        self.assertTrue(lot_otp.TEXT['ka'])

    def test_script_only_touches_the_lot_window(self):
        script = lot_otp.SCRIPT
        self.assertIn('getElementById("kl-card-body")', script)
        self.assertNotIn('kl-item', script)  # the lot list and search stay as they are
        self.assertNotIn('</', script[:-len('</script>')])

    def test_links_to_the_credit_section(self):
        self.assertEqual(lot_otp.PAGE['uk'], '/video/seo/ua/kredyt-lizynh-avto.html#kredyt')
        self.assertEqual(lot_otp.PAGE['ru'], '/video/seo/ru/kredit-lizing-avto.html#kredyt')
        line = json.loads(re.search(r'LINE=("(?:[^"\\]|\\.)*")', lot_otp.SCRIPT).group(1))
        self.assertIn('src="/video/finance/otp-bank.png"', line)
        self.assertIn('translate="no"', line)
        self.assertIn('data-ru="%s"' % lot_otp.TEXT['ru'], line)

    def test_already_live_or_unknown_page_changes_nothing(self):
        for page in (self.after.encode('utf-8'), LIVE.replace(edit_korea.WINDOW.encode(), b''),
                     LIVE + b'</body>'):
            with self.assertRaisesRegex(ValueError, 'LOT_OTP_ANCHOR'):
                edit_korea.build(page)


if __name__ == '__main__':
    unittest.main()
