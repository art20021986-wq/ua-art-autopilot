"""KOREA-OFFER-001 edit against a copy of the live korea.html (2026-11-25)."""
from pathlib import Path
import unittest

import candidate_builder
import offer

F = Path(__file__).resolve().parent / 'fixtures'


class OfferTests(unittest.TestCase):
    def test_one_block_after_main_and_nothing_else(self):
        before = (F / 'korea_live.html').read_text(encoding='utf-8')
        after = offer.build(before.encode()).decode()
        self.assertEqual(after.replace(offer.block(), '', 1), before)
        self.assertIn(offer.ANCHOR + offer.block(), after)
        block = offer.block()
        for lang in ('uk', 'ru', 'ka'):
            self.assertIn('data-%s="%s"' % (lang, offer.TEXT[lang]), block)
            self.assertIn('data-%s="%s"' % (lang, offer.BUTTON[lang]), block)
        # The button opens the existing short lead form like the lot buttons do.
        self.assertIn('data-quick-lead-auction="korea"', block)
        with self.assertRaisesRegex(ValueError, 'OFFER_ALREADY_THERE'):
            offer.build(after.encode())

    def test_layout_checked(self):
        with self.assertRaisesRegex(ValueError, 'KOREA_LAYOUT'):
            offer.build(b'<html><main id="main-content"></main></html>')

    def test_builder_touches_only_korea(self):
        source = {offer.NAME: (F / 'korea_live.html').read_bytes()}
        self.assertEqual(set(candidate_builder.build(source)), {offer.NAME})
        self.assertEqual(candidate_builder.targets(None), (offer.NAME,))
        with self.assertRaisesRegex(ValueError, 'UNPLANNED'):
            candidate_builder.build({'video/index.html': b'x'})


if __name__ == '__main__':
    unittest.main()
