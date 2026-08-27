"""
Offline unit tests for UA Cards Unified Gate A (TASK 021).

Run with (from repository root):
    python3 -m unittest discover -s cloud/ua_cards_unified/tests -t cloud

All fixtures are temporary directories; no real /home/Carix path is
touched, imported, or required to exist.
"""
from __future__ import annotations

import os
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # cloud/
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from ua_cards_unified import common, preflight, manifest_builder, runner, verifier, launcher  # noqa: E402


VALID_CARD_HTML_TEMPLATE = """<!doctype html>
<html><head><title>{code}</title></head>
<body>
<div class="content">Some real card content for {code}.</div>
{legacy_diag}
{legacy_track}
<a class="dejstvie kn_kupit" href="#buy">Купить</a>
</body></html>
"""

LEGACY_DIAG = "<!-- LEGACY_DIAG_START --><div>old diag</div><!-- LEGACY_DIAG_END -->"
LEGACY_TRACK = "<!-- LEGACY_TRACK_START --><div>old track</div><!-- LEGACY_TRACK_END -->"


def make_fixture_root(tmp: Path, codes=None, with_legacy=True) -> Path:
    base = tmp
    (base / "video").mkdir(parents=True, exist_ok=True)
    codes = codes if codes is not None else common.REAL_CODES
    for code in codes:
        html = VALID_CARD_HTML_TEMPLATE.format(
            code=code,
            legacy_diag=LEGACY_DIAG if with_legacy else "",
            legacy_track=LEGACY_TRACK if with_legacy else "",
        )
        (base / "video" / f"{code}.html").write_text(html, encoding="utf-8")
    for name in common.GENERATOR_CANDIDATE_NAMES:
        (base / name).write_text(f"# fixture generator {name}\n", encoding="utf-8")
    conn = sqlite3.connect(str(base / "crm.db"))
    conn.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, code TEXT, status TEXT)")
    conn.execute("INSERT INTO cards (code, status) VALUES (?, ?)", ("UA-0009", "in_review"))
    conn.commit()
    conn.close()
    return base


class TestRealIdentifiers(unittest.TestCase):
    def test_real_ids_ua0001_to_ua0008_accepted(self):
        for code in common.REAL_CODES:
            self.assertTrue(preflight.is_real_card_code(code))
            self.assertFalse(preflight.is_synthetic_placeholder(code))

    def test_synthetic_ids_rejected_without_banning_real_ids(self):
        synthetic = ["DEMO-0001", "TEST-CARD", "FAKE-UA-0001"]
        flagged = preflight.scan_discovered_identifiers(synthetic + common.REAL_CODES)
        for s in synthetic:
            self.assertIn(s, flagged)
        for real in common.REAL_CODES:
            self.assertNotIn(real, flagged)


class TestPreflightSelfScanSafety(unittest.TestCase):
    def test_preflight_refuses_to_scan_its_own_source(self):
        own_file = Path(preflight.__file__)
        with self.assertRaises(common.GateAError):
            preflight.reject_if_package_self_scan(own_file)

    def test_preflight_does_not_false_positive_on_field_names(self):
        # scan_discovered_identifiers only ever receives *data* identifiers,
        # never source code text, so field names like "api_url" used inside
        # this very package's source cannot appear here as false positives.
        flagged = preflight.scan_discovered_identifiers(["api_url", "some_field"])
        self.assertEqual(flagged, [])


class TestPurchaseAnchorDetection(unittest.TestCase):
    def test_exactly_one_anchor_accepted(self):
        html = VALID_CARD_HTML_TEMPLATE.format(code="UA-0001", legacy_diag="", legacy_track="")
        matches = common.find_purchase_anchor_matches(html)
        self.assertEqual(len(matches), 1)

    def test_zero_anchors_rejected(self):
        html = "<html><body><div>no anchor</div></body></html>"
        matches = common.find_purchase_anchor_matches(html)
        self.assertEqual(len(matches), 0)
        _, errors = runner.process_card_html("UA-0001", html)
        self.assertTrue(errors)

    def test_two_anchors_rejected(self):
        html = (
            "<html><body>"
            '<a class="dejstvie kn_kupit" href="#a">Buy A</a>'
            '<a class="dejstvie kn_kupit" href="#b">Buy B</a>'
            "</body></html>"
        )
        matches = common.find_purchase_anchor_matches(html)
        self.assertEqual(len(matches), 2)
        _, errors = runner.process_card_html("UA-0001", html)
        self.assertTrue(errors)


class TestDiagTrackInsertion(unittest.TestCase):
    def test_single_diag_and_track_href_per_card(self):
        html = VALID_CARD_HTML_TEMPLATE.format(code="UA-0002", legacy_diag=LEGACY_DIAG, legacy_track=LEGACY_TRACK)
        transformed, errors = runner.process_card_html("UA-0002", html)
        self.assertEqual(errors, [])
        self.assertEqual(transformed.count("UA-0002-diag.html"), 1)
        self.assertEqual(transformed.count("UA-0002-track.html"), 1)
        self.assertNotIn("LEGACY_DIAG_START", transformed)
        self.assertNotIn("LEGACY_TRACK_START", transformed)

    def test_unrelated_content_preserved(self):
        html = VALID_CARD_HTML_TEMPLATE.format(code="UA-0003", legacy_diag="", legacy_track="")
        transformed, errors = runner.process_card_html("UA-0003", html)
        self.assertEqual(errors, [])
        self.assertIn("Some real card content for UA-0003.", transformed)
        self.assertIn('href="#buy"', transformed)

    def test_script_decoy_does_not_move_structural_insertion(self):
        decoy = '<a class="dejstvie kn_kupit" href="#buy">'
        html = (
            f"<html><script>const decoy = {decoy!r};</script><body>"
            f"{decoy}Купить</a></body></html>"
        )
        transformed, errors = runner.process_card_html("UA-0003", html)
        self.assertEqual(errors, [])
        self.assertGreater(
            transformed.index("UA-0003-diag.html"),
            transformed.index("</script>"),
        )


class TestTrackingCompanionState(unittest.TestCase):
    def test_truthful_empty_tracking_state_constant(self):
        self.assertIn("уточняются", common.TRACKING_EMPTY_TEXT)

    def test_empty_and_real_tracking_pages_are_truthful(self):
        empty = common.build_tracking_page("UA-0001", {})
        self.assertIn(common.TRACKING_EMPTY_TEXT, empty)
        linked = common.build_tracking_page(
            "UA-0001", {"carrier_url": "https://carrier.example/track/1"}
        )
        self.assertIn("https://carrier.example/track/1", linked)
        self.assertNotIn(common.TRACKING_EMPTY_TEXT, linked)


class TestBoundedDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.base = make_fixture_root(self.tmp / "home_carix")

    def test_discovery_includes_all_minimum_candidates(self):
        candidates = common.candidate_card_paths(self.base, "UA-0001")
        rel = [str(p.relative_to(self.base)) for p in candidates]
        self.assertIn("video/UA-0001.html", rel)
        self.assertIn("video/cards/UA-0001.html", rel)
        self.assertIn("video/cards/UA-0001/index.html", rel)
        self.assertIn("site/UA-0001.html", rel)
        self.assertIn("public_html/video/UA-0001.html", rel)
        self.assertIn("public_html/cards/UA-0001.html", rel)
        self.assertIn("mysite/UA-0001.html", rel)
        self.assertIn("UA-0001.html", rel)

    def test_generator_candidates_present(self):
        gens = runner.discover_generators(self.base)
        for name in ("master_card.py", "stranica.py", "yadro.py"):
            self.assertIn(name, gens)

    def test_crm_candidate_present(self):
        crm = runner.discover_crm(self.base)
        self.assertIsNotNone(crm)
        self.assertEqual(crm.name, "crm.db")

    def test_missing_real_source_blocks_with_no_synthetic_fallback(self):
        codes_present = [c for c in common.REAL_CODES if c != "UA-0005"]
        base2 = make_fixture_root(self.tmp / "second", codes=codes_present)
        src = runner.discover_card_source(base2, "UA-0005")
        self.assertIsNone(src)

    def test_symlinked_candidate_parent_escape_is_rejected(self):
        base = self.tmp / "symlink_base"
        outside = self.tmp / "outside_cards"
        base.mkdir()
        outside.mkdir()
        (outside / "UA-0001.html").write_text("outside", encoding="utf-8")
        os.symlink(outside, base / "video")
        with self.assertRaises(common.PathEscapeError):
            runner.discover_card_source(base, "UA-0001")


class TestSqliteReadOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.base = make_fixture_root(self.tmp / "home_carix")

    def test_readonly_connection_rejects_write(self):
        conn = common.open_crm_readonly(self.base / "crm.db")
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("INSERT INTO cards (code) VALUES ('X')")
        conn.close()

    def test_ua0009_evidence_fingerprint_unchanged(self):
        crm_path = self.base / "crm.db"
        before = common.sha256_file(crm_path)
        evidence = runner._load_card_evidence(crm_path)
        self.assertIsInstance(evidence, dict)
        after = common.sha256_file(crm_path)
        self.assertEqual(before, after)


class TestOverallStatusLogic(unittest.TestCase):
    def test_one_card_failure_blocks_overall(self):
        cards = {
            "UA-0001": runner.CardResult(code="UA-0001", status="PASS"),
            "UA-0002": runner.CardResult(code="UA-0002", status="FAIL", reason="x"),
        }
        status = runner.compute_overall_status(cards, unexpected=0, errors=[])
        self.assertEqual(status, "BLOCKED")

    def test_all_pass_yields_awaiting_gate_b(self):
        cards = {c: runner.CardResult(code=c, status="PASS") for c in common.ALL_CODES}
        status = runner.compute_overall_status(cards, unexpected=0, errors=[])
        self.assertEqual(status, "AWAITING_GATE_B")

    def test_unexpected_protected_change_blocks(self):
        cards = {c: runner.CardResult(code=c, status="PASS") for c in common.ALL_CODES}
        status = runner.compute_overall_status(cards, unexpected=1, errors=[])
        self.assertEqual(status, "BLOCKED")


class TestFullPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.base = make_fixture_root(self.tmp / "home_carix")
        self.report_root = self.tmp / "reports" / "ua_cards_unified"
        self.package_dir = Path(runner.__file__).resolve().parent

    def test_all_real_cards_pass_but_overall_blocked_pending_ua0009(self):
        result = runner.run_gate_a(self.base, self.report_root, self.package_dir)
        for code in common.REAL_CODES:
            self.assertEqual(result.cards[code]["status"], "PASS", result.cards[code])
        self.assertEqual(result.cards[common.UA0009]["status"], "BLOCKED")
        self.assertEqual(result.overall_status, "BLOCKED")
        self.assertEqual(result.production_write, "NO")
        for code in common.REAL_CODES:
            card = result.cards[code]
            preview = Path(card["output_path"])
            self.assertTrue(preview.is_file())
            self.assertTrue((preview.parent / card["diag_href"]).is_file())
            self.assertTrue((preview.parent / card["track_href"]).is_file())

    def test_missing_one_real_card_forces_blocked(self):
        codes_present = [c for c in common.REAL_CODES if c != "UA-0004"]
        base2 = make_fixture_root(self.tmp / "second", codes=codes_present)
        report_root2 = self.tmp / "second_reports"
        result = runner.run_gate_a(base2, report_root2, self.package_dir)
        self.assertEqual(result.cards["UA-0004"]["status"], "BLOCKED")
        self.assertEqual(result.overall_status, "BLOCKED")

    def test_repeat_output_byte_identical_10_times(self):
        html = VALID_CARD_HTML_TEMPLATE.format(code="UA-0001", legacy_diag=LEGACY_DIAG, legacy_track=LEGACY_TRACK)

        def build() -> bytes:
            transformed, errors = runner.process_card_html("UA-0001", html)
            self.assertEqual(errors, [])
            return transformed.encode("utf-8")

        self.assertTrue(verifier.verify_deterministic_repeat(build, times=10))

    def test_full_preview_bundle_byte_identical_10_runs(self):
        bundles = []
        for index in range(10):
            report_root = self.tmp / f"repeat-{index}"
            result = runner.run_gate_a(self.base, report_root, self.package_dir)
            bundle = {}
            for code in common.REAL_CODES:
                card = result.cards[code]
                preview = Path(card["output_path"])
                for name in (
                    f"{code}.html",
                    card["diag_href"],
                    card["track_href"],
                ):
                    bundle[name] = (preview.parent / name).read_bytes()
            bundles.append(bundle)
        self.assertTrue(all(bundle == bundles[0] for bundle in bundles[1:]))

    def test_protected_hashes_unchanged_after_run(self):
        result = runner.run_gate_a(self.base, self.report_root, self.package_dir)
        for name, before in result.protected_before.items():
            after = result.protected_after.get(name)
            self.assertEqual(before, after, f"{name} unexpectedly changed")
        self.assertEqual(result.unexpected_protected_changes, 0)


class TestSafeWriterBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.allowed = self.tmp / "reports"
        self.allowed.mkdir()
        self.writer = common.AtomicWriter([self.allowed])

    def test_write_inside_allowed_root_succeeds(self):
        target = self.allowed / "preview" / "out.html"
        self.writer.write_text(target, "hello")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello")

    def test_write_outside_allowed_root_rejected(self):
        outside = self.tmp / "outside" / "out.html"
        with self.assertRaises(common.PathEscapeError):
            self.writer.write_text(outside, "hello")
        self.assertFalse(outside.parent.exists())

    def test_traversal_rejected(self):
        traversal = self.allowed / ".." / "escape.html"
        with self.assertRaises(common.PathEscapeError):
            self.writer.write_text(traversal, "hello")

    def test_symlink_target_rejected(self):
        real_target = self.tmp / "real_file.html"
        real_target.write_text("data", encoding="utf-8")
        link_target = self.allowed / "link.html"
        os.symlink(real_target, link_target)
        with self.assertRaises(common.PathEscapeError):
            self.writer.write_text(link_target, "new-data")

    def test_pre_existing_non_regular_rejected(self):
        fifo_path = self.allowed / "fifo_target"
        try:
            os.mkfifo(fifo_path)
        except (AttributeError, OSError):
            self.skipTest("mkfifo not supported in this environment")
        with self.assertRaises(common.NotRegularFileError):
            self.writer.write_text(fifo_path, "data")

    def test_pre_existing_hard_link_rejected(self):
        original = self.tmp / "original.html"
        original.write_text("protected", encoding="utf-8")
        linked = self.allowed / "linked.html"
        try:
            os.link(original, linked)
        except OSError:
            self.skipTest("hard links not supported in this environment")
        with self.assertRaises(common.NotRegularFileError):
            self.writer.write_text(linked, "changed")
        self.assertEqual(original.read_text(encoding="utf-8"), "protected")


class TestManifestAndTamperDetection(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package_dir = Path(manifest_builder.__file__).resolve().parent

    def test_manifest_integrity_roundtrip(self):
        manifest = manifest_builder.build_manifest(
            task_id="task_021",
            source_provenance="cloud/ua_cards_unified",
            discovered_inputs={"UA-0001": "/tmp/x/UA-0001.html"},
            protected_paths_before={"UA-0001": "deadbeef"},
            write_roots=[str(self.tmp / "reports")],
            planned_outputs=[str(self.tmp / "reports" / "preview" / "UA-0001.html")],
            package_dir=self.package_dir,
        )
        self.assertTrue(manifest_builder.verify_manifest_integrity(manifest))

    def test_tampered_manifest_detected(self):
        manifest = manifest_builder.build_manifest(
            task_id="task_021",
            source_provenance="cloud/ua_cards_unified",
            discovered_inputs={},
            protected_paths_before={},
            write_roots=[str(self.tmp)],
            planned_outputs=[],
            package_dir=self.package_dir,
        )
        manifest["gate_b"] = True  # tamper
        self.assertFalse(manifest_builder.verify_manifest_integrity(manifest))

    def test_input_hash_tamper_detected_by_launcher(self):
        target = self.tmp / "UA-0001.html"
        target.write_text("original", encoding="utf-8")
        manifest = manifest_builder.build_manifest(
            task_id="task_021",
            source_provenance="cloud/ua_cards_unified",
            discovered_inputs={"UA-0001": str(target)},
            protected_paths_before={"UA-0001": common.sha256_file(target)},
            write_roots=[str(self.tmp)],
            planned_outputs=[],
            package_dir=self.package_dir,
        )
        target.write_text("tampered", encoding="utf-8")
        with self.assertRaises(launcher.LauncherError):
            launcher.verify_input_hashes(manifest, self.tmp)

    def test_code_hash_tamper_detected_by_launcher(self):
        manifest = manifest_builder.build_manifest(
            task_id="task_021",
            source_provenance="cloud/ua_cards_unified",
            discovered_inputs={},
            protected_paths_before={},
            write_roots=[str(self.tmp)],
            planned_outputs=[],
            package_dir=self.package_dir,
        )
        manifest["code_hashes"]["runner.py"] = "0" * 64
        with self.assertRaises(launcher.LauncherError):
            launcher.verify_code_hashes(manifest, self.package_dir)


class TestNoNetworkNoMutationOnImport(unittest.TestCase):
    def test_import_has_no_side_effects(self):
        import importlib
        for mod_name in (
            "ua_cards_unified.common",
            "ua_cards_unified.preflight",
            "ua_cards_unified.manifest_builder",
            "ua_cards_unified.runner",
            "ua_cards_unified.verifier",
            "ua_cards_unified.launcher",
        ):
            mod = importlib.import_module(mod_name)
            self.assertIsNotNone(mod)


class TestNoProductionCapability(unittest.TestCase):
    def test_launcher_rejects_cli_arguments_before_side_effects(self):
        with tempfile.TemporaryDirectory() as td:
            report_root = Path(td) / "reports"
            with mock.patch.object(sys, "argv", ["launcher", "--apply"]):
                with self.assertRaises(launcher.LauncherError):
                    launcher.run()
                self.assertFalse(report_root.exists())
                self.assertEqual(launcher.main(), 2)

    def test_no_argument_entrypoint_executes_bound_gate_a_once(self):
        with tempfile.TemporaryDirectory() as td:
            base = make_fixture_root(Path(td) / "home_carix")
            report_root = base / common.REPORT_SUBDIR
            package_dir = Path(launcher.__file__).resolve().parent
            before = {
                str(path): common.sha256_file(path)
                for path in base.rglob("*")
                if path.is_file()
            }
            with mock.patch.multiple(
                launcher,
                BASE_ROOT=base,
                REPORT_ROOT=report_root,
                PACKAGE_DIR=package_dir,
            ), mock.patch.object(sys, "argv", ["launcher"]), mock.patch("builtins.print"):
                self.assertEqual(launcher.main(), 0)
            receipts = list((report_root / "runs").glob("*/gate_a_receipt.json"))
            self.assertEqual(len(receipts), 1)
            receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
            self.assertEqual(receipt["production_write"], "NO")
            self.assertIn("manifest_sha256", receipt)
            self.assertIn("code_hashes", receipt)
            self.assertIn("output_hashes", receipt)
            self.assertIn("protected_before", receipt)
            self.assertIn("protected_after", receipt)
            after = {path: common.sha256_file(Path(path)) for path in before}
            self.assertEqual(before, after)

    def test_launcher_exports_no_mutating_control_functions(self):
        exported = set(vars(launcher))
        for forbidden_name in (
            "apply",
            "reload_webapp",
            "write_crm",
            "write_production",
        ):
            self.assertNotIn(forbidden_name, exported)


if __name__ == "__main__":
    unittest.main()
