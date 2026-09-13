import json
from pathlib import Path
import unittest

from price_captions import price_caption


class PriceCaptionTests(unittest.TestCase):
    def test_russian_captions_match_owner_confirmation(self):
        self.assertEqual(price_caption("ukraine"), "Украина — с растаможкой в Украине")
        self.assertEqual(price_caption("georgia"), "Грузия — без растаможки в Грузии")

    def test_ukrainian_captions_and_site_language_alias(self):
        for language in ("uk", "ua"):
            self.assertEqual(price_caption("ukraine", language), "Україна — з розмитненням в Україні")
            self.assertEqual(price_caption("georgia", language), "Грузія — без розмитнення в Грузії")

    def test_unknown_inputs_cannot_silently_pick_wrong_market(self):
        for market, language in (("", "ru"), ("russia", "ru"), ("ukraine", "xx"),
                                 (None, "ru"), ("georgia", True)):
            with self.subTest(market=market, language=language), self.assertRaises(ValueError):
                price_caption(market, language)

    def test_contract_matches_code_and_keeps_price_independence(self):
        contract = json.loads(Path(__file__).with_name("owner_decisions.json").read_text())
        rules = contract["pricing"]
        self.assertIs(rules["ukraine_customs_included"], True)
        self.assertIs(rules["georgia_customs_included"], False)
        self.assertIs(rules["keep_existing_ukrainian_prices"], True)
        self.assertIs(rules["independent_fields"], True)
        self.assertEqual((rules["currency_ukraine"], rules["currency_georgia"]), ("USD", "USD"))
        for market, caption in rules["customs_captions_ru"].items():
            self.assertEqual(price_caption(market), caption)

    def test_customs_confirmation_does_not_expand_price_promise(self):
        for market in ("ukraine", "georgia"):
            caption = price_caption(market).lower()
            for unconfirmed in ("доплат нет", "под ключ", "доставка включена", "сертификация включена"):
                self.assertNotIn(unconfirmed, caption)


if __name__ == "__main__":
    unittest.main()
