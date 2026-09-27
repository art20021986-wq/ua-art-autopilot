"""Preserve media data and page content while fixing current and saved card layouts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_candidate as build
import deployment_remote as remote
from previous_media_styles import CSS as PREVIOUS_CSS
from ua_media_styles import CSS
from ua_media_gallery import assets, photos, videos


class FinalGalleryTests(unittest.TestCase):
    def sources(self):
        return {'stranica.py': b'def sobrat_kartochku():\n    from ua_media_gallery import photos\n',
                **{name: Path(__file__).with_name('previous_media_styles.py' if name=='ua_media_styles.py' else name).read_bytes()
                   for name in build.ASSET_NAMES}}

    def current_page(self):
        return ('<body><header>VIN PRICE</header>'+photos(['1.jpg','2.jpg'],['m/1.jpg','m/2.jpg'])+
                videos(['v1.mp4','v2.mp4'],['p1.jpg','p2.jpg'])+assets()+'<footer>CONTACTS</footer></body>')

    def test_only_existing_style_module_is_changed(self):
        result=build.build(self.sources())
        self.assertEqual(set(result),{'ua_media_styles.py'})
        self.assertEqual(build.MODULES,())
        compile(result['ua_media_styles.py'],'ua_media_styles.py','exec')

    def test_unknown_installed_assets_are_rejected(self):
        for name in build.ASSET_NAMES:
            with self.subTest(name=name):
                sources=self.sources(); sources[name]+=b'\n'
                with self.assertRaisesRegex(ValueError,'INSTALLED_MEDIA_ASSET_MISMATCH'):
                    build.build(sources)

    def test_generator_must_already_use_shared_gallery(self):
        sources=self.sources(); sources['stranica.py']=b'def sobrat_kartochku():\n    pass\n'
        with self.assertRaisesRegex(ValueError,'MEDIA_RENDERER_NOT_INSTALLED'):
            build.build(sources)

    def test_current_card_changes_exact_style_block_only(self):
        expected=self.current_page()
        before=expected.replace('<style>'+CSS+'</style>','<style>'+PREVIOUS_CSS+'</style>')
        self.assertEqual(build.upgrade_card(before),expected)

    def test_idempotence_and_unknown_styles(self):
        current=self.current_page()
        self.assertEqual(build.upgrade_card(current),current)
        with self.assertRaisesRegex(ValueError,'MEDIA_STYLE_DRIFT'):
            build.upgrade_card(current.replace(CSS,'unknown style'))
        with self.assertRaisesRegex(ValueError,'MEDIA_ASSET_MARKER_DRIFT'):
            build.upgrade_card(current+assets())

    def test_saved_legacy_card_gets_same_new_gallery(self):
        rail="<div class='lenta'><div class='kadr'><img src='m/1.jpg' alt='Car — фото 1'></div></div>"
        viewer=("<div id='lupa'><img id='bolshoe' src='' alt=''></div><div id='lupaschet'></div>"+
                '<script>var kadry='+json.dumps(['1.jpg'])+';var tek=0;'+build.LEGACY+'</script>')
        source='<body><header>VIN PRICE</header>'+rail+viewer+'<footer>CONTACTS</footer></body>'
        result=build.upgrade_card(source)
        self.assertTrue(result.startswith('<body><header>VIN PRICE</header>'))
        self.assertTrue(result.endswith('<footer>CONTACTS</footer></body>'))
        self.assertIn('"src":"1.jpg","preview":"m/1.jpg"',result)
        self.assertIn(assets(),result)
        self.assertNotIn("id='lupa'",result)

    def test_inventory_includes_canonical_and_saved_cards_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            names=('video/UA-0023.html','site/UA-0023.html','video/UA-0023-956711ae.html',
                   'site/UA-0023-956711ae.html','video/UA-0023-diag.html','video/katalog.html',
                   'video/UA-0023-956711ae.txt')
            for name in names:
                path=root/name; path.parent.mkdir(exist_ok=True); path.write_text('preserve')
            with patch.object(remote,'ROOT',root):
                self.assertEqual(remote.gallery_paths(),sorted(names[:4]))


if __name__=='__main__':
    unittest.main()
