from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("task074_installer", ROOT / "installer.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MOD)


def source_fixture() -> str:
    return '''# UA-CARDS-FERRY-VIN-001-V1.1-PERMANENT
def _ua068_eta(row, stage):
    return (
        "Автомобиль на пароме: Корея → Грузия.",
        "Автомобіль на поромі: Корея → Грузія.",
        "Автомобиль на пароме · количество дней до Киева уточняется.",
        "Автомобіль на поромі · кількість днів до Києва уточнюється.",
    )
def _ua068_ensure_catalog(source, rows):
    css = """<style id="ua-cat-vin-v1-style">.ua-cat-vin-v1{background:red}</style>"""
    return source
def _ua068_card_errors(source, kod, row):
    return []
'''


def catalog_fixture() -> str:
    cards = []
    for number in range(1, 12):
        identifier = f"UA-{number:04d}"
        stage = "sea" if number >= 5 else "kiev"
        status = (
            '<div class="status-pill" data-ru="На пароме&#10;Маршрут: Корея → Грузия">'
            'На пароме&#10;Маршрут: Корея → Грузия</div>'
            if stage == "sea" else '<div class="status-pill">В Киеве</div>'
        )
        cards.append(
            f'<article class="catalog-card" data-stage="{stage}"><div class="catalog-body">'
            f'{status}</div>{MOD.CAT_START}<div class="ua-cat-vin-v1" data-ua-card="{identifier}">'
            '<span class="ua068-ru">11 дн. до Киева · ориентировочно 9 сентября 2026. '
            f'{MOD.RU_DUPLICATE}</span><span class="ua068-uk">11 дн. до Києва · орієнтовно 9 вересня 2026. '
            f'{MOD.UK_DUPLICATE}</span></div>{MOD.CAT_END}</article>'
        )
    return '<!doctype html><html><head><title>x</title></head><body>' + "".join(cards) + '</body></html>'


class InstallerTests(unittest.TestCase):
    def test_source_patch_is_exact_and_idempotent(self):
        before = source_fixture()
        after = MOD.patch_eta_source(before)
        self.assertIn(MOD.SOURCE_MARKER, after)
        self.assertIn(MOD.STYLE_MARKER, after)
        self.assertNotIn(MOD.RU_DUPLICATE, after)
        self.assertNotIn(MOD.UK_DUPLICATE, after)
        self.assertIn(MOD.RU_UNKNOWN_NEW, after)
        self.assertIn(MOD.UK_UNKNOWN_NEW, after)
        self.assertEqual(MOD.patch_eta_source(after), after)

    def test_catalog_removes_only_duplicate_and_adds_joined_style(self):
        before = catalog_fixture()
        after = MOD.patch_catalog(before)
        result = MOD.validate_catalog(after)
        self.assertEqual(result["card_count"], 11)
        self.assertIn("UA-0009", result["identifiers"])
        self.assertNotIn(MOD.RU_DUPLICATE, after)
        self.assertNotIn(MOD.UK_DUPLICATE, after)
        self.assertIn("11 дн. до Киева", after)
        self.assertIn("На пароме&#10;Маршрут: Корея → Грузия", after)
        self.assertEqual(after.count(MOD.STYLE_MARKER), 1)
        self.assertEqual(
            MOD.semantic_catalog_without_task074(after),
            MOD.semantic_catalog_without_task074(before),
        )

    def test_catalog_patch_is_idempotent(self):
        once = MOD.patch_catalog(catalog_fixture())
        twice = MOD.patch_catalog(once)
        self.assertEqual(once, twice)

    def test_ferry_status_accepts_encoded_route_arrow(self):
        source = (
            '<article class="catalog-card" data-stage="sea">'
            '<span class="status-pill">НА&nbsp;ПАРОМЕ</span>'
            + MOD.CAT_START + '<div data-ua-card="UA-0009">'
            + MOD.RU_DUPLICATE + '</div>' + MOD.CAT_END + '</article>'
        )
        self.assertTrue(MOD.ferry_status_present(source))

    def test_ferry_status_does_not_depend_on_card_tag_or_stage_attribute(self):
        source = (
            '<section class="vehicle"><div class="green-stage">На пароме</div>'
            + MOD.CAT_START + '<div data-ua-card="UA-0009">eta</div>'
            + MOD.CAT_END + '</section>'
        )
        self.assertTrue(MOD.ferry_status_present(source))

    def test_unknown_eta_keeps_timing_information_without_stage_duplicate(self):
        block = (
            MOD.CAT_START + '<div data-ua-card="UA-0009">' + MOD.RU_UNKNOWN_OLD
            + ' ' + MOD.UK_UNKNOWN_OLD + '</div>' + MOD.CAT_END
        )
        fixed = MOD.patch_catalog_block(block)
        self.assertIn(MOD.RU_UNKNOWN_NEW, fixed)
        self.assertIn(MOD.UK_UNKNOWN_NEW, fixed)
        self.assertNotIn("Автомобиль на пароме", fixed)
        self.assertNotIn("Автомобіль на поромі", fixed)


if __name__ == "__main__":
    unittest.main()
