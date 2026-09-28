#!/usr/bin/env python3
import hashlib, json, os, pathlib, re, shutil, tempfile, time, urllib.request, urllib.error
ROOT=pathlib.Path("/home/Carix"); VIDEO=ROOT/"video"; ORIGIN="https://www.uaart.com.ua"
STAMP=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime()); BACK=ROOT/"archive/backups"/("SEO-TOP-KYIV-002_"+STAMP)
CARD=re.compile(r"^UA-[0-9]{4,}\.html$",re.I); DIAG=re.compile(r"^UA-[0-9]{4,}-diag\.html$",re.I)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic(p,b):
 p.parent.mkdir(parents=True,exist_ok=True); fd,t=tempfile.mkstemp(prefix=".seo2-",dir=str(p.parent))
 try:
  with os.fdopen(fd,"wb") as f:f.write(b);f.flush();os.fsync(f.fileno())
  os.replace(t,p)
 finally:
  try:os.unlink(t)
  except FileNotFoundError:pass
def backup(paths):
 m=[]
 for p in paths:
  rel=p.relative_to(ROOT); d=BACK/rel; d.parent.mkdir(parents=True,exist_ok=True)
  if p.exists():shutil.copy2(p,d);m.append({"path":str(p),"exists":True,"sha":sha(p),"copy":str(d)})
  else:m.append({"path":str(p),"exists":False,"sha":None,"copy":None})
 atomic(BACK/"manifest.json",(json.dumps(m,indent=2)+"\n").encode());return m
def rollback(m):
 for x in m:
  p=pathlib.Path(x["path"])
  if x["exists"]:shutil.copy2(x["copy"],p)
  elif p.exists():p.unlink()
def add_canonical(s,url):
 s=re.sub(r'<link\b(?=[^>]*\brel\s*=\s*["\'][^"\']*canonical[^"\']*["\'])[^>]*>\s*',"",s,flags=re.I)
 tag='<link rel="canonical" href="%s">\n'%url
 return re.sub(r"</head\s*>",tag+"</head>",s,count=1,flags=re.I) if re.search(r"</head\s*>",s,re.I) else tag+s
cards=sorted([p for p in VIDEO.glob("UA-*.html") if CARD.fullmatch(p.name)])
diags=sorted([p for p in VIDEO.glob("UA-*-diag.html") if DIAG.fullmatch(p.name)])
landings=sorted((VIDEO/"seo").glob("*/*.html")) if (VIDEO/"seo").exists() else []
core=[VIDEO/x for x in ("index.html","katalog.html","podbor.html","info.html")]
targets=[VIDEO/"sitemap.xml"]+diags+landings
before_cards={p.name:sha(p) for p in cards}
manifest=backup(targets)
try:
 # self-canonical diagnostics
 for p in diags:
  s=p.read_text(encoding="utf-8",errors="replace"); url=ORIGIN+"/video/"+p.name
  atomic(p,add_canonical(s,url).encode())
 # repair only proven wrong catalog href in SEO landings
 for p in landings:
  s=p.read_text(encoding="utf-8",errors="replace").replace("/video/catalog.html","/video/katalog.html")
  atomic(p,s.encode())
 urls=[ORIGIN+"/video/"+p.name for p in core if p.exists()]
 urls += [ORIGIN+"/video/"+p.name for p in cards]
 urls += [ORIGIN+"/video/"+str(p.relative_to(VIDEO)).replace(os.sep,"/") for p in landings]
 urls=list(dict.fromkeys(urls))
 xml="<?xml version='1.0' encoding='UTF-8'?>\n<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>\n"+"\n".join("<url><loc>%s</loc></url>"%u for u in urls)+"\n</urlset>\n"
 atomic(VIDEO/"sitemap.xml",xml.encode())
 if {p.name:sha(p) for p in cards}!=before_cards:raise RuntimeError("CARD_HASH_REGRESSION")
 for p in diags:
  s=p.read_text(encoding="utf-8",errors="replace"); expected=ORIGIN+"/video/"+p.name
  if s.count('rel="canonical"')!=1 or expected not in s:raise RuntimeError("DIAG_CANONICAL:"+p.name)
 bad=[]
 for u in urls:
  try:
   with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"UA-ART-SEO-VERIFY/1"}),timeout=20) as r:
    if r.status!=200:bad.append([u,r.status])
  except Exception as e:bad.append([u,type(e).__name__])
 if bad:raise RuntimeError("LIVE_URL_FAIL:"+json.dumps(bad[:10]))
 receipt={"status":"PASS","task":"SEO-TOP-KYIV-002","cards_untouched":len(cards),"diagnostics_canonicalized":len(diags),"landings":len(landings),"sitemap_urls":len(urls),"backup":str(BACK),"rollback":None}
except Exception as e:
 rollback(manifest);receipt={"status":"FAIL_ROLLED_BACK","task":"SEO-TOP-KYIV-002","error":str(e),"backup":str(BACK),"rollback":"DONE"}
path=ROOT/"archive/reports/SEO_TOP_KYIV_002.json";atomic(path,(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n").encode())
print(json.dumps(receipt,ensure_ascii=False))
raise SystemExit(0 if receipt["status"]=="PASS" else 1)
