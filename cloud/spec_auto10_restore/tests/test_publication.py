import copy
import importlib.util
import re
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))
spec = importlib.util.spec_from_file_location("spec_publication_test", RUNTIME / "spec_publication.py")
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)

PAGE = ('<!doctype html><html><head><style>.card{color:white}</style></head><body><h1>UA-0001</h1>'
        '<p>Price 17849</p><video src="unchanged.mp4"></video>'
        "<table><tr><td class='k'>VIN</td><td>WDDZF0EB7HA053001</td></tr></table>"
        '<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START --><div>Stage 2</div>'
        '<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END --></body></html>')
CARD = {"car_uid": "UA-0001", "vin": "WDDZF0EB7HA053001", "published": True}
FACTS = [{"field_key": "length", "label_ru": "Длина", "field_value": "4923", "unit": "мм",
          "category": "dimensions", "verification_status": "VERIFIED_10SRC", "is_visible": 1}]
PANEL = ('<!-- UA-ART-VIN-GUARD-LITE-V1:START -->'
         '<div class="blok ua-clean-vin" data-ua-clean-vin="1" data-ua-card="UA-0001" data-ua-stage="2" data-ua-video-count="1">'
         '<div class="zag">VIN</div><div class="ua-vin-value">WDDZF0EB7HA053001</div></div>'
         '<!-- UA-ART-VIN-GUARD-LITE-V1:END -->')


class PublicationTests(unittest.TestCase):
    def test_regeneration_keeps_exact_non_spec_bytes_and_one_section(self):
        once = publication.inject(PAGE, "UA-0001", FACTS)
        twice = publication.inject(once, "UA-0001", FACTS)
        self.assertEqual(once, twice)
        self.assertEqual(publication.strip_block(once), PAGE)
        self.assertEqual(once.count('data-ua-additional-spec="1"'), 1)
        self.assertIn("Додаткова специфікація", once)

    def test_summary_exposes_native_tap_control_and_localized_action(self):
        block = publication.render_block("UA-0001", FACTS)
        summary = re.search(r"<summary>(.*?)</summary>", block).group(1)
        visible_text = re.sub(r"<[^>]*>", " ", summary)
        self.assertIn("Додаткова специфікація", visible_text)
        self.assertIn("Переглянути характеристики", visible_text)
        self.assertIn('data-ru="Дополнительная спецификация"', summary)
        self.assertIn('data-ru="Посмотреть характеристики"', summary)
        self.assertIn('data-uk="Переглянути характеристики"', summary)
        self.assertIn('data-ua="Переглянути характеристики"', summary)
        self.assertIn("min-height:44px", block)
        self.assertIn("min-width:0;overflow-wrap:anywhere", block)
        self.assertNotRegex(block, r"<script|<a\b|onclick=|role=\"button\"")
        self.assertRegex(block, r"<details\b[^>]*><summary>")

    def test_partial_facts_allowed_and_empty_is_explicit_not_ready(self):
        ready = publication.inject(PAGE, "UA-0001", FACTS)
        self.assertEqual(publication.validate_page(ready, "UA-0001", FACTS, previous=PAGE)["rows"], 1)
        empty = publication.inject(PAGE, "UA-0001", [])
        self.assertEqual(publication.validate_page(empty, "UA-0001", [], previous=PAGE)["data_status"], "NEEDS_REVIEW")

    def test_no_confirmed_field_loss(self):
        old = publication.inject(PAGE, "UA-0001", FACTS)
        with self.assertRaisesRegex(publication.SpecError, "LOST"):
            publication.inject(old, "UA-0001", [])

    def test_manual_is_rendered_pending_hidden_are_not(self):
        facts = copy.deepcopy(FACTS)
        facts[0]["verification_status"] = "MANUAL_VERIFIED"
        self.assertEqual(len(publication.normalize_facts(facts)), 1)
        facts[0]["verification_status"] = "IDENTITY_CHANGED_REVIEW"
        self.assertEqual(publication.normalize_facts(facts), [])

    def test_provider_html_prices_and_vin_ads_rejected(self):
        for value in ('<script>alert(1)</script>', 'https://carhistory.kr', 'cost $5'):
            with self.subTest(value=value):
                facts = copy.deepcopy(FACTS)
                facts[0]["field_value"] = value
                with self.assertRaises(publication.SpecError):
                    publication.inject(PAGE, "UA-0001", facts)
        with self.assertRaisesRegex(publication.SpecError, "VIN_ADVERTISEMENT"):
            publication.inject(PAGE.replace('</body>', '<a href="https://carhistory.kr">VIN</a></body>'), "UA-0001", FACTS)

    def test_malformed_duplicate_and_unknown_anchor_fail_closed(self):
        for page in (PAGE + publication.START, PAGE + publication.START + publication.END + publication.START + publication.END,
                     '<html><body>no known anchor</body></html>'):
            with self.assertRaises(publication.SpecError):
                publication.inject(page, "UA-0001", FACTS)

    def test_tampered_and_foreign_data_fail(self):
        page = publication.inject(PAGE, "UA-0001", FACTS)
        with self.assertRaises(publication.SpecError):
            publication.validate_page(page.replace('4923', '9999'), "UA-0001", FACTS)
        with self.assertRaises(publication.SpecError):
            publication.validate_page(page, "UA-0002", FACTS)

    def _runtime(self, root):
        for folder in ("video", "site"):
            (root / folder).mkdir()
            (root / folder / "UA-0001.html").write_text(PAGE)

    def test_sync_changes_only_spec_and_verifies_public(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._runtime(root)
            calls = []
            def reader(code):
                calls.append(code)
                return (root / "video" / (code + ".html")).read_text()
            args = dict(root=root, public_reader=reader, state_reader=lambda code: (CARD, FACTS))
            result = publication.reconcile_published(CARD, FACTS, **args)
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(calls, ["UA-0001"])
            self.assertEqual(publication.strip_block((root / "video/UA-0001.html").read_text()), PAGE)
            self.assertEqual(publication.reconcile_published(CARD, FACTS, **args)["status"], "UNCHANGED")

    def test_public_failure_remains_failure_and_can_retry_without_fetch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._runtime(root)
            result = publication.reconcile_published(CARD, FACTS, root=root,
                public_reader=lambda code: PAGE, state_reader=lambda code: (CARD, FACTS))
            self.assertEqual(result["status"], "FAIL")
            result = publication.reconcile_published(CARD, FACTS, root=root,
                public_reader=lambda code: (root / "video/UA-0001.html").read_text(), state_reader=lambda code: (CARD, FACTS))
            self.assertEqual(result["status"], "UNCHANGED")

    def test_local_partial_write_failure_restores_own_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._runtime(root)
            atomic = publication._atomic
            def fail_second(path, data):
                if path.parent.name == "site":
                    raise OSError("fixture disk failure")
                return atomic(path, data)
            with patch.object(publication, "_atomic", fail_second):
                result = publication.reconcile_published(CARD, FACTS, root=root,
                    public_reader=lambda code: self.fail("Should not verify failed transaction"),
                    state_reader=lambda code: (CARD, FACTS))
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual((root / "video/UA-0001.html").read_text(), PAGE)
            self.assertEqual((root / "site/UA-0001.html").read_text(), PAGE)

    def test_draft_does_not_touch_files_or_network(self):
        result = publication.reconcile_published({**CARD, "published": False}, FACTS,
            public_reader=lambda code: self.fail("Draft network call"))
        self.assertEqual(result["status"], "NOT_REQUIRED")

    def test_stale_vehicle_or_manual_facts_do_not_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._runtime(root)
            changed = {**CARD, "vin": "changed"}
            result = publication.reconcile_published(CARD, FACTS, root=root,
                public_reader=lambda code: self.fail("stale card should not publish"),
                state_reader=lambda code: (changed, FACTS))
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual((root / "video/UA-0001.html").read_text(), PAGE)

    def test_live_writer_blocks_missing_section_but_ignores_non_primary_files(self):
        with tempfile.TemporaryDirectory() as folder:
            primary = Path(folder) / "UA-0001.html"
            with patch.object(publication, "load_facts", return_value=FACTS):
                with self.assertRaisesRegex(publication.SpecError, "BLOCK_MISSING"):
                    publication.guard_write(primary, PAGE.encode())
                publication.guard_write(primary.with_name("UA-0001-diag.html"), b"diagnostics")

    def test_common_inject_removes_proven_duplicate_before_every_rebuild(self):
        source = PAGE.replace('</body>', PANEL + '</body>')
        once = publication.inject(source, "UA-0001", FACTS)
        self.assertEqual(publication.strip_block(once), PAGE)
        self.assertEqual(publication.inject(once, "UA-0001", FACTS), once)
        result = publication.validate_page(once, "UA-0001", FACTS, previous=source)
        self.assertEqual(result["visible_vin_count"], 1)
        self.assertEqual(publication.card_shell.permitted_delta(source, once, "UA-0001")["outside_permitted_regions_byte_changes"], 0)

    def test_standalone_block_validation_never_substitutes_for_page_validation(self):
        block = publication.render_block("UA-0001", FACTS)
        self.assertEqual(publication.validate_block(block, "UA-0001", FACTS)["rows"], 1)
        with self.assertRaisesRegex(publication.SpecError, "SHELL_MAIN_VIN"):
            publication.validate_page(block, "UA-0001", FACTS)
        full_page = publication.inject(PAGE, "UA-0001", FACTS)
        with self.assertRaisesRegex(publication.SpecError, "STANDALONE_SPECIFICATION_FRAGMENT_REQUIRED"):
            publication.validate_block(full_page, "UA-0001", FACTS)

    def test_existing_writer_allows_card_values_and_gallery_but_blocks_shell_or_vin_regression(self):
        before = publication.inject(PAGE, "UA-0001", FACTS)
        with tempfile.TemporaryDirectory() as folder, patch.object(publication, "load_facts", return_value=FACTS):
            path = Path(folder) / "UA-0001.html"
            path.write_text(before)
            edited = before.replace("Price 17849", "Price 19000").replace("unchanged.mp4", "new-gallery.mp4").replace("<h1>UA-0001</h1>", "<h1>Updated vehicle title</h1>")
            publication.guard_write(path, edited.encode())
            for invalid in (edited.replace("color:white", "color:red"), edited + PANEL,
                            edited.replace('</body>', '<p>VIN: WDDZF0EB7HA053001</p></body>')):
                with self.assertRaises(publication.SpecError):
                    publication.guard_write(path, invalid.encode())
            self.assertEqual(path.read_text(), before)

    def test_new_writer_requires_reviewed_template_pin(self):
        assets = (Path(__file__).parent / "fixtures/reviewed_shell_assets.html").read_text()
        reviewed = PAGE.replace('<style>.card{color:white}</style>', assets)
        candidate = publication.inject(reviewed, "UA-0001", FACTS)
        with tempfile.TemporaryDirectory() as folder, patch.object(publication, "load_facts", return_value=FACTS):
            path = Path(folder) / "UA-0001.html"
            publication.guard_write(path, candidate.encode())
            self.assertFalse(path.exists())
            self.assertEqual(publication.validate_page(candidate, "UA-0001", FACTS)["shell_reference"], "reviewed_template_pin")
            with self.assertRaisesRegex(publication.SpecError, "UNREVIEWED_NEW_CARD_SHELL_ASSETS"):
                publication.guard_write(path, publication.inject(PAGE, "UA-0001", FACTS).encode())
            with self.assertRaisesRegex(publication.SpecError, "UNREVIEWED_NEW_CARD_SHELL_ASSETS"):
                publication.guard_write(path, candidate.replace("telegram-web-app.js", "unexpected.js").encode())

    def test_reconciliation_rejects_public_shell_loss_even_if_specification_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._runtime(root)
            result = publication.reconcile_published(CARD, FACTS, root=root,
                public_reader=lambda code: (root / "video/UA-0001.html").read_text().replace("color:white", "color:red"),
                state_reader=lambda code: (CARD, FACTS))
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("SHELL_STATIC_ASSETS_CHANGED", result["detail"])

    def test_reallocated_database_id_cannot_resume_old_uid_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._runtime(root)
            original = {**CARD, "car_id": 1}
            current = {**CARD, "car_id": 2}
            result = publication.reconcile_published(original, FACTS, root=root,
                public_reader=lambda code: self.fail("Reallocated UID must not reach public GET"),
                state_reader=lambda code: (current, FACTS))
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("CARD_CHANGED_DURING_SPECIFICATION_SYNC", result["detail"])
            self.assertEqual((root / "video/UA-0001.html").read_text(), PAGE)


if __name__ == "__main__":
    unittest.main()
