import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("repair_remote", ROOT / "repair_remote.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


BASE = '''def render(card, staff):
    L = []
    L.append("<b>%s</b>" % (card.get("auto_number") or "#%s" % card.get("id")))
    return "\\n".join(L)


async def open_card(update, context):
    card = {}
    staff = {}
    await update.message.reply_text(render(card, staff), parse_mode="HTML")


async def cars_list(update, context):
    cards = []
    lines = []
    rows = []
    for card in cards:
        card = card
        nomer = card.get("auto_number") or "#%d" % card["id"]
        name = " ".join(str(x) for x in (card.get("brand"), card.get("model"),
                                         card.get("year")) if x) or "без названия"
        lines.append("<b>%s</b> · %s" % (nomer, name))
        rows.append([InlineKeyboardButton("%s · %s" % (nomer, name[:28]),
                                          callback_data="car_open:%d" % card["id"])])
'''


class PatcherTests(unittest.TestCase):
    def test_patch_is_idempotent(self):
        candidate, changed = MODULE.patch_source(BASE)
        self.assertTrue(changed)
        again, changed_again = MODULE.patch_source(candidate)
        self.assertFalse(changed_again)
        self.assertEqual(candidate, again)

    def test_candidate_contract(self):
        candidate, _ = MODULE.patch_source(BASE)
        checks = MODULE.run_candidate_tests(candidate)
        self.assertTrue(all(checks.values()))

    def test_current_title_shape(self):
        candidate, _ = MODULE.patch_source(BASE)
        namespace = MODULE.helper_namespace(candidate)
        card = {
            "id": 20,
            "auto_number": "UA-0013",
            "brand": "Mercedes-Benz",
            "model": "Б-КЛАССА",
            "year": 2015,
            "vin": "WDD00000000002530",
        }
        self.assertEqual(
            namespace["_ua082_title_html"](card),
            "UA-0013 · Mercedes-Benz Б-КЛАССА 2015 · VIN <b>2530</b>",
        )
        self.assertEqual(
            namespace["_ua082_title_button"](card),
            "UA-0013 · Mercedes-Benz Б-КЛАССА 2015 · VIN 2530",
        )

    def test_invalid_vin_is_not_invented(self):
        candidate, _ = MODULE.patch_source(BASE)
        namespace = MODULE.helper_namespace(candidate)
        self.assertEqual(namespace["_ua082_vin4"]({"vin": "bad"}), "НЕТ")

    def test_drift_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "RENDER_ANCHOR_DRIFT"):
            MODULE.patch_source(BASE.replace(MODULE.OLD_RENDER, "    L.append('changed')\n"))


if __name__ == "__main__":
    unittest.main()
