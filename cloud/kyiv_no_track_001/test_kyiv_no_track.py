"""KYIV-NO-TRACK-001: the generator edit on the live generator copies, rendered before/after for every stage."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'container_tracking_001'))  # ua_tracking_widget, as installed

import candidate_builder
import edit_generators
import edit_metadata
import orphan_pages
import stage_preview

FIXTURES = HERE.parent / 'card_lead_001' / 'fixtures'
GENERATORS = {'stranica.py': HERE / 'fixtures' / 'stranica_stage.txt',
              'master_card.py': HERE / 'fixtures' / 'master_card_stage.txt'}


def car(code, status, container=None, **extra):
    return {'auto_number': code, 'status': status, 'sea_container': container, **extra}


ROWS = [car('UA-0001', 'ua_ready'), car('UA-0011', 'ua_ready', 'ONEYSELGB4471700'),
        car('UA-0005', 'sea_way', 'ONEYSELGF1046602', sea_date_out='2026-10-01'),
        car('UA-0021', 'ge_waiting', 'FBLU0045137'), car('UA-0003', 'kr_parking'),
        car('UA-0030', 'ua_ready', 'FBLU0045137', sea_date_out='2026-09-01')]


class GeneratorEditTests(unittest.TestCase):
    def test_every_generator_applies_once_and_compiles(self):
        for name, path in GENERATORS.items():
            source = path.read_bytes()
            self.assertTrue(edit_generators.has_hook(source))
            after = edit_generators.build(name, source)
            self.assertIn(edit_generators.NEW.encode(), after)
            self.assertNotIn(edit_generators.OLD.encode(), after)
            self.assertEqual(len(after) - len(source), len(edit_generators.NEW.encode()) - len(edit_generators.OLD.encode()))
            with self.assertRaisesRegex(ValueError, 'TRACKING_HOOK_NOT_UNIQUE'):
                edit_generators.build(name, after)

    def test_changed_hook_is_refused(self):
        source = GENERATORS['stranica.py'].read_bytes().replace(b'out.append(render_tracking(', b'out.append(render_tracking2(')
        with self.assertRaisesRegex(ValueError, 'TRACKING_HOOK_NOT_UNIQUE'):
            edit_generators.build('stranica.py', source)

    def test_unknown_file_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'GENERATOR_NAME'):
            edit_generators.build('cars_ui.py', b'')

    def test_kyiv_block_loses_only_tracking(self):
        for name, path in GENERATORS.items():
            source = path.read_text(encoding='utf-8')
            after = edit_generators.build(name, source.encode()).decode()
            value = stage_preview.compare(source, after, ROWS)
            self.assertEqual(value['problems'], {}, name)
            cars = value['cars']
            self.assertEqual((cars['UA-0011']['before'], cars['UA-0011']['after']), ('button', 'none'))
            self.assertEqual((cars['UA-0001']['before'], cars['UA-0001']['after']), ('message', 'none'))
            self.assertEqual(cars['UA-0005'], {'stage': 2, 'before': 'button', 'after': 'button'})
            self.assertEqual(cars['UA-0021'], {'stage': 3, 'before': 'button', 'after': 'button'})
            self.assertEqual(cars['UA-0003'], {'stage': 1, 'before': 'message', 'after': 'message'})
            self.assertEqual(value['kyiv_changed'], ['UA-0001', 'UA-0011', 'UA-0030'])
            self.assertEqual(value['unchanged'], 3)

    def test_kyiv_shipping_date_stays(self):
        source = GENERATORS['stranica.py'].read_text(encoding='utf-8')
        after = edit_generators.build('stranica.py', source.encode()).decode()
        block = stage_preview.renderer(after)(ROWS[-1])
        self.assertIn('Отправлен: <b>1 сентября 2026</b>', block)
        self.assertNotIn('ua-multi-track', block)
        empty = stage_preview.renderer(after)(ROWS[0])
        self.assertNotIn('ua-stage-v1-meta"', empty)
        self.assertIn('Автомобиль в Киеве — можно приехать на осмотр', empty)

    def test_page_state_of_published_card(self):
        page = stage_preview.renderer(GENERATORS['stranica.py'].read_text(encoding='utf-8'))(ROWS[1])
        self.assertEqual(stage_preview.page_state(page), {'stage': 4, 'tracking': 'button'})


class MetadataTests(unittest.TestCase):
    def test_revision_bumped_once(self):
        source = (FIXTURES / 'ua_seo_metadata.txt').read_bytes()
        after = edit_metadata.build(source).decode()
        self.assertIn("SEO_REVISION = 'KYIV-NO-TRACK-001'\n", after)
        self.assertEqual(after.count('SEO_REVISION = '), source.decode().count('SEO_REVISION = '))
        with self.assertRaisesRegex(ValueError, 'METADATA_REVISION'):
            edit_metadata.build(after.encode())


class CandidateTests(unittest.TestCase):
    def test_targets_need_both_main_generators(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'stranica.py').write_bytes(GENERATORS['stranica.py'].read_bytes())
            with self.assertRaisesRegex(ValueError, 'TRACKING_HOOK_MISSING'):
                candidate_builder.targets(root)
            (root / 'master_card.py').write_bytes(GENERATORS['master_card.py'].read_bytes())
            (root / 'yadro.py').write_bytes(b'# no hook\n')
            import sqlite3
            with sqlite3.connect(root / 'crm.db') as connection:
                connection.execute('CREATE TABLE cars(auto_number TEXT)')
            self.assertEqual(candidate_builder.targets(root), ('stranica.py', 'master_card.py', 'ua_seo_metadata.py'))


class OrphanPageTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        page = (HERE / 'fixtures' / 'orphan_kyiv_page.txt').read_bytes()
        for name in ('video/UA-0007.html', 'video/UA-0007-de6e3ebe.html', 'site/UA-0007.html', 'video/UA-0011.html'):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(page)
        (self.root / 'video/UA-0005.html').write_bytes(page.replace(b'data-ua-stage-current="4"', b'data-ua-stage-current="2"'))
        (self.root / 'video/katalog.html').write_bytes(page)

    def test_only_kyiv_pages_of_cars_not_in_crm(self):
        self.assertEqual(orphan_pages.find(self.root, {'UA-0011', 'UA-0012'}),
                         ('video/UA-0007-de6e3ebe.html', 'video/UA-0007.html', 'site/UA-0007.html'))

    def test_build_removes_only_the_tracking(self):
        source = (self.root / 'video/UA-0007.html').read_bytes()
        after = orphan_pages.build(source).decode()
        self.assertEqual(stage_preview.page_state(after), {'stage': 4, 'tracking': 'none'})
        self.assertNotIn('Номер отправки ещё не указан', after)
        self.assertNotIn('<div class="ua-stage-v1-meta"></div>', after)
        self.assertIn('Автомобиль в Киеве — можно приехать на осмотр', after)
        self.assertEqual(after, stage_preview.without_tracking(source.decode()))
        with self.assertRaisesRegex(ValueError, 'ORPHAN_TRACKING_NOT_REMOVED'):
            orphan_pages.build(after.encode())

    def test_not_kyiv_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'ORPHAN_NOT_KYIV'):
            orphan_pages.build((self.root / 'video/UA-0005.html').read_bytes())


if __name__ == '__main__':
    unittest.main()
