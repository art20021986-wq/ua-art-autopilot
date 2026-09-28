#!/usr/bin/env python3
import json, os, urllib.parse, urllib.request, urllib.error
CID=os.environ["GSC_CLIENT_ID"];SEC=os.environ["GSC_CLIENT_SECRET"];REF=os.environ["GSC_REFRESH_TOKEN"]
SITE="https://www.uaart.com.ua/";MAP=SITE+"sitemap.xml"
form=urllib.parse.urlencode({"client_id":CID,"client_secret":SEC,"refresh_token":REF,"grant_type":"refresh_token"}).encode()
with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token",data=form,headers={"Content-Type":"application/x-www-form-urlencoded"}),timeout=30) as r:tok=json.load(r)["access_token"]
url="https://www.googleapis.com/webmasters/v3/sites/"+urllib.parse.quote(SITE,safe="")+"/sitemaps/"+urllib.parse.quote(MAP,safe="")
req=urllib.request.Request(url,data=b"",headers={"Authorization":"Bearer "+tok},method="PUT")
try:
 with urllib.request.urlopen(req,timeout=30) as r:
  print("GSC_SITEMAP_SUBMIT_PASS",r.status,MAP)
except urllib.error.HTTPError as e:
 body=e.read().decode("utf-8","replace")
 if e.code in (401,403):
  print("GSC_SITEMAP_SUBMIT_SKIPPED_READONLY_SCOPE",e.code,body[:500])
 else:raise
