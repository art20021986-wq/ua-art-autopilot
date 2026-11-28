"""video/usa.html with the IAAI lot list, from the live video/usa.html and video/japan.html (USA-PAGE-001)."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import usa_page  # noqa: E402

USA = (HERE / 'fixtures' / 'usa_live.html').read_bytes()
JAPAN = (HERE / 'fixtures' / 'japan_live.html').read_bytes()


class UsaPageTests(unittest.TestCase):
    def setUp(self):
        self.page = usa_page.build(USA, JAPAN).decode('utf-8')

    def test_usa_list_texts_and_card(self):
        for piece in ('Зараз на торгах у США', 'Ціни — на аукціоні IAAI. Ваша ціна під ключ — у менеджера.',
                      'Сейчас на торгах в США', 'fetch("/video/usa/lots.json"', "fetch('/video/usa/gallery/'",
                      '"ціна — за запитом", "цена — по запросу"', '"купити зараз"', '"на ходу"', 'сліди граду',
                      'дрібні вм’ятини, подряпини', 'звичайний знос', '"Europe/Kyiv"', 'L.trade[i]',
                      'data-quick-lead-auction="usa"', 'id="kl-card"', 'id="quick-lead-dialog"', '.kr-btn{'):
            self.assertIn(piece, self.page)
        self.assertEqual(self.page.count(usa_page.SHARE), 1)
        self.assertIn(usa_page.SHARE + '</body>', self.page)

    def test_japan_parts_left_out(self):
        for piece in ('/video/japan/', '/video/korea/gallery/', 'start_jpy', '¥', 'Японія', 'Лоти найближчих торгів',
                      'row("score"', 'row("house"', '324e5', 'data-quick-lead-auction="japan"'):
            self.assertNotIn(piece, self.page)

    def test_placed_after_the_calculator(self):
        calc, block = self.page.index('id="usa-result"'), self.page.index(usa_page.START)
        self.assertLess(calc, block)
        self.assertEqual(self.page[block - len('</section>'):block], '</section>')
        self.assertNotIn('</section>', self.page[calc:block - len('</section>')])

    def test_the_rest_stays(self):
        old = USA.decode('utf-8').replace(*usa_page.GALLERY)
        start, end = self.page.index(usa_page.START), self.page.index(usa_page.END) + len(usa_page.END)
        self.assertEqual((self.page[:start] + self.page[end:]).replace(usa_page.SHARE, ''), old)

    def test_idempotent(self):
        once = usa_page.build(USA, JAPAN)
        self.assertEqual(usa_page.build(once, JAPAN), once)

    def test_anchor_missing_stops(self):
        with self.assertRaisesRegex(ValueError, 'USA_PAGE'):
            usa_page.build(USA.replace(b'id="usa-result"', b'id="x"'), JAPAN)
        with self.assertRaisesRegex(ValueError, 'USA_PAGE'):
            usa_page.build(USA, JAPAN.replace(b'<!--UA-KOREA-LOTS-V1-->', b''))
        with self.assertRaisesRegex(ValueError, 'USA_PAGE'):
            usa_page.build(USA, JAPAN.replace('Лоти найближчих торгів'.encode(), b'X'))
        with self.assertRaisesRegex(ValueError, 'USA_PAGE'):
            usa_page.build(USA.replace(b"fetch('/video/korea/gallery/'", b"fetch('/x/'"), JAPAN)


if __name__ == '__main__':
    unittest.main()
