import ast
import contextlib
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

import integrate_private_sources as integration


class _Fence:
    def __init__(self, events, state):
        self.events = events
        self.state = state

    def __enter__(self):
        self.events.append("fence-enter")
        self.state["held"] += 1
        return self

    def __exit__(self, *args):
        self.events.append("fence-exit")
        self.state["held"] -= 1


@contextlib.contextmanager
def _module(name, value):
    previous = sys.modules.get(name)
    sys.modules[name] = value
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


class IntegrationTests(unittest.TestCase):
    def _cars_namespace(self, *, rebuild=True, photo_error=False, video_failures=None):
        events = []
        state = {"held": 0}
        card = {
            "id": 7,
            "auto_number": "UA-0007",
            "photos": json.dumps([{"file_id": "p1"}]),
            "cover_photo": "p1",
            "hidden_photos": json.dumps([{"file_id": "h1"}]),
            "videos": json.dumps([{"file_id": "v1"}]),
            "video_h": "vh",
            "video_v": "vv",
            "condition_photos": json.dumps([{"file_id": "dp1"}]),
            "condition_videos": json.dumps([{"file_id": "dv1"}]),
        }

        def held(event):
            self.assertGreater(state["held"], 0, event)
            events.append(event)

        class DB:
            @staticmethod
            def update_card_field(_table, _cid, field, value, _actor):
                held("db:" + field)
                card[field] = value

        def photo_remove(_code):
            held("photo-remove")
            if photo_error:
                raise OSError("simulated photo failure")
            return 1

        def video_remove(_code):
            held("video-remove-files")
            return 1

        def video_full(_code):
            held("video-remove-full")
            return 1, list(video_failures or [])

        def rebuild_pages():
            held("rebuild")
            return rebuild

        ns = {
            "Update": object,
            "ContextTypes": types.SimpleNamespace(DEFAULT_TYPE=object),
            "_ubrat_fayly_foto": photo_remove,
            "_ubrat_fayly_video": video_remove,
            "_ubrat_video_polno": video_full,
            "_peresobrat_stranicy": rebuild_pages,
            "card_of": lambda _cid: dict(card),
            "photos_of": lambda row: json.loads(row.get("photos") or "[]"),
            "videos_of": lambda row: json.loads(row.get("videos") or "[]"),
            "jdump": json.dumps,
            "jload": lambda value: json.loads(value or "[]"),
            "os": os,
            "db": DB(),
            "_v142_zapas_foto": lambda _code: ("backup", 1),
            "_v142_vernut_foto": lambda _code, _backup: (held("photo-restore") or 1),
            "_v142_papka": lambda _code, _kind: "backup",
            "_v142_kopirovat": lambda paths, _backup: len(paths),
            "_v142_vernut": lambda _backup, _directory: 0,
        }
        module = types.ModuleType("publication_fence")
        module.publication_fence = lambda **_kwargs: _Fence(events, state)
        module.require_publication_fence = lambda **_kwargs: self.assertGreater(state["held"], 0)
        with _module("publication_fence", module):
            exec(integration.CARS_BLOCK, ns)
        return ns, card, events, state

    def test_private_hash_mismatch_fails_before_output(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            source_path = Path(source)
            output_path = Path(output) / "candidate"
            for name in integration.BEFORE_SHA256:
                (source_path / name).write_text("not the bound source", encoding="utf-8")
            fence = source_path / "publication_fence.py"
            fence.write_text("pass\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "PRIVATE_SOURCE_SHA256_MISMATCH"):
                integration.build(source_path, output_path, fence)
            self.assertFalse(output_path.exists())

    def test_stranica_insertion_precedes_direct_main(self):
        source = (
            "def zapisat(*a, **k): pass\n"
            "def obnovit_etalon(*a, **k): pass\n"
            "def main():\n    _horosho = True\n    if _horosho: pass\n    else: pass\n"
            "def main():\n    _bedy = []\n    if _bedy: return\n"
            "if __name__ == \"__main__\":\n    main()\n"
        )
        candidate = integration._integrate_stranica_text(source)
        self.assertLess(candidate.index(integration.STRANICA_MARKER),
                        candidate.index('if __name__ == "__main__":'))
        compile(candidate, "stranica.py", "exec")

    def test_photo_success_holds_one_outer_fence(self):
        ns, card, events, state = self._cars_namespace()
        result = ns["_ua114_photo_remove_all_mutation"](7, 99)
        self.assertTrue(result["ok"])
        self.assertEqual(card["photos"], "[]")
        self.assertEqual(events[0], "fence-enter")
        self.assertEqual(events[-1], "fence-exit")
        self.assertEqual(state["held"], 0)
        self.assertLess(events.index("photo-remove"), events.index("db:photos"))
        self.assertLess(events.index("db:hidden_photos"), events.index("rebuild"))

    def test_low_level_media_remove_fails_without_outer_fence(self):
        ns, _card, _events, _state = self._cars_namespace()
        with self.assertRaises(AssertionError):
            ns["_ubrat_fayly_foto"]("UA-0007")
        with self.assertRaises(AssertionError):
            ns["_ubrat_video_polno"]("UA-0007")

    def test_async_handlers_delegate_mutation_to_thread(self):
        tree = ast.parse(integration.CARS_BLOCK)
        handlers = {
            node.name: node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name in {"photo_remove_all", "video_remove_all", "diag_clear"}
        }
        self.assertEqual(set(handlers), {"photo_remove_all", "video_remove_all", "diag_clear"})
        for node in handlers.values():
            calls = [item for item in ast.walk(node) if isinstance(item, ast.Call)]
            self.assertTrue(any(
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "to_thread" for call in calls
            ))

    def test_diagnostic_clear_is_inside_fence_through_rebuild(self):
        ns, card, events, state = self._cars_namespace()
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as backup:
            source = Path(directory) / "clip.jpg"
            source.write_bytes(b"xxxxftyp-video")

            def copy(paths, target):
                self.assertGreater(state["held"], 0)
                events.append("diag-backup")
                for path in paths:
                    shutil.copy2(path, Path(target) / Path(path).name)
                return len(paths)

            def restore(source_dir, target):
                self.assertGreater(state["held"], 0)
                events.append("diag-restore")
                for path in Path(source_dir).iterdir():
                    destination = Path(target) / path.name
                    if not destination.exists():
                        shutil.copy2(path, destination)
                return 1

            ns["_ua114_diag_directory"] = lambda _code: directory
            ns["_v142_papka"] = lambda _code, _kind: backup
            ns["_v142_kopirovat"] = copy
            ns["_v142_vernut"] = restore
            result = ns["_ua114_diag_clear_mutation"](7, "condition_videos", 99)
            self.assertFalse(source.exists())

        self.assertTrue(result["ok"])
        self.assertEqual(card["condition_videos"], "[]")
        self.assertEqual(events[0], "fence-enter")
        self.assertEqual(events[-1], "fence-exit")
        self.assertLess(events.index("db:condition_videos"), events.index("rebuild"))

    def test_photo_failure_restores_inside_fence(self):
        ns, card, events, _state = self._cars_namespace(photo_error=True)
        ns["_ua114_regular_files"] = lambda _root: ["/tmp/original-photo.jpg"]
        ns["_ua114_backup_exact"] = lambda *_args: [
            ("/tmp/original-photo.jpg", "/tmp/backup-photo.jpg", "sha", "original-photo.jpg")]
        ns["_ua114_restore_exact"] = lambda _entries: (
            events.append("photo-restore") or [])
        before = dict(card)
        result = ns["_ua114_photo_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertEqual(card, before)
        self.assertEqual(result["rollback_conflicts"], [])
        self.assertIn("photo-restore", events)
        self.assertLess(events.index("fence-enter"), events.index("photo-restore"))
        self.assertLess(events.index("photo-restore"), events.index("fence-exit"))

    def test_incomplete_backup_fails_before_destructive_photo_action(self):
        ns, card, events, _state = self._cars_namespace()
        ns["_ua114_regular_files"] = lambda _root: ["/tmp/original-photo.jpg"]

        def fail_backup(*_args):
            raise RuntimeError("MEDIA_BACKUP_SHA256_MISMATCH:original-photo.jpg")

        ns["_ua114_backup_exact"] = fail_backup
        before = dict(card)
        result = ns["_ua114_photo_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertIn("MEDIA_BACKUP_SHA256_MISMATCH", result["error"])
        self.assertEqual(card, before)
        self.assertNotIn("photo-remove", events)
        self.assertFalse(any(event.startswith("db:") for event in events))

    def test_exact_restore_preserves_new_operator_file(self):
        ns, _card, _events, _state = self._cars_namespace()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.jpg"
            backup = root / "backup.jpg"
            original.write_bytes(b"operator-new")
            backup.write_bytes(b"old")
            old_sha = integration.hashlib.sha256(b"old").hexdigest()
            conflicts = ns["_ua114_restore_exact"]([
                (str(original), str(backup), old_sha, "original.jpg")])
            self.assertEqual(original.read_bytes(), b"operator-new")
            self.assertEqual(conflicts, ["media:original.jpg"])

    def test_video_failure_restores_database_fields(self):
        ns, card, events, _state = self._cars_namespace(video_failures=["simulated"])
        before = {name: card[name] for name in ("videos", "video_h", "video_v")}
        result = ns["_ua114_video_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertEqual({name: card[name] for name in before}, before)
        self.assertLess(events.index("db:videos"), events.index("video-remove-full"))
        self.assertLess(events.index("video-remove-full"), events.index("fence-exit"))

    def test_restore_refuses_corrupt_backup_without_publishing_it(self):
        ns, *_ = self._cars_namespace()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, backup = root / "photo.jpg", root / "backup.jpg"
            backup.write_bytes(b"corrupted")
            expected = integration.hashlib.sha256(b"old").hexdigest()
            result = ns["_ua114_restore_exact"]([
                (str(original), str(backup), expected, "photo.jpg")])
            self.assertEqual(result, ["media:photo.jpg"])
            self.assertFalse(original.exists())

    def test_restore_preserves_operator_file_created_during_copy(self):
        ns, *_ = self._cars_namespace()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, backup = root / "photo.jpg", root / "backup.jpg"
            backup.write_bytes(b"old")
            expected = integration.hashlib.sha256(b"old").hexdigest()

            def racing_copy(source, destination):
                original.write_bytes(b"new operator bytes")
                return shutil.copy2(source, destination)

            ns["_ua114_shutil"] = types.SimpleNamespace(copy2=racing_copy)
            result = ns["_ua114_restore_exact"]([
                (str(original), str(backup), expected, "photo.jpg")])
            self.assertEqual(original.read_bytes(), b"new operator bytes")
            self.assertEqual(result, ["media:photo.jpg"])
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["backup.jpg", "photo.jpg"])

    def test_restore_publishes_verified_missing_file(self):
        ns, *_ = self._cars_namespace()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, backup = root / "photo.jpg", root / "backup.jpg"
            backup.write_bytes(b"old")
            expected = integration.hashlib.sha256(b"old").hexdigest()
            result = ns["_ua114_restore_exact"]([
                (str(original), str(backup), expected, "photo.jpg")])
            self.assertEqual(result, [])
            self.assertEqual(original.read_bytes(), b"old")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["backup.jpg", "photo.jpg"])

    def test_changed_after_image_is_not_overwritten_by_rollback(self):
        ns, card, _events, _state = self._cars_namespace(rebuild=False)
        base_rebuild = ns["_ua114_rebuild_pages_base"]
        calls = {"count": 0}

        def changed_rebuild():
            calls["count"] += 1
            if calls["count"] == 1:
                card["photos"] = '"operator-new-value"'
            return base_rebuild()

        ns["_ua114_rebuild_pages_base"] = changed_rebuild
        result = ns["_ua114_photo_remove_all_mutation"](7, 99)
        self.assertFalse(result["ok"])
        self.assertIn("photos", result["rollback_conflicts"])
        self.assertEqual(card["photos"], '"operator-new-value"')

    def test_guard_reuses_shared_fence_registry(self):
        events = []
        state = {"held": 0}
        module = types.ModuleType("publication_fence")
        module.publication_fence = lambda **_kwargs: _Fence(events, state)
        ns = {"WAIT_SECONDS": 90}
        with _module("publication_fence", module):
            exec(integration.GUARD_BLOCK, ns)
        with ns["_exclusive_lock"]():
            self.assertEqual(state["held"], 1)
        self.assertEqual(events, ["fence-enter", "fence-exit"])

    def test_stranica_nested_write_order(self):
        events = []
        state = {"held": 0}
        module = types.ModuleType("publication_fence")
        module.publication_fence = lambda **_kwargs: _Fence(events, state)

        def require_held(name):
            self.assertGreater(state["held"], 0, name)
            events.append(name)

        ns = {
            "zapisat": lambda *_a, **_k: require_held("write"),
            "obnovit_etalon": lambda *_a, **_k: require_held("etalon"),
            "main": lambda *_a, **_k: require_held("main"),
        }
        with _module("publication_fence", module):
            exec(integration.STRANICA_BLOCK, ns)
        ns["main"]()
        ns["zapisat"]("x", "y")
        ns["obnovit_etalon"]("x", "y")
        self.assertEqual(state["held"], 0)
        self.assertEqual(events.count("fence-enter"), 3)


if __name__ == "__main__":
    unittest.main()
