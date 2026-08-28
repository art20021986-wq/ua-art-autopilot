from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


builder = load_module("build_candidate", HERE / "build_candidate.py")


class PipelineTests(unittest.TestCase):
    def test_inventory_is_exactly_seventeen(self):
        config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(len(config["inventory_paths"]), 17)
        self.assertEqual(len(config["index_paths"]), 14)
        self.assertEqual(len(config["diagnostic_paths"]), 10)
        self.assertEqual(config["index_paths"][-1], "/video/UA-0010.html")

    def test_head_patch_replaces_noindex_and_preview_canonical(self):
        source = """<!doctype html><html><head><title>UA-0009</title>
        <meta name="robots" content="noindex,nofollow">
        <link href="https://www.uaart.com.ua/video/preview/v4/UA-0009.html" rel="canonical">
        </head><body><h1>UA-0009</h1><p>VIN: SAFE</p></body></html>"""
        result = builder.insert_head(source, "/video/UA-0009.html", "https://www.uaart.com.ua")
        self.assertNotIn("noindex", result.lower())
        self.assertNotIn("/preview/", result)
        self.assertEqual(result.count('rel="canonical"'), 1)
        self.assertIn('href="https://www.uaart.com.ua/video/UA-0009.html"', result)
        self.assertIn("UA-0009 | UA ART</title>", result)
        self.assertIn("seo-preview-guard", result)
        self.assertIn("VIN: SAFE", result)

    def test_cta_patch_is_allowlisted_by_vehicle(self):
        source = "<html><body><button>Купить авто</button><p>VIN: X</p></body></html>"
        changed, count = builder.patch_cta(source, "/video/UA-0002.html", {"UA-0002"})
        self.assertEqual(count, 1)
        self.assertIn("Забронировать авто за 500$", changed)
        self.assertIn("VIN: X", changed)
        unchanged, count = builder.patch_cta(source, "/video/UA-0001.html", {"UA-0002"})
        self.assertEqual(count, 0)
        self.assertEqual(unchanged, source)

    def test_normalized_protected_body_is_equal(self):
        before = "<p>VIN: X</p><button>Купить авто</button>"
        after = "<p>VIN: X</p><button>Забронировать авто за 500$</button>"
        self.assertEqual(builder.normalize_allowed_body(before), builder.normalize_allowed_body(after))

    def test_diagnostic_link_is_added_only_for_verified_page(self):
        source = "<html><body><a class='dejstvie kn_kupit'>Купить авто</a></body></html>"
        changed, count = builder.ensure_diagnostic_link(source, "/video/UA-0009.html", {"UA-0009"})
        self.assertEqual(count, 1)
        self.assertIn('href="UA-0009-diag.html"', changed)
        unchanged, count = builder.ensure_diagnostic_link(source, "/video/UA-0009.html", set())
        self.assertEqual(count, 0)
        self.assertEqual(unchanged, source)

    def test_builder_is_deterministic_for_same_input(self):
        source = "<html><head><title>A</title></head><body><h1>A</h1></body></html>"
        first = builder.insert_head(source, "/video/info.html", "https://www.uaart.com.ua")
        second = builder.insert_head(source, "/video/info.html", "https://www.uaart.com.ua")
        self.assertEqual(first.encode(), second.encode())


if __name__ == "__main__":
    unittest.main()
