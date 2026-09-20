"""New point3 checks: real extracted helper + SQLite/files; no site/CRM access."""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import integrate_private_sources as builder
import mutation_recovery as recovery
import publication_fence as fence


BASE = Path(os.environ["UA114_PRIVATE_BASE"])


def extract(source, name, *, occurrence=-1, root=None):
    nodes = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    node = nodes[occurrence]
    if root is not None:
        class Paths(ast.NodeTransformer):
            def visit_Constant(self, n):
                if isinstance(n.value, str) and n.value.startswith("/home/Carix"):
                    return ast.copy_location(ast.Constant(str(root) + n.value[len("/home/Carix"):]), n)
                return n
        node = Paths().visit(node)
    tree = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    return compile(tree, "<private-helper-without-logged-source>", "exec")


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "crm.db"
        self.video = self.root / "video"
        self.video.mkdir()
        (self.video / "foto" / "UA-0007").mkdir(parents=True)
        (self.video / "diag" / "UA-0007").mkdir(parents=True)
        self.cache = self.root / ".video_sinhron.json"
        self.cache.write_text(json.dumps({"UA-0007": {"clip": "old"}, "UA-0008": {"clip": "other"}}))
        self.con = sqlite3.connect(self.database)
        self.addCleanup(self.con.close)
        self.con.executescript("""
        CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,photos TEXT,cover_photo TEXT,
          hidden_photos TEXT,videos TEXT,video_h TEXT,video_v TEXT,condition_photos TEXT,
          condition_videos TEXT,price_uah INTEGER,price_georgia INTEGER);
        CREATE TABLE media(id INTEGER PRIMARY KEY,car_id INTEGER,vid TEXT,status TEXT,
          file_id TEXT,tag TEXT,poryadok INTEGER);
        INSERT INTO cars VALUES(7,'UA-0007','["p"]','p','[]','[{"file_id":"v","tag":""}]',
          'h','v','["dp"]','["dv"]',10000,9000);
        INSERT INTO media VALUES(1,7,'video','ready','v','',1);
        INSERT INTO media VALUES(2,7,'photo','ready','p','',2);
        INSERT INTO media VALUES(3,8,'video','ready','other','',1);
        """)
        self.con.commit()
        self.events = []
        self.lock = self.root / "publication.lock"
        self.ns = self.namespace()

    def card(self, cid=7):
        cur = self.con.execute("SELECT * FROM cars WHERE id=?", (cid,))
        row = cur.fetchone()
        return dict(zip([x[0] for x in cur.description], row)) if row else None

    def namespace(self):
        original = (BASE / "private_v5_sources_recovered/cars_ui.py").read_text()
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), builder.BEFORE_SHA256["cars_ui.py"])
        source = builder._integrate_cars_text(original)
        state = self

        def update(_table, cid, field, value, actor):
            fence.require_publication_fence(lock_path=state.lock)
            con = sqlite3.connect(state.database)
            try:
                con.execute('UPDATE cars SET "' + field + '"=? WHERE id=?', (value, cid))
                con.commit()
            finally:
                con.close()
            state.events.append("field:" + field)

        def rebuild():
            fence.require_publication_fence(lock_path=state.lock)
            state.events.append("rebuild")
            return True

        ns = dict(os=os, json=json, Update=object,
                  ContextTypes=types.SimpleNamespace(DEFAULT_TYPE=object),
                  _ubrat_fayly_foto=lambda *_: 0, _ubrat_fayly_video=lambda *_: 0,
                  _ubrat_video_polno=lambda *_: (0, []), _peresobrat_stranicy=rebuild,
                  card_of=self.card, db=types.SimpleNamespace(update_card_field=update),
                  jdump=json.dumps, jload=lambda v: json.loads(v or "[]"),
                  photos_of=lambda c: json.loads(c["photos"] or "[]"),
                  videos_of=lambda c: json.loads(c["videos"] or "[]"),
                  _v142_papka=lambda *_: tempfile.mkdtemp(dir=self.root),
                  _s163=sqlite3, _j163=json, _v140_zapis=lambda *_: None)
        # These are the exact generated public additions, with fixture roots only.
        blocks = (builder.CARS_BLOCK + builder.RECOVERY_BLOCK).replace("/home/Carix", str(self.root))
        exec(compile(blocks, "<generated-additions>", "exec"), ns)
        exec(extract(source, "_v163_status", root=self.root), ns)
        ns["_ua114_publication_fence"] = lambda: fence.PublicationFence(lock_path=self.lock, _test_only_path=True)
        ns["_ua114_require_fence"] = lambda: fence.require_publication_fence(lock_path=self.lock)
        return ns

    def seed_video(self):
        for name, data in [("UA-0007.mp4", b"video-original"), ("UA-0007.mp4.poster.jpg", b"poster"), ("UA-0008.mp4", b"other-video")]:
            (self.video / name).write_bytes(data)

    def test_real_video_path_success_includes_media_and_cache(self):
        self.seed_video()
        result = self.ns["_ua114_video_remove_all_mutation"](7, 99)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.card()["videos"], "[]")
        self.assertEqual(self.con.execute("SELECT status FROM media WHERE id=1").fetchone()[0], "rejected")
        self.assertEqual(self.con.execute("SELECT status FROM media WHERE id=2").fetchone()[0], "ready")
        self.assertNotIn("UA-0007", json.loads(self.cache.read_text()))
        self.assertTrue((self.video / "UA-0008.mp4").exists())
        self.assertEqual(self.events[-1], "rebuild")

    def test_rebuild_failure_restores_real_media_fields_cache_and_files(self):
        self.seed_video()
        before = self.card()
        cache = json.loads(self.cache.read_text())
        statuses = self.con.execute("SELECT * FROM media ORDER BY id").fetchall()
        calls = []
        self.ns["_ua114_rebuild_pages_base"] = lambda: (calls.append(True) or len(calls) > 1)
        result = self.ns["_ua114_video_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertEqual(result["rollback_conflicts"], [], result)
        self.assertEqual(self.card(), before)
        self.assertEqual(self.con.execute("SELECT * FROM media ORDER BY id").fetchall(), statuses)
        self.assertEqual(json.loads(self.cache.read_text()), cache)
        self.assertEqual((self.video / "UA-0007.mp4").read_bytes(), b"video-original")

    def test_failed_video_preserves_operator_updates(self):
        self.seed_video()
        def fail():
            self.con.execute("UPDATE media SET status='operator-new' WHERE id=1")
            self.con.execute("UPDATE cars SET video_h='operator-new',price_uah=12345 WHERE id=7")
            self.con.commit()
            (self.video / "UA-0007.mp4").write_bytes(b"operator-new")
            cache = json.loads(self.cache.read_text())
            cache["UA-0008"] = {"clip": "operator-other"}
            self.cache.write_text(json.dumps(cache))
            return False
        self.ns["_ua114_rebuild_pages_base"] = fail
        result = self.ns["_ua114_video_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertIn("media:1", result["rollback_conflicts"])
        self.assertIn("video_h", result["rollback_conflicts"])
        self.assertEqual(self.card()["price_uah"], 12345)
        self.assertEqual(self.card()["price_georgia"], 9000)
        self.assertEqual(self.card()["video_h"], "operator-new")
        self.assertEqual((self.video / "UA-0007.mp4").read_bytes(), b"operator-new")
        self.assertEqual(json.loads(self.cache.read_text())["UA-0008"], {"clip": "operator-other"})

    def test_write_raises_after_commit_is_reconciled(self):
        self.seed_video()
        before = self.card()
        real = self.ns["db"].update_card_field
        def unknown(*args):
            real(*args)
            raise OSError("lost acknowledgement after commit")
        self.ns["db"].update_card_field = unknown
        result = self.ns["_ua114_video_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertEqual(self.card(), before)

    def test_fields_compare_and_swap_preserves_new_value(self):
        self.con.execute("UPDATE cars SET video_h='operator' WHERE id=7")
        self.con.commit()
        result = recovery.restore_fields(self.database, 7, {"video_h": "old"}, {"video_h": None})
        self.assertEqual(result, ["video_h"])
        self.assertEqual(self.card()["video_h"], "operator")

    def test_waiting_field_restore_observes_later_operator_commit(self):
        self.con.execute("BEGIN IMMEDIATE")
        self.con.execute("UPDATE cars SET video_h='operator' WHERE id=7")
        result = []
        thread = threading.Thread(target=lambda: result.extend(recovery.restore_fields(
            self.database, 7, {"video_h": "old"}, {"video_h": None})))
        thread.start()
        time.sleep(0.03)
        self.assertTrue(thread.is_alive())
        self.con.commit()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, ["video_h"])
        self.assertEqual(self.card()["video_h"], "operator")

    def test_cache_same_key_conflict_keeps_operator_value(self):
        entry = recovery.CacheEntry(self.cache, "UA-0007")
        entry.remove()
        self.cache.write_text(json.dumps({"UA-0007": "new", "UA-0008": "changed"}))
        self.assertEqual(entry.restore(), ["cache:UA-0007"])
        self.assertEqual(json.loads(self.cache.read_text())["UA-0007"], "new")

    def test_symlinked_photo_root_rejected_before_mutation(self):
        root = self.video / "foto/UA-0007"
        root.rmdir()
        external = self.root / "outside"
        external.mkdir()
        (external / "p.jpg").write_bytes(b"protected")
        root.symlink_to(external, target_is_directory=True)
        result = self.ns["_ua114_photo_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertEqual((external / "p.jpg").read_bytes(), b"protected")
        self.assertFalse(self.events)

    def test_restore_rejects_swapped_parent_symlink(self):
        folder = self.root / "original"
        folder.mkdir()
        target = folder / "p.jpg"
        target.write_bytes(b"original")
        backup = self.root / "backup"
        backup.mkdir()
        entries = recovery.backup_exact([target], folder, backup)
        target.unlink()
        folder.rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        folder.symlink_to(outside, target_is_directory=True)
        self.assertEqual(recovery.restore_exact(entries), ["media:p.jpg"])
        self.assertFalse((outside / "p.jpg").exists())

    def test_corrupt_backup_never_becomes_visible(self):
        target = self.root / "p.jpg"
        target.write_bytes(b"original")
        backup = self.root / "backup"
        backup.mkdir()
        entries = recovery.backup_exact([target], self.root, backup)
        target.unlink()
        Path(entries[0][1]).write_bytes(b"corrupt")
        self.assertEqual(recovery.restore_exact(entries), ["media:p.jpg"])
        self.assertFalse(target.exists())

    def test_restore_keeps_original_file_permissions(self):
        target = self.root / "p.jpg"
        target.write_bytes(b"original")
        target.chmod(0o640)
        backup = self.root / "backup"
        backup.mkdir()
        entries = recovery.backup_exact([target], self.root, backup)
        target.unlink()
        self.assertEqual(recovery.restore_exact(entries), [])
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_large_media_copy_and_restore_use_bounded_reads(self):
        target = self.root / "large.mp4"
        target.write_bytes(b"x" * (3 * 1024 * 1024 + 17))
        backup = self.root / "backup"
        backup.mkdir()
        original_open = recovery.open_regular
        sizes = []
        @contextlib.contextmanager
        def bounded(path):
            with original_open(path) as stream:
                class Reader:
                    def read(inner, size=-1):
                        self.assertGreater(size, 0)
                        self.assertLessEqual(size, 1024 * 1024)
                        sizes.append(size)
                        return stream.read(size)
                yield Reader()
        with patch.object(recovery, "open_regular", bounded):
            entries = recovery.backup_exact([target], self.root, backup)
            target.unlink()
            self.assertEqual(recovery.restore_exact(entries), [])
        self.assertEqual(target.stat().st_size, 3 * 1024 * 1024 + 17)
        self.assertTrue(sizes)

    def test_cache_recovery_keeps_permissions_and_unrelated_entry(self):
        self.cache.chmod(0o640)
        entry = recovery.CacheEntry(self.cache, "UA-0007")
        entry.remove()
        current = json.loads(self.cache.read_text())
        current["UA-0008"] = "operator"
        self.cache.write_text(json.dumps(current))
        self.assertEqual(entry.restore(), [])
        self.assertEqual(json.loads(self.cache.read_text())["UA-0008"], "operator")
        self.assertEqual(self.cache.stat().st_mode & 0o777, 0o640)

    def test_atomic_restore_preserves_racing_file(self):
        target = self.root / "p.jpg"
        target.write_bytes(b"original")
        backup = self.root / "backup"
        backup.mkdir()
        entries = recovery.backup_exact([target], self.root, backup)
        target.unlink()
        link = os.link
        def race(*args, **kwargs):
            target.write_bytes(b"new")
            return link(*args, **kwargs)
        with patch.object(recovery.os, "link", race):
            self.assertEqual(recovery.restore_exact(entries), ["media:p.jpg"])
        self.assertEqual(target.read_bytes(), b"new")

    def test_photo_failure_preserves_operator_field(self):
        photo = self.video / "foto/UA-0007/p.jpg"
        photo.write_bytes(b"photo")
        count = []
        def rebuild():
            count.append(1)
            if len(count) == 1:
                self.con.execute("UPDATE cars SET photos='[\"operator\"]' WHERE id=7")
                self.con.commit()
                return False
            return True
        self.ns["_ua114_rebuild_pages_base"] = rebuild
        result = self.ns["_ua114_photo_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertIn("photos", result["rollback_conflicts"])
        self.assertEqual(self.card()["photos"], '["operator"]')
        self.assertEqual(photo.read_bytes(), b"photo")

    def test_diagnostic_failure_restores_files_and_field(self):
        target = self.video / "diag/UA-0007/clip.mp4"
        target.write_bytes(b"xxxxftyp-video")
        original = self.card()["condition_videos"]
        calls = []
        self.ns["_ua114_rebuild_pages_base"] = lambda: (calls.append(1) or len(calls) > 1)
        result = self.ns["_ua114_diag_clear_mutation"](7, "condition_videos", 99)
        self.assertFalse(result["ok"])
        self.assertEqual(result["rollback_conflicts"], [])
        self.assertEqual(self.card()["condition_videos"], original)
        self.assertEqual(target.read_bytes(), b"xxxxftyp-video")

    def test_raw_media_helper_requires_fence(self):
        with self.assertRaises(Exception):
            self.ns["_v163_status"]("UA-0007", "rejected", "ready")
        self.assertEqual(self.con.execute("SELECT status FROM media WHERE id=1").fetchone()[0], "ready")

    def test_direct_video_entry_uses_transactional_path(self):
        self.seed_video()
        with self.ns["_ua114_publication_fence"]():
            removed, failures = self.ns["_ubrat_video_polno"]("UA-0007")
        self.assertEqual(failures, [])
        self.assertEqual(removed, 2)
        self.assertEqual(self.con.execute("SELECT status FROM media WHERE id=1").fetchone()[0], "rejected")

    def test_obsolete_video_primitive_stops_before_deletion(self):
        self.seed_video()
        with self.ns["_ua114_publication_fence"]():
            with self.assertRaisesRegex(RuntimeError, "USE_TRANSACTIONAL_VIDEO_MUTATION"):
                self.ns["_ubrat_fayly_video"]("UA-0007")
        self.assertEqual((self.video / "UA-0007.mp4").read_bytes(), b"video-original")

    def test_media_journal_intent_exists_before_commit(self):
        journal = recovery.MediaJournal(self.database, "UA-0007")
        backup = self.root / "journal"
        backup.mkdir()
        journal.evidence_directory = backup
        with self.ns["_ua114_publication_fence"](), journal.active():
            self.ns["_v163_status"]("UA-0007", "rejected", "ready")
        evidence = list(backup.glob("media-commit-*.json"))
        self.assertEqual(len(evidence), 1)
        saved = json.loads(evidence[0].read_text())
        self.assertTrue(saved["changes"])
        with self.ns["_ua114_publication_fence"]():
            self.assertEqual(journal.restore(), [])
        self.assertEqual(self.con.execute("SELECT status FROM media WHERE id=1").fetchone()[0], "ready")

    def test_private_spec_lock_acquires_publication_first(self):
        source = (BASE / "private_dependencies_20260920/ua_spec_permanent.py").read_text()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), builder.DEPENDENCY_SHA256["ua_spec_permanent.py"])
        import fcntl, stat
        ns = dict(Path=Path, contextmanager=contextlib.contextmanager, fcntl=fcntl,
                  os=os, stat=stat, time=time, threading=threading,
                  _WRITE_LOCK_REGISTRY={}, _WRITE_LOCK_REGISTRY_GUARD=threading.Lock(),
                  _require=lambda ok, message: None if ok else (_ for _ in ()).throw(RuntimeError(message)))
        exec(extract(source, "write_lock"), ns)
        exec(builder.SPEC_BLOCK, ns)
        ns["_ua114_publication_fence"] = self.ns["_ua114_publication_fence"]
        # The original private lock must remain usable and reentrant beneath publication.
        with ns["write_lock"](self.root):
            fence.require_publication_fence(lock_path=self.lock)
            with ns["write_lock"](self.root):
                fence.require_publication_fence(lock_path=self.lock)
        inode = self.lock.stat().st_ino
        with ns["write_lock"](self.root):
            self.assertEqual(self.lock.stat().st_ino, inode)

    def test_html_validation_fallback_restores_then_signals_failure(self):
        source = (BASE / "private_v5_sources_recovered/stranica.py").read_text()
        candidate = builder._integrate_stranica_text(source)
        page = self.video / "card.html"
        page.write_text("new")
        ns = dict(io=io, os=os, time=time, BAZA_DIR=str(self.root), VIDEO_DIR=str(self.video),
                  _v135_snimok=lambda: {str(page): "before"},
                  _v135_main_ishodnyy=lambda: None, _v135_proverka=lambda: (False, ["fixture"]),
                  print=lambda *_: None)
        # Second original main is the actual validation/fallback wrapper.
        exec(extract(candidate, "main", occurrence=1, root=self.root), ns)
        with self.assertRaisesRegex(RuntimeError, "HTML_VALIDATION_FALLBACK"):
            ns["main"]()
        self.assertEqual(page.read_text(), "before")

    def test_html_missing_media_aborts_instead_of_false_success(self):
        source = (BASE / "private_v5_sources_recovered/stranica.py").read_text()
        candidate = builder._integrate_stranica_text(source)
        ns = dict(io=io, os=os, time=time, BAZA_DIR=str(self.root),
                  _v157_net_fajlov=lambda: ["fixture"], print=lambda *_: None)
        exec(extract(candidate, "main", occurrence=2, root=self.root), ns)
        with self.assertRaisesRegex(RuntimeError, "HTML_MISSING_MEDIA_ABORT"):
            ns["main"]()

    def test_real_reload_and_main_failure_stay_inside_shared_fence(self):
        source = (BASE / "private_v5_sources_recovered/cars_ui.py").read_text()
        namespace = {"log": types.SimpleNamespace(warning=lambda *_: None)}
        exec(extract(source, "_peresobrat_stranicy", root=self.root), namespace)
        events = []
        module = types.ModuleType("stranica")
        def reload(value):
            fence.require_publication_fence(lock_path=self.lock)
            events.append("reload")
            return value
        def main():
            fence.require_publication_fence(lock_path=self.lock)
            events.append("main")
            raise RuntimeError("HTML_VALIDATION_FALLBACK")
        module.main = main
        self.ns["_ua114_rebuild_pages_base"] = namespace["_peresobrat_stranicy"]
        saved_path = list(sys.path)
        try:
            with patch.dict(sys.modules, {"stranica": module}), patch("importlib.reload", reload):
                self.assertFalse(self.ns["_peresobrat_stranicy"]())
        finally:
            sys.path[:] = saved_path
        self.assertEqual(events, ["reload", "main"])

    def test_legacy_transaction_guard_reuses_held_registry(self):
        ns = {"WAIT_SECONDS": 1}
        exec(builder.GUARD_BLOCK, ns)
        ns["_ua114_publication_fence"] = lambda **_: self.ns["_ua114_publication_fence"]()
        with self.ns["_ua114_publication_fence"]():
            inode = self.lock.stat().st_ino
            with ns["_exclusive_lock"]():
                fence.require_publication_fence(lock_path=self.lock)
                self.assertEqual(self.lock.stat().st_ino, inode)


if __name__ == "__main__":
    unittest.main()
