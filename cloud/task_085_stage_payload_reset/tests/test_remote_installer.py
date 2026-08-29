#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "task085_remote_installer", ROOT / "remote_installer.py"
)
remote = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(remote)


class SourcePatchTests(unittest.TestCase):
    def test_db_patch_is_atomic_and_idempotent(self):
        source = '''def update_card_field(table: str, card_id: int, field: str, value, actor_id: int):
    old = get_card(table, card_id)
    with connect() as c:
        c.execute("UPDATE")
    log_action(actor_id)
'''
        candidate = remote.patch_db(source)
        compile(candidate, "db.py", "exec")
        self.assertEqual(candidate.count(remote.MARKERS["db.py"]), 1)
        self.assertIn("cleanup_fields_for_transition", candidate)
        self.assertIn("UPDATE cars SET", candidate)
        self.assertEqual(remote.patch_db(candidate), candidate)

    def test_stage_set_refreshes_after_atomic_status_write(self):
        source = '''async def stage_set(update, context):
    q = update.callback_query
    _, cid, code = q.data.split(":")
    cid = int(cid)
    card_before = card_of(cid)
    set_field(cid, "status", code, q.from_user.id)
    card = card_of(cid)
    return card
'''
        candidate = remote.patch_cars_ui(source)
        compile(candidate, "cars_ui.py", "exec")
        self.assertEqual(candidate.count(remote.MARKERS["cars_ui.py"]), 1)
        status_pos = candidate.index('set_field(cid, "status"')
        refresh_pos = candidate.index("card_before = card_of(cid)", status_pos)
        self.assertGreater(refresh_pos, status_pos)
        self.assertEqual(remote.patch_cars_ui(candidate), candidate)

    def test_all_renderers_receive_public_projection_once(self):
        cases = (
            (remote.patch_stranica,
             "def sobrat_kartochku(m, kadry, sredn=None):\n    nom = nomer(m)\n    return nom\n",
             "stranica.py"),
            (remote.patch_master_card,
             "def obrabotat_kartochku(html, kod):\n    row = load_row(kod)\n    return html\n",
             "master_card.py"),
            (remote.patch_cars_schema,
             "def render_card(car, role='owner', today=None):\n    return car.get('status')\n",
             "cars_schema.py"),
        )
        for patcher, source, name in cases:
            with self.subTest(name=name):
                candidate = patcher(source)
                compile(candidate, name, "exec")
                self.assertIn("public_projection", candidate)
                self.assertEqual(candidate.count(remote.MARKERS[name]), 1)
                self.assertEqual(patcher(candidate), candidate)

    def test_stranica_projection_tracks_active_definition_without_old_anchor(self):
        source = '''def sobrat_kartochku(m, kadry):
    nom = nomer(m)
    return nom

def sobrat_kartochku(m, kadry, sredn=None):
    """Active renderer with a changed body."""
    code = m.get("auto_number")
    return code
'''
        candidate = remote.patch_stranica(source)
        compile(candidate, "stranica.py", "exec")
        _start, _end, active = remote._function(candidate, "sobrat_kartochku")
        self.assertEqual(candidate.count(remote.MARKERS["stranica.py"]), 1)
        self.assertEqual(active.count(remote.MARKERS["stranica.py"]), 1)
        self.assertLess(active.index("public_projection"), active.index("code ="))
        self.assertEqual(remote.patch_stranica(candidate), candidate)

    def test_detail_contract_rejects_old_container(self):
        with self.assertRaises(remote.Task085Error):
            with __import__("tempfile").TemporaryDirectory() as raw:
                path = pathlib.Path(raw) / "UA-0011.html"
                path.write_text(
                    "<html><body>UA-0011 Корея VIN 4289 <img src='x.jpg'> "
                    + remote.OLD_CONTAINER + "</body></html>", encoding="utf-8"
                )
                remote.inspect_detail(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)

