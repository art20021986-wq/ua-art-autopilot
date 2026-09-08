#!/usr/bin/env python3
import pathlib
import sys
import unittest


HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import patcher


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


class ContractTests(unittest.TestCase):
    def test_exact_single_button_restore(self):
        cars = patcher.patch_cars_ui(CARS_UI)
        container = patcher.patch_konteyner(KONTEYNER)
        schema = patcher.patch_schema(SCHEMA)
        proof = patcher.verify(cars, container, schema)
        self.assertEqual(proof["button_code"], "kr_bought")
        self.assertEqual(proof["button_label"], "В Корее")
        self.assertEqual(proof["button_count_added"], 1)
        self.assertEqual(proof["hidden_codes"], ["sea_loaded", "sea_transit", "ua_handed"])

    def test_transform_is_idempotent(self):
        cars = patcher.patch_cars_ui(CARS_UI)
        container = patcher.patch_konteyner(KONTEYNER)
        schema = patcher.patch_schema(SCHEMA)
        self.assertEqual(cars, patcher.patch_cars_ui(cars))
        self.assertEqual(container, patcher.patch_konteyner(container))
        self.assertEqual(schema, patcher.patch_schema(schema))

    def test_unknown_preimage_fails_closed(self):
        with self.assertRaises(patcher.PatchError):
            patcher.patch_schema(SCHEMA.replace("Выкуплено, на нашей парковке", "Другое"))


if __name__ == "__main__":
    unittest.main()
