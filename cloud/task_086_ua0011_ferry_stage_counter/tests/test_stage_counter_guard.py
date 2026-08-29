import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("task086_guard", ROOT / "stage_counter_guard.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def catalog(target_stage="more", duplicate=False, chip_more=1):
    cards = [
        ("UA-0009", "korea"),
        ("UA-0011", target_stage),
        ("UA-0012", "gruzia"),
        ("UA-0013", "kiev"),
    ]
    if duplicate:
        cards.append(("UA-0011", target_stage))
    counts = {
        "all": len(cards), "korea": 1, "more": chip_more,
        "gruzia": 1, "kiev": 1,
    }
    chips = "".join(
        "<a class='chip' data-f='%s'>x<b>%d</b></a>" % (key, counts[key])
        for key in ("all", "korea", "more", "gruzia", "kiev")
    )
    blocks = "".join(
        "<a data-ua-card-stage='%s' href='%s.html'><img src='%s.jpg'></a>"
        % (stage, code, code) for code, stage in cards
    )
    return chips + blocks


def modern_catalog(canonical_target=True, chip_more=1):
    cards = [
        ("UA-0009", "sea"),
        ("UA-0012", "georgia"),
        ("UA-0013", "kiev"),
    ]
    if canonical_target:
        cards.append(("UA-0011", "sea"))
    chips = "".join([
        "<button class='chip' data-f='all'>x<b>4</b></button>",
        "<button class='chip' data-f='korea'>x<b>0</b></button>",
        "<button class='chip' data-f='sea'>x<b>%d</b></button>" % chip_more,
        "<button class='chip' data-f='georgia'>x<b>1</b></button>",
        "<button class='chip' data-f='kiev'>x<b>1</b></button>",
    ])
    blocks = "".join(
        "<article class='catalog-card' data-stage='%s'>"
        "<a class='catalog-photo' href='%s.html'><img src='%s.jpg'></a>"
        "<a class='card-arrow' href='%s.html'>open</a></article>"
        % (stage, code, code, code)
        for code, stage in cards
    )
    if not canonical_target:
        blocks += (
            "<a class='ua-cat-fallback-v1' data-ua-stage-tile='2' "
            "href='UA-0011.html'>UA-0011</a>"
        )
    return chips + blocks


class StageCounterGuardTests(unittest.TestCase):
    def test_normalize_catalog_uses_fresh_rows_and_rewrites_chips(self):
        source = "".join([
            "<button class='chip' data-f='all'>Все <b>99</b></button>",
            "<button class='chip' data-f='korea'>Корея <b>99</b></button>",
            "<button class='chip' data-f='sea'>Паром <b>99</b></button>",
            "<button class='chip' data-f='georgia'>Грузия <b>99</b></button>",
            "<button class='chip' data-f='kiev'>Киев <b>99</b></button>",
            "<article class='catalog-card'><a href='UA-0001.html'><img src='1.jpg'></a></article>",
            "<article class='catalog-card'><a href='UA-0011.html'><img src='11.jpg'></a></article>",
        ])
        rows = [
            {"auto_number": "UA-0001", "status": "kr_bought", "published": 1},
            {"auto_number": "UA-0011", "status": "sea_loaded", "published": 1},
        ]
        candidate = guard.normalize_catalog_from_rows(source, rows)
        self.assertEqual(guard.verify_catalog(candidate, "UA-0011", "more"), {
            "all": 2, "korea": 1, "more": 1, "gruzia": 0, "kiev": 0,
        })
        self.assertIn('data-stage="korea"', candidate)
        self.assertIn('data-stage="sea"', candidate)

    def test_stage_mapping_and_legacy_destination(self):
        self.assertEqual(guard.public_bucket("kr_bought"), "korea")
        self.assertEqual(guard.public_bucket("sea_loaded"), "more")
        self.assertEqual(guard.public_bucket("sold_transit"), "more")
        self.assertEqual(guard.public_bucket("ge_waiting"), "gruzia")
        self.assertEqual(guard.public_bucket("ua_delivered"), "kiev")
        with self.assertRaises(guard.StageCounterError):
            guard.validate_destination("sea_transit")

    def test_ferry_preserves_sea_eta_and_clears_later(self):
        fields = set(guard.ALL_STAGE_FIELDS)
        cleanup = set(guard.cleanup_fields_for_transition("kr_bought", "sea_loaded", fields))
        self.assertEqual(cleanup, set(guard.GEORGIA_FIELDS))
        self.assertTrue(set(guard.SEA_FIELDS + guard.ETA_FIELDS).isdisjoint(cleanup))

    def test_korea_clears_all_downstream_payload(self):
        cleanup = set(guard.cleanup_fields_for_transition(
            "ua_delivered", "kr_bought", guard.ALL_STAGE_FIELDS
        ))
        self.assertEqual(cleanup, set(guard.ALL_STAGE_FIELDS))

    def test_same_stage_is_idempotent(self):
        self.assertEqual(
            guard.cleanup_fields_for_transition("sea_loaded", "sea_loaded", guard.ALL_STAGE_FIELDS),
            (),
        )

    def test_projection_hides_only_incompatible_payload(self):
        raw = {field: "x" for field in guard.ALL_STAGE_FIELDS}
        raw["status"] = "sea_loaded"
        projected = guard.public_projection(raw)
        for field in guard.SEA_FIELDS + guard.ETA_FIELDS:
            self.assertEqual(projected[field], "x")
        for field in guard.GEORGIA_FIELDS:
            self.assertIsNone(projected[field])

    def test_catalog_counts_equal_unique_cards_and_chips(self):
        counts = guard.verify_catalog(catalog(), "UA-0011", "more")
        self.assertEqual(counts, {
            "all": 4, "korea": 1, "more": 1, "gruzia": 1, "kiev": 1,
        })

    def test_catalog_rejects_duplicate_and_count_drift(self):
        with self.assertRaises(guard.StageCounterError):
            guard.verify_catalog(catalog(duplicate=True, chip_more=2), "UA-0011", "more")
        with self.assertRaises(guard.StageCounterError):
            guard.verify_catalog(catalog(chip_more=9), "UA-0011", "more")

    def test_live_article_cards_count_once_and_normalize_stage_aliases(self):
        counts = guard.verify_catalog(modern_catalog(chip_more=2), "UA-0011", "more")
        self.assertEqual(counts, {
            "all": 4, "korea": 0, "more": 2, "gruzia": 1, "kiev": 1,
        })
        self.assertEqual(len(guard.card_entries(modern_catalog(chip_more=2))), 4)

    def test_fallback_is_semantic_card_but_counter_drift_still_fails(self):
        source = modern_catalog(canonical_target=False, chip_more=1)
        self.assertEqual(guard.catalog_counts(source), {
            "all": 4, "korea": 0, "more": 2, "gruzia": 1, "kiev": 1,
        })
        with self.assertRaises(guard.StageCounterError):
            guard.verify_catalog(source, "UA-0011", "more")


if __name__ == "__main__":
    unittest.main()
