"""Check catalog adapters against pinned source files without touching production."""

import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from integration_patch import SOURCE_SHA256, patch_catalog_design, patch_sync


ARTICLE = '''<article class="catalog-card" data-stage="kiev">
<a href="UA-0001.html" class="catalog-photo"><img src="/video/test.webp" alt="Test"><span class="photo-count">1 фото</span></a>
<div class="catalog-body"><div class="catalog-top"><span>UA-0001</span><b>1 $</b></div>
<h2>Test</h2><div class="status-pill" data-ru="В Киеве" data-uk="У Києві">В Киеве</div>
<p>1 км · 1 см³ · бензин · автомат</p>
<a class="card-arrow" href="UA-0001.html" aria-label="Карточка"><svg><path d="M5 12h14"/></svg></a>
</div></article>'''
GOLDEN = '''<!doctype html><html><body>
<nav><button data-lang="ru">RU</button><button data-lang="uk">UA</button></nav>
<div class="schet">1 в подборке</div>
<button data-f="all">Все · 1</button><button data-f="kiev">В Киеве · 1</button>
<button data-f="georgia">В Грузии · 0</button><button data-f="sea">На пароме · 0</button>
<button data-f="korea">В Корее · 0</button><div class="catalog-result">Показано: 1</div>
<div class="catalog-grid">''' + ARTICLE + '''</div>
<a href="https://wa.me/000">WhatsApp</a><footer>Test</footer></body></html>'''


def row(number, status):
    return {"auto_number": "UA-%04d" % number, "published": 1, "status": status,
            "brand": "Test", "model": "Car", "year": "2020", "price": 1,
            "vin": "TESTVIN%010d" % number, "mileage_km": 1, "engine_cc": 1}


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CatalogIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.sandbox.cleanup)
        target = Path(cls.sandbox.name)
        original = Path(os.environ.get("DELIVERY_SOURCE_ROOT", "/home/Carix"))
        cls.modules = patch.dict(sys.modules)
        cls.modules.start()
        cls.addClassCleanup(cls.modules.stop)
        policy_path = target / "ua_delivery_status.py"
        policy_path.write_bytes(Path(__file__).with_name("delivery_status.py").read_bytes())
        load_module(policy_path)
        for name, transform, attribute in (
            ("catalog_design_guard.py", patch_catalog_design, "design"),
            ("ua_stage_catalog_sync.py", patch_sync, "sync"),
        ):
            content = (original / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != SOURCE_SHA256[name]:
                raise ValueError("SOURCE_CHANGED:" + name)
            candidate = target / name
            candidate.write_text(transform(content.decode("utf-8")), encoding="utf-8")
            setattr(cls, attribute, load_module(candidate))

    def build(self, rows):
        return self.design.build_catalog(
            GOLDEN, rows, {r["auto_number"]: "/video/test.webp" for r in rows})

    def test_four_active_counts(self):
        rows = [row(i, code) for i, code in enumerate(
            ("kr_bought", "sea_loaded", "ge_waiting", "ua_arrived"), 1)]
        audit = self.design.audit_catalog(self.build(rows), rows, GOLDEN)
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["counts"], {"all": 4, "korea": 1, "sea": 1, "georgia": 1, "kiev": 1})

    def test_hidden_and_unknown_excluded(self):
        rows = [row(1, "ferry")] + [row(i, status) for i, status in enumerate(
            ("archive", "sold", "sold_transit", "ge_to_kyiv", "hidden", "sea_unknown", None, [], {}), 2)]
        result = self.build(rows)
        audit = self.design.audit_catalog(result, rows, GOLDEN)
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["ids"], ["UA-0001"])
        self.assertEqual(audit["counts"]["sea"], 1)

    def test_all_hidden_produces_valid_empty_shell(self):
        rows = [row(1, "hidden"), row(2, "archive")]
        result = self.build(rows)
        audit = self.design.audit_catalog(result, rows, GOLDEN)
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["article_cards"], 0)
        self.assertTrue(all(value == 0 for value in audit["counts"].values()))
        self.assertIn("Все · 0", result)
        self.assertEqual(self.design.shell_fingerprint(result), self.design.shell_fingerprint(GOLDEN))

    def test_empty_shell_checks_remain_active(self):
        empty = self.build([])
        broken = empty.replace("<footer>", "<div>").replace("</footer>", "</div>")
        self.assertEqual(self.design.audit_catalog(broken, [], GOLDEN)["status"], "FAIL")
        self.assertEqual(self.design.audit_catalog(empty, [row(1, "korea")], GOLDEN)["status"], "FAIL")

    def test_full_render_can_reactivate_car_after_empty_catalog(self):
        self.build([row(1, "hidden")])
        active = [row(1, "ferry")]
        self.assertEqual(self.design.audit_catalog(self.build(active), active, GOLDEN)["ids"], ["UA-0001"])

    def test_sync_removes_one_hidden_car(self):
        before = self.build([row(1, "ferry"), row(2, "kyiv")])
        rows = {r["auto_number"]: r for r in (row(1, "ferry"), row(2, "hidden"))}
        result, changed = self.sync.patch_catalog_stages(before, rows)
        self.assertEqual(changed, ["UA-0002"])
        self.assertEqual(self.design.audit_catalog(result, rows.values(), GOLDEN)["status"], "PASS")
        self.assertNotIn("UA-0002", result)

    def test_sync_empty_is_valid_and_idempotent(self):
        before = self.build([row(1, "korea"), row(2, "kyiv")])
        rows = {r["auto_number"]: r for r in (row(1, "hidden"), row(2, "archive"))}
        result, changed = self.sync.patch_catalog_stages(before, rows)
        self.assertEqual(changed, ["UA-0001", "UA-0002"])
        self.assertEqual(self.design.audit_catalog(result, [], GOLDEN)["status"], "PASS")
        self.assertEqual(self.sync.patch_catalog_stages(result, rows), (result, []))

    def test_sync_rejects_missing_active_car(self):
        with self.assertRaises(self.sync.StageSyncError):
            self.sync.patch_catalog_stages(self.build([]), {"UA-0001": row(1, "korea")})


if __name__ == "__main__":
    unittest.main()
