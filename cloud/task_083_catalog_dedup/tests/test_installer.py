from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("task083_installer", ROOT / "installer.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MOD)

STAGE_PATH = ROOT.parent / "task_075_stage_guard" / "stage_guard.py"
STAGE_SPEC = importlib.util.spec_from_file_location("task083_stage_guard", STAGE_PATH)
STAGE = importlib.util.module_from_spec(STAGE_SPEC)
assert STAGE_SPEC.loader
sys.modules[STAGE_SPEC.name] = STAGE
STAGE_SPEC.loader.exec_module(STAGE)


def source_fixture() -> str:
    return f'''{MOD.PREVIOUS_SOURCE_MARKER}
# {MOD.STYLE_MARKER}
def _ua068_ensure_catalog(source, rows):
    return source
def _ua068_card_errors(source, kod, row):
    return []
'''


def canonical_card(
    number: int,
    *,
    stage: str,
    stage_number: int,
    status: str,
    engine: str = "2 000 см³",
    video: int = 0,
    media_video: int | None = None,
    copy: str = "11 дн. до Киева · ориентировочно 9 сентября 2026.",
) -> str:
    identifier = f"UA-{number:04d}"
    media = "11 фото" + (
        f" · {media_video} видео" if media_video is not None else ""
    )
    vin = "WDD" + f"{number:014d}"
    return (
        f'<article class="catalog-card" data-stage="{stage}" data-ua-kod="{identifier}">'
        f'<a class="catalog-photo"><span class="photo-count">{media}</span></a>'
        f'<div class="catalog-body"><div class="status-pill">{status}</div>'
        f'<p>100 000 км · {engine} · бензин · автомат</p></div>'
        + MOD.CAT_START
        + f'<div class="ua-cat-vin-v1" data-ua-card="{identifier}" '
          f'data-ua-stage="{stage_number}" data-ua-video-count="{video}">'
        + f'<div class="ua-cat-vin-v1-top"><span>VIN <b>{vin}</b></span>'
          f'<i class="ok">VIN ПРОВЕРЕН</i></div>'
        + f'<div class="ua-cat-vin-v1-spec">Двигатель: <b>{engine}</b> · '
          f'Видео: <b>{video}</b></div>'
        + f'<div class="ua-cat-vin-v1-copy"><span class="ua068-ru">{copy}</span>'
          f'<span class="ua068-uk">{copy}</span></div></div>'
        + MOD.CAT_END
        + "</article>"
    )


def fallback_card() -> str:
    return (
        '<a class="ua-cat-fallback-v1" href="UA-0011.html">'
        '<span>UA-0011 · ЭТАП 2 ИЗ 4</span><strong>Hyundai SONATA 2018</strong>'
        '<span>На пароме · Корея → Грузия</span>'
        + MOD.CAT_START
        + '<div class="ua-cat-vin-v1" data-ua-card="UA-0011" '
          'data-ua-stage="2" data-ua-video-count="0">'
        '<div class="ua-cat-vin-v1-top"><span>VIN <b>KMHE341DBKA544289</b></span>'
        '<i class="ok">VIN ПРОВЕРЕН</i></div>'
        '<div class="ua-cat-vin-v1-spec">Двигатель: <b>2 000 см³</b> · '
        'Видео: <b>0</b></div>'
        '<div class="ua-cat-vin-v1-copy"><span class="ua068-ru">'
        '11 дн. до Киева · ориентировочно 9 сентября 2026. </span>'
        '<span class="ua068-uk">11 дн. до Києва · орієнтовно 9 вересня 2026. '
        '</span></div></div>'
        + MOD.CAT_END
        + '<span>Открыть карточку →</span></a>'
    )


def catalog_fixture() -> str:
    cards = [
        canonical_card(
            1, stage="georgia", stage_number=3,
            status="В Грузии · финальный этап", video=1, media_video=1,
            copy=MOD.RU_GEORGIA_OLD,
        ),
        canonical_card(
            2, stage="kiev", stage_number=4,
            status="В Киеве · можно посмотреть", video=2, media_video=2,
            copy=MOD.RU_KYIV_DUPLICATE,
        ),
        canonical_card(
            3, stage="korea", stage_number=1,
            status="Выкуплен и проверен в Корее", copy=MOD.RU_KOREA_OLD,
        ),
        canonical_card(
            4, stage="sea", stage_number=2,
            status="На пароме Маршрут: Корея → Грузия",
        ),
        canonical_card(
            5, stage="sea", stage_number=2,
            status="На пароме Маршрут: Корея → Грузия",
        ),
        canonical_card(
            6, stage="sea", stage_number=2,
            status="На пароме Маршрут: Корея → Грузия",
        ),
        canonical_card(
            7, stage="kiev", stage_number=4,
            status="В Киеве · можно посмотреть", copy=MOD.RU_KYIV_DUPLICATE,
        ),
        canonical_card(
            8, stage="kiev", stage_number=4,
            status="В Киеве · можно посмотреть", video=2,
            copy=MOD.RU_KYIV_DUPLICATE,
        ),
        canonical_card(
            9, stage="sea", stage_number=2,
            status="На пароме Маршрут: Корея → Грузия",
        ),
        canonical_card(
            10, stage="korea", stage_number=1,
            status="Выкуплен и проверен в Корее", copy=MOD.RU_KOREA_OLD,
        ),
        fallback_card(),
    ]
    return (
        '<!doctype html><html><head><style>/* '
        + MOD.STYLE_MARKER
        + ' */</style></head><body><main data-untouched="yes">'
        + "".join(cards)
        + "</main></body></html>"
    )


def block_for(source: str, identifier: str) -> str:
    for block in MOD.catalog_blocks(source):
        if f'data-ua-card="{identifier}"' in block:
            return block
    raise AssertionError(identifier)


def stage_catalog_fixture() -> str:
    cards = []
    rows = []
    for number in range(1, 12):
        stage = 2 if number in (4, 5, 6, 9, 11) else (4 if number in (2, 7, 8) else 1)
        row = {
            "auto_number": f"UA-{number:04d}",
            "published": 1,
            "status": {1: "korea", 2: "sea_loaded", 4: "ua_ready"}[stage],
            "stage": stage,
            "brand": "Test",
            "model": "Car",
            "year": 2020,
            "vin": "WDD" + f"{number:014d}",
            "mileage_km": 100000,
            "engine_cc": 2000,
            "fuel": "бензин",
            "gearbox": "автомат",
            "photos": '["one.jpg"]',
            "videos": '["one.mp4", "two.mp4"]' if number == 8 else "[]",
            "price": 10000,
        }
        rows.append(row)
        cards.append(STAGE.render_card(row, "https://www.uaart.com.ua/foto/%d.jpg" % number))
    source = (
        "<!doctype html><html><head>" + STAGE.STYLE + "</head><body>"
        + "".join(cards) + "</body></html>"
    )
    return source


class InstallerTests(unittest.TestCase):
    def test_stage_renderer_source_contains_permanent_semantic_guard(self):
        source = STAGE_PATH.read_text(encoding="utf-8")
        MOD.validate_core_source(source)
        self.assertIn(MOD.CORE_MARKER, source)
        self.assertEqual(STAGE.public_media_summary(4, 0), "Фото: 4")
        self.assertEqual(STAGE.public_media_summary(4, 2), "Фото: 4 · Видео: 2")

    def test_stage_v2_cards_are_supported_and_zero_video_is_not_rendered(self):
        source = stage_catalog_fixture()
        analysis = MOD.validate_catalog(source, require_dedup=True)
        self.assertEqual(analysis["mode"], "stage_v2")
        self.assertEqual(analysis["card_count"], 11)
        self.assertNotIn("Видео: 0", source)
        self.assertEqual(source.count("Видео: 2"), 1)
        self.assertEqual(MOD.patch_any_catalog(source), source)
        self.assertTrue(MOD.ferry_status_present(source))

    def test_stage_v2_duplicate_expression_fails_closed(self):
        source = stage_catalog_fixture()
        repeated = (
            '<div class="ua-stage-card-v2-status">'
            '<span class="ua075-ru">На пароме · маршрут — Киев</span>'
            '<span class="ua075-uk">На поромі · маршрут — Київ</span></div>'
        )
        broken = source.replace(
            '<div class="ua-stage-card-v2-status">',
            repeated + '<div class="ua-stage-card-v2-status">',
            1,
        )
        with self.assertRaises(MOD.Blocked):
            MOD.validate_catalog(broken, require_dedup=True)

    def test_generator_patch_is_compilable_idempotent_and_permanent(self):
        before = source_fixture()
        after = MOD.patch_generator_source(before)
        self.assertIn(MOD.SOURCE_MARKER, after)
        self.assertIn("def _ua083_dedup_catalog(", after)
        self.assertIn("def _ua068_ensure_catalog_base(", after)
        self.assertEqual(MOD.patch_generator_source(after), after)
        compile(after, "future-generator.py", "exec")

    def test_generator_wrapper_deduplicates_future_catalogs(self):
        namespace: dict[str, object] = {}
        exec(MOD.patch_generator_source(source_fixture()), namespace)
        rendered = namespace["_ua068_ensure_catalog"](catalog_fixture(), [])
        self.assertEqual(rendered, MOD.patch_catalog(catalog_fixture()))
        MOD.validate_catalog(rendered, require_dedup=True)

    def test_all_current_shapes_are_deduplicated_without_data_loss(self):
        before = catalog_fixture()
        baseline = MOD.validate_catalog(before, require_dedup=False)
        self.assertEqual(baseline["card_count"], 11)
        self.assertTrue(baseline["duplicate_issues"])

        after = MOD.patch_catalog(before)
        result = MOD.validate_catalog(after, require_dedup=True)
        self.assertEqual(result["card_count"], 11)
        self.assertEqual(result["duplicate_issues"], {})
        self.assertIn("UA-0009", result["identifiers"])
        self.assertEqual(MOD.catalog_shell(after), MOD.catalog_shell(before))
        self.assertIn('data-untouched="yes"', after)
        self.assertEqual(after.count("VIN ПРОВЕРЕН"), 11)

        kyiv = block_for(after, "UA-0002")
        self.assertNotIn("ua-cat-vin-v1-spec", kyiv)
        self.assertNotIn("ua-cat-vin-v1-copy", kyiv)

        unique_video = block_for(after, "UA-0008")
        self.assertIn("Видео: <b>2</b>", unique_video)
        self.assertNotIn("Двигатель:", unique_video)

        fallback = block_for(after, "UA-0011")
        self.assertIn("Двигатель: <b>2 000 см³</b>", fallback)
        self.assertNotIn("Видео: <b>0</b>", fallback)
        self.assertIn("11 дн. до Киева", fallback)

        self.assertIn(MOD.RU_GEORGIA_NEW, after)
        self.assertIn(MOD.RU_KOREA_NEW, after)
        self.assertNotIn(MOD.RU_GEORGIA_OLD, after)
        self.assertNotIn(MOD.RU_KOREA_OLD, after)

    def test_catalog_patch_is_idempotent(self):
        once = MOD.patch_catalog(catalog_fixture())
        twice = MOD.patch_catalog(once)
        self.assertEqual(once, twice)

    def test_ukrainian_wording_is_rewritten_too(self):
        block = (
            MOD.CAT_START
            + '<div class="ua-cat-vin-v1" data-ua-card="UA-0009">'
              '<div class="ua-cat-vin-v1-top"><span>VIN '
              '<b>KNAGU416BJA242741</b></span></div>'
              '<div class="ua-cat-vin-v1-copy"><span class="ua068-uk">'
            + MOD.UK_GEORGIA_OLD
            + '</span></div></div>'
            + MOD.CAT_END
        )
        fixed = MOD.patch_catalog_block(block, '<div>В Грузии</div>')
        self.assertIn(MOD.UK_GEORGIA_NEW, fixed)
        self.assertNotIn(MOD.UK_GEORGIA_OLD, fixed)

    def test_ferry_status_is_preserved(self):
        after = MOD.patch_catalog(catalog_fixture())
        self.assertTrue(MOD.ferry_status_present(after))
        self.assertIn("На пароме Маршрут: Корея → Грузия", after)

    def test_vin_or_identifier_loss_fails_closed(self):
        broken_vin = catalog_fixture().replace("KMHE341DBKA544289", "", 1)
        with self.assertRaises(MOD.Blocked):
            MOD.validate_catalog(broken_vin, require_dedup=False)
        duplicate = catalog_fixture().replace(
            'data-ua-card="UA-0010"', 'data-ua-card="UA-0009"', 1
        )
        with self.assertRaises(MOD.Blocked):
            MOD.validate_catalog(duplicate, require_dedup=False)


if __name__ == "__main__":
    unittest.main()
