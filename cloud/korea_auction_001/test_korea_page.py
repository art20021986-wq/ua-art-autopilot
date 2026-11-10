import pathlib
import unittest

import ua_korea_page as p

HOME = (pathlib.Path(__file__).parent / 'fixtures' / 'index_live.html').read_text()


class KoreaPageTest(unittest.TestCase):
    def setUp(self):
        self.page = p.build(HOME)

    def test_layout_kept_main_replaced(self):
        head, foot = HOME.split('<main id="main-content">')[0], HOME.split('</main>')[1]
        self.assertIn('<footer class="site-footer">', self.page)
        self.assertEqual(self.page.count('<main'), 1)
        main = self.page[self.page.index('<main'):self.page.index('</main>')]
        self.assertNotIn('ua-order-first', main)
        self.assertTrue(self.page.endswith(foot))
        self.assertIn('<header', head)

    def test_seo_fields(self):
        self.assertIn('<link rel="canonical" href="%s">' % p.URL, self.page)
        self.assertIn('Аукціони Кореї онлайн — UA ART COMPANY</title>', self.page)
        self.assertNotIn('application/ld+json', self.page)

    def test_owner_content_three_languages(self):
        for text in ('Дивитися онлайн', 'Депозит 2000 $ — входить у вартість авто',
                     'індивідуальних умовах', 'Незабаром — Японія та інші країни', 'data-ka="ონლაინ ნახვა"', 'id="online"'):
            self.assertIn(text, self.page)

    def test_platform_never_named(self):
        low = self.page.lower()
        self.assertNotIn('beforward', low)
        self.assertNotIn('be forward', low)
        self.assertNotIn('jpauto', low)
        self.assertNotIn('jp auto', low)


if __name__ == '__main__':
    unittest.main()
