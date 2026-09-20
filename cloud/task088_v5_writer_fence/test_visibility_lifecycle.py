"""Affected native visibility lifecycle proofs on isolated SQLite/static roots."""
import contextlib
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "task088_price_sync"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import outbox
sys.modules["uaart_price_sync_outbox"] = outbox
import visibility_lifecycle as visibility
from publication_fence import PublicationFence


class NativeVisibility(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "crm.db"
        with sqlite3.connect(self.database) as conn:
            conn.execute("CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,published INTEGER,status TEXT,price_uah INTEGER,price_georgia INTEGER,vin TEXT)")
            conn.execute("INSERT INTO cars VALUES(1,'UA-0001',1,'kr_bought',10000,NULL,'VIN1')")
            conn.execute("CREATE TABLE " + outbox.V5_TABLE + "(event_key TEXT,car_id INTEGER,state TEXT,sequence INTEGER)")
        for folder in ("video", "site"):
            root = self.root / folder; root.mkdir()
            for name in ("UA-0001.html", "UA-0001-diag.html", "UA-0001-abcdef.html"):
                (root / name).write_text("old car UA-0001 price 10000")
            (root / "katalog.html").write_text("UA-0001")
            (root / "index.html").write_text("count=1")
            (root / "UA-0001.mp4").write_bytes(b"media preserved")
        journal = self.root / "journal"; journal.mkdir(mode=0o700)
        self.binding = types.SimpleNamespace(db_path=self.database, journal_root=journal,
            resolve_surfaces=lambda code: [types.SimpleNamespace(kind="HOME", path=self.root / folder / "index.html")
                                          for folder in ("video", "site")],
            publication_lock=self.root / "publication.lock")
        self.binding.clock = lambda: 1000
        self.binding.authorize_visibility = lambda car_id, actor_id: {
            "car_id": car_id, "actor_id": actor_id, "permission": "EDIT_CAR",
            "writer_fence_verified": True, "observed_ms": 999, "expires_ms": 2000,
            "identity": {"auto_number": "UA-0001"}}
        self.publish_calls = 0
        self.rebuild_calls = 0
        self.worker = types.SimpleNamespace(connection=lambda: sqlite3.connect(self.database),
            lock=lambda path: contextlib.nullcontext(), process_operation=self.process)
        self.service = visibility.Lifecycle(self.binding, worker=self.worker,
            publish=self.publish, rebuild=self.rebuild, verify_published=self.verify_published,
            verify_shared=self.verify_shared, ready=lambda row: [],
            fence=lambda: PublicationFence(lock_path=self.binding.publication_lock, _test_only_path=True))

    def process(self, key):
        with sqlite3.connect(self.database) as conn:
            conn.execute("UPDATE cars SET price_uah=12000 WHERE id=1")
            conn.execute("UPDATE " + outbox.V5_TABLE + " SET state='COMPLETED' WHERE event_key=?", (key,))
        return {"state": "COMPLETED"}

    def key(self, value):
        return hashlib.sha256(value.encode()).hexdigest()

    def call(self, value, target=0, **kw):
        return self.service.transition(key=self.key(value), car_id=1, target=target, actor_id=7, **kw)

    def rebuild(self, code=None, key=None):
        self.rebuild_calls += 1
        row = visibility.current_row(self.binding, 1)
        for folder in ("video", "site"):
            (self.root / folder / "katalog.html").write_text("UA-0001" if row["published"] else "empty")
            (self.root / folder / "index.html").write_text("count=" + str(row["published"]))
        return True, "done"

    def publish(self, code):
        self.publish_calls += 1
        row = visibility.current_row(self.binding, 1)
        for folder in ("video", "site"):
            for suffix in ("", "-diag"):
                (self.root / folder / (code + suffix + ".html")).write_text(str(row["price_uah"]))
        return self.rebuild()

    def verify_shared(self, code=None):
        row = visibility.current_row(self.binding, 1)
        for folder in ("video", "site"):
            self.assertEqual((self.root / folder / "index.html").read_text(), "count=" + str(row["published"]))

    def verify_published(self, code):
        row = visibility.current_row(self.binding, 1)
        for folder in ("video", "site"):
            self.assertEqual((self.root / folder / (code + ".html")).read_text(), str(row["price_uah"]))
        return {"files": "verified", "price": row["price_uah"]}

    def test_withdrawal_retires_direct_and_alias_paths_preserves_media(self):
        result = self.call("unpublish")
        self.assertEqual(result["state"], "VERIFIED")
        self.assertFalse(result["live_http_verified"])
        for folder in ("video", "site"):
            self.assertFalse(list((self.root / folder).glob("UA-0001*.html")))
            self.assertEqual((self.root / folder / "UA-0001.mp4").read_bytes(), b"media preserved")
        self.assertEqual(visibility.current_row(self.binding, 1)["price_uah"], 10000)

    def test_pending_price_drained_before_republication_current_data(self):
        self.call("unpublish")
        with sqlite3.connect(self.database) as conn:
            conn.execute("INSERT INTO " + outbox.V5_TABLE + " VALUES('intent',1,'DB_COMMITTED',1)")
        result = self.call("republish", 1)
        self.assertEqual(result["proof"]["price"], 12000)

    def test_replay_old_event_does_not_toggle_newer_visibility(self):
        self.call("unpublish")
        self.call("republish", 1)
        replay = self.call("unpublish")
        self.assertTrue(replay["replay"])
        self.assertEqual(visibility.current_row(self.binding, 1)["published"], 1)
        self.assertEqual(self.publish_calls, 1)

    def test_unknown_projection_after_crash_is_inspected_not_repeated(self):
        original = self.service.rebuild
        def interrupted(code, key):
            original(code)
            raise KeyboardInterrupt()
        self.service.rebuild = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.call("interrupted")
        self.service.rebuild = original
        result = self.call("interrupted")
        self.assertEqual(result["state"], "VERIFIED")
        self.assertEqual(self.rebuild_calls, 1)

    def test_ambiguous_incomplete_projection_never_blindly_repeats(self):
        self.service.rebuild = lambda code, key: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.call("ambiguous")
        self.service.rebuild = self.rebuild
        with self.assertRaises(AssertionError):
            self.call("ambiguous")
        self.assertEqual(self.rebuild_calls, 0)

    def test_sold_uses_same_visibility_closure_and_keeps_record(self):
        self.call("sold", status="sold")
        row = visibility.current_row(self.binding, 1)
        self.assertEqual((row["published"], row["status"]), (0, "sold"))

    def test_sold_from_nullable_status_compares_and_reads_back(self):
        with sqlite3.connect(self.database) as conn:
            conn.execute("UPDATE cars SET published=NULL,status=NULL WHERE id=1")
        result = self.call("sold-null", status="sold")
        self.assertEqual(result["state"], "VERIFIED")
        row = visibility.current_row(self.binding, 1)
        self.assertEqual((row["published"], row["status"]), (0, "sold"))

    def test_withdrawal_closes_before_reconciling_each_price_checkpoint(self):
        for checkpoint in ("QUEUED", "CLAIMED", "DB_COMMITTED", "SITE_PUBLISHED", "VERIFIED"):
            with self.subTest(checkpoint=checkpoint):
                if visibility.current_row(self.binding, 1)["published"] == 0:
                    self.call("republish-" + checkpoint, 1)
                with sqlite3.connect(self.database) as conn:
                    conn.execute("INSERT INTO " + outbox.V5_TABLE + " VALUES(?,1,?,1)", (checkpoint, checkpoint))
                def reconcile(key):
                    # This must succeed before the price state is touched.
                    visibility.verify_hidden(self.binding, visibility.current_row(self.binding, 1))
                    return self.process(key)
                self.worker.reconcile_hidden_operation = reconcile
                result = self.call("withdraw-" + checkpoint)
                self.assertEqual(result["price_reconciliation"], [{"state": "COMPLETED"}])

    def test_generic_stage_image_not_a_public_listing(self):
        self.call("thumbnail")
        path = self.root / "video" / "index.html"
        path.write_text('<img src="/video/stage/UA-0001.webp" alt="Stage">')
        proof = visibility.verify_hidden(self.binding, visibility.current_row(self.binding, 1))
        self.assertTrue(proof["retired_public_views_verified"])
        path.write_text('<a href="/video/UA-0001.html">Car</a>')
        with self.assertRaisesRegex(visibility.VisibilityError, "PUBLIC_LISTING_NOT_RETIRED"):
            visibility.verify_hidden(self.binding, visibility.current_row(self.binding, 1))

    def test_unknown_alias_fails_before_visibility_or_files_change(self):
        path = self.root / "video" / "UA-0001-offer.html"
        path.write_text("unknown")
        with self.assertRaisesRegex(visibility.VisibilityError, "UNBOUND_PUBLIC_ALIAS"):
            self.call("unknown-alias")
        self.assertEqual(visibility.current_row(self.binding, 1)["published"], 1)
        self.assertEqual(path.read_text(), "unknown")

    def test_authority_expiry_before_db_commit_rolls_back_visibility(self):
        ticks = iter((1000, 2000))
        self.binding.clock = lambda: next(ticks)
        with self.assertRaisesRegex(visibility.VisibilityError, "VISIBILITY_AUTHORITY_EXPIRED"):
            self.call("expired-before-commit")
        self.assertEqual(visibility.current_row(self.binding, 1)["published"], 1)
        self.assertTrue((self.root / "video" / "UA-0001.html").exists())

    def test_authority_expiry_before_unlink_preserves_file_and_resumes_same_id(self):
        ticks = iter((1000, 1000, 2000))
        self.binding.clock = lambda: next(ticks)
        with self.assertRaisesRegex(visibility.VisibilityError, "VISIBILITY_AUTHORITY_EXPIRED"):
            self.call("expired-before-unlink")
        self.assertEqual(visibility.current_row(self.binding, 1)["published"], 0)
        self.assertTrue((self.root / "video" / "UA-0001.html").exists())
        self.binding.clock = lambda: 1000
        result = self.call("expired-before-unlink")
        self.assertEqual(result["state"], "VERIFIED")

    def test_forward_atomic_switch_checks_after_staging(self):
        path = self.root / "video" / "atomic.html"
        path.write_bytes(b"previous")
        calls = []
        def check():
            calls.append(True)
            if len(calls) > 1:
                raise visibility.VisibilityError("expired")
        with self.assertRaisesRegex(visibility.VisibilityError, "expired"):
            with visibility.authority_scope(check):
                visibility.atomic_bytes(path, b"candidate", 0o644)
        self.assertEqual(path.read_bytes(), b"previous")

    def test_new_operator_price_between_crash_and_resume_is_preserved(self):
        original = self.service.rebuild
        def interrupted(code, key):
            original(code); raise KeyboardInterrupt()
        self.service.rebuild = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.call("operator")
        with sqlite3.connect(self.database) as conn:
            conn.execute("UPDATE cars SET price_uah=14000 WHERE id=1")
        self.call("operator")
        self.assertEqual(visibility.current_row(self.binding, 1)["price_uah"], 14000)


if __name__ == "__main__":
    unittest.main()
