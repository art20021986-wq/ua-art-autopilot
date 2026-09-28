#!/usr/bin/env python3
import json, os, pathlib, re, time
from html import unescape
ROOT=pathlib.Path("/home/Carix"); V=ROOT/"video"; REPORT=ROOT/"archive/reports/SEO_STRUCTURED_004_GATE_A.json"
CARD=re.compile(r"^UA-[0-9]{4,}\.html$",re.I)
def text(s):return " ".join(re.sub(r"<[^>]+>"," ",unescape(s)).split())
def one(p,s):
 m=re.search(p,s,re.I|re.S);return text(m.group(1)) if m else ""
def attr(p,s):
 m=re.search(p,s,re.I|re.S);return unescape(m.group(1)).strip() if m else ""
def public_image(s):
 patterns=[
  r'<meta\b(?=[^>]*property=["\']og:image["\'])[^>]*content=["\']([^"\']+)',
  r'<img\b(?=[^>]*data-mcf-foto=["\']1["\'])[^>]*src=["\']([^"\']+)',
  r'<img\b[^>]*src=["\']([^"\']+)']
 for p in patterns:
  v=attr(p,s)
  if v:
   if v.startswith("/"):return "https://www.uaart.com.ua"+v
   if v.startswith("http"):return v
   return "https://www.uaart.com.ua/video/"+v.lstrip("./")
 return ""
def table(s):
 out={}
 for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>",s,re.I|re.S):
  td=[text(x) for x in re.findall(r"<td\b[^>]*>(.*?)</td>",tr,re.I|re.S)]
  if len(td)==2 and td[0]:out[td[0]]=td[1]
 return out
rows=[]
for p in sorted(V.glob("UA-*.html")):
 if not CARD.fullmatch(p.name):continue
 s=p.read_text(encoding="utf-8",errors="replace"); t=table(s); code=p.stem
 def price(market):
  m=re.search(r'<div\b(?=[^>]*data-ua-market=["\']%s["\'])[^>]*data-ua-value=["\']([^"\']*)'%market,s,re.I|re.S)
  return m.group(1).strip() if m else ""
 schemas=sorted(set(re.findall(r'"@type"\s*:\s*"([^"]+)"',s)))
 multi=re.findall(r'"@type"\s*:\s*\[([^\]]+)\]',s)
 for x in multi:schemas+=re.findall(r'"([^"]+)"',x)
 mp4=V/(code+".mp4")
 rows.append({"id":code,"title":one(r"<title[^>]*>(.*?)</title>",s),"h1":one(r"<h1[^>]*>(.*?)</h1>",s),
 "canonical":attr(r'<link\b(?=[^>]*rel=["\'][^"\']*canonical)[^>]*href=["\']([^"\']+)',s),
 "price_ua":price("ukraine"),"price_ge":price("georgia"),"image":public_image(s),
 "mileage":t.get("Пробег",""),"engine":t.get("Двигатель",""),"fuel":t.get("Топливо",""),
 "schema":sorted(set(schemas)),"breadcrumb":("BreadcrumbList" in s),"product_car":("Product" in s and "Car" in s),
 "mp4":mp4.is_file(),"mp4_mtime":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(mp4.stat().st_mtime)) if mp4.is_file() else None,
 "seo_links":len(re.findall(r'/video/seo/',s,re.I))})
summary={"cards":len(rows),"with_ua_price":sum(bool(x["price_ua"]) for x in rows),"with_ge_price":sum(bool(x["price_ge"]) for x in rows),
"with_image":sum(bool(x["image"]) for x in rows),"with_mp4":sum(x["mp4"] for x in rows),"with_product_car":sum(x["product_car"] for x in rows),
"with_breadcrumb":sum(x["breadcrumb"] for x in rows),"with_seo_links":sum(x["seo_links"]>0 for x in rows)}
value={"status":"PASS" if rows and all(x["canonical"] for x in rows) else "FAIL","task":"SEO-STRUCTURED-004-GATE-A","summary":summary,"cards":rows,
"video_policy":"Do not publish VideoObject from filesystem mtime alone; Google requires factual uploadDate."}
REPORT.parent.mkdir(parents=True,exist_ok=True);REPORT.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(value,ensure_ascii=False));raise SystemExit(0 if value["status"]=="PASS" else 1)
