"""Exercise the exact final catalog renderer with an isolated synthetic shell."""

import ast
from collections import namedtuple
import datetime
import hashlib
import html
import json
import os
import pathlib
import re
from typing import Any, Iterable, Mapping
import unittest

from patch_catalog_design_guard import patch_catalog_design_guard
from uaart_market_prices import START, END, render_market_prices, replace_catalog_price_slot


def guard_namespace(source):
    tree = ast.parse(source)
    allowed_calls = {"re.compile", "tuple", "range"}
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            body.append(node)
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id in ("ROOT", "GOLDEN_PATH") for target in node.targets):
                continue
            for call in (n for n in ast.walk(node.value) if isinstance(n, ast.Call)):
                if ast.unparse(call.func) not in allowed_calls:
                    raise AssertionError("UNEXPECTED_CATALOG_MODULE_CALL")
            body.append(node)
    namespace = {
        "dt": datetime, "hashlib": hashlib, "html": html, "json": json,
        "pathlib": pathlib, "re": re, "Any": Any, "Iterable": Iterable, "Mapping": Mapping,
        "CatalogDesignError": type("CatalogDesignError", (RuntimeError,), {}),
        "CardSpan": namedtuple("CardSpan", "start end identifier source"),
        "GOLDEN_PATH": pathlib.Path("/unused-test-golden"),
        "_ua088_replace_catalog_price_slot": replace_catalog_price_slot,
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), "isolated_catalog_ast", "exec"), namespace)
    return namespace


def prototype():
    return ('<article class="catalog-card" data-stage="kiev"><a class="catalog-photo" href="UA-0010.html"><img src="fixture.jpg"></a>'
            '<span class="photo-count">2 фото</span><div class="catalog-body"><div class="catalog-top"><span>UA-0010</span><b>11 700 $</b></div>'
            '<h2>Fixture model</h2><div class="status-pill">В Киеве</div><p>Fixture specs</p><a class="card-arrow" href="UA-0010.html">→</a></div></article>')


def shell():
    return ('<html><head><title>Fixture catalog</title></head><body><nav>Preserved navigation</nav>'
            '<button data-lang="ru">RU</button><button data-lang="uk">UA</button>'
            '<button data-f="all">Все · 1</button><button data-f="kiev">В Киеве · 1</button>'
            '<button data-f="georgia">В Грузии · 0</button><button data-f="sea">На пароме · 0</button>'
            '<button data-f="korea">В Корее · 0</button><div class="catalog-result">Показано: 1</div>'
            + prototype() + '<footer><a href="https://wa.me/fixture">WhatsApp</a></footer></body></html>')


@unittest.skipUnless(os.environ.get("UA088_LIVE_SOURCE_DIR"), "Private snapshot path not supplied")
class CatalogGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (pathlib.Path(os.environ["UA088_LIVE_SOURCE_DIR"]) / "catalog_design_guard.py").read_bytes()
        cls.candidate, cls.provenance = patch_catalog_design_guard(cls.original)
        cls.before = guard_namespace(cls.original)
        cls.after = guard_namespace(cls.candidate)

    def rows(self):
        return [dict(auto_number="UA-%04d" % n, published=1,
                     status=("kr_ready", "sea_ready", "ge_waiting", "ua_ready")[n % 4],
                     price_uah=11700, price_georgia=8750 if n == 10 else None,
                     brand="Fixture", model="Preserved", year=2020, photos=["a.jpg", "b.jpg"],
                     mileage_km=100000, engine_cc=2000, fuel="LPG", gearbox="AT") for n in range(1, 19)]

    def test_final_catalog_eighteen_dual_prices_and_original_shell_audit(self):
        rows = self.rows()
        photos = {row["auto_number"]: "fixture.jpg" for row in rows}
        golden = shell()
        before = self.before["build_catalog"](golden, rows, photos)
        after = self.after["build_catalog"](golden, rows, photos)
        self.assertEqual(self.before["shell_fingerprint"](before), self.after["shell_fingerprint"](after))
        self.assertEqual(self.after["audit_catalog"](after, rows, golden)["status"], "PASS")
        self.assertEqual(after.count(START), 18)
        self.assertEqual(after.count(END), 18)
        restored = after
        for row in rows:
            restored = restored.replace(render_market_prices(row, compact=True, require_car_id=True), '<b data-ru="11 700 $" data-uk="11 700 $">11 700 $</b>', 1)
        self.assertEqual(restored, before)

    def test_final_catalog_guard_audits_remain_unmodified(self):
        self.assertEqual(self.provenance["other_functions_unchanged"], 24)
        compile(self.candidate, "catalog_design_guard.py", "exec")
        with self.assertRaisesRegex(ValueError, "SOURCE_HASH_MISMATCH"):
            patch_catalog_design_guard(self.candidate)


if __name__ == "__main__":
    unittest.main()
