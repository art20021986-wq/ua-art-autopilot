"""Keep gallery indexes aligned and preserve all unrelated catalog cards."""
import json
import unittest
from public_cleanup import cleanup_primary, cleanup_catalog, cleanup_page, class_spans, gallery_match


def primary():
    frames = ''.join("<div class='kadr'><img src='foto/UA-0023/m/%03d.jpg' loading='%s' alt='фото %d'><div class='podpis_kadra'>фото %d</div></div>" %
                     (i,'eager' if i==1 else 'lazy',i,i) for i in range(1,39))
    return ("<html><head><meta property='og:image' content='foto/UA-0023/001.jpg'></head><body><div class='lenta'>"+frames+
            "</div><div class='schet'>38 фото · листайте вбок</div><p>VIN KNAG541BBNA169806 · 20500 $ · 109353 км</p><script>var kadry="+
            json.dumps(['foto/UA-0023/%03d.jpg'%i for i in range(1,39)])+";</script></body></html>")


class PublicCleanupTests(unittest.TestCase):
    def test_desktop_viewer_keeps_controls_and_updates_only_its_sources(self):
        source=primary()
        original=gallery_match(source)
        viewer='<!--ua-gallery-desktop-v1--><script>(function(sources){ const controls="UNCHANGED"; })('+original.group(1)+');</script>'
        begin=source.index('<script>');end=source.index('</script>',begin)+len('</script>')
        source=source[:begin]+viewer+source[end:]
        result=cleanup_primary(source)
        self.assertNotIn('001.jpg',result)
        self.assertEqual(len(json.loads(gallery_match(result).group(1))),37)
        self.assertIn('const controls="UNCHANGED";',result)

    def test_hidden_middle_and_last_preserve_cover_and_renumber_remaining(self):
        source=primary().replace('UA-0023','UA-0017')
        value=cleanup_primary(source,'UA-0017',('017.jpg','038.jpg'),38)
        self.assertNotIn('017.jpg',value)
        self.assertNotIn('038.jpg',value)
        self.assertIn("content='foto/UA-0017/001.jpg'",value)
        self.assertIn("m/018.jpg' loading='lazy' alt='фото 17'",value)
        self.assertEqual(len(class_spans(value,'kadr')),36)

    def test_catalog_hidden_last_changes_counts_without_changing_cover(self):
        source="<article><a href='UA-0017.html'><img src='foto/UA-0017/m/001.jpg'><span>40 фото</span></a><p>VIN TESTVIN17</p><p>Фото: 40</p></article>"
        self.assertEqual(cleanup_catalog(source,'UA-0017','TESTVIN17',('040.jpg',),40,'001.jpg'),
                         source.replace('40 фото','39 фото').replace('Фото: 40','Фото: 39'))

    def test_page_dispatch_handles_alias_and_preserves_unrelated_diagnostic(self):
        cards={'UA-0023':{'vin':'KNAG541BBNA169806','hidden':['001.jpg'],'before_count':38,'cover':'002.jpg'}}
        self.assertEqual(cleanup_page(primary(),'video/UA-0023-956711ae.html',cards),cleanup_primary(primary()))
        self.assertEqual(cleanup_page('<html>Diagnostics unchanged</html>','video/UA-0023-diag.html',cards),'<html>Diagnostics unchanged</html>')

    def test_primary_keeps_photo_order_and_aligned_lightbox(self):
        value=cleanup_primary(primary())
        self.assertNotIn('001.jpg',value)
        self.assertEqual(len(class_spans(value,'kadr')),37)
        self.assertIn("src='foto/UA-0023/m/002.jpg' loading='eager' alt='фото 1'",value)
        self.assertIn("m/038.jpg' loading='lazy' alt='фото 37'",value)
        self.assertIn('var kadry=["foto/UA-0023/002.jpg"',value)
        self.assertIn('20500 $ · 109353 км',value)

    def test_primary_drift_stops_instead_of_guessing(self):
        for text in (primary().replace('m/002.jpg','m/009.jpg'),
                     primary().replace("<div class='schet'>38", "<div class='schet'>39")):
            with self.assertRaises(ValueError): cleanup_primary(text)

    def test_catalog_changes_only_target_cover_and_both_counts(self):
        neighbor="<article>UA-0022<img src='foto/UA-0022/001.jpg'><span>38 фото</span><p>Фото: 38</p></article>"
        card="<article><a href='UA-0023.html'><img src='foto/UA-0023/m/001.jpg'><span>38 фото</span></a><p>VIN KNAG541BBNA169806</p><p>Фото: 38</p></article>"
        original='<main>'+neighbor+card+neighbor+'</main>'
        expected='<main>'+neighbor+card.replace('001.jpg','002.jpg').replace('38 фото','37 фото').replace('Фото: 38','Фото: 37')+neighbor+'</main>'
        self.assertEqual(cleanup_catalog(original),expected)


if __name__=='__main__': unittest.main()
