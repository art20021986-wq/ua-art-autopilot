import unittest

from initial_html_prices import migrate_card, migrate_catalog
from uaart_market_prices import START, END, render_market_prices, replace_catalog_price_slot


def row(number=10):
    return {"auto_number": "UA-%04d" % number, "price_uah": 11700, "price_georgia": 8750}


def article(number=10):
    return ('<article class="catalog-card" data-stage="georgia"><a class="catalog-photo" href="UA-%04d.html"><img src="photo.jpg"></a>'
            '<div class="catalog-body"><div class="catalog-top"><span>UA-%04d</span><b data-ru="11 700 $" data-uk="11 700 $">11 700 $</b></div>'
            '<h2>Preserved model</h2><p>Preserved specification</p><a class="card-arrow" href="UA-%04d.html">→</a></div></article>') % (number, number, number)


class InitialHtmlTest(unittest.TestCase):
    def test_yadro_card_only_price_parent_replaced(self):
        old = '<div><div class="cn_b">11 700 $</div><div class="cn_p"><span data-ru="Под ключ в Киеве">Под ключ в Киеве</span><br>доплат нет</div></div>'
        source = '<html><body><h1>UA-0010</h1>' + old + '<p>preserved</p><img src="photo.jpg"></body></html>'
        output, evidence = migrate_card(source, row())
        self.assertEqual(output, source.replace(old, render_market_prices(row(), require_car_id=True)))
        self.assertTrue(evidence["outside_price_unchanged"])

    def test_stranica_card_only_price_and_adjacent_caption_replaced(self):
        old = "<div class='cena' style='margin-top:14px'>11 700 $</div><div class='tihо'>Под ключ в Киеве. Выкуп на аукционе, доставка, растаможка и сертификат — доплат нет.</div>"
        source = "<html><body><div class='blok'><div class='nom'>UA-0010</div>" + old + "</div><p>preserved</p></body></html>"
        output, _ = migrate_card(source, row())
        self.assertEqual(output, source.replace(old, render_market_prices(row(), require_car_id=True)))

    def test_price_parent_extra_content_not_removed(self):
        source = '<html><body>UA-0010<div><span>preserved</span><div class="cn_b">11 700 $</div><div class="cn_p">caption</div></div></body></html>'
        with self.assertRaisesRegex(ValueError, "EXTRA_CONTENT"):
            migrate_card(source, row())

    def test_mismatched_ua_price_fails(self):
        source = '<html><body>UA-0010<div><div class="cn_b">11 600 $</div><div class="cn_p">caption</div></div></body></html>'
        with self.assertRaisesRegex(ValueError, "INITIAL_UA_PRICE_CRM_MISMATCH"):
            migrate_card(source, row())

    def test_catalog_only_price_nodes_change_in_all_eighteen_articles(self):
        rows = [row(n) for n in range(1, 19)]
        source = '<html><body><nav>unchanged</nav>' + ''.join(article(n) for n in range(1, 19)) + '<footer>unchanged</footer></body></html>'
        result, evidence = migrate_catalog(source, rows)
        restored = result
        old = '<b data-ru="11 700 $" data-uk="11 700 $">11 700 $</b>'
        for item in rows:
            restored = restored.replace(render_market_prices(item, compact=True, require_car_id=True), old, 1)
        self.assertEqual(restored, source)
        self.assertEqual(evidence["price_regions_changed"], 18)

    def test_initial_migration_reapply_rejected(self):
        after, _ = migrate_catalog('<html><body>' + article() + '</body></html>', [row()])
        with self.assertRaisesRegex(ValueError, "ALREADY_PRESENT"):
            migrate_catalog(after, [row()])

    def test_catalog_missing_duplicate_or_foreign_row_rejected(self):
        source = '<html><body>' + article() + '</body></html>'
        for rows in ([row(11)], [row(), row()], [row(), row(11)]):
            with self.assertRaises(ValueError):
                migrate_catalog(source, rows)

    def test_legacy_catalog_alias_mismatch_rejected(self):
        for alias in (11000, "1e4", -11000, True, "NaN", "bad"):
            with self.assertRaisesRegex(ValueError, "LEGACY_CATALOG_UA_PRICE_REQUIRES_RECONCILIATION"):
                replace_catalog_price_slot(article(), dict(row(), price_usd=alias))

    def test_unexpected_caption_link_or_content_is_never_removed(self):
        for amount_class, caption_class in (("cn_b", "cn_p"), ("cena", "tihо")):
            for extra in ('<a href="UA-0010-diag.html">Комплексная диагностика</a>', " Additional private note", '<span onclick="action()"></span>'):
                source = '<html><body>UA-0010<div><div class="%s">11 700 $</div><div class="%s">Под ключ в Киеве · доплат нет%s</div></div></body></html>' % (amount_class, caption_class, extra)
                with self.assertRaisesRegex(ValueError, "INITIAL_PRICE_CAPTION"):
                    migrate_card(source, row())

    def test_golden_render_of_marked_prototype_does_not_duplicate(self):
        one = replace_catalog_price_slot(article(), row())
        two = replace_catalog_price_slot(one, dict(row(), price_georgia=8800))
        self.assertEqual(two.count(START), 1)
        self.assertEqual(two.count(END), 1)
        self.assertIn('data-ua-value="8800"', two)

    def test_malformed_price_parent_fails(self):
        with self.assertRaisesRegex(ValueError, "PRICE_DOM"):
            migrate_catalog('<article class="catalog-card">UA-0010<div><b>11 700 $</div></b></article>', [row()])


if __name__ == "__main__":
    unittest.main()
