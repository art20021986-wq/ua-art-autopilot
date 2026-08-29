#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

import catalog_design_guard as guard


ARTICLE = """<article class="catalog-card" data-stage="kiev">
<a href="UA-0001.html" class="catalog-photo"><img src="/video/stage/UA-0001.webp" alt="Old"><span class="photo-count">1 фото</span></a>
<div class="catalog-body"><div class="catalog-top"><span>UA-0001</span><b data-ru="1 $" data-uk="1 $">1 $</b></div>
<h2>Old car</h2><div class="status-pill" data-ru="Старый статус" data-uk="Старий статус">Старый статус</div>
<p>1 км · 1 см³ · бензин · автомат</p>
<a class="card-arrow" href="UA-0001.html" aria-label="Открыть карточку"><svg><path d="M5 12h14"/></svg></a>
</div></article>"""


GOLDEN = """<!doctype html><html lang="ru"><head><style>.catalog-card{display:grid}</style></head><body>
<nav><a href="/">UA ART</a><button data-lang="ru">RU</button><button data-lang="uk">UA</button></nav>
<main><h1>Автомобили в наличии и в пути</h1><div class="schet">1 в подборке</div>
<div class="catalog-filters">
<button data-f="all">Все · 1</button><button data-f="kiev">В Киеве · 1</button>
<button data-f="georgia">В Грузии · 0</button><button data-f="sea">На пароме · 0</button>
<button data-f="korea">В Корее · 0</button></div><div class="catalog-result">Показано: 1</div>
<div class="catalog-grid">""" + ARTICLE + """</div>
<section class="empty-assist">Не нашли подходящий автомобиль?</section></main>
<a class="whatsapp" href="https://wa.me/380999222002">Чат online</a><footer>UA ART COMPANY</footer>
<script>function setLang(x){document.documentElement.lang=x}</script></body></html>"""


def rows_13():
    result = []
    stages = {
        4: ("UA-0002", "UA-0007", "UA-0008"),
        3: ("UA-0001",),
        2: ("UA-0005", "UA-0006", "UA-0009", "UA-0010", "UA-0011", "UA-0012", "UA-0013"),
        1: ("UA-0003", "UA-0004"),
    }
    statuses = {1: "kr_bought", 2: "sea_loaded", 3: "ge_to_kyiv", 4: "ua_ready"}
    for stage, identifiers in stages.items():
        for number, identifier in enumerate(identifiers):
            result.append({
                "auto_number": identifier,
                "published": 1,
                "status": statuses[stage],
                "brand": "Kia" if number else "Mercedes-Benz",
                "model": "K5",
                "year": "2018",
                "price_uah": 10000 + number,
                "mileage_km": 100000 + number,
                "engine_cc": 2000,
                "fuel": "газ",
                "gearbox": "автомат",
                "vin": "TESTVIN%09d" % int(identifier[-4:]),
                "photos": '[{"x":1},{"x":2}]',
                "videos": '[{"x":1}]',
            })
    return result


class CatalogDesignGuardTests(unittest.TestCase):
    def setUp(self):
        self.rows = rows_13()
        self.photos = {
            row["auto_number"]: "/video/stage/%s.webp" % row["auto_number"]
            for row in self.rows
        }

    def test_restore_13_and_exact_stages(self):
        result = guard.build_catalog(GOLDEN, self.rows, self.photos)
        audit = guard.assert_live_acceptance(result, self.rows, GOLDEN)
        self.assertEqual(audit["counts"], guard.EXPECTED_STAGE_COUNTS)
        self.assertEqual(audit["article_cards"], 13)
        self.assertIn("Все · 13", result)
        self.assertIn("В Киеве · 3", result)
        self.assertIn("В Грузии · 1", result)
        self.assertIn("На пароме · 7", result)
        self.assertIn("В Корее · 2", result)
        self.assertEqual(result.count('data-ua-card="UA-0012"'), 1)
        self.assertEqual(result.count('data-ua-card="UA-0013"'), 1)

    def test_shell_fingerprint_is_immutable_and_idempotent(self):
        first = guard.build_catalog(GOLDEN, self.rows, self.photos)
        second = guard.build_catalog(first, self.rows, self.photos)
        self.assertEqual(first, second)
        self.assertEqual(guard.shell_fingerprint(GOLDEN), guard.shell_fingerprint(first))
        value = first
        for _ in range(10):
            value = guard.build_catalog(value, self.rows, self.photos)
        self.assertEqual(first, value)

    def test_future_published_card_changes_only_mutable_region(self):
        initial = guard.build_catalog(GOLDEN, self.rows, self.photos)
        future = copy.deepcopy(self.rows)
        row = copy.deepcopy(future[-1])
        row.update({
            "auto_number": "UA-0014",
            "published": 1,
            "status": "kr_bought",
            "vin": "FUTUREVIN000014",
        })
        future.append(row)
        photos = dict(self.photos, **{"UA-0014": "/video/stage/UA-0014.webp"})
        updated = guard.build_catalog(initial, future, photos)
        audit = guard.audit_catalog(updated, future, GOLDEN)
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["article_cards"], 14)
        self.assertEqual(guard.shell_fingerprint(initial), guard.shell_fingerprint(updated))

    def test_unpublished_draft_is_excluded(self):
        draft = copy.deepcopy(self.rows[0])
        draft.update({"auto_number": "UA-0014", "published": 0})
        result = guard.build_catalog(GOLDEN, self.rows + [draft], self.photos)
        self.assertNotIn("UA-0014", result)

    def test_missing_shell_or_duplicate_identifier_fails_closed(self):
        with self.assertRaises(guard.CatalogDesignError):
            guard.build_catalog(GOLDEN.replace("<nav>", "<div>"), self.rows, self.photos)
        duplicate = self.rows + [copy.deepcopy(self.rows[0])]
        with self.assertRaises(guard.CatalogDesignError):
            guard.build_catalog(GOLDEN, duplicate, self.photos)


if __name__ == "__main__":
    unittest.main()

