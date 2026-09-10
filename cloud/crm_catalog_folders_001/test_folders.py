import copy
import unittest

from folders import InvalidSnapshot, listing, menu, parse_callback, partition


def cards(count=19):
    return [{"id": i, "auto_number": "UA-%04d" % i,
             "published": 1, "stage": i % 4, "vin": "VIN-%d" % i,
             "additional_spec": {"fuel": "LPG"}, "photos": ["photo.jpg"]}
            for i in range(count, 0, -1)]


def label(card):
    return card["auto_number"]


class FolderTests(unittest.TestCase):
    def test_partition_preserves_all_records_and_data(self):
        source = cards() + [{"id": 20, "published": 0}]
        before = copy.deepcopy(source)
        groups = partition(source)
        self.assertEqual([len(groups[k]) for k in groups], [19, 1])
        self.assertEqual(source, before)
        self.assertIs(groups["catalog"][0], source[0])
        self.assertEqual({c["id"] for g in groups.values() for c in g},
                         {c["id"] for c in source})

    def test_counts_are_dynamic_after_committed_publication(self):
        source = cards() + [{"id": 20, "published": 0}]
        self.assertEqual(menu(source).rows[1][0].text, "Не опубликованные · 1")
        source[-1]["published"] = 1  # Simulate the existing successful commit.
        self.assertEqual(menu(source).rows[0][0].text, "В каталоге · 20")
        self.assertEqual(menu(source).rows[1][0].text, "Не опубликованные · 0")
        source[-1]["published"] = 0  # Simulate successful unpublication.
        self.assertEqual(len(partition(source)["unpublished"]), 1)

    def test_stage_and_other_edits_do_not_move_a_card(self):
        source = cards(1)
        for stage in (None, "kr_bought", "sea_transit", "kyiv", "unknown"):
            source[0]["stage"] = stage
            source[0]["additional_spec"] = {}
            self.assertEqual(len(partition(source)["catalog"]), 1)

    def test_failed_publish_leaves_view_and_input_unchanged(self):
        source = [{"id": 20, "published": 0}]
        before = copy.deepcopy(source)
        initial = menu(source)
        self.assertEqual(menu(source), initial)  # No committed flag change.
        self.assertEqual(source, before)

    def test_invalid_state_and_duplicate_id_are_not_silently_classified(self):
        for flag in (None, "0", "1", "false", 2, -1):
            with self.assertRaises(InvalidSnapshot):
                partition([{"id": 1, "published": flag}])
        with self.assertRaises(InvalidSnapshot):
            partition(cards(1) * 2)
        for cid in (None, "1", 0, True):
            with self.assertRaises(InvalidSnapshot):
                partition([{"id": cid, "published": 0}])

    def test_pagination_keeps_folder_and_existing_open_callback(self):
        source = cards(30)
        found = []
        for page in range(3):
            view = listing(source, "catalog", page, label, page_size=12)
            found.extend(b.callback_data for row in view.rows for b in row
                         if b.callback_data.startswith("car_open:"))
            for row in view.rows:
                for button in row:
                    if button.text in ("←", "→"):
                        self.assertEqual(parse_callback(button.callback_data)[0], "catalog")
        self.assertEqual(found, ["car_open:%d" % c["id"] for c in source])
        self.assertEqual(listing(cards(1), "catalog", 9, label, page_size=12).rows[0][0].callback_data,
                         "car_open:1")

    def test_empty_folder_and_strict_callbacks(self):
        view = listing([], "unpublished", 0, label, page_size=12)
        self.assertIn("пока нет автомобилей", view.text)
        self.assertEqual(view.rows[-1][0].callback_data, "cars_folders")
        self.assertEqual(parse_callback("cars_folder:unpublished:0"), ("unpublished", 0))
        for size in (0, -1, True, "12"):
            with self.assertRaises(ValueError):
                listing([], "catalog", 0, label, page_size=size)
        for value in ("cars_folder:all:0", "cars_folder:catalog:-1", "car_open:1",
                      "cars_folder:catalog:1:0", "cars_folder:catalog:١",
                      "cars_folder:catalog:" + "9" * 40):
            with self.assertRaises(ValueError):
                parse_callback(value)


if __name__ == "__main__":
    unittest.main()
