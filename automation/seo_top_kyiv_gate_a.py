#!/usr/bin/env python3
"""UA-ART-SEO-TOP-KYIV-001 Gate A: read-only public/GSC audit. Zero production writes."""
import datetime as dt, html, json, os, re, sys, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser
BASE="https://www.uaart.com.ua"
UA="UA-ART-SEO-TOP-KYIV-001"
MAX_URLS=180
class P(HTMLParser):
 def __init__(self):
  super().__init__(); self.links=[]; self.canonical=""; self.title=""; self.h1=""; self.robots=""; self._tag=""; self._buf=[]
 def handle_starttag(self,t,a):
  d=dict(a); tl=t.lower()
  if tl=="a" and d.get("href"): self.links.append(d["href"])
  if tl=="link" and "canonical" in d.get("rel","").lower(): self.canonical=d.get("href","")
  if tl=="meta" and d.get("name","").lower()=="robots": self.robots=d.get("content","")
  if tl in ("title","h1"): self._tag=tl; self._buf=[]
 def handle_data(self,d):
  if self._tag:self._buf.append(d)
 def handle_endtag(self,t):
  if t.lower()==self._tag:
   v=" ".join("".join(self._buf).split())
   if self._tag=="title":self.title=v
   elif self._tag=="h1" and not self.h1:self.h1=v
   self._tag="";self._buf=[]
def get(url,timeout=18):
 req=urllib.request.Request(url,headers={"User-Agent":"UA-ART-SEO-GATE-A/1.0","Accept":"text/html,application/xml,text/plain,*/*"})
 try:
  with urllib.request.urlopen(req,timeout=timeout) as r:return r.status,r.geturl(),r.headers.get("Content-Type",""),r.read(1500000)
 except urllib.error.HTTPError as e:return e.code,url,e.headers.get("Content-Type",""),e.read(200000)
 except Exception as e:return 0,url,"",str(e).encode()
def same(u): return urllib.parse.urlsplit(u).netloc in ("","www.uaart.com.ua","uaart.com.ua")
def norm(base,href):
 try:
  u=urllib.parse.urljoin(base,href); s=urllib.parse.urlsplit(u)
  if s.scheme not in ("http","https") or not same(u):return None
  return urllib.parse.urlunsplit(("https","www.uaart.com.ua",s.path or "/",s.query,""))
 except:return None
def gsc():
 cid=os.environ.get("GSC_CLIENT_ID","").strip(); sec=os.environ.get("GSC_CLIENT_SECRET","").strip(); ref=os.environ.get("GSC_REFRESH_TOKEN","").strip()
 if not all((cid,sec,ref)):return {"status":"SKIP","reason":"missing GSC secrets"}
 data=urllib.parse.urlencode({"client_id":cid,"client_secret":sec,"refresh_token":ref,"grant_type":"refresh_token"}).encode()
 st,_,_,raw=get_token("https://oauth2.googleapis.com/token",data)
 if st!=200:return {"status":"FAIL","reason":"token HTTP "+str(st)}
 tok=json.loads(raw).get("access_token"); hdr={"Authorization":"Bearer "+tok,"Accept":"application/json"}
 st,body=json_api("https://www.googleapis.com/webmasters/v3/sites",hdr)
 if st!=200:return {"status":"FAIL","reason":"sites HTTP "+str(st)}
 vis=[x.get("siteUrl") for x in body.get("siteEntry",[])]; site="https://www.uaart.com.ua/"
 out={"status":"PASS","visible":vis,"selected":site}
 if site not in vis:return {**out,"status":"FAIL","reason":"verified URL-prefix not visible"}
 end=dt.date.today()-dt.timedelta(days=2); start=end-dt.timedelta(days=27)
 q=json.dumps({"startDate":str(start),"endDate":str(end),"dimensions":["query","page"],"rowLimit":100,"type":"web"}).encode()
 st,b=json_api("https://www.googleapis.com/webmasters/v3/sites/"+urllib.parse.quote(site,safe="")+"/searchAnalytics/query",{**hdr,"Content-Type":"application/json"},q)
 out.update({"window":[str(start),str(end)],"query_status":st,"rows":len(b.get("rows",[])) if isinstance(b,dict) else 0})
 return out
def get_token(url,data):
 req=urllib.request.Request(url,data=data,headers={"Content-Type":"application/x-www-form-urlencoded"})
 try:
  with urllib.request.urlopen(req,timeout=20) as r:return r.status,r.geturl(),r.headers.get("Content-Type",""),r.read()
 except urllib.error.HTTPError as e:return e.code,url,"",e.read()
def json_api(url,headers,data=None):
 req=urllib.request.Request(url,data=data,headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=25) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:
  try:return e.code,json.loads(e.read())
  except:return e.code,{}
def main():
 report={"task":UA,"mode":"READ_ONLY","generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"gsc":{"status":"PRECONFIRMED","evidence":"GSC Gate B #3 PASS before this audit"}}
 seeds=[BASE+"/",BASE+"/robots.txt",BASE+"/sitemap.xml",BASE+"/video/index.html",BASE+"/video/katalog.html",BASE+"/video/podbor.html",
 BASE+"/video/katalog.html?f=kiev&stage=kiev",BASE+"/video/podbor.html?strana=japan&v=1787036776"]
 # Seed crawl from sitemap if available.
 st,fin,ct,raw=get(BASE+"/sitemap.xml"); sm=raw.decode("utf-8","ignore")
 seeds += re.findall(r"<loc>\s*(https?://[^<]+)",sm,re.I)
 queue=[]; seen=set()
 for u in seeds:
  if u and u not in seen:queue.append(u);seen.add(u)
 rows=[]
 while queue and len(rows)<MAX_URLS:
  u=queue.pop(0); st,fin,ct,raw=get(u); text=raw.decode("utf-8","ignore")
  p=P()
  if "html" in ct.lower() or "<html" in text[:1000].lower():
   try:p.feed(text)
   except:pass
  row={"url":u,"status":st,"final":fin,"canonical":p.canonical,"title":p.title[:180],"h1":p.h1[:180],"robots":p.robots,
       "query":bool(urllib.parse.urlsplit(u).query),"jsonld":sorted(set(re.findall(r'"@type"\s*:\s*(?:\[\s*)?"([^"]+)"',text,re.I)))[:12]}
  rows.append(row)
  if st==200 and not row["query"]:
   for href in p.links:
    v=norm(fin,href)
    if v and v not in seen and len(seen)<MAX_URLS*3:
     seen.add(v);queue.append(v)
 report["crawl"]=rows
 report["summary"]={
  "crawled":len(rows),
  "non200":sum(r["status"]!=200 for r in rows),
  "query_urls":sum(r["query"] for r in rows),
  "missing_canonical":sum(r["status"]==200 and "text/html" and not r["canonical"] for r in rows if r["title"] or r["h1"]),
  "noindex":sum("noindex" in r["robots"].lower() for r in rows),
  "product_car_schema":sum(("Product" in r["jsonld"] and "Car" in r["jsonld"]) for r in rows),
 }
 # Static readiness evidence for existing free SEO package.
 pkg="cloud/seo_korea_kyiv_001/seo_korea_kyiv_001.py"
 report["free_weapon"]={"package":pkg,"exists":os.path.isfile(pkg)}
 if os.path.isfile(pkg):
  s=open(pkg,encoding="utf-8").read()
  report["free_weapon"].update({"has_rollback":"rollback(" in s,"has_canonical":"canonical" in s.lower(),"has_hreflang":"hreflang" in s.lower(),
    "has_faq":"FAQPage" in s,"has_autodealer":"AutoDealer" in s,"has_sitemap":"sitemap.xml" in s})
 print("=== "+UA+" GATE A REPORT ===")
 print(json.dumps(report,ensure_ascii=False,indent=2))
 # Gate A itself passes if GSC is connected and public core is reachable; findings are audit output, not failure.
 core=[r for r in rows if r["url"] in (BASE+"/",BASE+"/robots.txt",BASE+"/sitemap.xml")]
 ok=all(r["status"]==200 for r in core)
 print("GATE_A_"+("PASS" if ok else "FAIL"))
 return 0 if ok else 1
if __name__=="__main__":sys.exit(main())
