import unittest
from public_media import verify_photo_structure, visible_photo_ids

class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.card = dict(auto_number='UA-0001', photos=[{'file_id':'a'}, {'file_id':'b'}], hidden_photos=[], cover_photo='001.jpg')
        self.html = '<img src="foto/UA-0001/m/001.jpg"><img src="foto/UA-0001/m/002.jpg"><script>var kadry=["foto/UA-0001/001.jpg","foto/UA-0001/002.jpg"];</script>'
    def test_valid_is_only_structural(self):
        result = verify_photo_structure(self.html, self.card)
        self.assertTrue(result['structure_verified'])
        self.assertFalse(result['full_consistency_accepted'])
        self.assertFalse(result['content_identity_verified'])
    def test_hidden_must_not_count(self):
        self.card['hidden_photos']=['b']
        with self.assertRaisesRegex(RuntimeError,'count'):verify_photo_structure(self.html,self.card)
    def test_ledger_order_required_even_with_equal_count(self):
        with self.assertRaisesRegex(RuntimeError,'ledger order'):
            verify_photo_structure(self.html,self.card,['foto/UA-0001/002.jpg','foto/UA-0001/001.jpg'])
    def test_exact_ledger_order_passes_structure_only(self):
        self.assertFalse(verify_photo_structure(self.html,self.card,['foto/UA-0001/001.jpg','foto/UA-0001/002.jpg'])['full_consistency_accepted'])
    def test_missing_photo(self):
        self.card['photos'].append('c')
        with self.assertRaisesRegex(RuntimeError,'count'):verify_photo_structure(self.html,self.card)
    def test_duplicate_gallery(self):
        with self.assertRaisesRegex(RuntimeError,'Duplicate'):verify_photo_structure(self.html.replace('002.jpg','001.jpg'),self.card)
    def test_wrong_cover(self):
        self.card['cover_photo']='002.jpg'
        with self.assertRaisesRegex(RuntimeError,'cover'):verify_photo_structure(self.html,self.card)
    def test_visible_order(self):
        bad=self.html.replace('m/001.jpg','m/003.jpg')
        with self.assertRaisesRegex(RuntimeError,'order'):verify_photo_structure(bad,self.card)
    def test_foreign_gallery(self):
        with self.assertRaisesRegex(RuntimeError,'foreign'):verify_photo_structure(self.html.replace('UA-0001','UA-0002'),self.card)
    def test_missing_and_duplicate_scripts(self):
        for bad in ['',self.html+self.html]:
            with self.subTest(bad=bad),self.assertRaisesRegex(RuntimeError,'gallery'):verify_photo_structure(bad,self.card)
    def test_legacy_string_ids_and_json(self):
        self.assertEqual(visible_photo_ids({'photos':'["a","b"]','hidden_photos':'["a"]'}),['b'])
    def test_invalid_crm_never_passes(self):
        for value in ['{}',[{}],['a','a'],[None]]:
            with self.subTest(value=value),self.assertRaises((RuntimeError,ValueError)):
                visible_photo_ids({'photos':value})
    def test_path_traversal_cover(self):
        self.card['cover_photo']='../001.jpg'
        with self.assertRaisesRegex(RuntimeError,'cover'):verify_photo_structure(self.html,self.card)
    def test_fake_comment_gallery_ignored(self):
        with self.assertRaisesRegex(RuntimeError,'gallery'):verify_photo_structure('<!--'+self.html+'-->',self.card)

if __name__=='__main__':unittest.main()
