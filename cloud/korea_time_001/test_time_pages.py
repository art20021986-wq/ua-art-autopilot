"""KOREA-TIME-001 page edits on the pages as KOREA-LOTS-FULL-001 installs them (fixtures: its rendered files)."""
from pathlib import Path
import json
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import time_pages as tp  # noqa: E402

FIXTURES = {tp.KOREA: 'korea_live.html', tp.ORDER: 'order_js_lots_full.txt',
            tp.STRINGS: 'order_strings_lots_full.txt', tp.PODBOR: 'podbor_script_tag.txt'}


def page(name):
    return (HERE / 'fixtures' / FIXTURES[name]).read_text(encoding='utf-8')


def undo(name, text):
    for old, new in tp.EDITS[name]:
        text = text.replace(new, old)
    return text


class KoreaPageTests(unittest.TestCase):
    def test_list_card_and_lot_card_get_korea_and_kyiv(self):
        after = tp.build(tp.KOREA, page(tp.KOREA))
        self.assertNotIn('(час Кореї)', after)
        self.assertIn('["Корея","Київ"],["Корея","Киев"],["კორეა","კიევი"]', after)
        self.assertIn('slice(11,16)+zones(s,i);', after)
        self.assertIn('slice(11,16)+zones(l.auction_start,i);', after)
        self.assertEqual(undo(tp.KOREA, after), page(tp.KOREA))  # nothing else changes


class OrderPageTests(unittest.TestCase):
    def test_carousel_strip_gets_korea_and_kyiv(self):
        after = tp.build(tp.ORDER, page(tp.ORDER))
        self.assertIn("${lot.date}`+auctionTime(lot.start)+", after)
        self.assertEqual(after.count('function auctionTime('), 1)
        self.assertEqual(undo(tp.ORDER, after), page(tp.ORDER))

    def test_strings_in_three_languages(self):
        after = json.loads(tp.build(tp.STRINGS, page(tp.STRINGS)))
        self.assertEqual([after[l]['auction_korea'] for l in ('uk', 'ru', 'ka')], ['Корея', 'Корея', 'კორეა'])
        self.assertEqual([after[l]['auction_kyiv'] for l in ('uk', 'ru', 'ka')], ['Київ', 'Киев', 'კიევი'])

    def test_order_page_loads_the_new_script(self):
        after = tp.build(tp.PODBOR, page(tp.PODBOR))
        self.assertIn('order/order.js?v=' + tp.VERSION, after)
        self.assertEqual(after.count('order/order.js?v='), 1)


class RefusalTests(unittest.TestCase):
    def test_applied_twice_is_refused(self):
        for name in tp.FILES:
            with self.assertRaises(ValueError):
                tp.build(name, tp.build(name, page(name)))

    def test_changed_page_is_refused(self):
        with self.assertRaises(ValueError):
            tp.build(tp.KOREA, page(tp.KOREA).replace('function tri(f){', ''))
        with self.assertRaises(ValueError):
            tp.build(tp.ORDER, page(tp.ORDER).replace('${lot.date}', '${lot.day}'))


if __name__ == '__main__':
    unittest.main()
