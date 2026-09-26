import copy
import unittest
from crm_gallery import select_names
from build_gallery_patch import replace_function,build

class GalleryTests(unittest.TestCase):
 def setUp(self):
  self.card={'auto_number':'UA-0019','photos':[{'file_id':'a'},{'file_id':'b'},{'file_id':'c'}], 'hidden_photos':['a']}
  self.ledger={'foto:UA-0019':{'009.jpg':'c','001.jpg':'a','004.jpg':'b'}}
 def test_hidden_and_crm_order_not_filename_order(self):
  self.assertEqual(select_names(self.card,self.ledger),['004.jpg','009.jpg'])
 def test_cover_first(self):
  self.card['cover_photo']='009.jpg'
  self.assertEqual(select_names(self.card,self.ledger),['009.jpg','004.jpg'])
 def test_hidden_cover_never_reappears(self):
  self.card['cover_photo']='001.jpg'
  self.assertEqual(select_names(self.card,self.ledger),['004.jpg','009.jpg'])
 def test_missing_map_rejected(self):
  del self.ledger['foto:UA-0019']['004.jpg']
  with self.assertRaisesRegex(RuntimeError,'not confirmed'):select_names(self.card,self.ledger)
 def test_duplicate_identity_rejected(self):
  self.ledger['foto:UA-0019']['010.jpg']='b'
  with self.assertRaisesRegex(RuntimeError,'Ambiguous'):select_names(self.card,self.ledger)
 def test_traversal_rejected(self):
  self.ledger['foto:UA-0019']['../005.jpg']='d'
  with self.assertRaisesRegex(RuntimeError,'filename'):select_names(self.card,self.ledger)
 def test_removed_cover_rejected(self):
  self.card['cover_photo']='009.jpg';self.card['photos']=self.card['photos'][:2]
  with self.assertRaisesRegex(RuntimeError,'current'):select_names(self.card,self.ledger)
 def test_extra_disk_ledger_photo_not_included(self):
  self.ledger['foto:UA-0019']['050.jpg']='extra'
  self.assertEqual(select_names(self.card,self.ledger),['004.jpg','009.jpg'])
 def test_patch_preserves_surrounding_code(self):
  s='x = 3\ndef target(a):\n    return a\ny = 4\n'
  got=replace_function(s,'target','def target(a):\n    return a + 1\n')
  self.assertEqual(got,'x = 3\ndef target(a):\n    return a + 1\ny = 4\n')
 def test_source_drift_rejected(self):
  with self.assertRaisesRegex(ValueError,'changed'):build('stranica.py',b'# drift')
 def test_ambiguous_function_rejected(self):
  with self.assertRaisesRegex(ValueError,'Ambiguous'):
   replace_function('def target(): pass\ndef target(): pass\n','target','def target(): pass\n')

if __name__=='__main__':unittest.main()
