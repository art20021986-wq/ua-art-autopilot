#!/usr/bin/env python3
"""Standard-library-only regression suite for TASK 037/039.

Run with:
    python3 -m py_compile cloud/bot_logistics/*.py
    python3 -m unittest discover -v -s cloud/bot_logistics -p 'test*.py'

No pytest, no pip install, no network. All fixtures use temp dirs / temp
sqlite files only. Nothing here touches Production, CRM, or
/home/Carix/crm.db.

NOTE ON SCOPE: bot_logistics_transform.py and bot_logistics_gate_b.py were
delivered under TASK 037 and are not reproduced in this round's context.
The tests in TestContainerUpdateLogic import those modules directly and
introspect their real public API (they do not re-implement it) so that a
real behavioral mismatch fails loudly instead of being silently skipped.
See TASK_039_REPORT.md section 'Known limitation' for details.
"""
import contextlib
import importlib
import inspect
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUD_DIR = os.path.dirname(THIS_DIR)
if CLOUD_DIR not in sys.path:
    sys.path.insert(0, CLOUD_DIR)

from bot_logistics import bot_logistics_discovery as discovery  # noqa: E402

try:
    transform = importlib.import_module("bot_logistics.bot_logistics_transform")
    TRANSFORM_ERROR = None
except Exception as exc:  # pragma: no cover
    transform = None
    TRANSFORM_ERROR = exc

try:
    gate_b = importlib.import_module("bot_logistics.bot_logistics_gate_b")
    GATE_B_ERROR = None
except Exception as exc:  # pragma: no cover
    gate_b = None
    GATE_B_ERROR = exc


def _find_symbol(names, *modules):
    for mod in modules:
        if mod is None:
            continue
        for name in names:
            if hasattr(mod, name):
                return getattr(mod, name)
    return None


UPDATE_FN = _find_symbol(["update_single_container_row"], transform, gate_b)
GATE_B_REFUSED = _find_symbol(["GateBRefused"], gate_b, transform)
CORRECT_CONTAINER = getattr(transform, "CORRECT_CONTAINER", None) or \
    getattr(gate_b, "CORRECT_CONTAINER", None) or "ONEYSELGF1046602"


def _call_update(func, **kwargs):
    """Call the real update function using only the keyword arguments it
    actually declares, so the test adapts to the real signature instead of
    guessing blindly."""
    defaults = {
        "table": "cars",
        "id_col": "ua_id",
        "container_col": "container",
    }
    defaults.update(kwargs)
    sig = inspect.signature(func)
    accepted = {k: v for k, v in defaults.items() if k in sig.parameters}
    return func(**accepted)


class TestModuleImports(unittest.TestCase):
    def test_transform_module_imports(self):
        self.assertIsNotNone(transform, "bot_logistics_transform import failed: %r" % (TRANSFORM_ERROR,))

    def test_gate_b_module_imports(self):
        self.assertIsNotNone(gate_b, "bot_logistics_gate_b import failed: %r" % (GATE_B_ERROR,))

    def test_discovery_module_imports(self):
        self.assertIsNotNone(discovery)

    def test_update_function_present(self):
        self.assertIsNotNone(UPDATE_FN, "update_single_container_row not found in either module")

    def test_gate_b_refused_present(self):
        self.assertIsNotNone(GATE_B_REFUSED, "GateBRefused exception class not found in either module")


class TestCanonicalHubLogic(unittest.TestCase):
    def test_container_number_is_accepted_exactly(self):
        self.assertEqual(
            transform.normalize_container("  oneyselgf1046602  "),
            "ONEYSELGF1046602",
        )

    def test_container_validation_rejects_unsafe_shapes(self):
        for value in ("", "ABC 1234567", "ABC/1234567", "SHORT"):
            with self.subTest(value=value):
                with self.assertRaises(transform.ValidationError):
                    transform.normalize_container(value)

    def test_one_hub_entry_in_main_menu(self):
        menu = transform.build_main_menu(["UA-0006"])
        self.assertEqual(menu.count_button_text(transform.HUB_BUTTON_TEXT), 1)
        self.assertFalse(menu.has_any(transform.OLD_STAGE_MENU_LABELS))
        self.assertFalse(menu.has_any(transform.OLD_CARD_EDITOR_LABELS))

    def test_one_hub_entry_in_card_editor(self):
        menu = transform.build_card_editor_menu("UA-0006")
        self.assertEqual(menu.count_button_text(transform.HUB_BUTTON_TEXT), 1)
        self.assertFalse(menu.has_any(transform.OLD_STAGE_MENU_LABELS))
        self.assertFalse(menu.has_any(transform.OLD_CARD_EDITOR_LABELS))

    def test_hub_contains_all_centralized_controls_and_back(self):
        record = transform.LogisticsRecord(
            ua_id="UA-0006",
            stage="В пути",
            container="ONEYSELGF1046602",
            departure_date=date(2026, 8, 27),
            days_to_arrival=12,
        )
        menu = transform.build_hub_menu(record, "card")
        self.assertEqual(
            [button.text for button in menu.buttons],
            ["Этап", "Контейнер и дата", "Дней до прибытия", "Назад"],
        )
        for button in menu.buttons:
            transform.assert_callback_valid(button.callback_data)
            self.assertIn("UA-0006", button.callback_data)

    def test_eta_uses_one_canonical_calculation(self):
        record = transform.LogisticsRecord(
            ua_id="UA-0006",
            departure_date=date(2026, 8, 27),
            days_to_arrival=12,
        )
        self.assertEqual(record.eta(), date(2026, 9, 8))
        self.assertIn("ETA: 2026-09-08", record.render_hub_text())

    def test_candidate_transform_is_idempotent_ten_times(self):
        source = (
            "def build_menu():\n"
            "    marker = True\n"
            "    add_button('Срок доставки', 'old')\n"
            "    add_button('Номер контейнера', 'old2')\n"
        )
        hashes, output = transform.apply_n_times_stable(
            source,
            transform.OLD_STAGE_MENU_LABELS
            + transform.OLD_CARD_EDITOR_LABELS,
            "marker = True",
            n=10,
        )
        self.assertEqual(len(set(hashes)), 1)
        self.assertEqual(output.count(transform.HUB_BUTTON_TEXT), 1)
        for label in (
            transform.OLD_STAGE_MENU_LABELS
            + transform.OLD_CARD_EDITOR_LABELS
        ):
            self.assertNotIn(label, output)

    def test_gate_b_remains_disabled_in_phase_a(self):
        with self.assertRaises(gate_b.GateBRefused):
            gate_b.run_gate_b()


class DiscoveryTestBase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bl_disc_")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.sources = {}
        names = [
            "cars_ui.py", "team_bot.py", "avtoperedacha.py",
            "db.py", "run_all.py", "start_safe.py",
        ]
        for n in names:
            p = os.path.join(self.tmpdir, n)
            with open(p, "w", encoding="utf-8") as f:
                f.write("# %s\ndef handler_ua0006_container():\n    pass\n" % n)
            self.sources[n] = p

        self.required_sources = tuple(self.sources[n] for n in names)
        self.db_path = os.path.join(self.tmpdir, "crm.db")

        self._orig_required_sources = discovery.REQUIRED_SOURCES
        self._orig_required_db = discovery.REQUIRED_DB
        discovery.REQUIRED_SOURCES = self.required_sources
        discovery.REQUIRED_DB = self.db_path
        self.addCleanup(self._restore_constants)

    def _restore_constants(self):
        discovery.REQUIRED_SOURCES = self._orig_required_sources
        discovery.REQUIRED_DB = self._orig_required_db

    def _make_db(self, container_value="ONEYSELGF1046602", ua_id="UA-0006"):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE cars (ua_id TEXT PRIMARY KEY, container TEXT, other TEXT)"
        )
        conn.execute(
            "INSERT INTO cars (ua_id, container, other) VALUES (?, ?, ?)",
            (ua_id, container_value, "keep-me"),
        )
        conn.commit()
        conn.close()


class TestDiscoveryHappyPath(DiscoveryTestBase):
    def test_pass_already_correct(self):
        self._make_db(container_value=discovery.CORRECT_CONTAINER)
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["UA0006_CONTAINER_STATUS"], "ALREADY_CORRECT")
        self.assertFalse(result["production_write"])
        self.assertFalse(result["crm_write"])
        self.assertFalse(result["db_write"])
        self.assertFalse(result["ua0009_published"])

    def test_pass_needs_update(self):
        self._make_db(container_value="WRONGCONTAINER0000000")
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["UA0006_CONTAINER_STATUS"], "NEEDS_EXACT_UPDATE")
        # current value must never be echoed
        payload = json.dumps(result)
        self.assertNotIn("WRONGCONTAINER0000000", payload)

    def test_strict_json_single_object_stdout(self):
        self._make_db()
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True)
        parsed = json.loads(payload)
        self.assertEqual(parsed["task_id"], "task_037")
        self.assertEqual(parsed["mode"], "READ_ONLY_DISCOVERY")


class TestDiscoverySourceContract(DiscoveryTestBase):
    def test_missing_source_blocked(self):
        self._make_db()
        subset = list(self.required_sources)[:-1]
        result = discovery.run_discovery(self.db_path, subset)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("count_mismatch" in e for e in result["errors"]))

    def test_duplicate_source_blocked(self):
        self._make_db()
        dup = list(self.required_sources)
        dup[1] = dup[0]
        result = discovery.run_discovery(self.db_path, dup)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("duplicate_source" in e for e in result["errors"]))

    def test_extra_source_blocked(self):
        self._make_db()
        extra_path = os.path.join(self.tmpdir, "extra.py")
        with open(extra_path, "w") as f:
            f.write("# extra\n")
        extra_set = list(self.required_sources) + [extra_path]
        result = discovery.run_discovery(self.db_path, extra_set)
        self.assertEqual(result["status"], "BLOCKED")

    def test_path_variant_blocked(self):
        self._make_db()
        variant = list(self.required_sources)
        variant[0] = variant[0] + "/../cars_ui.py"
        result = discovery.run_discovery(self.db_path, variant)
        self.assertEqual(result["status"], "BLOCKED")

    def test_symlink_source_blocked(self):
        self._make_db()
        real = self.required_sources[0]
        link = real + ".link"
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError) as exc:
            self.fail("test platform must support symlinks: %r" % (exc,))
        variant = list(self.required_sources)
        variant[0] = link
        result = discovery.run_discovery(self.db_path, variant)
        self.assertEqual(result["status"], "BLOCKED")

    def test_hardlink_source_blocked(self):
        self._make_db()
        real = self.required_sources[0]
        link = real + ".hardlink"
        try:
            os.link(real, link)
        except OSError as exc:
            self.fail("test platform must support hardlinks: %r" % (exc,))
        # nlink on the original is now 2 -> must be rejected
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        self.assertEqual(result["status"], "BLOCKED")

    def test_oversize_source_blocked(self):
        self._make_db()
        big = self.required_sources[0]
        orig_max = discovery.MAX_SOURCE_SIZE
        discovery.MAX_SOURCE_SIZE = 4
        try:
            result = discovery.run_discovery(self.db_path, list(self.required_sources))
            self.assertEqual(result["status"], "BLOCKED")
        finally:
            discovery.MAX_SOURCE_SIZE = orig_max

    def test_source_sha_reported_and_stable(self):
        self._make_db()
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        self.assertEqual(len(result["sources"]), 6)
        for entry in result["sources"]:
            self.assertIn("sha256", entry)
            self.assertEqual(len(entry["sha256"]), 64)

    def test_source_identity_change_blocked(self):
        self._make_db()
        target = self.required_sources[0]
        real_read = discovery.os.read
        changed = {"done": False}

        def changing_read(fd, count):
            data = real_read(fd, count)
            if data and not changed["done"]:
                changed["done"] = True
                with open(target, "a", encoding="utf-8") as handle:
                    handle.write("# concurrent change\n")
            return data

        with mock.patch.object(discovery.os, "read", side_effect=changing_read):
            result = discovery.run_discovery(
                self.db_path, list(self.required_sources)
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(
            any("concurrent_change" in error for error in result["errors"])
        )

    def test_secret_adjacent_anchor_redacted(self):
        secret_path = self.required_sources[3]  # db.py
        with open(secret_path, "a", encoding="utf-8") as f:
            f.write("API_KEY = 'abcdefghijklmnopqrstuvwxyz012345'\n")
            f.write("def container_handler_ua0006():\n    pass\n")
        self._make_db()
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        payload = json.dumps(result)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz012345", payload)

    def test_container_value_near_anchor_is_never_relayed(self):
        target = self.required_sources[0]
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(
                "container = 'ONEYSELGF1046602'\n"
                "button = 'Номер контейнера'\n"
            )
        self._make_db()
        result = discovery.run_discovery(
            self.db_path, list(self.required_sources)
        )
        payload = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("ONEYSELGF1046602", payload)
        self.assertIn("[REDACTED]", payload)


class TestDiscoveryDbContract(DiscoveryTestBase):
    def test_unapproved_db_path_is_blocked_before_read(self):
        self._make_db()
        other = os.path.join(self.tmpdir, "other.db")
        shutil.copyfile(self.db_path, other)
        with mock.patch.object(discovery, "secure_digest") as digest:
            result = discovery.run_discovery(
                other, list(self.required_sources)
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["errors"], ["db_path_mismatch"])
        digest.assert_not_called()

    def test_no_match_blocked_with_schema_hint(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE unrelated (id INTEGER, name TEXT)")
        conn.commit()
        conn.close()
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("schema_hint", result["db"])

    def test_ambiguous_across_two_tables_blocked(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE cars_a (ua_id TEXT, container TEXT)")
        conn.execute("CREATE TABLE cars_b (ua_id TEXT, container TEXT)")
        conn.execute("INSERT INTO cars_a VALUES ('UA-0006','A1')")
        conn.execute("INSERT INTO cars_b VALUES ('UA-0006','B1')")
        conn.commit()
        conn.close()
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("ambiguous_candidates", result["db"])

    def test_ambiguous_across_two_container_columns_blocked(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE cars (ua_id TEXT, container TEXT, container_ext TEXT)"
        )
        conn.execute(
            "INSERT INTO cars VALUES ('UA-0006','X1','X2')"
        )
        conn.commit()
        conn.close()
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_like_used_exact_identity(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE cars (ua_id TEXT, container TEXT)")
        conn.execute("INSERT INTO cars VALUES ('UA-00060','SHOULD-NOT-MATCH')")
        conn.commit()
        conn.close()
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("no_match" in e for e in result["errors"]))

    def test_db_identity_stable_reported(self):
        self._make_db()
        result = discovery.run_discovery(self.db_path, list(self.required_sources))
        self.assertTrue(result["db"]["identity_stable"])
        self.assertEqual(
            result["db"]["sha256_before"], result["db"]["sha256_after"]
        )
        self.assertRegex(result["db"]["sha256_before"], r"^[0-9a-f]{64}$")

    def test_executed_discovery_sql_is_read_only(self):
        self._make_db()
        statements = []
        real_connect = sqlite3.connect

        def traced_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        with mock.patch.object(
            discovery.sqlite3, "connect", side_effect=traced_connect
        ):
            result = discovery.run_discovery(
                self.db_path, list(self.required_sources)
            )
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(statements)
        for statement in statements:
            first = statement.lstrip().split(None, 1)[0].upper()
            self.assertIn(first, {"SELECT", "PRAGMA"})
        forbidden = ("INSERT", "UPDATE", "DELETE", "ATTACH", "VACUUM", "DROP")
        joined = "\n".join(statements).upper()
        for token in forbidden:
            self.assertNotRegex(joined, r"\b%s\b" % token)


class TestDiscoveryCli(DiscoveryTestBase):
    def test_main_exit_code_pass(self):
        self._make_db()
        argv = ["--db", self.db_path]
        for s in self.required_sources:
            argv += ["--source", s]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            rc = discovery.main(argv)
        self.assertEqual(rc, 0)
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["status"], "PASS")

    def test_main_exit_code_blocked(self):
        argv = ["--db", self.db_path]
        for s in self.required_sources:
            argv += ["--source", s]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            rc = discovery.main(argv)
        self.assertNotEqual(rc, 0)
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["status"], "BLOCKED")


class TestContainerUpdateLogic(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bl_update_")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.db_path = os.path.join(self.tmpdir, "crm.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE cars (ua_id TEXT PRIMARY KEY, container TEXT, other TEXT)"
        )
        conn.execute(
            "INSERT INTO cars (ua_id, container, other) VALUES ('UA-0006', 'OLDVALUE0000000000', 'keep')"
        )
        conn.execute(
            "INSERT INTO cars (ua_id, container, other) VALUES ('UA-0007', 'OTHERROW00000000000', 'keep2')"
        )
        conn.commit()
        conn.close()

    def test_exact_single_row_update_and_readback(self):
        _call_update(
            UPDATE_FN, db_path=self.db_path, ua_id="UA-0006",
            container=CORRECT_CONTAINER, new_container=CORRECT_CONTAINER,
        )
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT container, other FROM cars WHERE ua_id='UA-0006'").fetchone()
        conn.close()
        self.assertEqual(row[0], CORRECT_CONTAINER)
        self.assertEqual(row[1], "keep")

    def test_other_rows_unchanged(self):
        _call_update(
            UPDATE_FN, db_path=self.db_path, ua_id="UA-0006",
            container=CORRECT_CONTAINER, new_container=CORRECT_CONTAINER,
        )
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT container, other FROM cars WHERE ua_id='UA-0007'").fetchone()
        conn.close()
        self.assertEqual(row[0], "OTHERROW00000000000")

    def test_idempotence(self):
        for _ in range(3):
            _call_update(
                UPDATE_FN, db_path=self.db_path, ua_id="UA-0006",
                container=CORRECT_CONTAINER, new_container=CORRECT_CONTAINER,
            )
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT container FROM cars WHERE ua_id='UA-0006'").fetchone()
        conn.close()
        self.assertEqual(row[0], CORRECT_CONTAINER)

    def test_missing_row_rollback(self):
        with self.assertRaises(GATE_B_REFUSED):
            _call_update(
                UPDATE_FN, db_path=self.db_path, ua_id="UA-9999",
                container=CORRECT_CONTAINER, new_container=CORRECT_CONTAINER,
            )

    def test_rollback_on_ambiguous_row_never_reports_success(self):
        """Repaired regression: build a *separate* table whose UA identifier
        is deliberately non-unique, insert exactly two UA-0006 rows before
        measuring pre-call evidence, call the real update function, and
        prove GateBRefused is raised with zero state change. This never
        fails during fixture setup (no PRIMARY KEY constraint here).
        """
        amb_db = os.path.join(self.tmpdir, "ambiguous.db")
        conn = sqlite3.connect(amb_db)
        conn.execute("CREATE TABLE cars_ambiguous (ua_id TEXT, container TEXT, other TEXT)")
        conn.execute(
            "INSERT INTO cars_ambiguous (ua_id, container, other) VALUES ('UA-0006','ROWA','a')"
        )
        conn.execute(
            "INSERT INTO cars_ambiguous (ua_id, container, other) VALUES ('UA-0006','ROWB','b')"
        )
        conn.commit()
        conn.close()

        with open(amb_db, "rb") as handle:
            pre_bytes = handle.read()

        sentinel = object()
        result = sentinel
        try:
            result = _call_update(
                UPDATE_FN, db_path=amb_db, table="cars_ambiguous", ua_id="UA-0006",
                container=CORRECT_CONTAINER, new_container=CORRECT_CONTAINER,
            )
        except GATE_B_REFUSED:
            pass

        self.assertIs(
            result,
            sentinel,
            "ambiguous update must not return any success result",
        )

        with open(amb_db, "rb") as handle:
            post_bytes = handle.read()
        self.assertEqual(pre_bytes, post_bytes, "database bytes must not change on a refused ambiguous update")

        conn = sqlite3.connect(amb_db)
        rows = conn.execute("SELECT container FROM cars_ambiguous WHERE ua_id='UA-0006'").fetchall()
        conn.close()
        values = sorted(r[0] for r in rows)
        self.assertEqual(values, ["ROWA", "ROWB"], "row values must be unchanged after refused ambiguous update")

    def test_field_preservation(self):
        _call_update(
            UPDATE_FN, db_path=self.db_path, ua_id="UA-0006",
            container=CORRECT_CONTAINER, new_container=CORRECT_CONTAINER,
        )
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT other FROM cars WHERE ua_id='UA-0006'").fetchone()
        conn.close()
        self.assertEqual(row[0], "keep")

    def test_10_repeat_determinism(self):
        results = []
        for _ in range(10):
            db_copy = os.path.join(self.tmpdir, "repeat_%d.db" % len(results))
            shutil.copyfile(self.db_path, db_copy)
            _call_update(
                UPDATE_FN, db_path=db_copy, ua_id="UA-0006",
                container=CORRECT_CONTAINER, new_container=CORRECT_CONTAINER,
            )
            conn = sqlite3.connect(db_copy)
            row = conn.execute("SELECT container FROM cars WHERE ua_id='UA-0006'").fetchone()
            conn.close()
            results.append(row[0])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(results[0], CORRECT_CONTAINER)

    def test_backup_tamper_rollback(self):
        backup = self.db_path + ".bak"
        shutil.copyfile(self.db_path, backup)
        with open(self.db_path, "r+b") as f:
            f.seek(0)
            f.write(b"TAMPERED")
        raised = False
        try:
            _call_update(
                UPDATE_FN, db_path=self.db_path, ua_id="UA-0006",
                container=CORRECT_CONTAINER, new_container=CORRECT_CONTAINER,
            )
        except Exception:
            raised = True
        self.assertTrue(raised, "tampered database must not silently succeed")
        shutil.copyfile(backup, self.db_path)


class TestExactValidator(unittest.TestCase):
    def test_correct_container_constant_exact(self):
        self.assertEqual(discovery.CORRECT_CONTAINER, "ONEYSELGF1046602")


if __name__ == "__main__":
    unittest.main(verbosity=2)
