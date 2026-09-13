"""Offline follow-up against exact captured, already-coordinated analytics."""
import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from repair_analytics_shell import patch_analytics_shell


class AnalyticsOwnershipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[4] / "private-runtime/complete-candidate17-v1/analitika_wsgi.py"
        # Source capture is intentionally outside Git; server bundle includes
        # the already-patched SHA-pinned candidate instead of this test input.
        if not source.is_file():
            raise unittest.SkipTest("private source capture unavailable")
        cls.original = source.read_bytes()
        cls.patched = patch_analytics_shell(cls.original)

    def test_canonical_pages_remain_byte_exact_and_optional_html_is_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ("video", "site"):
                (root / folder).mkdir()
            (root / ".ua_art_publish_transaction.lock").touch()
            protected = {}
            for folder in ("video", "site"):
                for name in ("UA-0001.html", "UA-0017-diag.html", "ua-000018.html", "UA-1234567.html", "katalog.html"):
                    data = ("<html><body><style>body{color:black}</style>" + name + "</body></html>").encode()
                    path = root / folder / name
                    path.write_bytes(data)
                    protected[path] = data
            optional = root / "video" / "optional.html"
            optional.write_bytes(b"<html><body>optional maintenance</body></html>")
            module = types.ModuleType("analytics_shell_fixture")
            source = self.patched.decode().replace('DOM = "/home/Carix"', "DOM = " + repr(str(root)))
            exec(compile(source, "analitika_wsgi.py", "exec"), module.__dict__)
            module._storozh()
            self.assertTrue(all(path.read_bytes() == data for path, data in protected.items()))
            self.assertIn(module.STROKA.encode(), optional.read_bytes())
            before = optional.read_bytes()
            module._FON[0] = 0
            module._storozh()
            self.assertEqual(optional.read_bytes(), before)

    def test_source_drift_and_repeat_refused(self):
        for source in (self.original + b"\n", self.patched):
            with self.assertRaisesRegex(ValueError, "ANALYTICS_SHELL_SOURCE_SHA_MISMATCH"):
                patch_analytics_shell(source)


if __name__ == "__main__":
    unittest.main()
