"""Offline integration contracts; these fixtures do not prove live deployment."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


PACKAGE = Path(__file__).resolve().parents[1]
CLOUD = PACKAGE.parent


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


integration = load_file("auto10_integration_under_test", PACKAGE / "integration.py")
legacy111 = load_file("auto10_legacy111_patcher", CLOUD / "task_111_vin_spec_10src" / "integration_patcher.py")
legacy099 = load_file("auto10_legacy099_patcher", CLOUD / "task_099_site_crm_repair" / "task099_patches.py")
BASE_SPEC = (CLOUD / "task_099_site_crm_repair" / "ua_additional_spec.py").read_text()
BASE_GUARD = (CLOUD / "task_083_publish_transaction" / "publish_transaction_guard.py").read_text()


def spec_source():
    return legacy111.patch_additional_spec(BASE_SPEC)


def publisher_source():
    source = '''
CALLS = []
CARD = {"auto_number": "UA-0001", "vin": "VIN_STAYS"}
def _master(kod): return 'healthy master', 'diagnostics unchanged', CARD
def proverit(html, kod): return []
def opublikovat(kod, proba=False): return True, 'fixture'
def _zapisat_atomarno(put, tekst):
    CALLS.append((put, tekst))
    return 'written'
'''
    return legacy111.patch_publisher(legacy099.patch_publikaciya(source))


def crm_source():
    return '''
import vin_spec_service as _ua110_vin_service
# >>> UA099 ADDITIONAL SPEC CRM V1
class InlineKeyboardMarkup:
    def __init__(self, rows, api_kwargs=None):
        self.inline_keyboard = tuple(tuple(row) for row in rows)
        self.api_kwargs = api_kwargs

def card_kb(card, staff): return card['markup']
# <<< UA099 ADDITIONAL SPEC CRM V1
# >>> UA110 VIN SPEC AUTO QUEUE V1
def register(app):
    _ua110_vin_service.start_worker()
    app.append('legacy-handler')
# <<< UA110 VIN SPEC AUTO QUEUE V1
'''


def execute(source, injected=None):
    namespace = {"__name__": "offline_integration_fixture"}
    namespace.update(injected or {})
    exec(compile(source, "<offline-fixture>", "exec"), namespace)
    return namespace


def crm_source_with_stage_wrapper():
    return crm_source() + r'''
_UA117_BASE_REGISTER = register
def _ua117_block_removed_stage(update, context):
    pass
def register(app):
    _UA117_BASE_REGISTER(app)
    app.add_handler(CallbackQueryHandler(
        _ua117_block_removed_stage,
        pattern=r"^car_setstage:\d+:(?:sea_loaded|sea_transit|ua_handed)$"),
        group=-100)
'''


class PublicationFake(types.ModuleType):
    class SpecError(RuntimeError):
        pass

    def __init__(self):
        super().__init__("spec_publication")
        self.calls = []
        self.facts = [{"field_key": "wheelbase", "field_value": "2805"}]

    def load_facts(self, code):
        self.calls.append(("load", code))
        return self.facts

    def render_block(self, code, facts):
        self.calls.append(("render", code, facts))
        return "healthy spec-only"

    def inject(self, source, code, facts):
        self.calls.append(("inject", source, code, facts))
        return source + " healthy spec-only"

    def validate_page(self, source, code, facts, **kwargs):
        self.calls.append(("validate", source, code, facts))
        if "healthy" not in source:
            raise self.SpecError("SPECIFICATION_BLOCK_MISSING")
        if "carhistory.kr" in source:
            raise self.SpecError("VIN_AD_FORBIDDEN")
        return {"status": "PASS"}

    def guard_write(self, path, data):
        self.calls.append(("guard", path, data))
        self.validate_page(data.decode(), path.stem, self.facts)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.publication = PublicationFake()
        self.worker = types.ModuleType("vin_spec_service")
        self.starts = []
        self.worker.start_worker = lambda: self.starts.append("start")
        self.worker.card_state = lambda value: {"status": "READY", "site_sync_status": "FAILED"}
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {"spec_publication": self.publication, "vin_spec_service": self.worker}).start()

    def test_four_patches_compile_and_are_strictly_idempotent(self):
        for function, source in [
            (integration.patch_additional_spec, spec_source()),
            (integration.patch_publisher, publisher_source()),
            (integration.patch_publish_transaction_guard, BASE_GUARD),
            (integration.patch_publish_transaction_guard, legacy099.patch_publish_transaction_guard(BASE_GUARD)),
            (integration.patch_cars_ui, crm_source()),
        ]:
            with self.subTest(function=function.__name__):
                once = function(source)
                self.assertEqual(once, function(once))
                compile(once, "candidate.py", "exec")
                self.assertTrue(once.startswith(source.rstrip()))

    def test_patcher_never_executes_input_modules(self):
        source = "raise RuntimeError('do not execute user source')\n" + spec_source()
        # Future import placement is intentionally fixed for a valid source.
        source = source.replace("from __future__ import annotations\n", "")
        result = integration.patch_additional_spec(source)
        self.assertIn("do not execute user source", result)
        self.assertEqual(self.starts, [])
        self.assertEqual(self.publication.calls, [])

    def test_rejects_missing_anchors_signatures_and_noncompilable_source(self):
        samples = [
            (integration.patch_additional_spec, BASE_SPEC),
            (integration.patch_publisher, publisher_source().replace("def _master(kod):", "def _master(kod, extra=None):")),
            (integration.patch_publish_transaction_guard, BASE_GUARD.replace("def _atomic(path:", "def _atomic(new_path:")),
            (integration.patch_cars_ui, crm_source().replace("def card_kb(card, staff):", "async def card_kb(card, staff):")),
            (integration.patch_cars_ui, "this is not python"),
        ]
        for function, source in samples:
            with self.subTest(function=function.__name__):
                with self.assertRaises(integration.IntegrationError):
                    function(source)

    def test_rejects_altered_or_nonfinal_patch_and_broken_markers(self):
        once = integration.patch_cars_ui(crm_source())
        for changed in [
            once + "def card_kb(card, staff): return None\n",
            once.replace("rows.append(kept)", "rows.append([])"),
            once.replace("# <<< UA SPEC AUTO10 RESTORE CRM V1", ""),
            once + "# >>> UA SPEC AUTO10 RESTORE CRM V1\n",
        ]:
            with self.assertRaises(integration.IntegrationError):
                integration.patch_cars_ui(changed)

    def test_canonical_database_path_cannot_silently_diverge(self):
        altered = spec_source().replace('"/home/Carix/vin_specs_task111_v3.db"', '"/different/spec.db"')
        with self.assertRaisesRegex(integration.IntegrationError, "CANONICAL_SIDECAR_PATH"):
            integration.patch_additional_spec(altered)

    def test_public_spec_uses_canonical_reader_and_preserves_manual_helpers(self):
        original = spec_source()
        candidate = integration.patch_additional_spec(original)
        # The actual legacy source is preserved byte-for-byte before our block.
        self.assertTrue(candidate.startswith(original.rstrip()))
        namespace = execute(candidate)
        unchanged = ["fetch_specs", "get_spec", "set_manual_value", "set_visible", "_car_vin", "public_contract_errors"]
        before_ast = ast.parse(original)
        after_ast = ast.parse(candidate)
        for name in unchanged:
            before = [n for n in before_ast.body if isinstance(n, ast.FunctionDef) and n.name == name]
            after = [n for n in after_ast.body if isinstance(n, ast.FunctionDef) and n.name == name]
            self.assertEqual([ast.dump(n) for n in before], [ast.dump(n) for n in after])
        namespace["fetch_specs"] = lambda *a, **k: self.fail("public rendering used legacy reader")
        namespace["_UA110_BASE_INJECT_PUBLIC_SPEC"] = lambda *a, **k: self.fail("legacy injector rewrote VIN")
        namespace["_car_vin"] = lambda *a: self.fail("spec injection touched VIN")
        self.assertEqual(namespace["render_public_block"]("UA-1"), "healthy spec-only")
        source = "VIN_STAYS CTA_STAYS PHOTO_STAYS healthy primary"
        self.assertEqual(namespace["inject_public_spec"](source, "UA-1"), source + " healthy spec-only")
        self.assertEqual([c[1] for c in self.publication.calls if c[0] == "load"], ["UA-0001", "UA-0001"])
        self.assertEqual(self.starts, [])

    def test_crm_summary_separates_collection_from_publication_status(self):
        namespace = execute(integration.patch_additional_spec(spec_source()))
        namespace["_UA110_BASE_CRM_SUMMARY"] = lambda value: "Подтверждено: 1"
        for status, text in {
            "PENDING": "обновление сайта в очереди", "RUNNING": "идёт обновление сайта",
            "PASS": "страница проверена и обновлена", "UNCHANGED": "данные актуальны",
            "FAILED": "обновление сайта не прошло", "SUPERSEDED": "более новых данных",
        }.items():
            self.worker.card_state = lambda value, status=status: {"status": "READY", "site_sync_status": status}
            summary = namespace["crm_summary"]("UA-0001")
            self.assertIn(text, summary)
            self.assertNotIn("сбор завершён", summary)
            self.assertNotIn("ДОПОЛНИТЕЛЬНАЯ СПЕЦИФИКАЦИЯ", summary)

    def test_final_master_keeps_diagnostics_and_card_objects(self):
        fake_spec = types.ModuleType("ua_additional_spec")
        fake_spec.canonical_uid = lambda value: value
        fake_spec.inject_public_spec = lambda source, code: source + " healthy legacy-normalized"
        patch.dict(sys.modules, {"ua_additional_spec": fake_spec}).start()
        namespace = execute(integration.patch_publisher(publisher_source()))
        source, diag, card = namespace["_master"]("UA-0001")
        self.assertIn("healthy spec-only", source)
        self.assertEqual(diag, "diagnostics unchanged")
        self.assertIs(card, namespace["CARD"])
        self.assertEqual(card["vin"], "VIN_STAYS")
        self.assertEqual(self.publication.calls[-1][0], "validate")
        self.assertEqual(namespace["CALLS"], [])
        namespace["_UA_AUTO10_BASE_MASTER"] = lambda code: ("", None, {})
        with self.assertRaisesRegex(self.publication.SpecError, "PRIMARY_HTML_MISSING"):
            namespace["_master"]("UA-0001")

    def test_publisher_writer_blocks_bad_primary_before_legacy_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "video").mkdir()
            patch.dict(os.environ, {"UA_ART_ROOT": str(root)}).start()
            namespace = execute(integration.patch_publisher(publisher_source()))
            path = root / "video" / "UA-0001.html"
            with self.assertRaises(self.publication.SpecError):
                namespace["_zapisat_atomarno"](path, "missing spec")
            self.assertEqual(namespace["CALLS"], [])
            self.assertEqual(namespace["_zapisat_atomarno"](path, "healthy spec"), "written")
            self.assertEqual(namespace["CALLS"], [(path, "healthy spec")])
            # Non-primary writer input is passed through without our checks.
            for filename in ["katalog.html", "UA-0001-diag.html"]:
                self.publication.calls.clear()
                namespace["_zapisat_atomarno"](root / "video" / filename, b"legacy content")
                self.assertEqual(self.publication.calls, [])

    def guard_namespace(self, root, gzip=False):
        patch.dict(os.environ, {"UA_ART_ROOT": str(root)}).start()
        source = legacy099.patch_publish_transaction_guard(BASE_GUARD) if gzip else BASE_GUARD
        return execute(integration.patch_publish_transaction_guard(source))

    def test_transaction_atomic_blocks_bad_primary_and_leaves_other_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "video").mkdir()
            namespace = self.guard_namespace(root)
            primary = root / "video" / "UA-0001.html"
            primary.write_bytes(b"healthy old")
            with self.assertRaises(self.publication.SpecError):
                namespace["_atomic"](primary, b"missing block")
            self.assertEqual(primary.read_bytes(), b"healthy old")
            for path in [root / "backup" / "UA-0001.html", root / "video" / "UA-0001-diag.html", root / "video" / "katalog.html"]:
                self.publication.calls.clear()
                namespace["_atomic"](path, b"exact old bytes")
                self.assertEqual(path.read_bytes(), b"exact old bytes")
                self.assertEqual(self.publication.calls, [])

    def test_transaction_primary_validator_keeps_legacy_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            namespace = self.guard_namespace(Path(folder))
            prior = []
            namespace["_UA_AUTO10_BASE_VALIDATE_PRIMARY"] = lambda *args: prior.append(args) or {"legacy": "PASS"}
            with self.assertRaises(self.publication.SpecError):
                namespace["_validate_primary"]("UA-0001", {}, "missing")
            self.assertEqual(prior, [])
            self.assertEqual(namespace["_validate_primary"]("UA-0001", {}, "healthy spec"), {"legacy": "PASS"})
            self.assertEqual(len(prior), 1)

    def test_preflight_requires_healthy_preimage_before_any_legacy_transaction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "video").mkdir()
            (root / "site").mkdir()
            primary = root / "video" / "UA-0001.html"
            primary.write_bytes(b"missing block")
            namespace = self.guard_namespace(root)
            entered = []
            namespace["_UA_AUTO10_BASE_PUBLISH_LOCKED"] = lambda *args, **kwargs: entered.append((args, kwargs)) or "transaction"
            with self.assertRaises(self.publication.SpecError):
                namespace["_publish_locked"](None, ["UA-0001"])
            self.assertEqual(entered, [])
            self.assertFalse(namespace["BACKUPS"].exists())
            primary.write_bytes(b"healthy preimage")
            self.assertEqual(namespace["_publish_locked"](None, ["UA-0001"], proba=True), "transaction")
            self.assertEqual(entered[0][1], {"proba": True})

    def test_both_known_snapshot_variants_restore_healthy_bytes_through_guard(self):
        for gzip in [False, True]:
            with self.subTest(gzip=gzip), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                for dirname in ["video", "site"]:
                    (root / dirname).mkdir()
                    (root / dirname / "UA-0001.html").write_bytes(b"healthy preimage")
                namespace = self.guard_namespace(root, gzip)
                snapshot = namespace["Snapshot"](["UA-0001"])
                self.publication.calls.clear()
                primary = root / "video" / "UA-0001.html"
                primary.write_bytes(b"failed partially changed candidate")
                snapshot.restore()
                self.assertEqual(primary.read_bytes(), b"healthy preimage")
                guards = [c for c in self.publication.calls if c[0] == "guard"]
                self.assertTrue(any(c[1] == primary and c[2] == b"healthy preimage" for c in guards))

    def test_no_ads_blocking_survives_both_publisher_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "video").mkdir()
            namespace = self.guard_namespace(root)
            with self.assertRaisesRegex(self.publication.SpecError, "VIN_AD_FORBIDDEN"):
                namespace["_atomic"](root / "video" / "UA-0001.html", b"healthy carhistory.kr")
            self.assertFalse((root / "video" / "UA-0001.html").exists())
            with self.assertRaisesRegex(self.publication.SpecError, "VIN_AD_FORBIDDEN"):
                namespace["_validate_primary"]("UA-0001", {}, "healthy carhistory.kr")

    def test_keyboard_only_removes_exact_callback_and_worker_hook_is_unchanged(self):
        namespace = execute(integration.patch_cars_ui(crm_source()))
        button = lambda callback=None, url=None: types.SimpleNamespace(callback_data=callback, url=url)
        publish = button("car_publish:1")
        detail = button("car_spec_item:1:4")
        malformed = button("car_spec:1:extra")
        external = button(url="https://example.org")
        markup = namespace["InlineKeyboardMarkup"](
            [[button("car_spec:1")], [publish, button("car_spec:002")], [detail, malformed, external]],
            api_kwargs={"known": "metadata"},
        )
        filtered = namespace["card_kb"]({"markup": markup}, None)
        self.assertEqual(filtered.inline_keyboard, ((publish,), (detail, malformed, external)))
        self.assertIs(filtered.inline_keyboard[0][0], publish)
        self.assertEqual(filtered.api_kwargs, markup.api_kwargs)
        self.assertEqual(len(markup.inline_keyboard), 3)
        self.assertEqual(self.starts, [])
        handlers = []
        namespace["register"](handlers)
        self.assertEqual(self.starts, ["start"])
        self.assertEqual(handlers, ["legacy-handler"])

    def test_rejects_missing_duplicate_or_import_time_worker_start(self):
        source = crm_source()
        variants = [
            source.replace("    _ua110_vin_service.start_worker()", "    pass"),
            source + "\n_ua110_vin_service.start_worker()\n",
            source.replace("    _ua110_vin_service.start_worker()", "    pass") + "\n_ua110_vin_service.start_worker()\n",
        ]
        for variant in variants:
            with self.assertRaisesRegex(integration.IntegrationError, "EXISTING_WORKER_HOOK"):
                integration.patch_cars_ui(variant)

    def test_verified_stage_wrapper_preserves_single_start_and_existing_handler(self):
        source = crm_source_with_stage_wrapper()
        patched = integration.patch_cars_ui(source)
        self.assertTrue(patched.startswith(source.rstrip()))
        self.assertEqual(integration.patch_cars_ui(patched), patched)
        namespace = execute(patched, {"CallbackQueryHandler": lambda callback, pattern: (callback, pattern)})

        class App(list):
            def add_handler(self, handler, group):
                self.append((handler[1], group))

        app = App()
        namespace["register"](app)
        self.assertEqual(self.starts, ["start"])
        self.assertEqual(app, ["legacy-handler", (r"^car_setstage:\d+:(?:sea_loaded|sea_transit|ua_handed)$", -100)])

    def test_rejects_broken_or_unknown_stage_wrapper_chains(self):
        source = crm_source_with_stage_wrapper()
        variants = [
            source.replace("_UA117_BASE_REGISTER = register", "_UA117_BASE_REGISTER = other_register"),
            source + "\n_UA117_BASE_REGISTER = other_register\n",
            source.replace("    _UA117_BASE_REGISTER(app)", "    return\n    _UA117_BASE_REGISTER(app)"),
            source.replace("    _UA117_BASE_REGISTER(app)", "    _UA117_BASE_REGISTER(app)\n    _UA117_BASE_REGISTER(app)"),
            source.replace("group=-100)", "group=-99)"),
        ]
        for variant in variants:
            with self.subTest(variant=variant[-100:]):
                with self.assertRaisesRegex(integration.IntegrationError, "EXISTING_WORKER_HOOK"):
                    integration.patch_cars_ui(variant)


if __name__ == "__main__":
    unittest.main()
