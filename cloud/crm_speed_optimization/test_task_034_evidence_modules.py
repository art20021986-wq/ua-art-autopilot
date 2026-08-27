"""Offline, deterministic, temporary-directory-only tests for TASK 034:
four standalone evidence modules (sqlite_ownership, ua0009_publication_
check, build_manifest, verify_gate_a). No network access. No
/home/Carix or production paths. No PythonAnywhere access. No Gate A
execution.
"""
import hashlib
import json
import os
import py_compile
import shutil
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite_ownership
import ua0009_publication_check as ua_check
import build_manifest
import verify_gate_a

MODULE_FILES = [
    "sqlite_ownership.py",
    "ua0009_publication_check.py",
    "build_manifest.py",
    "verify_gate_a.py",
    "test_task_034_evidence_modules.py",
]

SEEDED_SECRET = "no-pii-seed-marker-should-not-leak"


class CompileTests(unittest.TestCase):
    def test_all_modules_compile(self):
        base = os.path.dirname(os.path.abspath(__file__))
        for name in MODULE_FILES:
            path = os.path.join(base, name)
            py_compile.compile(path, doraise=True)


def _make_db(tmp, table="cards", column="code", value="UA-0009", extra_rows=None):
    db_path = os.path.join(tmp, "crm.db")
    conn = sqlite3.connect(db_path)
    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, {column} TEXT, secret TEXT)")
    conn.execute(f"INSERT INTO {table} ({column}, secret) VALUES (?, ?)", (value, SEEDED_SECRET))
    if extra_rows:
        for row_val in extra_rows:
            conn.execute(f"INSERT INTO {table} ({column}, secret) VALUES (?, ?)", (row_val, "extra"))
    conn.commit()
    conn.close()
    return db_path


class SqliteOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task034_sqlite_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_quick_check_ok_and_query_only_confirmed(self):
        db = _make_db(self.tmp)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "OK")
        self.assertEqual(ev.quick_check, "ok")
        self.assertEqual(ev.query_only, 1)

    def test_missing_db_blocks(self):
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(
            os.path.join(self.tmp, "nope.db"), "cards", "code", "UA-0009"
        )
        self.assertEqual(ev.status, "BLOCKED")

    def test_symlink_db_blocks(self):
        db = _make_db(self.tmp)
        link = os.path.join(self.tmp, "link.db")
        os.symlink(db, link)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(link, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "path_is_symlink")

    def test_hardlink_db_blocks(self):
        db = _make_db(self.tmp)
        other = os.path.join(self.tmp, "other.db")
        os.link(db, other)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "path_hard_linked")

    def test_malformed_db_blocks(self):
        bad = os.path.join(self.tmp, "bad.db")
        with open(bad, "wb") as fh:
            fh.write(b"not a real sqlite database file, garbage bytes here" * 10)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(bad, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "BLOCKED")

    def test_locked_db_blocks_identical_bytes_before_after(self):
        db = _make_db(self.tmp)
        with open(db, "rb") as fh:
            before_bytes = fh.read()
        conn = sqlite3.connect(db)
        conn.execute("BEGIN EXCLUSIVE")
        try:
            ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009", timeout=0.2)
            self.assertEqual(ev.status, "BLOCKED")
        finally:
            conn.rollback()
            conn.close()
        with open(db, "rb") as fh:
            after_bytes = fh.read()
        self.assertEqual(before_bytes, after_bytes)

    def test_missing_table_and_column_block(self):
        db = _make_db(self.tmp)
        ev1 = sqlite_ownership.collect_ua0009_ownership_evidence(db, "nope", "code", "UA-0009")
        self.assertEqual(ev1.status, "BLOCKED")
        self.assertEqual(ev1.reason, "missing_table")
        ev2 = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "nope", "UA-0009")
        self.assertEqual(ev2.status, "BLOCKED")
        self.assertEqual(ev2.reason, "missing_column")

    def test_missing_row_blocks(self):
        db = _make_db(self.tmp)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-9999")
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "missing_row")

    def test_ambiguous_rows_block(self):
        db = _make_db(self.tmp, extra_rows=["UA-0009"])
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "ambiguous_row")

    def test_table_overflow_blocks(self):
        db = _make_db(self.tmp)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(
            db, "cards", "code", "UA-0009", max_tables=0
        )
        self.assertEqual(ev.status, "BLOCKED")
        self.assertEqual(ev.reason, "table_overflow")

    def test_evidence_has_no_seeded_pii(self):
        db = _make_db(self.tmp)
        ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        serialized = json.dumps(ev.to_dict())
        self.assertNotIn(SEEDED_SECRET, serialized)

    def test_compare_before_after_identical_is_ok(self):
        db = _make_db(self.tmp)
        before = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        after = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        ok, reason = sqlite_ownership.compare_ownership_evidence(before, after)
        self.assertTrue(ok, reason)

    def test_compare_before_after_changed_blocks(self):
        db = _make_db(self.tmp)
        before = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        conn = sqlite3.connect(db)
        conn.execute("UPDATE cards SET secret = 'changed-value' WHERE code = 'UA-0009'")
        conn.commit()
        conn.close()
        after = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")
        ok, reason = sqlite_ownership.compare_ownership_evidence(before, after)
        self.assertFalse(ok)

    def test_incomplete_evidence_compare_blocks(self):
        blocked = sqlite_ownership.OwnershipEvidence(status="BLOCKED", reason="x")
        ok_ev = sqlite_ownership.OwnershipEvidence(status="OK", reason="ok", evidence_sha256="a" * 64)
        ok, reason = sqlite_ownership.compare_ownership_evidence(blocked, ok_ev)
        self.assertFalse(ok)
        self.assertEqual(reason, "incomplete_evidence")

    def test_cursor_and_connection_closed_before_hashing(self):
        db = _make_db(self.tmp)
        events = []
        orig_connect = sqlite_ownership.sqlite3.connect
        orig_sha256 = sqlite_ownership.hashlib.sha256

        class ProxyCursor:
            def __init__(self, real):
                self._real = real

            def execute(self, *a, **kw):
                return self._real.execute(*a, **kw)

            def close(self):
                events.append("cursor_close")
                self._real.close()

        class ProxyConn:
            def __init__(self, real):
                self._real = real

            def cursor(self):
                return ProxyCursor(self._real.cursor())

            def close(self):
                events.append("conn_close")
                self._real.close()

        def fake_connect(*args, **kwargs):
            return ProxyConn(orig_connect(*args, **kwargs))

        def tracking_sha256(*args, **kwargs):
            events.append("sha256")
            return orig_sha256(*args, **kwargs)

        with mock.patch.object(sqlite_ownership.sqlite3, "connect", fake_connect), \
             mock.patch.object(sqlite_ownership.hashlib, "sha256", tracking_sha256):
            ev = sqlite_ownership.collect_ua0009_ownership_evidence(db, "cards", "code", "UA-0009")

        self.assertEqual(ev.status, "OK")
        self.assertIn("cursor_close", events)
        self.assertIn("conn_close", events)
        self.assertIn("sha256", events)
        self.assertLess(events.index("cursor_close"), events.index("sha256"))
        self.assertLess(events.index("conn_close"), events.index("sha256"))

    def test_public_names_still_importable(self):
        self.assertTrue(hasattr(sqlite_ownership, "transform_short_ownership"))
        self.assertTrue(hasattr(sqlite_ownership, "verify_no_live_handle_across_slow_call"))
        self.assertTrue(hasattr(sqlite_ownership, "find_db_handle_names"))
        self.assertTrue(hasattr(sqlite_ownership, "AnchorNotFoundError"))


class FakeResponse:
    def __init__(self, code):
        self._code = code

    def getcode(self):
        return self._code

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class BadResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, code=None, raise_exc=None):
        self.code = code
        self.raise_exc = raise_exc

    def open(self, req, timeout=None):
        if self.raise_exc:
            raise self.raise_exc
        return FakeResponse(self.code)


class BadOpener:
    def open(self, req, timeout=None):
        return BadResponse()


class PublicationCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task034_pub_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_404_passes(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "PASS")

    def test_410_passes(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 410, "gone", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "PASS")

    def test_200_blocks(self):
        opener = FakeOpener(code=200)
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")

    def test_redirect_status_blocks(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 301, "moved", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")

    def test_other_4xx_blocks(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 403, "forbidden", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")

    def test_5xx_blocks(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 500, "err", {}, None))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")

    def test_network_error_blocks_status_minus_one(self):
        opener = FakeOpener(raise_exc=urllib.error.URLError("no network"))
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.status_code, -1)

    def test_malformed_response_blocks(self):
        result = ua_check.canonical_probe_ua0009("https://example.com/UA-0009.html", opener=BadOpener())
        self.assertEqual(result.status, "BLOCKED")

    def test_non_https_blocks(self):
        result = ua_check.canonical_probe_ua0009("http://example.com/UA-0009.html", opener=FakeOpener(code=404))
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason, "non_https_url")

    def test_malformed_url_blocks(self):
        result = ua_check.canonical_probe_ua0009("not-a-url", opener=FakeOpener(code=404))
        self.assertEqual(result.status, "BLOCKED")

    def test_embedded_credentials_block(self):
        result = ua_check.canonical_probe_ua0009("https://user:pass@example.com/x", opener=FakeOpener(code=404))
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason, "embedded_credentials")

    def test_legacy_probe_no_redirect_returns_status_code(self):
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        code = ua_check.probe_no_redirect("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(code, 404)

    def test_legacy_probe_no_redirect_network_error_returns_minus_one(self):
        opener = FakeOpener(raise_exc=urllib.error.URLError("down"))
        code = ua_check.probe_no_redirect("https://example.com/UA-0009.html", opener=opener)
        self.assertEqual(code, -1)

    def test_legacy_check_ua0009_not_public_fails_closed_without_url(self):
        db = _make_db(self.tmp)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ua_check.CONFIG_ENV_VAR, None)
            result = ua_check.check_ua0009_not_public(db, url=None, opener=FakeOpener(code=404))
        self.assertFalse(result.ok)

    def test_legacy_check_ua0009_not_public_ok_on_404_and_quickcheck_ok(self):
        db = _make_db(self.tmp)
        opener = FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        result = ua_check.check_ua0009_not_public(db, url="https://example.com/UA-0009.html", opener=opener)
        self.assertTrue(result.ok, result.reason)

    def test_legacy_check_ua0009_not_public_blocks_on_200(self):
        db = _make_db(self.tmp)
        opener = FakeOpener(code=200)
        result = ua_check.check_ua0009_not_public(db, url="https://example.com/UA-0009.html", opener=opener)
        self.assertFalse(result.ok)

    def test_public_names_still_importable(self):
        self.assertTrue(hasattr(ua_check, "PublicationCheckResult"))
        self.assertTrue(hasattr(ua_check, "resolve_canonical_url"))
        self.assertTrue(hasattr(ua_check, "sqlite_quick_check"))
        self.assertTrue(hasattr(ua_check, "check_ua0009_not_public"))
        self.assertTrue(hasattr(ua_check, "CONFIG_ENV_VAR"))
        self.assertTrue(hasattr(ua_check, "CONFIG_FILE_CANDIDATE"))


class BuildManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task034_manifest_")
        self.package_dir = os.path.join(self.tmp, "package")
        os.makedirs(self.package_dir)
        with open(os.path.join(self.package_dir, "mod_a.py"), "w") as fh:
            fh.write("x = 1\n")
        self.run_dir = os.path.join(self.tmp, "run")
        os.makedirs(self.run_dir)
        self.receipt_path = os.path.join(self.run_dir, "receipt.json")
        with open(self.receipt_path, "w") as fh:
            json.dump({"status": "PASS"}, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_deterministic_manifest_from_identical_inputs(self):
        kwargs = dict(
            run_artifact_paths={"receipt": self.receipt_path},
            allowed_write_ledger=[{"path": "a", "sha256": "x"}, {"path": "b", "sha256": "y"}],
            sqlite_evidence={"quick_check": "ok"},
            ua0009_evidence_before={"h": "1"},
            ua0009_evidence_after={"h": "1"},
            publication_evidence={"status": "PASS"},
        )
        m1 = build_manifest.build_manifest(self.package_dir, self.run_dir, **kwargs)
        m2 = build_manifest.build_manifest(self.package_dir, self.run_dir, **kwargs)
        self.assertEqual(build_manifest.canonical_json(m1), build_manifest.canonical_json(m2))

    def test_pii_emitted_field_is_no(self):
        m = build_manifest.build_manifest(self.package_dir, self.run_dir)
        self.assertEqual(m["pii_emitted"], "NO")

    def test_manifest_has_no_self_referential_hash(self):
        m = build_manifest.build_manifest(self.package_dir, self.run_dir)
        self.assertNotIn("manifest_sha256", m)

    def test_symlink_run_artifact_blocks(self):
        link = os.path.join(self.run_dir, "link_receipt.json")
        os.symlink(self.receipt_path, link)
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(
                self.package_dir, self.run_dir, run_artifact_paths={"receipt": link}
            )

    def test_hardlink_run_artifact_blocks(self):
        other = os.path.join(self.run_dir, "other_receipt.json")
        os.link(self.receipt_path, other)
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(
                self.package_dir, self.run_dir, run_artifact_paths={"receipt": other}
            )

    def test_outside_run_dir_blocks(self):
        outside = os.path.join(self.tmp, "outside.json")
        with open(outside, "w") as fh:
            fh.write("{}")
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(
                self.package_dir, self.run_dir, run_artifact_paths={"receipt": outside}
            )

    def test_symlink_package_file_blocks(self):
        link = os.path.join(self.package_dir, "mod_link.py")
        os.symlink(os.path.join(self.package_dir, "mod_a.py"), link)
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(self.package_dir, self.run_dir)

    def test_missing_run_dir_blocks(self):
        with self.assertRaises(ValueError):
            build_manifest.build_manifest(self.package_dir, os.path.join(self.tmp, "nope"))


class VerifyGateATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="task034_verify_")
        self.run_dir = os.path.join(self.tmp, "run")
        os.makedirs(self.run_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _predicates_ok(self):
        return {k: {"status": "OK"} for k in verify_gate_a.REQUIRED_PREDICATES}

    def _write_receipt(self, data, name="receipt.json"):
        path = os.path.join(self.run_dir, name)
        with open(path, "w") as fh:
            json.dump(data, fh)
        return path

    def test_pass_receipt_verifies_ok(self):
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(), "unmet_predicates": [],
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertTrue(ok, reason)

    def test_legacy_two_positional_arg_call_still_works(self):
        receipt = {
            "status": "BLOCKED", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(),
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, None)
        self.assertTrue(ok, reason)

    def test_missing_predicate_blocks(self):
        preds = self._predicates_ok()
        del preds[verify_gate_a.REQUIRED_PREDICATES[0]]
        receipt = {
            "status": "BLOCKED", "production_write": "NO", "pii_emitted": "NO",
            "predicates": preds,
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("missing_or_malformed_predicate"))

    def test_pass_with_unmet_predicate_blocks(self):
        preds = self._predicates_ok()
        preds[verify_gate_a.REQUIRED_PREDICATES[0]] = {"status": "BLOCKED"}
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": preds, "unmet_predicates": [],
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_production_write_not_no_blocks(self):
        receipt = {
            "status": "BLOCKED", "production_write": "YES", "pii_emitted": "NO",
            "predicates": self._predicates_ok(),
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "production_write_not_no")

    def test_pii_emitted_not_no_blocks(self):
        receipt = {
            "status": "BLOCKED", "production_write": "NO", "pii_emitted": "YES",
            "predicates": self._predicates_ok(),
        }
        path = self._write_receipt(receipt)
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "pii_emitted_not_no")

    def test_symlink_receipt_blocks(self):
        real = self._write_receipt({"status": "BLOCKED", "production_write": "NO",
                                     "pii_emitted": "NO", "predicates": self._predicates_ok()})
        link = os.path.join(self.run_dir, "link.json")
        os.symlink(real, link)
        ok, reason = verify_gate_a.verify_receipt(link, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_hardlink_receipt_blocks(self):
        real = self._write_receipt({"status": "BLOCKED", "production_write": "NO",
                                     "pii_emitted": "NO", "predicates": self._predicates_ok()})
        other = os.path.join(self.run_dir, "hardlink.json")
        os.link(real, other)
        ok, reason = verify_gate_a.verify_receipt(other, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_non_regular_file_blocks(self):
        # a directory named receipt.json is not a regular file
        fake_dir = os.path.join(self.run_dir, "dir_receipt.json")
        os.makedirs(fake_dir)
        ok, reason = verify_gate_a.verify_receipt(fake_dir, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_duplicate_key_blocks(self):
        path = os.path.join(self.run_dir, "dup.json")
        with open(path, "w") as fh:
            fh.write(
                '{"status": "BLOCKED", "status": "PASS", "production_write": "NO", '
                '"pii_emitted": "NO", "predicates": {}}'
            )
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_extra_data_blocks(self):
        path = os.path.join(self.run_dir, "extra.json")
        with open(path, "w") as fh:
            fh.write('{"status": "BLOCKED"} garbage-extra-data')
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_non_utf8_blocks(self):
        path = os.path.join(self.run_dir, "bad.json")
        with open(path, "wb") as fh:
            fh.write(b"\xff\xfe\x00\x01not utf8")
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_oversized_blocks(self):
        path = os.path.join(self.run_dir, "big.json")
        with open(path, "w") as fh:
            fh.write('{"status": "BLOCKED", "pad": "' + ("a" * (verify_gate_a.MAX_JSON_BYTES + 100)) + '"}')
        ok, reason = verify_gate_a.verify_receipt(path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_manifest_hash_binding_ok_then_tamper_detected(self):
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(), "unmet_predicates": [],
        }
        receipt_path = self._write_receipt(receipt)
        receipt_hash = verify_gate_a._secure_hash_file(receipt_path, os.path.realpath(self.run_dir))
        manifest = {"receipt_sha256": receipt_hash}
        manifest_path = os.path.join(self.run_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh)

        ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path=manifest_path, run_dir=self.run_dir)
        self.assertTrue(ok, reason)

        with open(receipt_path, "a") as fh:
            fh.write(" ")
        ok2, reason2 = verify_gate_a.verify_receipt(receipt_path, manifest_path=manifest_path, run_dir=self.run_dir)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "receipt_hash_mismatch")

    def test_missing_evidence_manifest_blocks(self):
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(), "unmet_predicates": [],
        }
        receipt_path = self._write_receipt(receipt)
        manifest_path = os.path.join(self.run_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump({}, fh)
        ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path=manifest_path, run_dir=self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "receipt_hash_mismatch")

    def test_manifest_malformed_blocks(self):
        receipt = {
            "status": "PASS", "production_write": "NO", "pii_emitted": "NO",
            "predicates": self._predicates_ok(), "unmet_predicates": [],
        }
        receipt_path = self._write_receipt(receipt)
        manifest_path = os.path.join(self.run_dir, "manifest.json")
        with open(manifest_path, "wb") as fh:
            fh.write(b"{not valid json")
        ok, reason = verify_gate_a.verify_receipt(receipt_path, manifest_path=manifest_path, run_dir=self.run_dir)
        self.assertFalse(ok)

    def test_public_names_still_importable(self):
        self.assertTrue(hasattr(verify_gate_a, "verify_receipt"))
        self.assertTrue(hasattr(verify_gate_a, "REQUIRED_PREDICATES"))


class CrossModuleImportCompatibilityTests(unittest.TestCase):
    def test_all_four_modules_importable_together(self):
        self.assertTrue(hasattr(sqlite_ownership, "transform_short_ownership"))
        self.assertTrue(hasattr(ua0009_publication_check_module(), "resolve_canonical_url"))
        self.assertTrue(hasattr(build_manifest, "build_manifest"))
        self.assertTrue(hasattr(verify_gate_a, "verify_receipt"))


def ua0009_publication_check_module():
    return ua_check


if __name__ == "__main__":
    unittest.main()
