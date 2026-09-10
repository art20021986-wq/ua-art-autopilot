"""Synthetic markup only; no copied customer page or real VIN."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cloud.spec_rebuild10 import render


UID = "UA-9999"
# A deliberate synthetic alphabet-valid token; never a customer's identifier.
VIN = "A" * 17
FACTS = [
    {"key": "length", "value": "4900", "unit": "мм", "category": "dimensions",
     "label_uk": "Довжина", "label_ru": "Длина", "verification_status": "VERIFIED"},
    {"field_key": "doors", "field_value": "4", "category": "capacity",
     "label_ru": "Количество дверей", "is_visible": 1, "verification_status": "MANUAL_VERIFIED"},
]


def page(duplicate=True):
    dup = ("<!-- UA-ART-VIN-GUARD-LITE-V1:START -->"
           '<div class="blok ua-clean-vin" data-ua-clean-vin="1" data-ua-card="UA-9999" '
           'data-ua-stage="2" data-ua-video-count="0"><div class="zag">VIN</div>'
           '<div class="ua-vin-value">' + VIN + '</div></div>'
           "<!-- UA-ART-VIN-GUARD-LITE-V1:END -->") if duplicate else ""
    return ('<!doctype html><html><head><style>.base{color:white}</style>'
            '<script src="https://example.invalid/existing.js"></script></head><body>'
            '<header>Existing shell</header><main><table><tr><td class="k">VIN</td><td>'
            + VIN + '</td></tr></table>'
            '<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->'
            '<section>Delivery unchanged</section><!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END -->'
            + dup + '<a href="UA-9999-diag.html">Diagnostics unchanged</a>'
            '<img src="car.jpg" alt="Car"><p>Original description</p></main><footer>Existing footer</footer>'
            '</body></html>')


class RendererTests(unittest.TestCase):
    def test_link_is_visible_and_targets_native_expanded_section(self):
        result = render.compose_page(page(), UID, FACTS)
        self.assertIn('href="#additional-specification"', result)
        self.assertIn('<section id="additional-specification"', result)
        self.assertIn('>Додаткова специфікація →</span>', result)
        block = result[result.index(render.START):result.index(render.END)]
        self.assertNotIn("<script", block)
        self.assertNotIn("<iframe", block)
        self.assertNotIn("onclick", block)
        self.assertNotIn("<details class=\"blok", block)
        report = render.validate_page(result, UID, FACTS, previous=page())
        self.assertEqual(report["visible_vin_count"], 1)
        self.assertEqual(report["shell_delta"]["outside_permitted_regions_byte_changes"], 0)
        self.assertFalse(report["javascript_required"])

    def test_exact_outside_block_and_assets_preserved(self):
        before = page()
        result = render.compose_page(before, UID, FACTS)
        expected = render.shell_guard.normalize_html(before, UID)
        self.assertEqual(render._without_block(result), expected)
        self.assertEqual(result.count(VIN), 1)
        self.assertEqual(render.shell_guard._shell_assets(before), render.shell_guard._shell_assets(result))

    def test_composition_is_idempotent(self):
        first = render.compose_page(page(), UID, FACTS)
        self.assertEqual(first, render.compose_page(first, UID, FACTS))

    def test_unknown_duplicate_vin_fails_closed(self):
        before = page(False).replace("<footer>", "<p>" + VIN + "</p><footer>")
        with self.assertRaisesRegex(render.SpecError, "VISIBLE_VIN"):
            render.compose_page(before, UID, FACTS)

    def test_empty_hidden_or_unverified_facts_render_visible_pending_section(self):
        for facts in ([], [{"key": "length", "value": "9998", "verification_status": "PENDING"}],
                      [{"key": "length", "value": "9998", "is_visible": 0,
                        "verification_status": "VERIFIED"}]):
            with self.subTest(facts=facts):
                self.assertEqual(render.normalize_facts(facts), [])
                result = render.compose_page(page(), UID, facts)
                self.assertIn('href="#additional-specification"', result)
                self.assertIn('<section id="additional-specification"', result)
                self.assertIn('data-spec-status="PENDING"', result)
                self.assertIn('>Додаткові характеристики уточнюються.</span>', result)
                self.assertNotIn('data-spec-key=', result)
                self.assertNotIn("9998", result)
                report = render.validate_page(result, UID, facts, previous=page())
                self.assertEqual(report["data_status"], "PENDING")
                self.assertEqual(report["rows"], 0)
                self.assertEqual(report["visible_vin_count"], 1)
                self.assertEqual(report["shell_delta"]["outside_permitted_regions_byte_changes"], 0)
                self.assertEqual(render._without_block(result), render.shell_guard.normalize_html(page(), UID))
                self.assertEqual(result, render.compose_page(result, UID, facts))

    def test_pending_section_is_localized_without_invented_facts(self):
        result = render.render_block(UID, [], "ru")
        self.assertIn('data-uk="Додаткові характеристики уточнюються."', result)
        self.assertIn('data-ru="Дополнительные характеристики уточняются."', result)
        self.assertIn('>Дополнительные характеристики уточняются.</span>', result)
        self.assertNotIn('<dl>', result)

    def test_pending_to_confirmed_update_preserves_unrelated_bytes(self):
        pending = render.compose_page(page(), UID, [])
        filled = render.compose_page(pending, UID, FACTS)
        self.assertNotIn('class="ua-rb10-pending"', filled)
        self.assertIn('data-spec-status="READY"', filled)
        self.assertEqual(render._without_block(pending), render._without_block(filled))
        report = render.validate_page(filled, UID, FACTS, previous=pending)
        self.assertEqual(report["data_status"], "READY")
        self.assertEqual(report["rows"], len(FACTS))
        self.assertEqual(report["shell_delta"]["outside_permitted_regions_byte_changes"], 0)

    def test_confirmed_to_pending_cannot_remove_previously_published_fields(self):
        filled = render.compose_page(page(), UID, FACTS)
        for facts in ([], [{"key": "length", "value": "4900", "verification_status": "PENDING"}],
                      [{**fact, "is_visible": 0} for fact in FACTS]):
            with self.subTest(facts=facts), self.assertRaisesRegex(render.SpecError, "KEYS_LOST"):
                render.compose_page(filled, UID, facts)

    def test_pending_does_not_bypass_malformed_or_unsafe_fact_validation(self):
        for facts in ([None], [{**FACTS[0], "value": "<script>unsafe</script>"}],
                      [{**FACTS[0], "key": "vin"}]):
            with self.subTest(facts=facts), self.assertRaises(render.SpecError):
                render.compose_page(page(), UID, facts)
        unverified = [{"key": "length", "value": "<script>unsafe</script>"}]
        result = render.render_block(UID, unverified)
        self.assertIn('data-spec-status="PENDING"', result)
        self.assertNotIn("unsafe", result)
        self.assertNotIn("<script", result)

    def test_disappearing_field_does_not_replace_last_good_page(self):
        before = render.compose_page(page(), UID, FACTS)
        with self.assertRaisesRegex(render.SpecError, "KEYS_LOST"):
            render.compose_page(before, UID, FACTS[:1])

    def test_unapproved_shell_change_is_rejected(self):
        before = page()
        after = render.compose_page(before, UID, FACTS).replace("Original description", "Altered description")
        with self.assertRaisesRegex(render.SpecError, "UNAUTHORIZED_NON_SPEC_CHANGE"):
            render.validate_page(after, UID, FACTS, previous=before)

    def test_source_html_and_advertising_are_not_imported(self):
        for value in ('<script>alert(1)</script>', '<iframe src="https://evil.invalid">',
                      'https://example.invalid/ad', 'javascript:alert(1)', 'advertising', VIN):
            facts = deepcopy(FACTS)
            facts[0]["value"] = value
            with self.subTest(value=value), self.assertRaises(render.SpecError):
                render.render_block(UID, facts)

    def test_source_tracking_and_unsafe_protocol_rejected(self):
        for url in ("javascript:alert(1)", "http://www.kia.com/kr/vehicles/k5/specification",
                    "https://www.kia.com/kr/vehicles/k5/specification?utm_source=ad",
                    "https://www.kia.com/kr/vehicles/k5/specification?ref=affiliate",
                    "https://evil.invalid/<script>"):
            facts = deepcopy(FACTS)
            facts[0].update(source_id="kia_kr", source_url=url)
            with self.subTest(url=url), self.assertRaises(render.SpecError):
                render.render_block(UID, facts)

    def test_matching_registry_source_uses_plain_native_link(self):
        facts = deepcopy(FACTS)
        facts[0].update(source_id="kia_kr", source_url="https://www.kia.com/kr/vehicles/k5/specification")
        result = render.render_block(UID, facts)
        self.assertIn('href="https://www.kia.com/kr/vehicles/k5/specification"', result)
        self.assertIn('<details class="ua-rb10-source">', result)
        self.assertNotIn("<iframe", result)

    def test_historical_source_is_preserved_without_active_link(self):
        facts = deepcopy(FACTS)
        facts[0].update(source="legacy catalogue", source_url="https://www.carfolio.com/old-model")
        result = render.render_block(UID, facts)
        self.assertIn("Збережене джерело попередньої версії", result)
        self.assertNotIn("carfolio.com", result)

    def test_wrong_source_host_is_rejected(self):
        facts = deepcopy(FACTS)
        facts[0].update(source_id="kia_kr", source_url="https://www.hyundai.com/kr/ko")
        with self.assertRaisesRegex(render.SpecError, "SOURCE_URL_NOT_APPROVED"):
            render.render_block(UID, facts)

    def test_ambiguous_duplicate_or_unmarked_block_is_rejected(self):
        valid = render.compose_page(page(), UID, FACTS)
        for broken in (valid + render.START, valid + render.render_block(UID, FACTS),
                       valid.replace(render.END, ""), valid.replace(render.START, ""),
                       page() + '<section id="additional-specification">bad</section>'):
            with self.subTest(length=len(broken)), self.assertRaises(render.SpecError):
                render.compose_page(broken, UID, FACTS)

    def test_old_marked_details_migrates_without_losing_fields(self):
        old = (render.START + '<style id="ua-spec-auto10-style">.old{color:gold}</style>'
               '<details class="blok ua-additional-spec" data-ua-additional-spec="1">'
               '<summary>Old specification</summary><div data-spec-key="length">4900</div>'
               '<div data-spec-key="doors">4</div></details>' + render.END)
        before = page().replace('<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->',
                                old + '<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->')
        after = render.compose_page(before, UID, FACTS)
        self.assertNotIn("Old specification", after)
        self.assertIn('href="#additional-specification"', after)

    def test_russian_and_ukrainian_attributes(self):
        result = render.render_block(UID, FACTS, "ru")
        self.assertIn('>Дополнительная спецификация →</span>', result)
        self.assertIn('data-ua="Додаткова специфікація →"', result)
        self.assertIn('data-uk="Додаткова специфікація →"', result)
        self.assertIn('data-ru="Дополнительная спецификация →"', result)

    def test_conflicting_duplicate_field_is_rejected(self):
        facts = deepcopy(FACTS)
        facts.append({**facts[0], "value": "9999"})
        with self.assertRaisesRegex(render.SpecError, "CONFLICTING"):
            render.render_block(UID, facts)

    def test_unapproved_new_shell_requires_previous_baseline(self):
        result = render.compose_page(page(), UID, FACTS)
        with self.assertRaisesRegex(render.SpecError, "UNREVIEWED_NEW_CARD_SHELL_ASSETS"):
            render.validate_page(result, UID, FACTS)

    def test_modified_rendered_value_is_rejected(self):
        result = render.compose_page(page(), UID, FACTS).replace("4900 мм", "4901 мм")
        with self.assertRaisesRegex(render.SpecError, "DIFFERS_FROM_CONFIRMED_DATA"):
            render.validate_page(result, UID, FACTS, previous=page())

    def test_hidden_parent_cannot_make_validation_pass(self):
        before = page().replace("<main>", '<main hidden>')
        with self.assertRaises(render.SpecError):
            render.compose_page(before, UID, FACTS)

    def test_invalid_source_port_is_a_publication_guard_error(self):
        facts = deepcopy(FACTS)
        facts[0].update(source_id="kia_kr", source_url="https://www.kia.com:invalid/kr/vehicles/k5/specification")
        with self.assertRaisesRegex(render.SpecError, "UNSAFE_SOURCE_URL"):
            render.render_block(UID, facts)

    def _authorized_images(self):
        before = render.compose_page(page(), UID, FACTS)
        after = render.compose_page(page().replace("Original description", "Authorized price 11000"), UID, FACTS)
        row = {"uid": UID, "price": 11000}
        sha = lambda value: hashlib.sha256(value.encode()).hexdigest()
        manifest = {"uid": UID, "plan_id": "synthetic-exact-plan", "action": "publish",
                    "before_sha256": sha(before), "after_sha256": sha(after),
                    "crm_row_sha256": sha(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
                    "shell_assets_sha256": render.shell_guard.validate_shell_assets(before, after)["ordered_static_assets_sha256"],
                    "revision": 1, "facts_digest": "a" * 64, "render_facts_sha256": render.facts_digest(FACTS),
                    "authorization": "PASS"}
        return before, after, row, manifest

    def test_authorized_full_card_change_requires_exact_manifest(self):
        before, after, row, manifest = self._authorized_images()
        report = render.validate_authorized_card_change(before, after, UID, FACTS, manifest, row)
        self.assertEqual(report["shell_delta"]["status"], "EXACT_AUTHORIZED_FULL_CARD_CHANGE")
        self.assertEqual(report["visible_vin_count"], 1)
        with self.assertRaisesRegex(render.SpecError, "UNAUTHORIZED_NON_SPEC_CHANGE"):
            render.validate_page(after, UID, FACTS, previous=before)

    def test_authorized_full_card_rejects_wrong_hash_row_or_render_facts(self):
        before, after, row, manifest = self._authorized_images()
        for key in ("before_sha256", "after_sha256", "crm_row_sha256", "render_facts_sha256", "shell_assets_sha256"):
            changed = {**manifest, key: "b" * 64}
            with self.subTest(key=key), self.assertRaises(render.SpecError):
                render.validate_authorized_card_change(before, after, UID, FACTS, changed, row)
        with self.assertRaises(render.SpecError):
            render.validate_authorized_card_change(before, after, UID, FACTS, manifest, {**row, "price": 12000})

    def test_authorized_full_card_cannot_change_static_assets(self):
        before, after, row, manifest = self._authorized_images()
        after = after.replace(".base{color:white}", ".base{color:black}")
        manifest["after_sha256"] = hashlib.sha256(after.encode()).hexdigest()
        with self.assertRaisesRegex(render.SpecError, "STATIC_ASSETS_CHANGED"):
            render.validate_authorized_card_change(before, after, UID, FACTS, manifest, row)

    def test_missing_new_fact_verification_is_not_surfaced(self):
        pending = render.render_block(UID, [{"key": "length", "value": "4900"}])
        self.assertNotIn("4900", pending)
        self.assertIn('data-spec-status="PENDING"', pending)
        legacy = {"key": "length", "value": "4900",
                  "legacy_import": {"receipt_id": "synthetic-import", "fresh_verification": False}}
        self.assertIn("4900", render.render_block(UID, [legacy]))

    def test_worker_store_model_and_vehicle_boolean_facts_render(self):
        from cloud.spec_rebuild10 import sources
        from cloud.spec_rebuild10.store import SpecStore
        from cloud.spec_rebuild10.worker import SpecWorker, CollectorBinding, CollectedDocument
        identity = {"vin": VIN, "brand": "Kia", "model": "K5", "year": 2019,
                    "market": "KR", "fuel": "LPG", "transmission": "automatic", "engine_cc": 1999}
        def binding(equipment=False):
            def collect(request):
                fact = ({"key": "heated_seats", "value": False, "label_uk": "Підігрів сидінь",
                         "label_ru": "Подогрев сидений", "category": "equipment"} if equipment else
                        {"key": "length_mm", "value": 4900, "unit": "mm", "label_uk": "Довжина",
                         "label_ru": "Длина", "category": "technical"})
                payload = {"schema": "ua-art.normalized-source.v1", "source_id": "kia_kr",
                           "identity": dict(request.identity), "document": {
                               "url": "https://www.kia.com/kr/vehicles/k5/specification", "sha256": "c" * 64,
                               "evidence_kind": "vehicle_document" if equipment else "manufacturer_document"},
                           "facts": [fact]}
                return CollectedDocument("kia_kr", payload,
                    authorization=sources.ImportAuthorization("kia_kr", "SYNTHETIC-NORMALIZER", "c" * 64))
            return CollectorBinding("kia_kr", collect, sources.AccessGrant("kia_kr", True, True, True, "SYNTHETIC-RIGHTS"))
        with tempfile.TemporaryDirectory() as directory, SpecStore(Path(directory) / "spec.sqlite") as store:
            store.upsert_vehicle(UID, identity)
            first = SpecWorker(store, {"kia_kr": binding()}).run_once()
            self.assertEqual(first["accepted"], 1)
            self.assertEqual(store.get_facts(UID)[0]["verification_status"], "MODEL_VERIFIED")
            self.assertIn("4900 mm", render.render_block(UID, store.get_facts(UID)))
            store.request_refresh(UID, "Synthetic vehicle evidence", "boolean-test")
            second = SpecWorker(store, {"kia_kr": binding(True)}).run_once()
            self.assertEqual(second["accepted"], 1)
            facts = store.get_facts(UID)
            equipment = next(f for f in facts if f["key"] == "heated_seats")
            self.assertEqual(equipment["verification_status"], "VEHICLE_VERIFIED")
            self.assertIs(equipment["value"], False)
            self.assertIn('data-uk="Ні" data-ru="Нет">Ні</span>', render.render_block(UID, facts))
            self.assertIn('data-uk="Ні" data-ru="Нет">Нет</span>', render.render_block(UID, facts, "ru"))


if __name__ == "__main__":
    unittest.main()
