#!/usr/bin/env python3
import json, os, urllib.parse, urllib.request
token=os.environ["PYTHONANYWHERE_API_TOKEN"]
base="https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
path="/home/Carix/archive/reports/SEO_KOREA_KYIV_001_FINAL.txt"
req=urllib.request.Request(base+urllib.parse.quote(path,safe="/"),headers={"Authorization":"Token "+token,"User-Agent":"ua-art-seo-receipt-probe/1"})
with urllib.request.urlopen(req,timeout=45) as r:
 text=r.read().decode("utf-8","replace")
for line in text.splitlines():
 if line.startswith(("Run:","Landing URLs:","Sitemap URL count:","Gate A:","Gate B:","Gate C:","Gate D:","Rollback:","FINAL STATUS:")):
  print(line)
