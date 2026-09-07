#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest

import controller
import remote_installer as installer


CARS = '''
class ApplicationHandlerStop(Exception):
    pass
class InlineKeyboardButton:
    def __init__(self, *args, **kwargs): pass
class InlineKeyboardMarkup:
    def __init__(self, *args, **kwargs): pass
class CallbackQueryHandler:
    def __init__(self, *args, **kwargs): pass
class S:
    STAGES = ((1, "one"),)
    STATUSES = {}

async def stage_menu(update, context):
    q = update.callback_query
    cid = 1
    card = {"status": "sold"}
    rows = []
    for number, _name in S.STAGES:
        pair = [InlineKeyboardButton(
            ("• " if card.get("status") == code else "") + label,
            callback_data="car_setstage:%d:%s" % (cid, code))
            for code, (stage_no, label) in S.STATUSES.items() if stage_no == number]
        rows.append(pair)
    return rows

async def stage_set(update, context):
    q = update.callback_query
    _, cid, code = q.data.split(":")
    cid = int(cid)
    card_before = card_of(cid)
    set_field(cid, "status", code, q.from_user.id)

def unrelated():
    return "preserved"

def register(app):
    return None
'''

KONTEYNER = '''
class InlineKeyboardButton:
    def __init__(self, *args, **kwargs): pass
class S:
    STAGES = ((1, "one"),)
    STATUSES = {}

async def gde_mashina(update, context):
    cid = 1
    card = {"status": "sold"}
    rows = []
    for nomer_etapa, _nazv in S.STAGES:
        pary = [InlineKeyboardButton(
            label, callback_data="car_setstage:%d:%s" % (cid, code))
            for code, (stage_no, label) in S.STATUSES.items()
            if stage_no == nomer_etapa]
        rows.append(pary)
    return rows

def posle_statusa():
    return "preserved"
'''

SCHEMA = '''
STATUSES = {
    "kr_bought": (1, "Выкуплено, на нашей парковке"),
    "sea_loaded": (2, "Загружено в контейнер"),
    "sea_transit": (2, "В пути"),
    "sold_transit": (2, "Продано · в пути"),
    "ge_waiting": (3, "Авто в Грузии"),
    "ge_to_kyiv": (3, "Выехало в Киев"),
    "ua_arrived": (4, "В Киеве"),
    "ua_handed": (4, "Передано клиенту"),
    "sold": (4, "Продано"),
    "archive": (4, "Архив"),
}
'''


class ContractTests(unittest.TestCase):
    def test_patch_exact_two_menus_and_preserve_other_functions(self):
        unrelated_before = installer.function_text(CARS, "unrelated")
        writer_before = installer.function_text(KONTEYNER, "posle_statusa")
        cars = installer.patch_cars_ui(CARS)
        container = installer.patch_konteyner(KONTEYNER)
        self.assertTrue(installer.desired_cars_ui(cars))
        self.assertTrue(installer.desired_konteyner(container))
        self.assertEqual(unrelated_before, installer.function_text(cars, "unrelated"))
        self.assertEqual(writer_before, installer.function_text(container, "posle_statusa"))
        self.assertEqual(cars, installer.patch_cars_ui(cars))
        self.assertEqual(container, installer.patch_konteyner(container))

    def test_schema_history_preserved_and_exact_visible_set(self):
        cars = installer.patch_cars_ui(CARS).encode()
        container = installer.patch_konteyner(KONTEYNER).encode()
        proof = installer.verify_sources(cars, container, SCHEMA.encode())
        self.assertEqual(proof["hidden_codes"], list(installer.HIDDEN))
        self.assertEqual(proof["old_callbacks"], "BLOCKED_NO_WRITE")
        self.assertEqual(
            proof["visible_codes"],
            ["sold_transit", "ge_waiting", "ge_to_kyiv", "ua_arrived", "sold", "archive"],
        )
        self.assertEqual(installer.schema_statuses(SCHEMA)["ua_handed"][1], "Передано клиенту")

    def test_stale_callback_guard_precedes_writer(self):
        source = installer.function_text(installer.patch_cars_ui(CARS), "stage_set")
        self.assertLess(source.index("if code in _UA117_HIDDEN_STATUS_CODES"),
                        source.index('set_field(cid, "status"'))
        patched = installer.patch_cars_ui(CARS)
        self.assertEqual(patched.count("group=-100"), 1)
        self.assertEqual(patched.count("_ua117_block_removed_stage"), 2)

    def test_fail_closed_on_unknown_source_shape(self):
        broken = CARS.replace("if stage_no == number]", "if True]")
        with self.assertRaises(installer.InstallError):
            installer.patch_cars_ui(broken)

    def test_controller_remote_scope(self):
        good = controller.API.file_url(controller.REMOTE_SCRIPT)
        self.assertIn("files/path/home/Carix/", good)
        with self.assertRaises(controller.ControllerError):
            controller.API.file_url("/home/Carix/cars_ui.py")

    def test_all_package_modules_compile(self):
        root = pathlib.Path(__file__).resolve().parent
        for path in root.glob("*.py"):
            compile(path.read_text(encoding="utf-8"), path.name, "exec")


if __name__ == "__main__":
    unittest.main(verbosity=2)
