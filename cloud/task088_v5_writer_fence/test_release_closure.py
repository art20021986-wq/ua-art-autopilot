"""New point4 closure checks; private inputs stay in memory, all writes in TEST roots.

Set UA114_PRIVATE_BASE and UA114_DEPENDENCY_BASE to the verified private input
directories. No fresh preflight, live module import, or production action runs.
"""
import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for relative in ("cloud/task088_price_sync", "cloud/task088_stage3_renderer"):
    sys.path.insert(0, str(ROOT / relative))

import install_package as engine
import preflight
import build_preflight_bundle
import stage_preflight
import test_install_package as fixtures
import integrate_private_sources as integration
import patch_cars_ui
import patch_guard
import patch_stranica


def load(name):
    path = ROOT / "cloud/task088_v5_install" / (name + ".py")
    spec = importlib.util.spec_from_file_location("closure_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load("build_release")
controller = load("controller")
remote = load("remote_adapter")
NEW_MODULES = {"publication_fence.py", "mutation_recovery.py"}
NEW_DEPENDENCIES = {"lock4_zhurnal.py", "ua_additional_spec.py", "vin_spec_service.py"}


class ReleaseClosureTests(unittest.TestCase):
    def fixture(self):
        value = fixtures.InstallTests(methodName="runTest")
        value.setUp()
        self.addCleanup(value.doCleanups)
        return value

    def test_preflight_engine_controller_and_release_have_same_closure(self):
        self.assertEqual(engine.SOURCES, preflight.SOURCES)
        self.assertEqual(engine.MODULES, preflight.MODULES)
        self.assertEqual(engine.DEPENDENCIES, preflight.DEPENDENCIES)
        self.assertIn("ua_spec_permanent.py", engine.SOURCES)
        self.assertTrue(NEW_MODULES <= engine.MODULES)
        self.assertTrue(NEW_DEPENDENCIES <= engine.DEPENDENCIES)
        self.assertEqual(controller.REMOTE_FILES, engine.MODULES | {"remote_adapter.py", "install_package.py"})
        mapping = build_preflight_bundle.package_mapping(ROOT)
        self.assertEqual(set(mapping), preflight.MODULES | preflight.TOOLS)
        self.assertIn("integrate_private_sources.py", mapping)
        self.assertTrue(engine.MODULES <= set(release.sources()))
        for name in engine.MODULES:
            self.assertEqual(hashlib.sha256(mapping[name].read_bytes()).digest(),
                             hashlib.sha256(release.sources()[name].read_bytes()).digest(), name)

    def test_pure_builder_refuses_missing_or_extra_private_dependencies(self):
        originals = {name: b"# TEST untrusted source" for name in engine.SOURCES}
        dependencies = {name: b"# TEST untrusted dependency" for name in engine.DEPENDENCIES}
        for missing in NEW_DEPENDENCIES:
            with self.subTest(missing=missing), self.assertRaisesRegex(engine.InstallError, "SOURCE_DEPENDENCY_SET"):
                engine.build_source_candidates(originals, {name: value for name, value in dependencies.items() if name != missing})
        with self.assertRaisesRegex(engine.InstallError, "SOURCE_DEPENDENCY_SET"):
            engine.build_source_candidates(originals, dict(dependencies, unknown=b"unreviewed"))

    def test_complete_builder_refuses_missing_helper_before_source_processing(self):
        for missing in NEW_MODULES:
            modules = {name: b"# TEST module" for name in engine.MODULES if name != missing}
            with self.subTest(missing=missing), self.assertRaisesRegex(engine.InstallError, "SOURCE_MODULE_SET"):
                engine.build_candidates({}, {}, [], modules, dependency_files={})

    def test_rebound_partial_manifest_is_rejected_before_preparing_backup(self):
        for missing in NEW_MODULES | {"ua_spec_permanent.py"}:
            with self.subTest(missing=missing):
                value = self.fixture()
                value.files.pop(missing)
                value.before.pop(missing)
                value.bind()  # Even synthetic fully rebound evidence cannot omit closure.
                with self.assertRaisesRegex(engine.InstallError, "INSTALL_FILE_SET"):
                    engine._validate(value.plan, value.files, value.evidence, value.now,
                                     value.root, testing=True, phase="PREPARING")
                self.assertFalse((value.root / "rezerv_publikacii").exists())
                value.assert_no_candidate_files()

    def test_missing_new_dependency_pin_is_rejected_before_backup(self):
        value = self.fixture()
        for missing in NEW_DEPENDENCIES:
            with self.subTest(missing=missing):
                plan = dict(value.plan, dependencies_sha256={name: digest for name, digest in value.dependencies.items() if name != missing})
                with self.assertRaisesRegex(engine.InstallError, "DEPENDENCY_HASHES"):
                    engine._validate(plan, value.files, value.evidence, value.now,
                                     value.root, testing=True, phase="PREPARING")
        self.assertFalse((value.root / "rezerv_publikacii").exists())

    def test_new_sources_and_modules_are_backed_up_installed_and_scoped_restored(self):
        value = self.fixture()
        before = engine.system_inventory(value.root)
        backup = remote.backup(value.plan, value.files, value.evidence, value.root)
        full = Path(backup["backup_directory"]) / "full"
        for name in NEW_DEPENDENCIES | {"ua_spec_permanent.py"}:
            self.assertEqual(engine.sha((full / name).read_bytes()), before[name]["sha256"])
        receipt = value.call()
        for name in NEW_MODULES | {"ua_spec_permanent.py"}:
            self.assertEqual(receipt["installed_files_sha256"][name], engine.sha(value.files[name]))
        self.assertEqual(remote.verify(value.plan, value.files, value.root)["status"], "INSTALLATION_VERIFIED")
        value.db.execute("UPDATE cars SET price_georgia=8500 WHERE id=7")
        value.db.commit()
        restored = remote.rollback(value.plan, value.files, value.root, backup["backup_manifest_sha256"])
        self.assertEqual(restored["status"], "ROLLED_BACK")
        value.assert_no_candidate_files()
        self.assertEqual(engine.system_inventory(value.root), before)
        self.assertEqual(value.db.execute("SELECT price_georgia FROM cars WHERE id=7").fetchone()[0], 8500)

    def test_changed_spec_dependency_is_preserved_and_install_refused(self):
        value = self.fixture()
        changed = value.root / "ua_additional_spec.py"
        changed.write_bytes(b"# TEST newer operator dependency\n")
        with self.assertRaisesRegex(engine.InstallError, "DEPENDENCY_HASH"):
            value.call()
        self.assertEqual(changed.read_bytes(), b"# TEST newer operator dependency\n")
        value.assert_no_candidate_files()


class ExactPrivateCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path(os.environ["UA114_PRIVATE_BASE"])
        dependency_base = Path(os.environ["UA114_DEPENDENCY_BASE"])
        cls.originals = {name: (base / name).read_bytes() for name in integration.BEFORE_SHA256}
        for name, raw in cls.originals.items():
            if hashlib.sha256(raw).hexdigest() != integration.BEFORE_SHA256[name]:
                raise RuntimeError("EXACT_PRIVATE_ORIGINAL_REQUIRED:" + name)
        cls.dependencies = {name: (dependency_base / name).read_bytes() for name in integration.DEPENDENCY_SHA256}
        cls.prices = {
            "cars_ui.py": patch_cars_ui.patch_source(cls.originals["cars_ui.py"].decode()).encode(),
            "publish_transaction_guard.py": patch_guard.patch_source(cls.originals["publish_transaction_guard.py"].decode()).encode(),
            "stranica.py": patch_stranica.patch_stranica(cls.originals["stranica.py"])[0],
        }

    def test_exact_price_composition_preserves_all_price_helpers_and_renderers(self):
        combined = integration.compose_price_candidate(self.prices, self.dependencies)
        self.assertEqual(set(combined), set(self.prices) | {"ua_spec_permanent.py"})
        for name, raw in combined.items():
            compile(raw, "<private-candidate-no-source-output>", "exec")
            if name not in self.prices:
                continue
            def selected(value):
                return {node.name: ast.dump(node, include_attributes=False)
                        for node in ast.parse(value).body
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and (node.name.startswith("_task088") or node.name in
                             {"sobrat_kartochku", "sobrat_katalog", "sobrat_glavnuyu"})}
            self.assertTrue(selected(self.prices[name]), name)
            # Boolean comparison avoids dumping any private AST on failure.
            self.assertTrue(selected(self.prices[name]) == selected(raw), name)

    def test_price_afterimage_drift_cannot_be_composed(self):
        for name in self.prices:
            values = dict(self.prices)
            values[name] += b"\n# TEST unreviewed price drift\n"
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                integration.compose_price_candidate(values, self.dependencies)

    def test_dependency_drift_cannot_be_composed(self):
        for name in self.dependencies:
            values = dict(self.dependencies)
            values[name] += b"\n# TEST unreviewed dependency drift\n"
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                integration.compose_price_candidate(self.prices, values)

    def test_partial_dependency_set_cannot_be_composed(self):
        with self.assertRaises(RuntimeError):
            integration.compose_price_candidate(self.prices, {name: data for name, data in self.dependencies.items()
                                                              if name != "ua_spec_permanent.py"})


class StagingAndV5AdmissionTests(unittest.TestCase):
    """Affected admission only; older v1 delegation remains unchanged."""
    def fixture(self, *, v5):
        import test_binding
        value = (test_binding.BindingV5Tests if v5 else test_binding.BindingTests)(methodName="runTest")
        value.setUp()
        self.addCleanup(value.tearDown)
        return value, test_binding.binding

    def complete_v5_writer_evidence(self, value, binding):
        # Explicit synthetic TEST observations, never a production writer PASS.
        for name in binding.V5_REQUIRED_WRITERS:
            if name not in {item["path"] for item in value.writers["writers"]}:
                value.writers["writers"].append({"path": name, "installed_sha256": value.code[name], "fence": "VERIFIED"})
        value.artifacts["writer_fences"] = value.put("evidence/writers.json", value.writers)
        value.delegation["writer_fence_report_sha256"] = value.artifacts["writer_fences"]["sha256"]
        value.rebuild_chain()

    def test_staging_paths_match_hash_bound_archive_without_network(self):
        archive_mapping = build_preflight_bundle.package_mapping(ROOT)
        self.assertEqual(stage_preflight.package_mapping(),
                         {name: path.relative_to(ROOT).as_posix() for name, path in archive_mapping.items()})

    def test_legacy_v1_delegation_does_not_require_new_v5_files(self):
        value, binding = self.fixture(v5=False)
        self.assertFalse(NEW_MODULES & set(value.code))
        value.provider()

    def test_v5_rejects_new_helper_missing_from_code_pins(self):
        value, binding = self.fixture(v5=True)
        self.complete_v5_writer_evidence(value, binding)
        value.code.pop("mutation_recovery.py")
        value.rebuild_chain()
        with self.assertRaisesRegex(binding.BindingError, "ALL_INSTALLED_WRITERS_AND_MODULES"):
            value.provider()

    def test_v5_rejects_legacy_writer_list_even_with_all_code_pins(self):
        value, binding = self.fixture(v5=True)
        value.writers["writers"] = [item for item in value.writers["writers"] if item["path"] not in binding.V5_REQUIRED_WRITERS]
        value.artifacts["writer_fences"] = value.put("evidence/writers.json", value.writers)
        value.delegation["writer_fence_report_sha256"] = value.artifacts["writer_fences"]["sha256"]
        value.rebuild_chain()
        with self.assertRaisesRegex(binding.BindingError, "ALL_PRICE_AND_CATALOG_WRITERS"):
            value.provider()

    def test_v5_accepts_explicit_complete_synthetic_writer_closure(self):
        value, binding = self.fixture(v5=True)
        self.complete_v5_writer_evidence(value, binding)
        self.assertNotIn("lock4_zhurnal.py", binding.V5_REQUIRED_WRITERS)
        value.provider()


if __name__ == "__main__":
    unittest.main()
