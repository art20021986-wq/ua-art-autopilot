"""The stage-only homepage must never acquire one representative car's price."""

import unittest

from initial_html_prices import migrate_home


def stage_home():
    stage_links = ''.join(
        '<a class="stage-card" data-stage="%s" href="katalog.html?f=%s">'
        '<img src="foto/UA-0017/photo.jpg"><em>5 автомобилей</em></a>' % (stage, stage)
        for stage in ("kiev", "georgia", "sea", "korea")
    )
    return ('<!doctype html><html><head><title>Protected home</title>'
            '<link rel="canonical" href="https://uaart.com.ua/"></head><body>' + stage_links
            + '<a class="outline-cta" href="katalog.html">Все автомобили · 20</a>'
              '<script src="ua-site-languages.js"></script></body></html>')


class HomePricesTest(unittest.TestCase):
    def row(self):
        return {"auto_number": "UA-0017", "price_uah": 24500, "price_georgia": 18900}

    def test_stage_home_is_byte_identical_for_either_market_and_missing_ge(self):
        source = stage_home()
        for prices in ({}, {"price_uah": 24700}, {"price_georgia": 19100}, {"price_georgia": None}):
            with self.subTest(prices=prices):
                after, evidence = migrate_home(source, [dict(self.row(), **prices)])
                self.assertEqual(after.encode(), source.encode())
                self.assertTrue(evidence["all_bytes_unchanged"])
                self.assertTrue(evidence["no_car_price_surfaces"])
                self.assertEqual(evidence["price_regions_changed"], 0)

    def test_new_car_preview_cannot_be_silently_ignored(self):
        for extra in ('<a href="UA-0017.html">Автомобиль</a>',
                      '<article class="catalog-card">Автомобиль</article>',
                      '<div class="cn">24 500 $</div>'):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(ValueError, "CAR_PRICE_SURFACE_REQUIRES_MIGRATION"):
                    migrate_home(stage_home().replace('</body>', extra + '</body>'), [self.row()])

    def test_unknown_or_mismatched_stage_link_is_rejected(self):
        for source in (stage_home().replace('data-stage="sea"', 'data-stage="unknown"'),
                       stage_home().replace('katalog.html?f=sea', 'katalog.html?f=korea'),
                       stage_home().replace('class="outline-cta"', 'class="other"')):
            with self.assertRaises(ValueError):
                migrate_home(source, [self.row()])

    def test_duplicate_or_empty_published_set_is_rejected(self):
        for rows in ([], [self.row(), self.row()]):
            with self.assertRaises(ValueError):
                migrate_home(stage_home(), rows)


if __name__ == "__main__":
    unittest.main()
