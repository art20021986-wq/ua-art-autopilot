"""Evidence preparation is isolated; no server, GitHub or production is touched."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest

import install_package as I
import preflight
import build_preflight_bundle
import test_install_package as fixtures

HERE = Path(__file__).resolve().parents[1] / "task088_v5_install"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observe = load("observe_install_inputs")
prepare = load("prepare_install_plan")
release = load("build_release")


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InstallTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def test_authenticated_reader_is_in_complete_preflight_and_release_closure(self):
        repository = HERE.parents[1]
        mapping = build_preflight_bundle.package_mapping(repository)
        self.assertIn("uaart_price_control_reader.py", I.MODULES)
        self.assertEqual(I.MODULES, preflight.MODULES)
        self.assertEqual(set(mapping), preflight.MODULES | preflight.TOOLS)
        release_sources = release.sources()
        self.assertTrue(I.MODULES <= set(release_sources))
        self.assertEqual(mapping["uaart_price_control_reader.py"].read_bytes(),
                         release_sources["uaart_price_control_reader.py"].read_bytes())

    def inputs(self):
        fixture = self.fixture
        candidates = self.root / "private_candidates"
        evidence = self.root / "private_evidence"
        candidates.mkdir()
        evidence.mkdir()
        for name, content in fixture.files.items():
            path = candidates / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        for name, content in fixture.evidence.items():
            (evidence / (name + ".json")).write_bytes(content)
        report = {"contract": "TASK088-PRICE-SYNC-READONLY-PREFLIGHT-5", "environment": "TEST",
            "observed_at": fixture.at, "candidate_verification": "PASS",
            "offline_schema_test": "PASS_CRM_AND_AUDIT_UNCHANGED", "protected_system_readback": "PASS",
            "candidate_files": fixture.plan["files"], "candidate_manifest_sha256": fixture.plan["manifest_sha256"],
            "database": fixture.snapshot, "schema_sha256": fixture.schema_hash,
            "candidate_schema_sha256": fixture.plan["candidate_schema_sha256"],
            "published_count": fixture.plan["published_count"], "system_inventory": fixture.plan["system_inventory"],
            "dependencies": fixture.dependencies}
        report_path = self.root / "preflight_report.json"
        report_path.write_bytes(I.encoded(report))
        return {"preflight_report": report_path, "candidate_root": candidates,
            "evidence_directory": evidence, "output_directory": self.root / "immutable_plan",
            "test_root": self.root, "now": fixture.now}

    def test_prepare_pins_existing_evidence_without_installing(self):
        args = self.inputs()
        before = I.system_inventory(self.root)
        result = prepare.prepare(I, **args)
        self.assertEqual(result["status"], "IMMUTABLE_PLAN_PREPARED_NOT_EXECUTED")
        self.assertEqual(result["plan_sha256"], I.sha(Path(result["plan_path"]).read_bytes()))
        self.assertEqual(I.system_inventory(self.root), before)
        self.fixture.assert_original_database()
        self.assertFalse(result["gate_b_created"])
        self.assertEqual(Path(result["plan_path"]).stat().st_mode & 0o777, 0o600)

    def test_prepare_refuses_missing_canonical_claim(self):
        args = self.inputs()
        (args["evidence_directory"] / "claim.json").unlink()
        with self.assertRaises(FileNotFoundError):
            prepare.prepare(I, **args)
        self.assertFalse(args["output_directory"].exists())
        self.fixture.assert_no_candidate_files()

    def test_prepare_refuses_candidate_tampering_before_output(self):
        args = self.inputs()
        (args["candidate_root"] / "cars_ui.py").write_bytes(b"# unreviewed candidate")
        with self.assertRaisesRegex(ValueError, "CANDIDATE_BYTES_DRIFT"):
            prepare.prepare(I, **args)
        self.assertFalse(args["output_directory"].exists())

    def test_prepare_never_replaces_an_existing_plan(self):
        args = self.inputs()
        args["output_directory"].mkdir()
        sentinel = args["output_directory"] / "plan.json"
        sentinel.write_bytes(b"historical preparation")
        with self.assertRaises(FileExistsError):
            prepare.prepare(I, **args)
        self.assertEqual(sentinel.read_bytes(), b"historical preparation")

    def test_observation_reads_dynamic_car_set_without_source_or_price_output(self):
        before = I.system_inventory(self.root)
        quota = {"observed_at": datetime.now(timezone.utc).isoformat(),
            "source": "PYTHONANYWHERE_AUTHENTICATED_ACCOUNT", "account": "Carix",
            "used_bytes": 10, "limit_bytes": 10**9}
        result = observe.observe(I, quota, test_root=self.root)
        self.assertEqual(result["database"]["published_codes"], ["UA-0001", "UA-0002"])
        self.assertEqual(sum(result["stage_counts"].values()), 2)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(I.system_inventory(self.root), before)
        self.fixture.assert_original_database()
        self.assertNotIn("price_uah", json.dumps(result))

    def test_readonly_inventory_can_be_observed_while_exact_quota_is_pending(self):
        result = observe.observe(I, test_root=self.root)
        self.assertEqual(result["status"], "OBSERVED_QUOTA_PENDING")
        self.assertIsNone(result["quota_evidence"])
        self.assertEqual(result["database"]["published_codes"], ["UA-0001", "UA-0002"])
        self.fixture.assert_original_database()

    def test_observation_refuses_unverified_global_filesystem_quota(self):
        quota = {"observed_at": datetime.now(timezone.utc).isoformat(),
            "source": "OS_DISK_USAGE", "account": "Carix", "used_bytes": 10, "limit_bytes": 10**9}
        with self.assertRaisesRegex(ValueError, "AUTHENTICATED_ACCOUNT_QUOTA_REQUIRED"):
            observe.observe(I, quota, test_root=self.root)
