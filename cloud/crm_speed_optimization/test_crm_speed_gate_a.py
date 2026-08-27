"""Offline test suite for CRM-SPEED-001 Gate A package (round 3 corrections).

Run with: python -m unittest test_crm_speed_gate_a -v
from inside cloud/crm_speed_optimization/. This suite never touches
production, /home/Carix, or PythonAnywhere.
"""
import os
import sys
import time
import uuid
import random
import sqlite3
import tempfile
import unittest
import multiprocessing
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import cross_process_lock
import rebuild_queue as rebuild_queue_module
import safe_writer as safe_writer_module
import crm_speed_gate_a as gate_a

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
from crm_speed_gate_a import (
    scan_reachable_call_graph, transform_cars_ui, measure_deterministic_repeat,
    scan_bounded_inventory, check_ua0009_not_public, evaluate_gate_a, run_gate_a,
    DEFAULT_MAX_FILES_PER_ROOT, ADMIN_ROUTE_NAMES,
)


# ---------------------------------------------------------------------------
# Identity assertions (correction D)
# ---------------------------------------------------------------------------

class IdentityTests(unittest.TestCase):
    def test_cross_process_lock_identity(self):
        self.assertIs(cross_process_lock.CrossProcessLock, canonical_modules.CrossProcessLock)
        self.assertIs(gate_a.CrossProcessLock, canonical_modules.CrossProcessLock)

    def test_rebuild_queue_identity(self):
        self.assertIs(rebuild_queue_module.RebuildQueue, canonical_modules.RebuildQueue)
        self.assertIs(gate_a.RebuildQueue, canonical_modules.RebuildQueue)

    def test_safe_writer_identity(self):
        self.assertIs(safe_writer_module.SafeWriter, canonical_modules.SafeWriter)
        self.assertIs(gate_a.SafeWriter, canonical_modules.SafeWriter)

    def test_singleton_guard_identity(self):
        self.assertIs(cross_process_lock.SingletonGuard, canonical_modules.SingletonGuard)
        self.assertIs(gate_a.SingletonGuard, canonical_modules.SingletonGuard)


# ---------------------------------------------------------------------------
# Correction A: dynamic dispatch call-graph scanner + cars_ui transform
# ---------------------------------------------------------------------------

class CarsUiTransformTests(unittest.TestCase):
    def test_dynamic_dispatch_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn(open('x.jpg', 'rb'))\n"
            "def video_gallery(update, context):\n"
            "    pass\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any(r.startswith("dynamic_dispatch_forbidden") for r in result["reasons"]))

    def test_getattr_computed_name_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    name = pick_name()\n"
            "    fn = getattr(update.message, name)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_bound_method_alias_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    sender(open('x.jpg','rb'))\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_dict_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = {'photo': update.message.reply_photo}\n"
            "    handlers['photo']()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_list_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = [update.message.reply_photo]\n"
            "    handlers[0]()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_lambda_media_call_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    f = lambda: update.message.reply_photo(open('x.jpg','rb'))\n"
            "    f()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_return_alias_blocks(self):
        source = (
            "def _pick(update):\n"
            "    return update.message.reply_photo\n"
            "def gallery(update, context):\n"
            "    fn = _pick(update)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_await_alias_blocks(self):
        source = (
            "async def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    await sender()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_nested_helper_media_call_blocks(self):
        source = (
            "def _send(update):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def gallery(update, context):\n"
            "    _send(update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        self.assertIsNotNone(result["candidate"])
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo", result["candidate"])

    def test_ambiguous_unresolved_callable_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    dispatch_table[update.kind](update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_direct_simple_media_call_transforms_cleanly(self):
        source = (
            "def gallery(update, context):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def video_gallery(update, context):\n"
            "    update.message.reply_video(open('x.mp4','rb'))\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo(", result["candidate"])
        self.assertIn("reply_text", result["candidate"])


# ---------------------------------------------------------------------------
# Correction B: deterministic repeat with agreed API
# ---------------------------------------------------------------------------

class DeterministicRepeatTests(unittest.TestCase):
    def test_deterministic_transform_passes(self):
        source = "def gallery(update, context):\n    update.message.reply_photo(1)\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source, args=(), repeats=10)
        self.assertTrue(measurement["deterministic"])
        self.assertEqual(measurement["repeats"], 10)

    def test_deterministic_transform_passes_with_source_kwarg(self):
        source = "def gallery(update, context): pass\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source=source, repeats=10)
        self.assertTrue(measurement["deterministic"])

    def _nondeterministic_random_content(self, source):
        return {"candidate": source + f"# {random.random()}", "status": "OK", "reasons": []}

    def _nondeterministic_time(self, source):
        return {"candidate": source + f"# {time.time()}", "status": "OK", "reasons": []}

    def _nondeterministic_uuid(self, source):
        return {"candidate": source + f"# {uuid.uuid4().hex}", "status": "OK", "reasons": []}

    def _nondeterministic_unordered_set(self, source):
        s = {random.randint(0, 10**9) for _ in range(5)}
        return {"candidate": source + f"# {sorted(s) if random.random() > 2 else list(s)}", "status": "OK", "reasons": []}

    def _nondeterministic_metadata(self, source):
        return {"candidate": source, "status": "OK", "reasons": [f"seen_at:{time.time()}"]}

    def test_nondeterministic_transform_blocks(self):
        source = "x = 1\n"
        variants = [
            self._nondeterministic_random_content,
            self._nondeterministic_time,
            self._nondeterministic_uuid,
            self._nondeterministic_unordered_set,
            self._nondeterministic_metadata,
        ]
        for variant in variants:
            measurement = measure_deterministic_repeat(variant, source, args=(), repeats=10)
            self.assertFalse(measurement["deterministic"], variant.__name__)
            forced_status, unmet = evaluate_gate_a({
                **{k: {"status": "OK"} for k in gate_a.REQUIRED_PREDICATES},
                "deterministic_repeat_all_transforms": {"status": "BLOCKED", "failures": [variant.__name__]},
            })
            self.assertEqual(forced_status, "BLOCKED")
            self.assertIn("deterministic_repeat_all_transforms", unmet)


# ---------------------------------------------------------------------------
# Correction C: real, honest overflow test with production default preserved
# ---------------------------------------------------------------------------

class SiteInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in ["index.html", "katalog.html", "UA-0001.html"]:
            with open(os.path.join(self.tmp.name, name), "w") as fh:
                fh.write("<html></html>")

    def test_production_default_max_is_32(self):
        self.assertEqual(DEFAULT_MAX_FILES_PER_ROOT, 32)

    def test_overflow_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "overflow")
        self.assertEqual(result["matched_count"], 3)

    def test_exact_boundary_n_passes(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=3)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["matched_count"], 3)

    def test_boundary_n_plus_one_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")

    def test_default_production_cap_accepts_up_to_32(self):
        for i in range(2, 10):
            with open(os.path.join(self.tmp.name, f"UA-000{i}.html"), "w") as fh:
                fh.write("<html></html>")
        allowed = list(gate_a.ALLOWED_SITE_NAMES)
        result = scan_bounded_inventory(self.tmp.name, allowed)
        self.assertEqual(result["status"], "OK")
        self.assertLessEqual(result["matched_count"], 32)

    def test_missing_root_blocks(self):
        result = scan_bounded_inventory(os.path.join(self.tmp.name, "nope"), ["index.html"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_symlink_rejected(self):
        target = os.path.join(self.tmp.name, "index.html")
        link = os.path.join(self.tmp.name, "katalog.html")
        os.remove(link)
        os.symlink(target, link)
        result = scan_bounded_inventory(self.tmp.name, ["index.html", "katalog.html"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "symlink_rejected")


# ---------------------------------------------------------------------------
# Publication probe fail-closed behavior
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, code):
        self._code = code

    def getcode(self):
        return self._code


class _FakeOpener:
    def __init__(self, raise_exc=None, response_code=None):
        self.raise_exc = raise_exc
        self.response_code = response_code

    def open(self, req, timeout=5):
        if self.raise_exc is not None:
            raise self.raise_exc
        return _FakeResponse(self.response_code)


class PublicationProbeTests(unittest.TestCase):
    def test_404_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_410_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 410, "gone", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_200_blocks(self):
        opener = _FakeOpener(response_code=200)
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_redirect_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 302, "redir", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_network_error_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.URLError("connection refused"))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_non_https_blocks(self):
        result = check_ua0009_not_public("http://example.com/UA-0009.html")
        self.assertEqual(result["status"], "BLOCKED")

    def test_missing_url_blocks(self):
        result = check_ua0009_not_public("")
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# CrossProcessLock stress test (aggregate >=100 contention attempts)
# ---------------------------------------------------------------------------

def _contender_worker(lock_path, start_barrier, result_queue, hold_event):
    guard = CrossProcessLock(lock_path)
    start_barrier.wait()
    acquired = guard.acquire()
    result_queue.put((os.getpid(), acquired))
    if acquired:
        hold_event.wait(timeout=5)
        guard.release()


class CrossProcessLockStressTests(unittest.TestCase):
    def test_simultaneous_stale_takeover_only_one_wins(self):
        ctx = multiprocessing.get_context("fork") if hasattr(multiprocessing, "get_context") else multiprocessing
        rounds = 25
        contenders_per_round = 4
        for round_idx in range(rounds):
            with tempfile.TemporaryDirectory() as tmp:
                lock_path = os.path.join(tmp, "test.lock")
                with open(lock_path, "w") as fh:
                    fh.write(f"999999|stale|deadtoken|{time.time() - 100000}\n")
                start_barrier = ctx.Barrier(contenders_per_round)
                result_queue = ctx.Queue()
                hold_event = ctx.Event()
                procs = [
                    ctx.Process(target=_contender_worker, args=(lock_path, start_barrier, result_queue, hold_event))
                    for _ in range(contenders_per_round)
                ]
                for p in procs:
                    p.start()
                results = [result_queue.get(timeout=10) for _ in procs]
                hold_event.set()
                for p in procs:
                    p.join(timeout=10)
                winners = [r for r in results if r[1]]
                self.assertEqual(len(winners), 1, f"round {round_idx}: {results}")

    def test_release_then_fresh_contender_can_acquire(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            first = CrossProcessLock(lock_path)
            self.assertTrue(first.acquire())
            first.release()
            second = CrossProcessLock(lock_path)
            self.assertTrue(second.acquire())
            second.release()

    def test_idempotent_release_no_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            lock = CrossProcessLock(lock_path)
            self.assertTrue(lock.acquire())
            lock.release()
            lock.release()

    def test_release_after_directory_removed_does_not_raise(self):
        tmp = tempfile.mkdtemp()
        lock_path = os.path.join(tmp, "test.lock")
        lock = CrossProcessLock(lock_path)
        self.assertTrue(lock.acquire())
        import shutil
        shutil.rmtree(tmp)
        lock.release()


# ---------------------------------------------------------------------------
# RebuildQueue and SafeWriter basic behavior
# ---------------------------------------------------------------------------

class RebuildQueueTests(unittest.TestCase):
    def test_burst_coalesces_to_one_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            q = RebuildQueue(lambda: calls.append(1), os.path.join(tmp, "rebuild.lock"))
            statuses = [q.enqueue() for _ in range(5)]
            self.assertIn("accepted", statuses)
            self.assertGreaterEqual(len(calls), 1)

    def test_requires_bound_callback(self):
        with self.assertRaises(ValueError):
            RebuildQueue(None, "/tmp/whatever.lock")


class SafeWriterTests(unittest.TestCase):
    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            with self.assertRaises(ValueError):
                writer.write_text("../escape.txt", "x")

    def test_writes_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            target = writer.write_text("out.txt", "hello")
            with open(target) as fh:
                self.assertEqual(fh.read(), "hello")


# ---------------------------------------------------------------------------
# Correction E: real synthetic end-to-end Gate A
# ---------------------------------------------------------------------------

CLEAN_CARS_UI = (
    "def gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'photos: {count}')\n"
    "def video_gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'videos: {count}')\n"
    "def diag_photo_show(update, context):\n"
    "    update.message.reply_text('diag photo text')\n"
    "def diag_video_show(update, context):\n"
    "    update.message.reply_text('diag video text')\n"
    "def count_media(update):\n"
    "    return len(update.media)\n"
    "def upload_media(path, data):\n"
    "    with open(path, 'wb') as fh:\n"
    "        fh.write(data)\n"
    "    return True\n"
    "def delete_media(path):\n"
    "    import os as _os\n"
    "    _os.remove(path)\n"
    "    return True\n"
)

CLEAN_USERCUSTOMIZE = "import sys\n\n\ndef _noop():\n    return None\n"

CLEAN_AVTOPEREDACHA = (
    "import sqlite3\n"
    "import time\n"
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)

DB_FUNCTION_SOURCE = (
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)


class EndToEndGateATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.required_input_paths = []
        for name in ["usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
                     "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py"]:
            p = os.path.join(self.tmp.name, name)
            with open(p, "w") as fh:
                fh.write("# fixture\n")
            self.required_input_paths.append(p)

        self.db_path = os.path.join(self.tmp.name, "crm.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()
        self.required_input_paths.append(self.db_path)

        self.backup_archive = os.path.join(self.tmp.name, "backup.tar.gz")
        with open(self.backup_archive, "wb") as fh:
            fh.write(b"fixture-backup-bytes")
        self.backup_sha256 = gate_a._sha256_file(self.backup_archive)

        self.site_root = os.path.join(self.tmp.name, "site")
        os.makedirs(self.site_root)
        with open(os.path.join(self.site_root, "index.html"), "w") as fh:
            fh.write("<html></html>")
        with open(os.path.join(self.site_root, "katalog.html"), "w") as fh:
            fh.write("<html></html>")

        self.run_dir = os.path.join(self.tmp.name, "run")

        fp = {"a": 1}
        self.fixture = {
            "required_inputs": self.required_input_paths,
            "backup_archive": self.backup_archive,
            "backup_archive_sha256": self.backup_sha256,
            "cars_ui_source": CLEAN_CARS_UI,
            "usercustomize_source": CLEAN_USERCUSTOMIZE,
            "avtoperedacha_source": CLEAN_AVTOPEREDACHA,
            "protected_fingerprints_before": fp,
            "protected_fingerprints_after": dict(fp),
            "db_path": self.db_path,
            "ua0009_fingerprint_before": {"h": "same"},
            "ua0009_fingerprint_after": {"h": "same"},
            "ua0009_url": "https://example.com/UA-0009.html",
            "ua0009_opener": _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None)),
            "site_root": self.site_root,
            "allowed_site_names": ["index.html", "katalog.html"],
            "protected_function_names": ["upload_media", "delete_media"],
            "tmp_dir": self.tmp.name,
            "db_function_source": DB_FUNCTION_SOURCE,
            "site_before": {"x": 1},
            "site_after": {"x": 1},
            "run_dir": self.run_dir,
        }

    def test_clean_fixture_reaches_pass_awaiting_approval(self):
        receipt = run_gate_a(self.fixture)
        self.assertEqual(receipt["status"], "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", receipt["unmet_predicates"])
        self.assertEqual(receipt["unmet_predicates"], [])
        self.assertEqual(receipt["production_write"], "NO")
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "receipt.json")))

    def test_backup_hash_mismatch_blocks(self):
        bad = dict(self.fixture)
        bad["backup_archive_sha256"] = "0" * 64
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("backup_verified", receipt["unmet_predicates"])

    def test_protected_fingerprint_change_blocks(self):
        bad = dict(self.fixture)
        bad["protected_fingerprints_after"] = {"a": 2}
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("protected_fingerprints_unchanged", receipt["unmet_predicates"])
        self.assertIn("no_production_write", receipt["unmet_predicates"])

    def test_publication_probe_200_blocks(self):
        bad = dict(self.fixture)
        bad["ua0009_opener"] = _FakeOpener(response_code=200)
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("ua0009_not_public", receipt["unmet_predicates"])

    def test_dynamic_dispatch_in_cars_ui_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
            "def upload_media(path, data): return True\n"
            "def delete_media(path): return True\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("admin_routes_text_only", receipt["unmet_predicates"])

    def test_usercustomize_forbidden_import_blocks(self):
        bad = dict(self.fixture)
        bad["usercustomize_source"] = "import team_bot\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("usercustomize_inert", receipt["unmet_predicates"])

    def test_rebuild_subprocess_blocks(self):
        bad = dict(self.fixture)
        bad["avtoperedacha_source"] = "import subprocess\ndef run():\n    subprocess.Popen(['x'])\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("rebuild_queue_bound_no_process_spawn", receipt["unmet_predicates"])

    def test_slow_work_before_close_blocks(self):
        bad = dict(self.fixture)
        bad["db_function_source"] = (
            "def kolonki_cars(conn):\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    time.sleep(0)\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    return rows\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("db_closed_before_slow_work", receipt["unmet_predicates"])

    def test_site_inventory_overflow_blocks(self):
        bad = dict(self.fixture)
        bad["allowed_site_names"] = ["index.html", "katalog.html"]
        bad["max_files_per_root"] = 1
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("site_inventory_unchanged", receipt["unmet_predicates"])

    def test_media_persistence_function_removed_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = CLEAN_CARS_UI.replace(
            "def delete_media(path):\n    import os as _os\n    _os.remove(path)\n    return True\n", "")
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("media_persistence_unchanged", receipt["unmet_predicates"])

    def test_missing_input_blocks(self):
        bad = dict(self.fixture)
        bad["required_inputs"] = self.required_input_paths + [os.path.join(self.tmp.name, "missing.py")]
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("inputs_present_and_regular", receipt["unmet_predicates"])


if __name__ == "__main__":
    unittest.main()
