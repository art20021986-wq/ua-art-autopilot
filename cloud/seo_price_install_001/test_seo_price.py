import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metadata_tail  # noqa: E402
import ua_seo_price  # noqa: E402

BLOCK = '<div data-ua-market="ukraine" data-ua-field="price_uah" data-ua-value="19900" data-ua-currency="USD">'
RAW = '<html><head><title>Audi</title></head><body><div class="cena">19 900 $</div></body></html>'
METADATA = ("import re\n"
            "def card_facts(doc, source, name):\n"
            "    price = re.search(r'data-ua-value=\"([0-9]+)', source)\n"
            "    return {'name': name, 'price_usd': int(price.group(1)) if price else None}\n"
            "def normalize(source, name):\n"
            "    return 'T %s' % card_facts(None, source, name)['price_usd']\n")


class PriceTest(unittest.TestCase):
    def test_block_in_page(self):
        self.assertEqual(ua_seo_price.price_usd(RAW + BLOCK, render=lambda s: 1 / 0), 19900)

    def test_rendered_block(self):
        self.assertEqual(ua_seo_price.price_usd(RAW, render=lambda s: s + BLOCK), 19900)

    def test_no_price(self):
        self.assertIsNone(ua_seo_price.price_usd(RAW, render=lambda s: s))
        self.assertIsNone(ua_seo_price.price_usd(RAW, render=lambda s: 1 / 0))
        self.assertIsNone(ua_seo_price.price_usd(RAW + BLOCK.replace('19900', '0'), render=lambda s: s))


class TailTest(unittest.TestCase):
    def module(self, code):
        module = types.ModuleType('ua_seo_metadata_test')
        exec(compile(code, 'ua_seo_metadata.py', 'exec'), module.__dict__)
        return module

    def test_normalize_gets_price_before_block(self):
        fake = types.ModuleType('ua_price_html_v2')
        fake.render = lambda s: s + BLOCK
        sys.modules['ua_price_html_v2'] = fake
        self.addCleanup(sys.modules.pop, 'ua_price_html_v2')
        before = self.module(METADATA)
        after = self.module(metadata_tail.build(METADATA.encode()).decode())
        self.assertEqual(before.normalize(RAW, 'UA-0017.html'), 'T None')
        self.assertEqual(after.normalize(RAW, 'UA-0017.html'), 'T 19900')
        self.assertEqual(after.normalize(RAW + BLOCK.replace('19900', '18000'), 'UA-0017.html'), 'T 18000')

    def test_refused_twice_or_unknown(self):
        once = metadata_tail.build(METADATA.encode())
        with self.assertRaises(ValueError):
            metadata_tail.build(once)
        with self.assertRaises(ValueError):
            metadata_tail.build(b'def other(): pass\n')


if __name__ == '__main__':
    unittest.main()
