#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import controller
import patcher
import remote_installer


CARS_UI = r'''
class S:
    STATUSES = {}
async def stage_menu(update, context):
    rows = [code for code, (stage_no, label) in S.STATUSES.items()
            if stage_no == number and code not in _UA117_HIDDEN_STATUS_CODES]
async def stage_set(update, context):
    _, cid, code = q.data.split(":")
    cid = int(cid)
    if code in _UA117_HIDDEN_STATUS_CODES:
        raise Exception
def register(app):
    app.add_handler(CallbackQueryHandler(
        _ua117_block_removed_stage,
        pattern=r"^car_setstage:\d+:(?:kr_bought|sea_loaded|sea_transit|ua_handed)$"),
        group=-100)
_UA117_HIDDEN_STATUS_CODES = frozenset({'kr_bought', 'sea_loaded', 'sea_transit', 'ua_handed'})
'''

KONTEYNER = r'''
class S:
    STATUSES = {}
async def gde_mashina(update, context):
    rows = [code for code, (stage_no, label) in S.STATUSES.items()
            if stage_no == number and code not in _UA117_HIDDEN_STATUS_CODES]
_UA117_HIDDEN_STATUS_CODES = frozenset({'kr_bought', 'sea_loaded', 'sea_transit', 'ua_handed'})
'''

SCHEMA = '''
STATUSES = {
    "kr_bought":     (1, "Выкуплено, на нашей парковке"),
    "sea_loaded":    (2, "Загружено в контейнер"),
    "sea_transit":   (2, "В пути"),
    "sold_transit":  (2, "Продано · в пути"),
    "ge_waiting":    (3, "Авто в Грузии"),
    "ge_to_kyiv":    (3, "Выехало в Киев"),
    "ua_arrived":    (4, "В Киеве"),
    "ua_handed":     (4, "Передано клиенту"),
    "sold":          (4, "Продано"),
    "archive":       (4, "Архив"),
}
'''


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class PatcherContractTests(unittest.TestCase):
    def test_exact_single_button_restore(self):
        cars = patcher.patch_cars_ui(CARS_UI)
        container = patcher.patch_konteyner(KONTEYNER)
        schema = patcher.patch_schema(SCHEMA)
        proof = patcher.verify(cars, container, schema)
        self.assertEqual(proof["button_code"], "kr_bought")
        self.assertEqual(proof["button_label"], "В Корее")
        self.assertEqual(proof["button_count_added"], 1)
        self.assertEqual(
            proof["hidden_codes"], ["sea_loaded", "sea_transit", "ua_handed"]
        )
        self.assertEqual(proof["callback"], "ENABLED")
        self.assertEqual(proof["other_removed_buttons"], "STILL_HIDDEN")

    def test_transform_is_idempotent(self):
        cars = patcher.patch_cars_ui(CARS_UI)
        container = patcher.patch_konteyner(KONTEYNER)
        schema = patcher.patch_schema(SCHEMA)
        self.assertEqual(cars, patcher.patch_cars_ui(cars))
        self.assertEqual(container, patcher.patch_konteyner(container))
        self.assertEqual(schema, patcher.patch_schema(schema))

    def test_unknown_preimages_fail_closed(self):
        with self.assertRaises(patcher.PatchError):
            patcher.patch_schema(
                SCHEMA.replace("Выкуплено, на нашей парковке", "Другое")
            )
        with self.assertRaises(patcher.PatchError):
            patcher.patch_cars_ui(
                CARS_UI.replace(
                    "(?:kr_bought|sea_loaded|sea_transit|ua_handed)$",
                    "(?:kr_bought|sea_loaded|sea_transit|unexpected)$",
                )
            )


class RemoteTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temporary.name)
        inbox = root / "autopilot_inbox/cloud/task_068_ferry_vin"
        inbox.mkdir(parents=True)
        files = {
            "cars_ui.py": CARS_UI.encode(),
            "konteyner.py": KONTEYNER.encode(),
            "cars_schema.py": SCHEMA.encode(),
        }
        for name, value in files.items():
            (root / name).write_bytes(value)
        (root / "start_safe.py").write_text("print('safe')\n", encoding="utf-8")
        patcher_path = inbox / "task121_korea_patcher.py"
        patcher_path.write_bytes((HERE / "patcher.py").read_bytes())
        self.root = root
        self.files = files
        self.patcher_path = patcher_path
        self.nonce = "task121-123456-abcdef123456"
        self.settings = mock.patch.multiple(
            remote_installer,
            ROOT=root,
            REMOTE_DIR=inbox,
            PATCHER_PATH=patcher_path,
            RECEIPT=inbox / "receipt.json",
            STATE=inbox / "state.json",
            BACKUP_ROOT=inbox / "backups",
            START_SAFE=root / "start_safe.py",
            TARGETS={name: root / name for name in files},
            EXPECTED_BEFORE={name: digest(value) for name, value in files.items()},
        )
        self.settings.start()

    def tearDown(self):
        self.settings.stop()
        self.temporary.cleanup()

    def candidate_hashes(self):
        return {
            "cars_ui.py": digest(patcher.patch_cars_ui(CARS_UI).encode()),
            "konteyner.py": digest(patcher.patch_konteyner(KONTEYNER).encode()),
            "cars_schema.py": digest(patcher.patch_schema(SCHEMA).encode()),
        }

    def test_backup_install_verify_and_exact_rollback(self):
        backed_up = remote_installer.backup(self.nonce)
        backup_sha = backed_up["backup_manifest_sha256"]
        after = self.candidate_hashes()
        patcher_sha = digest(self.patcher_path.read_bytes())
        installed = remote_installer.install(
            self.nonce, backup_sha, patcher_sha, after
        )
        self.assertEqual(installed["proof"]["button_count_added"], 1)
        repeated = remote_installer.install(
            self.nonce, backup_sha, patcher_sha, after
        )
        self.assertTrue(repeated["idempotent"])
        self.assertFalse(repeated["production_write"])
        verified = remote_installer.verify(
            self.nonce, backup_sha, patcher_sha, after
        )
        self.assertEqual(verified["proof"]["hidden_codes"], list(patcher.HIDDEN_CODES))
        rolled_back = remote_installer.rollback(self.nonce, backup_sha)
        self.assertTrue(rolled_back["restored_exact"])
        for name, original in self.files.items():
            self.assertEqual((self.root / name).read_bytes(), original)

    def test_live_drift_after_backup_stops_before_write(self):
        backed_up = remote_installer.backup(self.nonce)
        backup_sha = backed_up["backup_manifest_sha256"]
        target = self.root / "cars_ui.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        with self.assertRaises(remote_installer.InstallError):
            remote_installer.install(
                self.nonce,
                backup_sha,
                digest(self.patcher_path.read_bytes()),
                self.candidate_hashes(),
            )


class ControllerScopeTests(unittest.TestCase):
    def test_remote_file_scope_is_exact(self):
        controller.API.file_url("/home/Carix/cars_ui.py")
        controller.API.file_url(controller.REMOTE_STATE)
        with self.assertRaises(controller.ControllerError):
            controller.API.file_url("/home/Carix/crm.db")
        with self.assertRaises(controller.ControllerError):
            controller.API.file_url("/home/Carix/master_card.py")

    def test_nonce_and_hash_validation(self):
        self.assertEqual(
            controller.nonce_value("task121-123456-abcdef123456"),
            "task121-123456-abcdef123456",
        )
        with self.assertRaises(controller.ControllerError):
            controller.nonce_value("task121-bad")
        with self.assertRaises(controller.ControllerError):
            controller.hash_value("x", "HASH")

    def test_remote_command_cannot_repeat_before_trigger_cleanup(self):
        nonce = "task121-123456-abcdef123456"
        api = controller.API("secret", nonce)
        captured = []
        receipt = {
            "task_id": controller.TASK_ID,
            "run_nonce": nonce,
            "mode": "BACKUP",
            "status": "PASS",
        }
        with (
            mock.patch.object(api, "delete_file"),
            mock.patch.object(
                api,
                "create_trigger",
                side_effect=lambda command: captured.append(command) or ("always_on", 9),
            ),
            mock.patch.object(api, "read", return_value=(
                __import__("json").dumps(receipt).encode("utf-8")
            )),
            mock.patch.object(api, "delete_trigger") as deleted,
        ):
            value = api.run_remote("backup", timeout=1)
        self.assertEqual(value, receipt)
        self.assertIn("sleep 180", captured[0])
        self.assertIn("task121_rc=$?", captured[0])
        deleted.assert_called_once_with(("always_on", 9))


if __name__ == "__main__":
    unittest.main()
