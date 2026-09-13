import json
from pathlib import Path
import unittest

from price_captions import price_caption


class PriceCaptionTests(unittest.TestCase):
    def test_russian_captions_match_owner_confirmation(self):
        self.assertEqual(price_caption("ukraine"), "Украина — с растаможкой в Украине")
        self.assertEqual(price_caption("georgia"), "Грузия — с доставкой до авторынка AUTOPAPA, паркинг №16; без растаможки в Грузии")

    def test_ukrainian_captions_and_site_language_alias(self):
        for language in ("uk", "ua"):
            self.assertEqual(price_caption("ukraine", language), "Україна — з розмитненням в Україні")
            self.assertEqual(price_caption("georgia", language), "Грузія — з доставкою до авторинку AUTOPAPA, паркінг №16; без розмитнення в Грузії")

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
            for unconfirmed in ("доплат нет", "под ключ", "сертификация включена"):
                self.assertNotIn(unconfirmed, caption)
        self.assertNotIn("достав", price_caption("ukraine").lower())

        contract = json.loads(Path(__file__).with_name("owner_decisions.json").read_text())
        rules = contract["pricing"]
        self.assertIs(rules["georgia_delivery_included"], True)
        self.assertIs(rules["georgia_customs_included"], False)
        self.assertEqual(rules["georgia_delivery_destination"]["market"], "AUTOPAPA")
        self.assertEqual(rules["georgia_delivery_destination"]["parking_number"], 16)
        self.assertEqual(set(rules["georgia_delivery_confirmation_does_not_imply"]),
                         {"storage_fees_included", "parking_fees_included", "storage_duration", "onward_delivery_to_ukraine"})
        for language, delivery, parking, customs in (
            ("ru", "с доставкой до авторынка AUTOPAPA", "паркинг №16", "без растаможки в Грузии"),
            ("uk", "з доставкою до авторинку AUTOPAPA", "паркінг №16", "без розмитнення в Грузії"),
        ):
            caption = price_caption("georgia", language)
            self.assertIn(delivery, caption)
            self.assertIn(parking, caption)
            self.assertIn(customs, caption)
            self.assertNotIn("AUTOPAPA", price_caption("ukraine", language))


if __name__ == "__main__":
    unittest.main()
