"""Offline exact-master transformations; I/O and external spec modules are fenced.

This proves the inspected master_card transformation chain keeps the price block.
It does not substitute for real specification/language/publication acceptance.
"""

import ast
import builtins
import datetime
import hashlib
import html
import json
import os
import pathlib
import re
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from test_private_source import master_base_renderers
from patch_stranica import patch_stranica
from uaart_market_prices import END, START, render_market_prices
from initial_html_prices import migrate_card

MASTER_SHA256 = "27e32420bbec9f1e0a25621e1c20dda20944537daa40c1ccac574689cd6c3f6e"


def master_transforms(source, row):
    if hashlib.sha256(source).hexdigest() != MASTER_SHA256:
        raise ValueError("MASTER_SOURCE_HASH_MISMATCH")
    tree = ast.parse(source)
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            body.append(node)
        elif isinstance(node, ast.Assign):
            # Inspected full-module assignments contain only string/list/dict
            # values, captured wrapper references, path joining and re.compile.
            for call in [n for n in ast.walk(node.value) if isinstance(n, ast.Call)]:
                if ast.unparse(call.func) not in ("os.path.join", "_ua_seo068_re.compile"):
                    raise AssertionError("UNEXPECTED_MASTER_MODULE_CALL")
            body.append(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            body.append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.Try)):
            # Imports are supplied below. No live source module is imported.
            continue
        else:
            raise AssertionError("UNEXPECTED_MASTER_MODULE_STATEMENT")

    attempts = []
    def deny(*args, **kwargs):
        attempts.append("io")
        raise AssertionError("UNEXPECTED_IO")

    fake_os = SimpleNamespace(path=SimpleNamespace(join=os.path.join, basename=os.path.basename,
                               isfile=lambda path: str(path).endswith("-diag.html"),
                               exists=lambda path: str(path).endswith("-diag.html")),
                              listdir=lambda path: [])
    namespace = {
        "__builtins__": dict(vars(builtins), open=deny), "os": fake_os,
        "re": re, "json": json, "_UaStageZoneInfo": None,
        "_ua_stage_dt": datetime, "_ua_stage_html": html, "_ua_stage_json": json,
        "_ua_stage_os": fake_os, "_ua_seo068_os": fake_os,
        "_ua_seo068_re": re, "_ua068_dt": datetime, "_ua068_html": html,
        "_ua068_os": fake_os, "_ua068_re": re, "_ua083_re": re,
        "_ua84_ensure_html": lambda text, code: text,
        "_ua84_uid_from_path": lambda path: re.fullmatch(r"(UA-[0-9]{4})\.html", path).group(1),
        "_ua84_write_lock": deny,
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), "controlled_master_ast", "exec"), namespace)
    namespace.update({
        "dannye": lambda code: dict(row), "vse_kody": lambda: [row["auto_number"]],
        "vybrat_glavnoe": lambda code, value: ("fixture.jpg", "unchanged"),
        "ubrat_dubli_video": lambda text, code: (text, []),
        "rasstavit_zastavki": lambda text: text,
        "_ua068_ensure_diag_files": lambda *args: None,
        "_ua068_video_count": lambda *args: 0,
    })
    return namespace, attempts


@unittest.skipUnless(os.environ.get("UA088_LIVE_SOURCE_DIR"), "Private snapshot path not supplied")
class MasterChainTest(unittest.TestCase):
    def test_master_chain_preserves_price_fragment_for_four_stages(self):
        private = pathlib.Path(os.environ["UA088_LIVE_SOURCE_DIR"])
        renderer = master_base_renderers(patch_stranica((private / "stranica.py").read_bytes())[0].decode())
        master = (private / "master_card.py").read_bytes()
        spec = ModuleType("ua_additional_spec")
        spec.inject_public_spec = lambda text, code: text
        for stage in ("kr_ready", "sea_ready", "ge_waiting", "ua_ready"):
            row = {"auto_number": "UA-0010", "brand": "Fixture", "model": "Preserved", "year": 2020,
                   "status": stage, "published": 1, "price_uah": 9100, "price_georgia": 7000,
                   "description": "Preserved description", "vin": "TEST0000000001234"}
            with self.subTest(stage=stage), patch.dict("sys.modules", {"ua_additional_spec": spec}):
                namespace, attempts = master_transforms(master, row)
                before = renderer["sobrat_kartochku"](row, ["fixture.jpg"])
                after = namespace["obrabotat_kartochku"](before, "UA-0010")
                component = render_market_prices(row, require_car_id=True)
                self.assertEqual(after.count(START), 1)
                self.assertEqual(after.count(END), 1)
                self.assertEqual(after[after.index(START):after.index(END) + len(END)], component)
                self.assertEqual(attempts, [])

    def test_initial_migration_accepts_current_master_transformed_card(self):
        private = pathlib.Path(os.environ["UA088_LIVE_SOURCE_DIR"])
        renderer = master_base_renderers((private / "stranica.py").read_text())
        master = (private / "master_card.py").read_bytes()
        spec = ModuleType("ua_additional_spec")
        spec.inject_public_spec = lambda text, code: text
        row = {"auto_number": "UA-0010", "brand": "Fixture", "model": "Preserved", "year": 2020,
               "status": "ge_waiting", "published": 1, "price_uah": 11700, "price_georgia": 8750,
               "description": "Preserved description", "vin": "TEST0000000001234"}
        with patch.dict("sys.modules", {"ua_additional_spec": spec}):
            namespace, attempts = master_transforms(master, row)
            before = namespace["obrabotat_kartochku"](renderer["sobrat_kartochku"](row, ["fixture.jpg"]), "UA-0010")
            after, evidence = migrate_card(before, row)
            self.assertTrue(evidence["outside_price_unchanged"])
            self.assertEqual(after.count(START), 1)
            self.assertEqual(after.count(END), 1)
            self.assertEqual(attempts, [])


if __name__ == "__main__":
    unittest.main()
