#!/usr/bin/env python3
from __future__ import annotations

import unittest

import home_counter_guard as guard


def fixture() -> str:
    cards = []
    for stage, count in (("kiev", 3), ("georgia", 1), ("sea", 4), ("korea", 2)):
        cards.append(
            '<a class="stage-card x" href="katalog.html?f=%s" '
            'data-stage="%s" data-count="%d">'
            '<span class="stage-copy"><b>%s</b>'
            '<em data-ru="%d автомобиля" data-uk="%d автомобілі">'
            '%d автомобиля</em></span></a>'
            % (stage, stage, count, stage, count, count, count)
        )
    return (
        '<!doctype html><html lang="ru"><body><div class="stage-list">'
        + "".join(cards)
        + '</div><a class="outline-cta" href="katalog.html">'
          '<i data-ru="Открыть все автомобили · 10" '
          'data-uk="Відкрити всі автомобілі · 10">'
          'Открыть все автомобили · 10</i></a></body></html>'
    )


class HomeCounterGuardTests(unittest.TestCase):
    def setUp(self):
        self.counts = {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2}

    def test_counts_from_rows_are_unique_and_stage_based(self):
        rows = []
        number = 1
        statuses = ["ua_delivered"] * 3 + ["ge_arrived"] + ["sea_loaded"] * 7 + ["kr_bought"] * 2
        for status in statuses:
            rows.append({"auto_number": "UA-%04d" % number, "published": 1, "status": status})
            number += 1
        self.assertEqual(guard.counts_from_rows(rows), self.counts)

    def test_patch_updates_all_server_values_and_script(self):
        result = guard.patch_home(fixture(), self.counts)
        audit = guard.audit_home(result, self.counts)
        self.assertEqual(audit["status"], "PASS", audit["errors"])
        self.assertIn('data-stage="sea" data-count="7"', result)
        self.assertIn("7 автомобилей", result)
        self.assertIn("7 автомобілів", result)
        self.assertIn("Открыть все автомобили · 13", result)
        self.assertIn('id="ua-home-stage-counter-sync-v1"', result)

    def test_patch_is_idempotent(self):
        once = guard.patch_home(fixture(), self.counts)
        twice = guard.patch_home(once, self.counts)
        self.assertEqual(once, twice)

    def test_duplicate_published_id_fails_closed(self):
        rows = [
            {"auto_number": "UA-0001", "published": 1, "status": "sea_loaded"},
            {"auto_number": "UA-0001", "published": 1, "status": "sea_loaded"},
        ]
        with self.assertRaises(guard.HomeCounterError):
            guard.counts_from_rows(rows)

    def test_missing_stage_card_fails_closed(self):
        broken = fixture().replace('data-stage="sea"', 'data-stage="missing"')
        with self.assertRaises(guard.HomeCounterError):
            guard.patch_home(broken, self.counts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
