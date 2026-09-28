#!/usr/bin/env python3
import hashlib, html, json, os, pathlib, re, shutil, tempfile, time, urllib.request
from html import unescape
from xml.sax.saxutils import escape as xesc
ROOT=pathlib.Path("/home/Carix");V=ROOT/"video";SEO=V/"seo";ORIGIN="https://www.uaart.com.ua"
STAMP=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime());BACK=ROOT/"archive/backups"/("SEO-STRUCTURED-004_"+STAMP)
START="<!-- UA-ART-SEO-STRUCTURED-004:START -->";END="<!-- UA-ART-SEO-STRUCTURED-004:END -->"
NAVS="<!-- UA-ART-SEO-LINKS-004:START -->";NAVE="<!-- UA-ART-SEO-LINKS-004:END -->"
CARD=re.compile(r"^UA-[0-9]{4,}\.html$",re.I)
BRANDS=("Mercedes-Benz","Mercedes","Hyundai","Kia","Audi","BMW","Toyota","Nissan","Volkswagen","Skoda","Renault","Tesla","BYD","Zeekr","Ford","Genesis")
def atomic(p,b):
 p.parent.mkdir(parents=True,exist_ok=True);fd,t=tempfile.mkstemp(prefix=".seo4-",dir=str(p.parent))
 try:
  with os.fdopen(fd,"wb") as f:f.write(b);f.flush();os.fsync(f.fileno())
  os.replace(t,p)
 finally:
  try:os.unlink(t)
  except FileNotFoundError:pass
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def txt(v):return " ".join(re.sub(r"<[^>]+>"," ",unescape(v)).split())
def one(p,s):
 m=re.search(p,s,re.I|re.S);return txt(m.group(1)) if m else ""
def attr(p,s):
 m=re.search(p,s,re.I|re.S);return unescape(m.group(1)).strip() if m else ""
def table(s):
 out={}
 for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>",s,re.I|re.S):
  td=[txt(x) for x in re.findall(r"<td\b[^>]*>(.*?)</td>",tr,re.I|re.S)]
  if len(td)==2 and td[0]:out[td[0]]=td[1]
 return out
def image(s):
 for p in (r'<meta\b(?=[^>]*property=["\']og:image["\'])[^>]*content=["\']([^"\']+)',r'<img\b(?=[^>]*data-mcf-foto=["\']1["\'])[^>]*src=["\']([^"\']+)',r'<img\b[^>]*src=["\']([^"\']+)'):
  v=attr(p,s)
  if v:return v if v.startswith("http") else ORIGIN+(v if v.startswith("/") else "/video/"+v.lstrip("./"))
 return ""
def ua_price(s):
 m=re.search(r'<div\b(?=[^>]*data-ua-market=["\']ukraine["\'])[^>]*data-ua-value=["\']([^"\']+)',s,re.I|re.S)
 return m.group(1).strip() if m else ""
def facts(s):
 t=table(s)
 return {"title":one(r"<title[^>]*>(.*?)</title>",s),"h1":one(r"<h1[^>]*>(.*?)</h1>",s),"canonical":attr(r'<link\b(?=[^>]*rel=["\'][^"\']*canonical)[^>]*href=["\']([^"\']+)',s),
 "price_ua":ua_price(s),"price_ge":attr(r'<div\b(?=[^>]*data-ua-market=["\']georgia["\'])[^>]*data-ua-value=["\']([^"\']*)',s),
 "mileage":t.get("Пробег",""),"engine":t.get("Двигатель",""),"vin":t.get("VIN",""),"image":image(s)}
def number(v):return re.sub(r"[^0-9.]","",v)
def brand(h1):
 for b in BRANDS:
  if h1.casefold().startswith(b.casefold()+" "):return b
 return ""
def schema(code,s):
 f=facts(s);price=number(f["price_ua"])
 if not price or float(price)<=0 or not f["image"] or not f["h1"]:raise RuntimeError("SCHEMA_FACTS:"+code)
 year_m=re.search(r"\b(19|20)\d{2}\b",f["h1"]);year=year_m.group(0) if year_m else None
 mileage=number(f["mileage"]);fuel=""
 m=re.search(r",\s*(.+)$",f["engine"]);fuel=m.group(1).strip() if m else ""
 canon=f["canonical"] or ORIGIN+"/video/"+code+".html"
 prod={"@context":"https://schema.org","@type":["Product","Car"],"@id":canon+"#vehicle","name":f["h1"],"url":canon,"sku":code,"image":[f["image"]],
 "offers":{"@type":"Offer","url":canon,"price":price,"priceCurrency":"USD"}}
 if brand(f["h1"]):prod["brand"]={"@type":"Brand","name":brand(f["h1"])}
 if year:prod["vehicleModelDate"]=year
 if mileage:prod["mileageFromOdometer"]={"@type":"QuantitativeValue","value":int(float(mileage)),"unitCode":"KMT"}
 if fuel:prod["fuelType"]=fuel
 prod["description"]=" · ".join(x for x in (f["h1"],f["mileage"],f["engine"]) if x)
 bread={"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
 {"@type":"ListItem","position":1,"name":"Головна","item":ORIGIN+"/video/index.html"},
 {"@type":"ListItem","position":2,"name":"Каталог автомобілів","item":ORIGIN+"/video/katalog.html"},
 {"@type":"ListItem","position":3,"name":f["h1"],"item":canon}]}
 return '<script type="application/ld+json">'+json.dumps(prod,ensure_ascii=False,separators=(",",":"))+'</script>\n<script type="application/ld+json">'+json.dumps(bread,ensure_ascii=False,separators=(",",":"))+'</script>'
def add_alt(s,h1):
 pat=re.compile(r'<img\b(?=[^>]*data-mcf-foto=["\']1["\'])[^>]*>',re.I|re.S);m=pat.search(s)
 if not m:return s
 tag=m.group(0)
 if re.search(r'\balt\s*=',tag,re.I):
  tag=re.sub(r'\balt\s*=\s*(["\']).*?\1','alt="'+html.escape(h1,quote=True)+'"',tag,count=1,flags=re.I|re.S)
 else:tag=tag[:-1]+' alt="'+html.escape(h1,quote=True)+'">'
 return s[:m.start()]+tag+s[m.end():]
def nav(h1):
 links=[("/video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html","Авто з Кореї"),("/video/seo/ru/avto-iz-korei-v-kiev-pod-kluch.html","Авто из Кореи"),("/video/seo/gu/avtomobili-koreidan-sakartveloshi.html","ავტომობილები კორეიდან")]
 if re.search(r"\bK(?:ia\s+)?K5\b|\bK5\b",h1,re.I):
  links.insert(0,("/video/seo/ua/kia-k5-koreya-kyiv.html","Kia K5 з Кореї"))
 elif re.search(r"Sonata",h1,re.I):
  links.insert(0,("/video/seo/ua/hyundai-sonata-koreya-kyiv.html","Hyundai Sonata з Кореї"))
 a=" · ".join('<a href="%s">%s</a>'%(u,t) for u,t in links)
 return NAVS+'<nav aria-label="Пов’язані сторінки" style="margin:18px 0 6px;font-size:13px;line-height:1.5;opacity:.88">'+a+'</nav>'+NAVE
def patch(code,s):
 f0=facts(s);s=re.sub(re.escape(START)+r".*?"+re.escape(END),"",s,flags=re.S);s=re.sub(re.escape(NAVS)+r".*?"+re.escape(NAVE),"",s,flags=re.S)
 block=START+schema(code,s)+END
 if "</head>" not in s.lower():raise RuntimeError("NO_HEAD:"+code)
 s=re.sub(r"</head\s*>",block+"\n</head>",s,count=1,flags=re.I)
 s=add_alt(s,f0["h1"])
 s=re.sub(r"</body\s*>",nav(f0["h1"])+"\n</body>",s,count=1,flags=re.I)
 if facts(s)!=f0:raise RuntimeError("FACT_REGRESSION:"+code)
 return s
cards=sorted([p for p in V.glob("UA-*.html") if CARD.fullmatch(p.name)])
landings=sorted(SEO.glob("*/*.html")) if SEO.exists() else [];sitemap=V/"sitemap.xml";targets=cards+landings+[sitemap]
manifest=[]
for p in targets:
 d=BACK/p.relative_to(ROOT);d.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():shutil.copy2(p,d);manifest.append((p,d,True))
 else:manifest.append((p,d,False))
try:
 card_images={}
 for p in cards:
  s=p.read_text(encoding="utf-8",errors="replace");candidate=patch(p.stem,s);atomic(p,candidate.encode());card_images[p.stem]=facts(candidate)["image"]
 # Add model-card links to each language landing without changing its primary copy.
 model_cards={"k5":[],"sonata":[]}
 for p in cards:
  h=facts(p.read_text(encoding="utf-8",errors="replace"))["h1"]
  if re.search(r"\bK5\b",h,re.I):model_cards["k5"].append((p.stem,h))
  if re.search(r"Sonata",h,re.I):model_cards["sonata"].append((p.stem,h))
 for p in landings:
  s=p.read_text(encoding="utf-8",errors="replace");s=re.sub(r'<!-- UA-ART-MODEL-CARDS-004:START -->.*?<!-- UA-ART-MODEL-CARDS-004:END -->',"",s,flags=re.S)
  key="k5" if "kia-k5-" in p.name else ("sonata" if "sonata-" in p.name else None)
  if key and model_cards[key]:
   links=" · ".join('<a href="/video/%s.html">%s</a>'%(code,html.escape(name)) for code,name in model_cards[key])
   block='<!-- UA-ART-MODEL-CARDS-004:START --><section><h2>Автомобілі в каталозі</h2><p>'+links+'</p></section><!-- UA-ART-MODEL-CARDS-004:END -->'
   s=re.sub(r"</body\s*>",block+"</body>",s,count=1,flags=re.I);atomic(p,s.encode())
 # Canonical sitemap + image extension.
 core=[V/x for x in ("index.html","katalog.html","podbor.html","info.html")]
 entries=[]
 for p in core:
  if p.exists():entries.append("<url><loc>%s</loc></url>"%xesc(ORIGIN+"/video/"+p.name))
 for p in cards:
  u=ORIGIN+"/video/"+p.name;im=card_images.get(p.stem,"");extra=("<image:image><image:loc>%s</image:loc></image:image>"%xesc(im)) if im else ""
  entries.append("<url><loc>%s</loc>%s</url>"%(xesc(u),extra))
 for p in landings:entries.append("<url><loc>%s</loc></url>"%xesc(ORIGIN+"/video/"+p.relative_to(V).as_posix()))
 xml='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'+"\n".join(entries)+"\n</urlset>\n";atomic(sitemap,xml.encode())
 # Local and live verification.
 for p in cards:
  s=p.read_text(encoding="utf-8",errors="replace")
  if s.count(START)!=1 or s.count(NAVS)!=1 or '"@type":["Product","Car"]' not in s or "BreadcrumbList" not in s:raise RuntimeError("POSTCHECK:"+p.stem)
 bad=[]
 for p in cards+landings:
  u=ORIGIN+"/video/"+p.relative_to(V).as_posix()
  try:
   with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"UA-ART-SEO-004/1"}),timeout=20) as r:
    if r.status!=200:bad.append([u,r.status])
  except Exception as e:bad.append([u,type(e).__name__])
 if bad:raise RuntimeError("LIVE_FAIL:"+json.dumps(bad[:5]))
 receipt={"status":"PASS","task":"SEO-STRUCTURED-004","cards":len(cards),"product_car_offer":len(cards),"breadcrumbs":len(cards),"images_in_sitemap":len(card_images),"internal_links":len(cards),"model_links":{"k5":len(model_cards["k5"]),"sonata":len(model_cards["sonata"])},"videoobject":0,"videoobject_blocker":"uploadDate is not proven for legacy MP4 files","backup":str(BACK),"rollback":None}
except Exception as e:
 for p,d,existed in manifest:
  if existed:shutil.copy2(d,p)
  elif p.exists():p.unlink()
 receipt={"status":"FAIL_ROLLED_BACK","task":"SEO-STRUCTURED-004","error":str(e),"backup":str(BACK),"rollback":"DONE"}
rp=ROOT/"archive/reports/SEO_STRUCTURED_004.json";atomic(rp,(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n").encode());print(json.dumps(receipt,ensure_ascii=False));raise SystemExit(0 if receipt["status"]=="PASS" else 1)
