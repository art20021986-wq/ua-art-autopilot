import sys,unittest,pathlib,importlib.util,types,tempfile
from unittest.mock import patch
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from public_fields import verify_core_fields
CARD={'brand':'Kia','model':'K5','year':'2020','vin':'KNAG741BBLA032716','mileage_km':167007,'engine_cc':1999,'fuel':'LPI','gearbox':'Автомат','drive':'Передний','color':'Черный'}
PAGE='''<title>Kia K5 2020 — UA ART COMPANY</title><h1>Kia K5 2020</h1><table class="kratko"><tr><td>Пробег</td><td>167 007 км</td></tr><tr><td>VIN</td><td>KNAG741BBLA032716</td></tr><tr><td>Двигатель</td><td>1 999 см³, LPI</td></tr><tr><td>Коробка</td><td>Автомат</td></tr><tr><td>Привод</td><td>Передний</td></tr><tr><td>Цвет</td><td>Черный</td></tr></table>'''
CAT='''<article><a href="UA-0022.html">open</a><h2>Kia K5 2020</h2><p>167007 км · 1999 см³ · LPI · Автомат</p><span>VIN KNAG741BBLA032716</span></article>'''
class Checks(unittest.TestCase):
 def test_valid_card_and_catalog(self):
  verify_core_fields(PAGE,CARD);verify_core_fields(CAT,CARD,True)
 def test_stale_mileage(self):
  with self.assertRaises(RuntimeError):verify_core_fields(PAGE.replace('167 007','167 008'),CARD)
 def test_catalog_stale_mileage(self):
  with self.assertRaises(RuntimeError):verify_core_fields(CAT.replace('167007','167008'),CARD,True)
 def test_vin_in_comment_does_not_mask_wrong_visible_vin(self):
  bad=PAGE.replace(CARD['vin'],'WRONG')+'<!--'+CARD['vin']+'-->'
  with self.assertRaises(RuntimeError):verify_core_fields(bad,CARD)
 def test_title_does_not_mask_stale_visible_heading(self):
  with self.assertRaises(RuntimeError):verify_core_fields(PAGE.replace('<h1>Kia K5 2020','<h1>Kia K5 2019'),CARD)
 def test_duplicate_mileage_is_rejected(self):
  with self.assertRaises(RuntimeError):verify_core_fields(PAGE.replace('</table>','<tr><td>Пробег</td><td>167 007 км</td></tr></table>'),CARD)
 def test_empty_crm_mileage_is_unverified(self):
  with self.assertRaises(RuntimeError):verify_core_fields(PAGE,dict(CARD,mileage_km=None))
 def test_nbsp_and_nested_elements(self):
  verify_core_fields(PAGE.replace('167 007','<b>167\u00a0007</b>'),CARD)
 def test_stale_brand(self):
  with self.assertRaises(RuntimeError):verify_core_fields(PAGE.replace('Kia','Hyundai'),CARD)
 def test_stale_specifications(self):
  for old,new in [('1 999','2 000'),('LPI','diesel'),('Автомат','Механика'),('Передний','Задний'),('Черный','Белый')]:
   with self.subTest(field=old), self.assertRaises(RuntimeError):verify_core_fields(PAGE.replace(old,new),CARD)
 def test_stale_catalog_specs(self):
  for old,new in [('1999','2000'),('LPI','diesel'),('Автомат','Механика')]:
   with self.subTest(field=old), self.assertRaises(RuntimeError):verify_core_fields(CAT.replace(old,new),CARD,True)
 def test_adapter_builder_rejects_unreviewed_source(self):
  from build_candidate import build
  with tempfile.TemporaryDirectory() as d:
   source=pathlib.Path(d)/'source.py';source.write_text('unreviewed source')
   with self.assertRaisesRegex(ValueError,'Live source changed'):
    build(source,pathlib.Path(d)/'out.py')

def check_actual_adapter(adapter_path):
 spec=importlib.util.spec_from_file_location('candidate_freshness',adapter_path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 class Response:
  status=200
  def __init__(self,data):self.data=data
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def read(self,limit):return self.data[:limit]
 with tempfile.TemporaryDirectory() as d:
  root=pathlib.Path(d);(root/'UA-0022.html').write_text(PAGE.replace('167 007','167 008'));(root/'katalog.html').write_text(CAT)
  def fetch(req,timeout):
   name=req.full_url.split('/')[-1].split('?')[0]
   return Response((root/name).read_bytes())
  with patch.dict(sys.modules,{'ua_price_html_v2':types.SimpleNamespace(verify_prices=lambda html:None)}):
   with unittest.TestCase().assertRaisesRegex(RuntimeError,'mileage'):
    module.verify_public('UA-0022',fetch=fetch,card=CARD,root=root)
if __name__=='__main__':unittest.main()
