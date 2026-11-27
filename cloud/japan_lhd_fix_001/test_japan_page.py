"""video/japan.html from the live video/korea.html (JAPAN-LHD-001)."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import japan_page  # noqa: E402

KOREA = (HERE / 'fixtures' / 'korea_live.html').read_bytes()


class JapanPageTests(unittest.TestCase):
    def setUp(self):
        self.page = japan_page.build(KOREA).decode('utf-8')

    def test_japan_texts_list_and_yen(self):
        for piece in ('Обирайте авто на аукціонах Японії — тільки з лівим кермом', 'АУКЦІОНИ ЯПОНІЇ · ОНЛАЙН',
                      'Японія: показуємо лише авто з лівим кермом.', 'Ціни — стартові в Японії.',
                      'fetch("/video/japan/lots.json"', "fetch('/video/japan/gallery/'",
                      '" <small>(¥"+n(l.start_jpy)+")</small>"', 'var ZN=[["Японія","Київ"]', 'var HOL={};',
                      '<link rel="canonical" href="https://www.uaart.com.ua/video/japan.html">'):
            self.assertIn(piece, self.page)
        self.assertEqual(self.page.count('data-quick-lead-auction="japan"'), 2)

    def test_korea_only_parts_left_out(self):
        for piece in ('/api/auction/bid', 'kc-dialog', 'UA-KOREA-LOGIN', 'UA-KOREA-BID', 'Аукціони, до яких',
                      'Чому аукціон вигідніше', 'id="faq"', 'пором Корея', 'start_krw', '₩', '/video/korea/',
                      'video/ru/korea.html', 'video/korea.html', 'class="kr-live"', 'Hyundai, Kia', '"2026/12/25"'):
            self.assertNotIn(piece, self.page)

    def test_the_rest_stays(self):
        for piece in ('Авто з усіх країн під ключ', 'id="kl-card"', 'id="kl-grid"', 'Для автобізнесу',
                      'id="quick-lead-dialog"', 'section class="ua-how', 'G-6SRBQK6GY4', 'PLAN=d.planned||null'):
            self.assertIn(piece, self.page)

    def test_anchor_missing_stops(self):
        with self.assertRaisesRegex(ValueError, 'JAPAN_PAGE'):
            japan_page.build(KOREA.replace('АУКЦІОНИ КОРЕЇ · ОНЛАЙН'.encode(), b'X'))
        with self.assertRaisesRegex(ValueError, 'JAPAN_PAGE_SOURCE_IS_JAPAN'):
            japan_page.build(self.page.encode('utf-8'))


if __name__ == '__main__':
    unittest.main()
