"""Package historical evidence explicitly; do not widen runtime file scope."""
from datetime import datetime, timezone
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import build_preflight_bundle as B
import install_package as I
import preflight as P
import source_successor as S
import stage_preflight as T

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    path = ROOT / "cloud/task088_v5_install" / (name + ".py")
    spec = importlib.util.spec_from_file_location("successor_packaging_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceSuccessorPackagingTests(unittest.TestCase):
    def test_exact_preflight_stager_release_and_remote_closures(self):
        release, controller = load("build_release"), load("controller")
        for reconciliation in (False, True):
            mapping = B.package_mapping(ROOT, catalog_reconciliation=reconciliation)
            self.assertEqual(T.package_mapping(catalog_reconciliation=reconciliation),
                {name:path.relative_to(ROOT).as_posix() for name,path in mapping.items()})
            self.assertEqual(set(mapping), P.MODULES | P.TOOLS | (P.RECONCILIATION_TOOLS if reconciliation else set()))
        self.assertEqual(controller.REMOTE_FILES, I.MODULES | {"remote_adapter.py", "install_package.py", "source_successor.py"})
        self.assertNotIn("source_successor.py", I.MODULES)  # Helper never becomes an installed app feature.
        self.assertEqual(B.package_mapping(ROOT)["source_successor.py"].read_bytes(), release.sources()["source_successor.py"].read_bytes())
        self.assertEqual(I.sha(release.sources()["source_successor.py"].read_bytes()), I.SOURCE_SUCCESSOR_VALIDATOR_SHA256)
        self.assertEqual(S.SOURCE_SUCCESSOR_BINDING, T.SOURCE_SUCCESSOR_BINDING)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="source-successor-package-TEST-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = (Path(__file__).parent / S.SOURCE_SUCCESSOR_BINDING["file"]).read_bytes()
        self.stage2_raw = json.loads(self.raw)["artifacts"][S.STAGE2_PATH]["raw"].encode()
        for name, path in B.package_mapping(self.root).items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((Path(__file__).parent / "source_successor.py").read_bytes()
                             if name == "source_successor.py" else b"# TEST public package stand-in\n")
        self.observation = self.root / "observation.json"
        observed = {"contract":"TASK088-V5-INSTALL-OBSERVATION-1", "status":"PASS", "read_only":True,
            "observed_at":datetime.now(timezone.utc).isoformat(),
            "source_sha256":dict({name:"0"*64 for name in I.SOURCES}, **{"cars_ui.py":S.SUCCESSOR}),
            "dependency_sha256":{name:"0"*64 for name in I.DEPENDENCIES},
            "system_inventory":{}, "database":{"published_codes":["UA-0001"]},
            "stage_counts":{"kiev":0,"georgia":1,"sea":0,"korea":0}, "quota_evidence":{"TEST_ONLY":True}}
        self.observation.write_text(json.dumps(observed))
        self.stage2, self.chain = self.root/"stage2.json", self.root/"chain.json"
        self.stage2.write_bytes(self.stage2_raw)
        self.chain.write_bytes(self.raw)

    def build(self, *, chain=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return B.build(self.root, observation=self.observation, stage2_receipt=self.stage2,
                output_directory=self.root/"output", source_successor_chain=self.chain if chain else None)

    def test_archive_pins_helper_and_exact_evidence_preserving_stage2_raw(self):
        metadata = self.build()
        with zipfile.ZipFile(metadata["archive"]) as archive:
            bundle = json.loads(archive.read("preflight_bundle.json"))
            self.assertEqual(bundle["source_successor"], S.SOURCE_SUCCESSOR_BINDING)
            self.assertEqual(archive.read(S.SOURCE_SUCCESSOR_BINDING["file"]), self.raw)
            self.assertEqual(bundle["canonical_stage2_raw_file_sha256"], I.sha(self.stage2_raw))
            self.assertEqual(bundle["stage2_receipt"]["installed_source_sha256"], S.PREDECESSOR)
            self.assertEqual(bundle["package_sha256"]["source_successor.py"], I.SOURCE_SUCCESSOR_VALIDATOR_SHA256)
            self.assertEqual(bundle["authority_status"], "READONLY_PREFLIGHT_NOT_A_PRODUCTION_GATE")
        self.assertEqual(self.stage2.read_bytes(), self.stage2_raw)

    def test_unknown_observed_successor_stops_before_archive_creation(self):
        observed = json.loads(self.observation.read_bytes())
        observed["source_sha256"]["cars_ui.py"] = "1"*64
        self.observation.write_text(json.dumps(observed))
        with self.assertRaisesRegex(ValueError, "CURRENT_SOURCE_DRIFT"):
            self.build()
        self.assertFalse((self.root/"output").exists())

    def test_omitted_chain_keeps_original_source_guard(self):
        with self.assertRaisesRegex(ValueError, "EXACT_STAGE1_STAGE2"):
            self.build(chain=False)

    def test_tampered_chain_rejected_before_archive_creation(self):
        self.chain.write_bytes(self.raw + b"\n")
        with self.assertRaisesRegex(ValueError, "EXACT_REVIEWED_CHAIN"):
            self.build()
        self.assertFalse((self.root/"output").exists())


if __name__ == "__main__":
    unittest.main()
