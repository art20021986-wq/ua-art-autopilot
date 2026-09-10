import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from ua_spec_permanent import ensure_html, owned_spans, validate_block, write_lock, SpecMarkupError, START, END, SECTION_ID

RENDERER_PATH = Path(os.environ.get(
    "UA_ART_SPEC_TEST_RENDERER",
    str(Path(__file__).resolve().parent.parent / "task_099_site_crm_repair/ua_additional_spec.py"),
))


def load_renderer():
    if not RENDERER_PATH.is_file():
        raise unittest.SkipTest("Renderer unavailable; set UA_ART_SPEC_TEST_RENDERER to a local renderer file")
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("_test_legacy_renderer", loader=None))
    exec(compile(RENDERER_PATH.read_bytes(), str(RENDERER_PATH), "exec"), module.__dict__)
    return module


class PermanentSpecTests(unittest.TestCase):
    def setUp(self):
        self.renderer = load_renderer()
        self.renderer.fetch_specs = lambda uid: []
        self.source = ("<!doctype html><html><head><title>UA-0017</title></head><body><main>"
                       "<div class='nom'>UA-0017</div><p>VIN WAU00000000012345; 23 000 $; На пароме</p>"
                       "<video src='/media/car.mp4'></video><a href='/buy'>Задаток 500 $</a>"
                       "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->Stage content</main></body></html>")

    def render(self, source=None):
        return ensure_html(source or self.source, "UA-0017", renderer=self.renderer.render_public_block, css=self.renderer._css)

    def set_rows(self, rows):
        self.renderer.fetch_specs = lambda uid: rows

    def test_empty_control_and_repeat_preserve_every_other_byte(self):
        result = self.render()
        self.assertEqual(owned_spans(result)[1], self.source)
        self.assertEqual(result.count("<summary>"), 1)
        self.assertIn("id='" + SECTION_ID + "'", result)
        self.assertIn("Дополнительные характеристики пока не найдены.", result)
        self.assertEqual(self.render(result), result)
        self.assertNotIn(".ua-clean-vin", result)

    def test_fields_are_escaped_and_stage_rebuild_retains_facts(self):
        self.set_rows([{"category": "engine", "label_ru": "Момент <точный>", "field_value": "A & B < 300", "unit": ""}])
        result = self.render()
        self.assertIn("Момент &lt;точный&gt;", result)
        self.assertIn("A &amp; B &lt; 300", result)
        rebuilt = self.render(self.source.replace("На пароме", "В Киеве"))
        self.assertIn("A &amp; B &lt; 300", rebuilt)
        self.assertEqual(owned_spans(rebuilt)[1], self.source.replace("На пароме", "В Киеве"))

    def test_existing_legacy_style_is_preserved_including_vin_presentation(self):
        legacy_css = self.renderer._css()
        source = self.source.replace("</head>", legacy_css + "</head>")
        source = source.replace("</main>", self.renderer.render_public_block("UA-0017") + "</main>")
        result = self.render(source)
        self.assertIn(legacy_css, result)
        self.assertEqual(owned_spans(result)[1], self.source)

    def test_renderer_failure_retains_current_facts_and_new_page_stays_usable(self):
        self.set_rows([{"category": "engine", "label_ru": "Мощность", "field_value": "240", "unit": "hp"}])
        prior = self.render()
        def fail(uid):
            raise OSError("database temporarily unavailable")
        self.assertEqual(ensure_html(prior, "UA-0017", renderer=fail, css=self.renderer._css), prior)
        fresh = ensure_html(self.source, "UA-0017", renderer=fail, css=self.renderer._css)
        self.assertIn("<summary>", fresh)
        self.assertIn("0 параметров", fresh)

    def test_successful_visibility_change_does_not_reveal_hidden_old_facts(self):
        self.set_rows([{"category": "engine", "label_ru": "Мощность", "field_value": "240", "unit": "hp"}])
        prior = self.render()
        self.set_rows([])
        result = self.render(prior)
        self.assertNotIn("240", result)
        self.assertIn("0 параметров", result)

    def test_ambiguous_duplicates_or_foreign_content_refuse_before_write(self):
        prior = self.render()
        block = self.renderer.render_public_block("UA-0017")
        for malformed in (prior.replace("</body>", block + "</body>"),
                          self.source.replace("</body>", START + "<p>foreign</p>" + END + "</body>"),
                          self.source.replace("</body>", "<div class='ua-additional-spec'>foreign</div></body>")):
            with self.assertRaises(SpecMarkupError):
                self.render(malformed)

    def test_unsafe_renderer_output_never_embedded(self):
        unsafe = self.renderer.render_public_block("UA-0017").replace("0 параметров", "https://ads.invalid")
        result = ensure_html(self.source, "UA-0017", renderer=lambda uid: unsafe, css=self.renderer._css)
        self.assertNotIn("ads.invalid", result)
        self.assertIn("0 параметров", result)

    def test_fallback_anchor_without_delivery_marker(self):
        source = self.source.replace("<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->", "")
        result = self.render(source)
        self.assertEqual(owned_spans(result)[1], source)
        self.assertLess(result.index(START), result.index("</main>"))

    def test_actual_renderer_respects_hidden_and_manual_database_rows(self):
        module = load_renderer()
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "spec.db"
            with sqlite3.connect(database) as conn:
                conn.executescript("""
                    CREATE TABLE additional_specification(id INTEGER, car_uid TEXT, field_key TEXT,
                      field_value TEXT, confidence REAL, is_price_field INTEGER);
                    CREATE TABLE additional_specification_meta(car_uid TEXT, field_key TEXT,
                      label_ru TEXT, category TEXT, unit TEXT, verification_status TEXT,
                      evidence_count INTEGER, source_domains_json TEXT, is_manual INTEGER, is_visible INTEGER);
                    INSERT INTO additional_specification VALUES(1,'UA-0017','power','240',1,0);
                    INSERT INTO additional_specification VALUES(2,'UA-0017','hidden','SECRET',1,0);
                    INSERT INTO additional_specification_meta VALUES('UA-0017','power','Мощность','engine','hp','VERIFIED',1,'[]',1,1);
                    INSERT INTO additional_specification_meta VALUES('UA-0017','hidden','Скрыто','engine','','VERIFIED',1,'[]',0,0);
                """)
            before = database.read_bytes()
            module.DB_PATH = module._UA110_SPEC_DB_PATH = database
            result = ensure_html(self.source, "UA-0017", renderer=module.render_public_block, css=module._css)
            self.assertIn("240 hp", result)
            self.assertNotIn("SECRET", result)
            self.assertEqual(database.read_bytes(), before)

    def test_write_lock_is_reentrant_but_excludes_other_threads(self):
        with tempfile.TemporaryDirectory() as folder:
            observed = []
            def contender():
                try:
                    with write_lock(folder, timeout=0.03):
                        observed.append("unexpected acquired")
                except TimeoutError:
                    observed.append("blocked")
            with write_lock(folder):
                inode = (Path(folder) / ".ua_spec84_write.lock").stat().st_ino
                with write_lock(folder):
                    thread = threading.Thread(target=contender)
                    thread.start()
                    thread.join(1)
            with write_lock(folder):
                self.assertEqual((Path(folder) / ".ua_spec84_write.lock").stat().st_ino, inode)
            self.assertEqual(observed, ["blocked"])

    def test_unknown_or_changed_vin_cannot_fallback_to_previous_html_facts(self):
        self.set_rows([{"category": "engine", "label_ru": "Мощность", "field_value": "240", "unit": "hp"}])
        prior = self.render()
        runtime = types.ModuleType("ua_spec84_runtime")
        def unknown(uid):
            raise OSError("identity database unavailable")
        for check in (lambda uid: False, unknown):
            runtime.fact_binding_matches = check
            with patch.dict(sys.modules, {"ua_additional_spec": self.renderer, "ua_spec84_runtime": runtime}):
                result = ensure_html(prior, "UA-0017")
            self.assertNotIn("240 hp", result)
            self.assertIn("0 параметров", result)


if __name__ == "__main__":
    unittest.main()
