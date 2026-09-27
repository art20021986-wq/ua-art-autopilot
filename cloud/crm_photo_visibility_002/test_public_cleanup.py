"""Keep gallery indexes aligned and preserve all unrelated catalog cards."""
import json
import unittest
from public_cleanup import cleanup_primary, cleanup_catalog, class_spans


def primary():
    frames = ''.join("<div class='kadr'><img src='foto/UA-0023/m/%03d.jpg' loading='%s' alt='фото %d'><div class='podpis_kadra'>фото %d</div></div>" %
                     (i,'eager' if i==1 else 'lazy',i,i) for i in range(1,39))
    return ("<html><head><meta property='og:image' content='foto/UA-0023/001.jpg'></head><body><div class='lenta'>"+frames+
            "</div><div class='schet'>38 фото · листайте вбок</div><p>VIN KNAG541BBNA169806 · 20500 $ · 109353 км</p><script>var kadry="+
            json.dumps(['foto/UA-0023/%03d.jpg'%i for i in range(1,39)])+";</script></body></html>")


class PublicCleanupTests(unittest.TestCase):
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
