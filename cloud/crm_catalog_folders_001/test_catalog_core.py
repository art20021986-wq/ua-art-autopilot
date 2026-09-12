import copy
import unittest

from catalog_core import CatalogSnapshotError, parse_catalog, partition_by_catalog


def html(numbers=()):
    cards = "".join('<article data-ua-card="%s"></article>' % n for n in numbers)
    return ('<!doctype html><html lang="uk"><head><meta charset="utf-8">'
            '<title>Каталог автомобилей — UA ART COMPANY</title></head>'
            '<body>%s</body></html>' % cards)


def rows(count):
    return [{"id": n, "auto_number": "UA-%04d" % n, "published": 1,
             "photos": ["photo.jpg"], "spec": {"fuel": "LPG"}}
            for n in range(count, 0, -1)]


class CatalogCoreTests(unittest.TestCase):
    def test_actual_eighteen_plus_one_with_existing_database_id(self):
        source = rows(19)
        source[0]["id"] = 29
        source[0]["published"] = 0
        ids = parse_catalog(html("UA-%04d" % n for n in range(1, 19)))
        groups = partition_by_catalog(source, ids)
        self.assertIsInstance(ids, frozenset)
        self.assertEqual(len(groups["catalog"]), 18)
        self.assertEqual(groups["unpublished"], [source[0]])
        self.assertEqual(groups["unpublished"][0]["auto_number"], "UA-0019")

    def test_publication_intent_race_does_not_move_absent_car(self):
        car = rows(1)[0]
        car["published"] = 1
        groups = partition_by_catalog([car], parse_catalog(html()))
        self.assertEqual(groups, {"catalog": [], "unpublished": [car]})

    def test_unpublication_intent_does_not_hide_still_present_car(self):
        car = rows(1)[0]
        car["published"] = 0
        groups = partition_by_catalog([car], parse_catalog(html(["UA-0001"])))
        self.assertEqual(groups, {"catalog": [car], "unpublished": []})

    def test_more_than_thirty_cards_and_future_number_are_not_truncated(self):
        source = rows(65) + [{"id": 10000, "auto_number": "UA-10000"}]
        ids = parse_catalog(html(c["auto_number"] for c in source))
        groups = partition_by_catalog(iter(source), ids)
        self.assertEqual(len(groups["catalog"]), 66)
        self.assertEqual(groups["catalog"], source)
        self.assertFalse(groups["unpublished"])

    def test_preserves_input_objects_order_and_nested_data(self):
        source = rows(4)
        before = copy.deepcopy(source)
        ids = frozenset(("UA-0001", "UA-0003"))
        groups = partition_by_catalog(source, ids)
        self.assertEqual(source, before)
        self.assertEqual(groups["catalog"], [source[1], source[3]])
        self.assertEqual(groups["unpublished"], [source[0], source[2]])
        self.assertIs(groups["catalog"][0], source[1])
        self.assertIs(groups["unpublished"][0], source[0])
        self.assertEqual(ids, frozenset(("UA-0001", "UA-0003")))

    def test_empty_complete_catalog_is_valid(self):
        self.assertEqual(parse_catalog(html()), frozenset())
        self.assertEqual(partition_by_catalog([], frozenset()),
                         {"catalog": [], "unpublished": []})

    def test_duplicate_markers_and_invalid_catalog_numbers_are_rejected(self):
        for numbers in (["UA-0001", "UA-0001"], ["ua-0001"], ["UA-001"],
                        ["UA0001"], ["UA-0001 "], ["UA-０００１"], [""]):
            with self.subTest(numbers=numbers), self.assertRaises(CatalogSnapshotError):
                parse_catalog(html(numbers))
        for marker in ('<article data-ua-card></article>',
                       '<article data-ua-card="UA-0001" data-ua-card="UA-0002"></article>'):
            with self.subTest(marker=marker), self.assertRaises(CatalogSnapshotError):
                parse_catalog(html().replace("<body>", "<body>" + marker))

    def test_partial_wrong_or_duplicate_document_is_rejected(self):
        complete = html(["UA-0001"])
        malformed = ["", '<article data-ua-card="UA-0001"></article>',
                     complete.replace("</html>", ""),
                     complete.replace("</body>", ""),
                     complete.replace("</title>", ""),
                     complete.replace("UA ART COMPANY", "Unavailable"),
                     complete.replace("<html lang=\"uk\">", "<html/>"),
                     complete + complete, complete + "broken tail",
                     complete.replace("</head>", "<title>UA ART</title></head>")]
        for content in malformed:
            with self.subTest(content=content), self.assertRaises(CatalogSnapshotError):
                parse_catalog(content)

    def test_parser_ignores_fake_markers_in_comments_and_scripts(self):
        extra = ('<!-- <article data-ua-card="UA-9998"></article> -->'
                 '<script>const sample = \'<div data-ua-card="UA-9999">\';</script>')
        source = html(["UA-0001"]).replace("</body>", extra + "</body>")
        self.assertEqual(parse_catalog(source), frozenset(("UA-0001",)))

    def test_incomplete_crm_snapshot_rejected_without_mutation(self):
        source = rows(1)
        before = copy.deepcopy(source)
        with self.assertRaises(CatalogSnapshotError):
            partition_by_catalog(source, {"UA-0001", "UA-0002"})
        self.assertEqual(source, before)

    def test_invalid_and_duplicate_crm_identity_is_rejected(self):
        invalid = [[{"id": 1, "auto_number": "UA0001"}],
                   [{"id": 1}], [{"auto_number": "UA-0001"}],
                   [{"id": True, "auto_number": "UA-0001"}],
                   [{"id": 0, "auto_number": "UA-0001"}],
                   rows(1) * 2,
                   [{"id": 1, "auto_number": "UA-0001"},
                    {"id": 2, "auto_number": "UA-0001"}],
                   [None]]
        for source in invalid:
            before = copy.deepcopy(source)
            with self.subTest(source=source), self.assertRaises(CatalogSnapshotError):
                partition_by_catalog(source, frozenset())
            self.assertEqual(source, before)
        for ids in (["UA-0001", "UA-0001"], ["invalid"], [None]):
            with self.subTest(ids=ids), self.assertRaises(CatalogSnapshotError):
                partition_by_catalog(rows(1), ids)


if __name__ == "__main__":
    unittest.main()
