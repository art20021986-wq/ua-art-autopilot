#!/usr/bin/env python3
import datetime as dt, json, os, urllib.parse, urllib.request, urllib.error
SITE="https://www.uaart.com.ua/"
URLS=[
 SITE+"video/index.html",SITE+"video/katalog.html",
 SITE+"video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html",
 SITE+"video/seo/ru/avto-iz-korei-v-kiev-pod-kluch.html",
 SITE+"video/seo/gu/avtomobili-koreidan-sakartveloshi.html",
 SITE+"video/seo/ua/kia-k5-koreya-kyiv.html",
 SITE+"video/seo/ua/hyundai-sonata-koreya-kyiv.html",
 SITE+"video/UA-0018.html",SITE+"video/UA-0021.html",SITE+"video/UA-0023.html"]
CID=os.environ["GSC_CLIENT_ID"];SEC=os.environ["GSC_CLIENT_SECRET"];REF=os.environ["GSC_REFRESH_TOKEN"]
def request(url,data=None,headers=None,method=None):
 r=urllib.request.Request(url,data=data,headers=headers or {},method=method)
 try:
  with urllib.request.urlopen(r,timeout=30) as x:
   raw=x.read();return x.status,json.loads(raw) if raw else {}
 except urllib.error.HTTPError as e:
  raw=e.read()
  try:v=json.loads(raw)
  except:v={"raw":raw.decode("utf-8","replace")}
  return e.code,v
form=urllib.parse.urlencode({"client_id":CID,"client_secret":SEC,"refresh_token":REF,"grant_type":"refresh_token"}).encode()
st,tok=request("https://oauth2.googleapis.com/token",form,{"Content-Type":"application/x-www-form-urlencoded"})
if st!=200:raise SystemExit("TOKEN_HTTP_"+str(st))
H={"Authorization":"Bearer "+tok["access_token"],"Content-Type":"application/json"}
end=dt.date.today()-dt.timedelta(days=2);start=end-dt.timedelta(days=27)
body=json.dumps({"startDate":str(start),"endDate":str(end),"dimensions":["query","page"],"rowLimit":25000,"type":"web"}).encode()
st,perf=request("https://www.googleapis.com/webmasters/v3/sites/"+urllib.parse.quote(SITE,safe="")+"/searchAnalytics/query",body,H)
if st!=200:raise SystemExit("ANALYTICS_HTTP_"+str(st))
rows=perf.get("rows",[])
summary={"window":[str(start),str(end)],"rows":len(rows),"clicks":sum(x.get("clicks",0) for x in rows),"impressions":sum(x.get("impressions",0) for x in rows),
"top":sorted(rows,key=lambda x:(x.get("impressions",0),x.get("clicks",0)),reverse=True)[:30]}
st,sitemaps=request("https://www.googleapis.com/webmasters/v3/sites/"+urllib.parse.quote(SITE,safe="")+"/sitemaps",headers=H)
summary["sitemaps_http"]=st;summary["sitemaps"]=sitemaps.get("sitemap",[]) if st==200 else sitemaps
ins=[];hard=[]
for u in URLS:
 payload=json.dumps({"inspectionUrl":u,"siteUrl":SITE,"languageCode":"ru-RU"}).encode()
 st,v=request("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",payload,H)
 item={"url":u,"http":st}
 if st==200:
  r=v.get("inspectionResult",{});idx=r.get("indexStatusResult",{});rich=r.get("richResultsResult",{})
  item.update({"index_verdict":idx.get("verdict"),"coverage":idx.get("coverageState"),"robots":idx.get("robotsTxtState"),"indexing":idx.get("indexingState"),
   "fetch":idx.get("pageFetchState"),"google_canonical":idx.get("googleCanonical"),"user_canonical":idx.get("userCanonical"),"last_crawl":idx.get("lastCrawlTime"),
   "rich_verdict":rich.get("verdict"),"rich_types":[x.get("richResultType") for x in rich.get("detectedItems",[])]})
  if idx.get("robotsTxtState")=="DISALLOWED" or idx.get("indexingState") in ("BLOCKED_BY_META_TAG","BLOCKED_BY_HTTP_HEADER") or idx.get("pageFetchState") in ("SERVER_ERROR","ACCESS_FORBIDDEN"):
   hard.append(item)
 elif st not in (403,429):hard.append(item)
 ins.append(item)
summary["inspection"]=ins
print(json.dumps(summary,ensure_ascii=False,indent=2))
if hard:print("GSC_DAILY_HARD_ISSUES",json.dumps(hard,ensure_ascii=False));raise SystemExit(1)
print("GSC_DAILY_RADAR_PASS")
