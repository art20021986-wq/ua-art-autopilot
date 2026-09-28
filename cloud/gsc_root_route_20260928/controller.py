#!/usr/bin/env python3
"""Install exactly one PythonAnywhere static-file mapping for Google verification."""
import json, os, socket, time, urllib.parse, urllib.request, urllib.error
TOKEN=(os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
if not TOKEN: raise SystemExit("PYTHONANYWHERE_API_TOKEN_MISSING")
BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
DOMAIN="www.uaart.com.ua"
URL="/google609494476a22f741.html"
PATH="/home/Carix/video/google609494476a22f741.html"
EXPECTED="google-site-verification: google609494476a22f741.html"
def call(method,url,data=None,headers=None,allowed=(200,),timeout=60,allow_timeout=False):
 h={"Authorization":"Token "+TOKEN,"User-Agent":"ua-art-gsc-static-route/2"};h.update(headers or {})
 try:
  with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=h,method=method),timeout=timeout) as r:return r.status,r.read()
 except urllib.error.HTTPError as e:
  body=e.read()
  if e.code in allowed:return e.code,body
  raise SystemExit("HTTP_%d:%s"%(e.code,body[:300].decode("utf-8","replace")))
 except (TimeoutError,socket.timeout) as e:
  if allow_timeout:return 0,b""
  raise
endpoint=BASE+"webapps/"+DOMAIN+"/static_files/"
_,raw=call("GET",endpoint)
current=json.loads(raw.decode())
if isinstance(current,dict): items=[{"url":k,"path":v} for k,v in current.items()]
else: items=current if isinstance(current,list) else []
for x in items:
 if x.get("url")==URL and x.get("path")!=PATH: raise SystemExit("STATIC_ROUTE_CONFLICT")
if not any(x.get("url")==URL and x.get("path")==PATH for x in items):
 data=urllib.parse.urlencode({"url":URL,"path":PATH}).encode()
 call("POST",endpoint,data,{"Content-Type":"application/x-www-form-urlencoded"},(200,201))
# PythonAnywhere reload can complete server-side while its API response stalls.
call("POST",BASE+"webapps/"+DOMAIN+"/reload/",b"",allowed=(200,),timeout=12,allow_timeout=True)
deadline=time.time()+150
last=""
while time.time()<deadline:
 try:
  req=urllib.request.Request("https://www.uaart.com.ua"+URL+"?verify="+str(int(time.time())),headers={"Cache-Control":"no-cache","User-Agent":"ua-art-gsc-static-route-verify/2"})
  with urllib.request.urlopen(req,timeout=20) as r:
   body=r.read().decode("utf-8","replace").strip()
   if r.status==200 and body==EXPECTED:
    print("GSC_ROOT_ROUTE_PASS");raise SystemExit(0)
   last="HTTP_%s BODY_%r"%(r.status,body[:120])
 except urllib.error.HTTPError as e:last="HTTP_%s"%e.code
 except Exception as e:last=type(e).__name__+":"+str(e)[:120]
 time.sleep(5)
raise SystemExit("PUBLIC_VERIFY_TIMEOUT:"+last)
