from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import sqlite3
import struct
import sys
import tempfile
import unittest


PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PACKAGE_DIR))

import live_discovery as ld  # noqa: E402


FIXTURE_DIR = pathlib.Path(
    os.environ.get(
        "TASK058_FIXTURE_DIR",
        str(REPO_ROOT / "tasks" / "fixtures" / "task_058"),
    )
)
FIXTURES = {
    "IMG_8128.jpeg": {
        "sha256": "333ca420282590d774f9f8f834987ea00aa7ec71361b8c4a6016391863ce4caf",
        "size": 224419,
        "dimensions": (1320, 1375),
    },
    "IMG_8129.jpeg": {
        "sha256": "5db32cee3e95fb5d5e738eb18250a730af928a0f47952cc706bb620396cdb4ad",
        "size": 285625,
        "dimensions": (1320, 1656),
    },
}
VISIBLE_FIELD_CONTRACT = {
    "make_model": "Kia K5",
    "year": 2018,
    "generation": "II покоління (FL)",
    "price_usd": 11400,
    "price_uah": 510720,
    "mileage_km": 198000,
    "fuel": "LPG",
    "engine_l": 2.0,
    "vin_sha256": "dee8b9174d73abde4cab91341a26790c12f8bc606b86b7417d3962927a8193c6",
    "transmission": None,
    "location": None,
}


def jpeg_dimensions(path: pathlib.Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise AssertionError("not a JPEG")
    offset = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        length = struct.unpack(">H", data[offset : offset + 2])[0]
        if length < 2 or offset + length > len(data):
            raise AssertionError("invalid JPEG segment")
        if marker in sof:
            height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
            return width, height
        offset += length
    raise AssertionError("JPEG dimensions not found")


@contextlib.contextmanager
def patched_runtime(base: pathlib.Path):
    old = (ld.BASE_DIR, ld.SAFE_INBOX_DIR, ld.ALLOWLIST_PATH, ld.RECEIPT_PATH)
    safe = base / "autopilot_inbox" / "cloud" / "task_058_crm_ocr_sync"
    safe.mkdir(parents=True)
    ld.BASE_DIR = base
    ld.SAFE_INBOX_DIR = safe
    ld.ALLOWLIST_PATH = safe / "allowlist.json"
    ld.RECEIPT_PATH = safe / "task_058_live_discovery_receipt.json"
    try:
        yield safe
    finally:
        ld.BASE_DIR, ld.SAFE_INBOX_DIR, ld.ALLOWLIST_PATH, ld.RECEIPT_PATH = old


def minimal_config(base: pathlib.Path) -> dict:
    return {
        "required_source_paths": [str(base / "team_bot.py")],
        "optional_source_paths": [],
        "db_path": str(base / "crm.db"),
        "required_site_paths": [str(base / "video" / "index.html")],
        "optional_site_paths": [str(base / "video" / "UA-0009.html")],
        "log_paths": [],
    }


def create_inputs(base: pathlib.Path) -> None:
    (base / "video").mkdir()
    (base / "video" / "index.html").write_text("<html>catalog</html>\n", encoding="utf-8")
    (base / "team_bot.py").write_text(
        "def detect_kind(msg): return ('photo', msg.photo[-1].file_id)\n"
        "async def intake(update, context): return await run_ai_draft(update)\n"
        "async def run_ai_draft(update):\n"
        "    try_ocr(update.photo)\n"
        "    reply('Изображение сохранено, но разобрать его не получилось')\n"
        "    reply('CRM: страницы сайта отстали от базы')\n"
        "async def ai_save(update, context): return True\n",
        encoding="utf-8",
    )
    connection = sqlite3.connect(base / "crm.db")
    connection.execute(
        "CREATE TABLE cars (id INTEGER PRIMARY KEY, auto_number TEXT, published INTEGER)"
    )
    connection.execute("INSERT INTO cars(auto_number, published) VALUES ('UA-0008', 1)")
    connection.execute(
        "CREATE TABLE inbox (id INTEGER PRIMARY KEY, kind TEXT, file_id TEXT, created_at TEXT)"
    )
    connection.execute(
        "INSERT INTO inbox(kind, file_id, created_at) VALUES (?, ?, ?)",
        ("photo", "telegram-file-id-must-never-leave-production", "2026-08-28 10:30:00"),
    )
    connection.commit()
    connection.close()


class FixtureIntegrityTests(unittest.TestCase):
    def test_exact_fixture_hash_size_and_dimensions(self):
        for name, expected in FIXTURES.items():
            path = FIXTURE_DIR / name
            self.assertTrue(path.is_file(), f"mandatory fixture missing: {path}")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"])
            self.assertEqual(path.stat().st_size, expected["size"])
            self.assertEqual(jpeg_dimensions(path), expected["dimensions"])

    def test_tampered_fixture_is_detected(self):
        source = FIXTURE_DIR / "IMG_8129.jpeg"
        self.assertTrue(source.is_file(), f"mandatory fixture missing: {source}")
        tampered = bytearray(source.read_bytes())
        tampered[-1] ^= 1
        self.assertNotEqual(hashlib.sha256(tampered).hexdigest(), FIXTURES[source.name]["sha256"])

    def test_visible_contract_keeps_cropped_fields_unknown(self):
        self.assertEqual(VISIBLE_FIELD_CONTRACT["make_model"], "Kia K5")
        self.assertEqual(VISIBLE_FIELD_CONTRACT["mileage_km"], 198000)
        self.assertEqual(VISIBLE_FIELD_CONTRACT["vin_sha256"], hashlib.sha256(b"KNAGU416BKA324445").hexdigest())
        self.assertIsNone(VISIBLE_FIELD_CONTRACT["transmission"])
        self.assertIsNone(VISIBLE_FIELD_CONTRACT["location"])
        self.assertNotIn("KNAGU416BKA324445", json.dumps(VISIBLE_FIELD_CONTRACT))


class AllowlistTests(unittest.TestCase):
    def test_committed_allowlist_has_exact_root_and_no_mysite(self):
        data = json.loads((PACKAGE_DIR / "allowlist.json").read_text(encoding="utf-8"))
        serialized = json.dumps(data)
        self.assertNotIn("/mysite/", serialized)
        self.assertEqual(data["db_path"], "/home/Carix/crm.db")
        self.assertEqual(len(data["required_source_paths"]), 6)
        self.assertEqual(len(data["required_site_paths"]), 20)
        self.assertEqual(
            set(data["optional_site_paths"]),
            {
                "/home/Carix/video/UA-0009.html",
                "/home/Carix/video/UA-0010.html",
                "/home/Carix/site/UA-0009.html",
                "/home/Carix/site/UA-0010.html",
            },
        )
        self.assertEqual(data["log_paths"], [])

    def test_unapproved_mysite_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            with patched_runtime(base) as safe:
                config = {
                    "task_id": "task_058",
                    "required_source_paths": [str(base / "team_bot.py")],
                    "optional_source_paths": [],
                    "db_path": str(base / "crm.db"),
                    "required_site_paths": [str(base / "mysite" / "index.html")],
                    "optional_site_paths": [],
                    "log_paths": [],
                }
                ld.ALLOWLIST_PATH.write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaisesRegex(ld.DiscoveryError, "UNAPPROVED_PATH"):
                    ld.load_allowlist(ld.ALLOWLIST_PATH)

    def test_duplicate_or_extra_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            with patched_runtime(base):
                data = {
                    "task_id": "task_058",
                    "required_source_paths": [str(base / "team_bot.py")] * 2,
                    "optional_source_paths": [],
                    "db_path": str(base / "crm.db"),
                    "required_site_paths": [],
                    "optional_site_paths": [],
                    "log_paths": [],
                    "unexpected": True,
                }
                ld.ALLOWLIST_PATH.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ld.DiscoveryError):
                    ld.load_allowlist(ld.ALLOWLIST_PATH)


class DiscoveryTests(unittest.TestCase):
    def test_readonly_report_passes_and_preserves_every_input(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            with patched_runtime(base):
                create_inputs(base)
                paths = [base / "team_bot.py", base / "crm.db", base / "video" / "index.html"]
                before = {str(path): ld.sha256_file(path) for path in paths}
                report = ld.build_report(minimal_config(base))
                after = {str(path): ld.sha256_file(path) for path in paths}
                self.assertEqual(report["status"], "PASS", report["errors"])
                self.assertEqual(before, after)
                self.assertTrue(report["source_identity_stable"])
                self.assertTrue(report["site_identity_stable"])
                self.assertTrue(report["database"]["identity_stable"])
                self.assertEqual(report["database"]["open_uri_mode"], "ro")
                self.assertEqual(report["database"]["query_only_value"], 1)
                self.assertEqual(
                    report["database"]["candidate_cards"]["UA-0010"]["row_count"], 0
                )
                candidates = report["database"]["recent_image_candidates"]
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0]["inbox_id"], 1)
                self.assertRegex(candidates[0]["file_id_sha256"], r"^[0-9a-f]{64}$")
                self.assertNotIn(
                    "telegram-file-id-must-never-leave-production",
                    json.dumps(report, ensure_ascii=False),
                )
                self.assertFalse(report["production_write"])
                self.assertFalse(report["site_rebuilt"])

    def test_missing_required_source_is_blocked_not_green(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            with patched_runtime(base):
                create_inputs(base)
                (base / "team_bot.py").unlink()
                report = ld.build_report(minimal_config(base))
                self.assertEqual(report["status"], "BLOCKED")
                self.assertFalse(report["completeness"]["required_sources_found"])
                self.assertIn("REQUIRED_SOURCES_INCOMPLETE", report["errors"])

    def test_missing_required_site_is_blocked_not_green(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            with patched_runtime(base):
                create_inputs(base)
                (base / "video" / "index.html").unlink()
                report = ld.build_report(minimal_config(base))
                self.assertEqual(report["status"], "BLOCKED")
                self.assertFalse(report["completeness"]["required_site_found"])

    def test_scan_finds_both_failure_messages_without_leaking_vin(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "source.py"
            source.write_text(
                "VIN='KNAGU416BKA324445'\n"
                "print('Изображение сохранено, но разобрать его не получилось')\n"
                "print('страницы сайта отстали от базы')\n",
                encoding="utf-8",
            )
            result = ld.scan_source(source)
            dumped = json.dumps(result, ensure_ascii=False)
            self.assertEqual({item["kind"] for item in result["message_locations"]}, {"ocr_failure", "rebuild_failure"})
            self.assertNotIn("KNAGU416BKA324445", dumped)
            self.assertIn("[REDACTED_VIN]", dumped)

    def test_target_function_excerpts_and_imports_are_bounded_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "team_bot.py"
            source.write_text(
                "import ai_runtime as ai\n"
                "def detect_kind(msg): return msg.photo[-1].file_id\n"
                "async def intake(update, context): return await run_ai_draft(update)\n"
                "async def run_ai_draft(update):\n"
                "    API_KEY='this-is-a-hardcoded-provider-secret'\n"
                "    parsed = ai.image(b'bytes')\n"
                "    return parsed\n"
                "async def ai_save(update, context): return True\n",
                encoding="utf-8",
            )
            result = ld.scan_source(source)
            self.assertIn(
                {"module": "ai_runtime", "name": None, "as": "ai"},
                result["imports"],
            )
            self.assertEqual(
                {item["name"] for item in result["function_excerpts"]},
                {"detect_kind", "intake", "run_ai_draft", "ai_save"},
            )
            excerpt = json.dumps(result["function_excerpts"])
            self.assertIn("ai.image", excerpt)
            self.assertNotIn("hardcoded-provider-secret", excerpt)

    def test_symlink_and_hardlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            with patched_runtime(base):
                target = base / "team_bot.py"
                target.write_text("x=1\n", encoding="utf-8")
                link = base / "db.py"
                link.symlink_to(target)
                with self.assertRaisesRegex(ld.DiscoveryError, "SYMLINK_REJECTED"):
                    ld.regular_file(str(link), allowed_paths=ld.hardcoded_paths(), max_bytes=100, required=True)
                hard = base / "cars_ui.py"
                os.link(target, hard)
                with self.assertRaisesRegex(ld.DiscoveryError, "HARDLINK_REJECTED"):
                    ld.regular_file(str(hard), allowed_paths=ld.hardcoded_paths(), max_bytes=100, required=True)

    def test_receipt_can_only_be_written_to_exact_safe_target(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            with patched_runtime(base):
                with self.assertRaisesRegex(ld.DiscoveryError, "RECEIPT_PATH_INVALID"):
                    ld.write_receipt({"status": "BLOCKED"}, base / "escape.json")
                ld.write_receipt({"status": "BLOCKED"}, ld.RECEIPT_PATH)
                self.assertEqual(json.loads(ld.RECEIPT_PATH.read_text())["status"], "BLOCKED")

    def test_redaction_covers_secret_email_phone_and_vin(self):
        value = (
            "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456 owner@example.com "
            "+380 67 123 45 67 KNAGU416BKA324445 "
            "API_KEY='this-is-a-hardcoded-provider-secret'"
        )
        redacted = ld.redact(value)
        for fragment in ("sk-ABC", "owner@example.com", "+380", "KNAGU416BKA324445"):
            self.assertNotIn(fragment, redacted)
        self.assertNotIn("hardcoded-provider-secret", redacted)


if __name__ == "__main__":
    unittest.main()
