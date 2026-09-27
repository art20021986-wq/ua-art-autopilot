"""Regression checks for CRM-hidden sources leaking into public selection."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from candidate_builder import CHANGES, patch_function
from photo_visibility import visible_names


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card = {'auto_number': 'UA-0023', 'hidden_photos': '["technical"]'}
        self.mapping = {'001.jpg': 'technical', '002.jpg': 'car-front', '003.jpg': 'car-rear'}
        self.write_ledger()

    def write_ledger(self):
        (self.root/'.video_sinhron.json').write_text(json.dumps({'foto:UA-0023': self.mapping}))

    def select(self, names=None):
        return visible_names(self.card, names if names is not None else list(self.mapping), self.root)

    def test_technical_first_photo_is_removed_without_renumbering(self):
        self.assertEqual(self.select(), ['002.jpg', '003.jpg'])

    def test_all_copies_of_hidden_identity_are_excluded(self):
        self.mapping['004.jpg'] = 'technical'
        self.write_ledger()
        self.assertEqual(self.select(), ['002.jpg', '003.jpg'])

    def test_existing_order_is_preserved(self):
        self.assertEqual(self.select(['003.jpg', '001.jpg', '002.jpg']), ['003.jpg', '002.jpg'])

    def test_no_hidden_photos_preserve_legacy_gallery_without_ledger(self):
        for hidden in (None, '', '[]', []):
            with self.subTest(hidden=hidden):
                self.assertEqual(visible_names({'hidden_photos': hidden}, ['legacy.webp'], self.root/'absent'), ['legacy.webp'])

    def test_all_hidden_returns_no_public_photo(self):
        self.card['hidden_photos'] = list(self.mapping.values())
        self.assertEqual(self.select(), [])

    def test_missing_binding_fails_instead_of_exposing_unknown_photo(self):
        with self.assertRaises(ValueError):
            self.select(['001.jpg', '099.jpg'])

    def test_malformed_visibility_fails_closed(self):
        for bad in ('{', '{}', [None], [3], ['']):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                visible_names({'hidden_photos': bad}, ['001.jpg'], self.root)

    def test_missing_car_mapping_fails_closed(self):
        self.card['auto_number'] = 'UA-9999'
        with self.assertRaises(ValueError):
            self.select()

    def test_hidden_record_is_retained_in_archive(self):
        before = (self.root/'.video_sinhron.json').read_bytes()
        self.select()
        self.assertEqual((self.root/'.video_sinhron.json').read_bytes(), before)
        self.assertEqual(json.loads(self.card['hidden_photos']), ['technical'])

    def test_unsafe_filename_rejected(self):
        with self.assertRaises(ValueError):
            self.select(['../001.jpg'])

    def load_function(self, filename, text):
        path = self.root/filename
        path.write_text(text)
        spec = importlib.util.spec_from_file_location(filename[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_both_renderer_selections_use_visibility_before_cover_ordering(self):
        gallery = '''import os
def kadry_mashiny(m):
    puti = ['foto/UA-0023/001.jpg', 'foto/UA-0023/002.jpg']
    # первым — первый горизонтальный кадр
    return puti
'''
        cover = '''import os
def vybrat_glavnoe(kod, m=None):
    fajly = ['001.jpg', '002.jpg']
    cover = os.path.basename((m.get("cover_photo") or "").strip()) if m else ""
    return cover if cover in fajly else fajly[0]
'''
        card = dict(self.card, cover_photo='001.jpg')
        original_gallery = self.load_function('old_gallery.py', gallery)
        original_cover = self.load_function('old_cover.py', cover)
        self.assertIn('foto/UA-0023/001.jpg', original_gallery.kadry_mashiny(card))
        self.assertEqual(original_cover.vybrat_glavnoe('UA-0023', card), '001.jpg')
        fixed_gallery = self.load_function('new_gallery.py', patch_function(gallery, *CHANGES['stranica.py']))
        fixed_cover = self.load_function('new_cover.py', patch_function(cover, *CHANGES['master_card.py']))
        with patch('photo_visibility.visible_names', side_effect=lambda c,n: visible_names(c,n,self.root)):
            self.assertEqual(fixed_gallery.kadry_mashiny(card), ['foto/UA-0023/002.jpg'])
            self.assertEqual(fixed_cover.vybrat_glavnoe('UA-0023', card), '002.jpg')
            card['hidden_photos'] = ['technical', 'car-front']
            self.assertEqual(fixed_gallery.kadry_mashiny(card), [])
            with self.assertRaisesRegex(ValueError, 'No visible photo'):
                fixed_cover.vybrat_glavnoe('UA-0023', card)

    def test_source_anchor_drift_is_rejected(self):
        with self.assertRaises(ValueError):
            patch_function('def other():\n    pass\n', *CHANGES['stranica.py'])


if __name__ == '__main__':
    unittest.main()
