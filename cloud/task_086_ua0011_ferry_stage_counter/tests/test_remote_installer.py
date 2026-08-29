import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("task086_remote", ROOT / "remote_installer.py")
remote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remote)


class SourcePatchTests(unittest.TestCase):
    def test_db_patch_is_atomic_and_idempotent(self):
        source = '''def update_card_field(table, card_id, field, value, actor_id):
    old = get_card(table, card_id)
    with connect() as c:
        c.execute("UPDATE cars SET status=? WHERE id=?", (value, card_id))
'''
        candidate = remote.patch_db(source)
        self.assertIn(remote.MARKERS["db.py"], candidate)
        self.assertIn("apply_stage_transition_live", candidate)
        self.assertEqual(remote.patch_db(candidate), candidate)
        compile(candidate, "db.py", "exec")

    def test_stage_set_uses_single_transaction_writer(self):
        source = '''async def stage_set(update, context):
    q = update.callback_query
    set_field(1, "status", "kr_bought", 1)

async def stage_menu(update, context):
    rows = [code for code, (stage_no, label) in S.STATUSES.items() if stage_no == number]
'''
        candidate = remote.patch_cars_ui(source)
        _start, _end, active = remote._function(candidate, "stage_set")
        self.assertIn("apply_stage_transition_live", active)
        self.assertNotIn("set_field(", active)
        self.assertIn('code != "sea_transit"', candidate)
        self.assertEqual(remote.patch_cars_ui(candidate), candidate)
        compile(candidate, "cars_ui.py", "exec")

    def test_publisher_rebuilds_both_catalogs_before_success(self):
        source = '''def opublikovat(kod, proba=False):
    try:
        html, diag, m = _master(kod)
    except Exception:
        return False, "build"
    celi = []
    papka_rez = "x"
    stalo = dict((put, _sha(put)) for put in celi)
    return True, "ok"
'''
        candidate = remote.patch_publikaciya(source)
        self.assertIn("rebuild_catalogs_live", candidate)
        self.assertIn(remote.MARKERS["publikaciya.py"], candidate)
        self.assertEqual(remote.patch_publikaciya(candidate), candidate)
        compile(candidate, "publikaciya.py", "exec")

    def test_all_renderers_receive_projection_once(self):
        fixtures = {
            "stranica.py": "def sobrat_kartochku(m, kadry, sredn=None):\n    nom = nomer(m)\n    return nom\n",
            "cars_schema.py": "def render_card(car):\n    L = []\n    return L\n",
        }
        for name, source in fixtures.items():
            candidate = remote.PATCHERS[name](source)
            self.assertEqual(candidate.count(remote.MARKERS[name]), 1)
            self.assertEqual(remote.PATCHERS[name](candidate), candidate)
            compile(candidate, name, "exec")

    def test_detail_contract_preserves_ferry_payload(self):
        target = {
            "sea_container": "ONEYSELGF1046602",
            "eta_manual": "2026-12-12",
        }
        good = '''<html><head><meta name="viewport" content="width=device-width"></head><body>
UA-0011 VIN 4289 <img src="foto/UA-0011/m/001.jpg">
<div>На пароме</div><div>Корея → Грузия</div>
<div>ONEYSELGF1046602</div><div>12.12.2026</div></body></html>'''
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "UA-0011.html"
            path.write_text(good, encoding="utf-8")
            result = remote.inspect_detail(path, target)
            self.assertTrue(all(result["checks"].values()))
            path.write_text(good.replace("На пароме", "Автомобиль на пароме"), encoding="utf-8")
            with self.assertRaises(remote.Task086Error):
                remote.inspect_detail(path, target)


if __name__ == "__main__":
    unittest.main()
