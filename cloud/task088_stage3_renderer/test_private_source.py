"""Offline differential tests: private live source is read, never imported.

Set UA088_LIVE_SOURCE_DIR to the verified private snapshot directory. Only named
pure base AST function definitions are executed, with all surrounding dependencies
stubbed. No production module top-level code, filesystem helpers or wrappers run.
"""

import ast
import hashlib
import html
import json
import os
import pathlib
import re
from types import SimpleNamespace
import unittest

from patch_yadro import EXPECTED_SHA256, patch_yadro
from patch_stranica import patch_stranica
from uaart_market_prices import END, START, render_market_prices


def base_renderers(source):
    tree = ast.parse(source)
    names = {"ekran", "t", "dengi", "nomer", "nazvanie", "etap", "_schet_mashin", "karta_html", "katalog_html"}
    selected = []
    seen = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names and node.name not in seen:
            selected.append(node)
            seen.add(node.name)
    if seen != names:
        raise AssertionError("BASE_FUNCTIONS_MISSING")
    namespace = {"_html": html, "_ua088_render_market_prices": render_market_prices}
    constants = {"ADRES_SAYTA", "ETAP_KOROTKO", "ETAP_ZNACHOK", "ETAP_CVET", "FILTRY", "STIL_KARTY", "SVOJSTVA", "TELEFON_TEL", "TELEFON_VID"}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in constants:
            namespace[node.targets[0].id] = ast.literal_eval(node.value)
    for name in ("golova", "hdr", "blok_share", "ftr", "kontakty_stroka", "na_glavnuyu"):
        namespace[name] = lambda *args, _name=name, **kwargs: "<fixture-%s>%s</fixture-%s>" % (_name, repr((args, kwargs)), _name)
    namespace["hvost"] = lambda: "</body></html>"
    namespace["wa_ssylka"] = lambda text: "https://wa.me/fixture?text=" + html.escape(text)
    namespace["blok_marshruta"] = lambda row: "<fixture-route>%s</fixture-route>" % row["status"]
    exec(compile(ast.Module(body=selected, type_ignores=[]), "selected_pure_ast", "exec"), namespace)
    return namespace


def master_base_renderers(source):
    tree = ast.parse(source)
    names = {"ekran", "cena", "nomer", "etap_dlinno", "etap_korotko", "sobrat_kartochku", "sobrat_katalog"}
    selected = []
    seen = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names and node.name not in seen:
            selected.append(node)
            seen.add(node.name)
    if seen != names:
        raise AssertionError("MASTER_BASE_FUNCTIONS_MISSING")
    namespace = {
        "_ua088_render_market_prices": render_market_prices,
        "os": SimpleNamespace(path=SimpleNamespace(exists=lambda _: False, join=os.path.join)),
        "time": SimpleNamespace(time=lambda: 1234567890), "json": json,
        "PAPKA_VID": "/private-test-no-access", "STIL": "fixture-css",
        "VALYUTA": "USD", "BRON_USD": 500,
        "USPEH_BLOK": "<fixture-success />", "CHAT_KNOPKA": "<fixture-chat />", "SKRIPT_TG": "<fixture-telegram />",
        "shapka": lambda: "<fixture-header />",
        "podval": lambda *args: "<fixture-footer>%s</fixture-footer>" % repr(args),
        "v_bota": lambda text: "https://t.me/fixture?start=" + text,
        "_ua_delivery_stage_anchor": lambda row: "<fixture-route>%s</fixture-route>" % row["status"],
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), "selected_master_pure_ast", "exec"), namespace)
    return namespace


@unittest.skipUnless(os.environ.get("UA088_LIVE_SOURCE_DIR"), "Private snapshot path not supplied")
class LiveSourceDifferentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (pathlib.Path(os.environ["UA088_LIVE_SOURCE_DIR"]) / "yadro.py").read_bytes()
        cls.candidate, cls.provenance = patch_yadro(cls.source)
        cls.before = base_renderers(cls.source.decode("utf-8"))
        cls.after = base_renderers(cls.candidate.decode("utf-8"))

    def model(self, number, stage="ua_ready", **extra):
        return dict(auto_number="UA-%04d" % number, brand="Fixture", model="Preserved", year=2020,
                    status=stage, price_uah=9000 + number, price_georgia=7000 + number,
                    vin="TEST0000000001234", mileage_km=123456, description="Description and special < > & preserved", **extra)

    def test_all_eighteen_cards_outside_price_fragment_byte_identical(self):
        for number in range(1, 19):
            row = self.model(number, ("kr_ready", "sea_ready", "ge_ready", "ua_ready")[number % 4])
            photos = ["%s-01.jpg" % row["auto_number"], "%s-02.jpg" % row["auto_number"]]
            before = self.before["karta_html"](row, photos)
            after = self.after["karta_html"](row, photos)
            price = re.search(r'<div><div class="cn_b">.*?</div></div>', before)
            self.assertIsNotNone(price)
            self.assertEqual(after.replace(render_market_prices(row), price.group(0), 1), before)
            self.assertEqual(after.count(START), 1)
            self.assertEqual(after.count(END), 1)

    def test_eighteen_car_catalog_outside_price_fragments_byte_identical(self):
        rows = [self.model(number, ("kr_ready", "sea_ready", "ge_ready", "ua_ready")[number % 4]) for number in range(1, 19)]
        photos = {row["auto_number"]: [row["auto_number"] + ".jpg"] for row in rows}
        videos = {row["auto_number"]: True for row in rows}
        before = self.before["katalog_html"](rows, photos, videos)
        after = self.after["katalog_html"](rows, photos, videos)
        restored = after
        for row in rows:
            old = '<div class="cn">%s</div>' % self.before["ekran"](self.before["dengi"](row["price_uah"]))
            restored = restored.replace(render_market_prices(row, compact=True), old, 1)
        restored = restored.replace("цены для Украины и Грузии", "цены под ключ в Киеве").replace("ціни для України та Грузії", "ціни під ключ у Києві")
        self.assertEqual(restored, before)
        self.assertEqual(after.count(START), 18)
        self.assertEqual(after.count(END), 18)
        self.assertIn("цены для Украины и Грузии", after)
        self.assertIn("ціни для України та Грузії", after)
        self.assertNotIn("цены под ключ в Киеве", after)

    def test_missing_both_prices_changes_only_former_empty_card_slot(self):
        row = self.model(10)
        row.update(price_uah=None, price_georgia=None)
        before = self.before["karta_html"](row, [])
        after = self.after["karta_html"](row, [])
        self.assertEqual(after.replace(render_market_prices(row), "", 1), before)

    def test_candidate_compiles_and_wrappers_remain_exact(self):
        compile(self.candidate, "candidate_yadro.py", "exec")
        self.assertEqual(self.provenance["wrappers_unchanged"], 5)
        self.assertEqual(self.provenance["price_statements_replaced"], 2)
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), EXPECTED_SHA256)

    def test_source_drift_is_rejected(self):
        for mutated in (self.source + b"\n", self.source.replace(b"price_uah", b"price_other", 1), self.candidate):
            with self.assertRaisesRegex(ValueError, "YADRO_SOURCE_HASH_MISMATCH"):
                patch_yadro(mutated)


@unittest.skipUnless(os.environ.get("UA088_LIVE_SOURCE_DIR"), "Private snapshot path not supplied")
class MasterSourceDifferentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (pathlib.Path(os.environ["UA088_LIVE_SOURCE_DIR"]) / "stranica.py").read_bytes()
        cls.candidate, cls.provenance = patch_stranica(cls.source)
        cls.before = master_base_renderers(cls.source.decode("utf-8"))
        cls.after = master_base_renderers(cls.candidate.decode("utf-8"))

    model = LiveSourceDifferentialTest.model

    def test_master_eighteen_cards_only_price_and_caption_change(self):
        for number in range(1, 19):
            row = self.model(number, ("kr_ready", "sea_ready", "ge_ready", "ua_ready")[number % 4])
            photos = [row["auto_number"] + "-01.jpg", row["auto_number"] + "-02.jpg"]
            before = self.before["sobrat_kartochku"](row, photos)
            after = self.after["sobrat_kartochku"](row, photos)
            previous = re.search(r"<div class='cena' style='margin-top:14px'>.*?</div><div class='tihо'>.*?</div>", before)
            self.assertIsNotNone(previous)
            self.assertEqual(after.replace(render_market_prices(row), previous.group(0), 1), before)

    def test_master_eighteen_catalog_items_only_price_changes(self):
        rows = [self.model(number, ("kr_ready", "sea_ready", "ge_ready", "ua_ready")[number % 4]) for number in range(1, 19)]
        photos = {row["auto_number"]: [row["auto_number"] + "-01.jpg", row["auto_number"] + "-02.jpg"] for row in rows}
        before = self.before["sobrat_katalog"](rows, photos)
        after = self.after["sobrat_katalog"](rows, photos)
        restored = after
        for row in rows:
            old = "<div class='cn'>%s</div>" % self.before["cena"](row)
            restored = restored.replace(render_market_prices(row, compact=True), old, 1)
        restored = restored.replace("цены для Украины и Грузии", "цены под ключ в Киеве")
        self.assertEqual(restored, before)
        self.assertEqual(after.count(START), 18)
        self.assertIn("цены для Украины и Грузии", after)
        self.assertNotIn("цены под ключ в Киеве", after)

    def test_master_wrapper_integrity_and_full_compile(self):
        self.assertTrue(self.provenance["candidate_compiles"])
        self.assertEqual(self.provenance["wrappers_unchanged"], 7)
        compile(self.candidate, "stranica.py", "exec")

    def test_master_input_drift_and_reapply_rejected(self):
        for changed in (self.source + b"\n", self.candidate):
            with self.assertRaisesRegex(ValueError, "STRANICA_SOURCE_HASH_MISMATCH"):
                patch_stranica(changed)


if __name__ == "__main__":
    unittest.main()
