"""PS-A08: zero public cars is a bounded valid inventory, never stale HTML.

Source composition is stubbed explicitly; the real canonical HTML builder and
migrators execute. No private input, production database, browser or installer.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "task088_price_sync"))
import install_package as engine
from initial_html_prices import migrate_catalog, migrate_home


HOME = "<!doctype html><html><body>" + "".join(
    '<a class="stage-card" data-stage="' + stage + '" href="katalog.html?f=' + stage + '">0</a>'
    for stage in ("kiev", "georgia", "sea", "korea")) + '<a class="outline-cta" href="katalog.html">Catalog</a></body></html>'
CATALOG = '<!doctype html><html><body><main class="catalog-grid"></main><p>No public cars</p></body></html>'


class EmptyCandidateCompositionTests(unittest.TestCase):
    def test_zero_published_cars_compose_only_four_unchanged_inventory_pages(self):
        sources = {name: b"# TEST explicitly stubbed source composition\n" for name in engine.SOURCES}
        modules = {name: b"# TEST runtime module bytes only\n" for name in engine.MODULES}
        pages = {root + "/" + name: body.encode() for root in ("site", "video")
                 for name, body in (("index.html", HOME), ("katalog.html", CATALOG))}
        # Hidden CRM rows do not create public pages, including when last car is hidden.
        rows = [{"id": 1, "auto_number": "UA-0001", "published": 0, "status": "sold"}]
        # Counter-source patching is independently tested with exact private
        # source pins; this case isolates empty HTML/identity composition.
        with patch.object(engine, "build_source_candidates", return_value=sources), patch.object(
                engine, "migrate_counter_client_candidate", side_effect=lambda name, value, *args: (value, {})):
            candidate = engine.build_candidates(sources, pages, rows, modules, dependency_files={})
        self.assertEqual(set(candidate), engine.SOURCES | engine.MODULES | set(pages))
        for name, original in pages.items():
            self.assertEqual(candidate[name], original)
        _, catalog_proof = migrate_catalog(CATALOG, [])
        _, home_proof = migrate_home(HOME, [])
        self.assertEqual(catalog_proof["cards"], [])
        self.assertEqual(catalog_proof["price_regions_changed"], 0)
        self.assertEqual(home_proof["published_count"], 0)

    def test_zero_catalog_refuses_retained_public_card(self):
        stale = CATALOG.replace("</main>", '<article class="catalog-card"><a href="UA-0001.html">Car</a></article></main>')
        with self.assertRaisesRegex(ValueError, "INITIAL_EMPTY_CATALOG_CAR_SURFACE"):
            migrate_catalog(stale, [])

    def test_zero_catalog_refuses_car_link_outside_article(self):
        stale = CATALOG.replace("</main>", '<a href="/video/UA-0001.html">Car</a></main>')
        with self.assertRaisesRegex(ValueError, "INITIAL_EMPTY_CATALOG_CAR_SURFACE"):
            migrate_catalog(stale, [])

    def test_zero_home_refuses_car_projection(self):
        stale = HOME.replace("</body>", '<a href="UA-0001.html">Car</a></body>')
        with self.assertRaisesRegex(ValueError, "INITIAL_HOME_CAR_PRICE_SURFACE_REQUIRES_MIGRATION"):
            migrate_home(stale, [])

    def test_zero_home_still_requires_exact_known_stage_topology(self):
        stale = HOME.replace('data-stage="kiev"', 'data-stage="unknown"')
        with self.assertRaisesRegex(ValueError, "INITIAL_HOME_STAGE_TOPOLOGY_UNKNOWN"):
            migrate_home(stale, [])


if __name__ == "__main__":
    unittest.main()
