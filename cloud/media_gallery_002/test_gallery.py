"""Regression tests against the audited renderer, native media contract and migration."""
import ast
from html import escape
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import renderer_expected

from build_candidate import LEGACY, MODULES, build, patch_source, upgrade_card
from media_migration import Tree
from desktop_fixture import render_viewer
from ua_media_gallery import MARKER, assets, photos, poster_url, videos

BASELINE = Path(__file__).with_name('renderer_fixture.py').read_text()


def legacy_viewer(urls):
    return ("<div id='lupa'><img id='bolshoe' src='' alt=''></div><div id='lupaschet'></div>"
            '<script>var kadry=' + json.dumps(urls) + ';var tek=0;' + LEGACY + '</script>')


def photo_rail():
    return ("<div class='lenta'><div class='kadr'><img src='m/1.jpg' alt='Car — фото 1'>"
            "<div class='podpis_kadra'>фото 1</div></div><div class='kadr'>"
            "<img src='m/2.jpg' alt='Car — фото 2'><div class='podpis_kadra'>фото 2</div></div></div>")


def video_rail():
    return ("<div class='lenta'><div class='kadr'><video controls poster='v1.jpg'>"
            "<source src='v1.mp4' type='video/mp4'><a href='v1.mp4'>Открыть</a></video>"
            "<div class='podpis_kadra'>видео 1</div></div><div class='kadr'>"
            "<video controls><source src='v2.mp4' type='video/mp4'></video>"
            "<div class='podpis_kadra'>видео 2</div></div></div>")


def page(viewer=None):
    return ('<html><body><p>VIN price status</p>'+photo_rail()+
            "<div class='schet'>2 фото · листайте вбок</div><h2>Видео</h2>"+video_rail()+
            '<p>Описание — без изменений</p>'+(viewer or legacy_viewer(['1.jpg','2.jpg']))+
            '<footer>Контакты</footer></body></html>')


def payloads(html):
    return [json.loads(html[n.start:n.end].split('>',1)[1].rsplit('</script>',1)[0])
            for n in Tree(html).nodes if n.tag=='script' and n.attrs.get('class')=='um-data']


class RendererTests(unittest.TestCase):
    def test_real_generator_executes_for_future_cards(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('UA-0018.mp4','UA-0018-02.mp4'): Path(folder,name).touch()
            ns = dict(os=os, json=json, time=time, PAPKA_VID=folder,
                      nomer=lambda m:'UA-0018', etap_dlinno=lambda m:('Корея',True),
                      STIL='', CHAT_KNOPKA='', SKRIPT_TG='', USPEH_BLOK='',
                      ekran=escape, cena=lambda m:'Цена 10000', shapka=lambda:'',
                      podval=lambda v:'', v_bota=lambda v:'https://example.com/'+v,
                      _ua_delivery_stage_anchor=lambda m:'<aside>Корея</aside>',
                      zastavka=lambda f:' poster="'+f+'.poster.jpg"')
            self.assertEqual(patch_source(BASELINE), Path(__file__).with_name('renderer_expected.py').read_text())
            with patch.multiple(renderer_expected, create=True, **ns):
                result=renderer_expected.sobrat_kartochku({'brand':'Kia','model':'K5','year':2021,
                    'vin':'TEST-VIN'},['1.jpg','2.jpg'],['m/1.jpg','m/2.jpg'])
            photo, video=payloads(result)
            self.assertEqual([i['src'] for i in photo],['1.jpg','2.jpg'])
            self.assertEqual([i['src'] for i in video],['UA-0018.mp4','UA-0018-02.mp4'])
            self.assertEqual(video[1]['preview'],'UA-0018-02.mp4.poster.jpg')
            self.assertIn('TEST-VIN',result)
            self.assertIn('<aside>Корея</aside>',result)
            self.assertEqual(result.count('<!--'+MARKER+'-->'),1)
            self.assertNotIn("class='lenta'",result)

    def test_diagnostics_and_later_wrappers_unchanged(self):
        diagnostic=BASELINE.replace('def sobrat_kartochku','def sobrat_diagnostiku',1)
        wrapper='\ndef sobrat_kartochku(m,kadry,sredn=None):\n    return original(m,kadry,sredn)\n'
        result=patch_source(diagnostic+BASELINE+wrapper)
        self.assertTrue(result.startswith(diagnostic))
        self.assertTrue(result.endswith(wrapper))

    def test_desktop_release_source_supported(self):
        fn=next(n for n in ast.parse(BASELINE).body if isinstance(n,ast.FunctionDef))
        old=next(n for n in fn.body if isinstance(n,ast.If) and any(
            isinstance(c,ast.Constant) and c.value==LEGACY for c in ast.walk(n)))
        lines=BASELINE.splitlines(keepends=True)
        lines[old.lineno-1:old.end_lineno]=['    if kadry:\n        from ua_gallery import render_viewer\n        c.append(render_viewer(kadry))\n']
        self.assertIn('c.append(assets())',patch_source(''.join(lines)))

    def test_extra_photo_side_effect_not_deleted(self):
        changed=BASELINE.replace("        c.append(\"<div class='lenta'>\")", "        audit()\n        c.append(\"<div class='lenta'>\")",1)
        with self.assertRaisesRegex(ValueError,'PHOTO_BLOCK_DRIFT'): patch_source(changed)

    def test_extra_video_side_effect_not_deleted(self):
        with self.assertRaisesRegex(ValueError,'VIDEO_BLOCK_DRIFT'):
            patch_source(BASELINE.replace('    if video_est:', '    if video_est:\n        audit()'))

    def test_ambiguous_renderer_rejected(self):
        with self.assertRaisesRegex(ValueError,'FUNCTION_ANCHOR'): patch_source(BASELINE+BASELINE)

    def test_runtime_bundle_self_contained(self):
        result=build({'stranica.py':BASELINE.encode()})
        self.assertEqual(set(result),{'stranica.py',*MODULES})
        for name, raw in result.items(): compile(raw,name,'exec')

    def test_separate_photo_video_order_and_one_player(self):
        html=photos(['2.jpg','1.jpg'],['m/2.jpg','m/1.jpg'],'Car')+videos(['2.mp4','1.mp4'],['p.jpg',''])
        one,two=payloads(html)
        self.assertEqual([x['src'] for x in one],['2.jpg','1.jpg'])
        self.assertEqual([x['src'] for x in two],['2.mp4','1.mp4'])
        self.assertEqual(html.count('<video '),1)
        self.assertNotIn('autoplay',html)
        self.assertIn('preload="none"',html)

    def test_unsafe_urls_rejected(self):
        for url in ('javascript:alert(1)','data:text/html,test','//external/x','https://user:password@host/x','x\nfoo'):
            with self.subTest(url=url),self.assertRaises(ValueError): photos([url],['m.jpg'])

    def test_json_and_attributes_cannot_inject_markup(self):
        html=photos(['a</script><script>x</script>'],['m".jpg'],'"><script>x</script>')
        self.assertEqual(html.count('</script>'),1)
        self.assertNotIn('<script>x',html)
        self.assertEqual(payloads(html)[0][0]['src'],'a</script><script>x</script>')

    def test_empty_single_and_mismatched_inputs(self):
        self.assertEqual(photos([],[]),'')
        self.assertEqual(videos([],[]),'')
        for node in Tree(photos(['1.jpg'],['m.jpg'])).nodes:
            if set(node.attrs.get('class','').split()) & {'um-prev','um-next'}:
                self.assertIn('hidden',node.attrs)
        with self.assertRaises(ValueError): photos(['1.jpg'],[])
        with self.assertRaises(ValueError): videos(['1.mp4'],[])

    def test_poster_attribute_decoded(self):
        self.assertEqual(poster_url(' poster="a&amp;b.jpg"'),'a&b.jpg')
        self.assertEqual(poster_url(''),'')

    def test_tabs_have_consistent_selection_and_panel(self):
        tree=Tree(photos(['1.jpg','2.jpg'],['m1.jpg','m2.jpg']))
        tabs=[n for n in tree.nodes if n.attrs.get('role')=='tab']
        panel=next(n for n in tree.nodes if n.attrs.get('role')=='tabpanel')
        self.assertEqual([n.attrs['aria-selected'] for n in tabs],['true','false'])
        self.assertEqual([n.attrs['tabindex'] for n in tabs],['0','-1'])
        self.assertTrue(all(n.attrs['aria-controls']==panel.attrs['id'] for n in tabs))
        self.assertEqual(panel.attrs['aria-labelledby'],tabs[0].attrs['id'])


class MigrationTests(unittest.TestCase):
    def test_media_and_unrelated_sections_preserved(self):
        result=upgrade_card(page())
        self.assertIn('<p>VIN price status</p>',result)
        self.assertIn('<p>Описание — без изменений</p>',result)
        self.assertTrue(result.endswith('<footer>Контакты</footer></body></html>'))
        p,v=payloads(result)
        self.assertEqual([x['src'] for x in p],['1.jpg','2.jpg'])
        self.assertEqual([x['src'] for x in v],['v1.mp4','v2.mp4'])
        self.assertEqual(v[0]['preview'],'v1.jpg')
        self.assertNotIn('листайте вбок',result)

    def test_desktop_markup_has_no_duplicate_controls(self):
        result=upgrade_card(page(render_viewer(['1.jpg','2.jpg'])))
        self.assertNotIn('<!--ua-gallery-desktop-v1-->',result)
        self.assertEqual(result.count('<!--'+MARKER+'-->'),1)

    def test_unknown_viewer_not_silently_removed(self):
        with self.assertRaisesRegex(ValueError,'VIEWER_DRIFT'):
            upgrade_card(page().replace('var x0=null;','var x0=2;'))

    def test_migration_idempotent(self):
        result=upgrade_card(page())
        self.assertEqual(upgrade_card(result),result)

    def test_original_photo_count_must_match(self):
        with self.assertRaisesRegex(ValueError,'PHOTO_COUNT'): upgrade_card(page(legacy_viewer(['1.jpg'])))

    def test_duplicate_photo_rail_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_RAIL'):
            upgrade_card(page().replace('<h2>Видео</h2>',photo_rail()))

    def test_video_without_photos_supported(self):
        result=upgrade_card('<html><body>'+video_rail()+'</body></html>')
        self.assertEqual(len(payloads(result)),1)
        self.assertIn('data-ua-media="video"',result)

    def test_empty_card_remains_usable(self):
        old='<html><body><p>Фотографии готовятся</p></body></html>'
        self.assertEqual(upgrade_card(old),old.replace('</body>',assets()+'</body>'))

    def test_unknown_video_formats_not_discarded(self):
        with self.assertRaisesRegex(ValueError,'VIDEO_CONTRACT'):
            upgrade_card('<html><body>'+video_rail().replace('<video controls>', '<video controls><track src="captions.vtt">')+'</body></html>')


if __name__ == '__main__':
    unittest.main()
