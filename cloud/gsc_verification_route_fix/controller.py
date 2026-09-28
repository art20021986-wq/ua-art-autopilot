#!/usr/bin/env python3
import os,urllib.request,urllib.parse,urllib.error,uuid,time,json
TOKEN=(os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
if not TOKEN: raise SystemExit("PYTHONANYWHERE_API_TOKEN_MISSING")
BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
LOCAL="cloud/gsc_verification_route_fix/install_remote.py"
REMOTE="/home/Carix/autopilot_inbox/cloud/gsc_verification_route_fix/install_remote.py"
def req(method,url,data=None,headers=None,allowed=(200,)):
 h={"Authorization":"Token "+TOKEN,"User-Agent":"ua-art-gsc-route-fix/1"};h.update(headers or {})
 try:
  with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=h,method=method),timeout=70) as r:return r.status,r.read()
 except urllib.error.HTTPError as e:
  if e.code in allowed:return e.code,e.read()
  raise
def furl(p):return BASE+"files/path"+urllib.parse.quote(p,safe="/")
v=open(LOCAL,"rb").read();bd="----gsc"+uuid.uuid4().hex
body=(("--"+bd+"\r\nContent-Disposition: form-data; name=\"content\"; filename=\"install_remote.py\"\r\nContent-Type: text/x-python\r\n\r\n").encode()+v+("\r\n--"+bd+"--\r\n").encode())
req("POST",furl(REMOTE),body,{"Content-Type":"multipart/form-data; boundary="+bd},(200,201))
m=time.gmtime(time.time()+60)
form=urllib.parse.urlencode({"command":"python3.10 "+REMOTE,"description":"gsc-verification-route-fix-once","enabled":"true","interval":"daily","hour":m.tm_hour,"minute":m.tm_min}).encode()
_,raw=req("POST",BASE+"schedule/",form,{"Content-Type":"application/x-www-form-urlencoded"},(200,201,202))
sid=json.loads(raw.decode()).get("id")
if not sid:raise SystemExit("NO_SCHEDULED_EXECUTOR")
try:
 deadline=time.time()+180
 url="https://www.uaart.com.ua/video/google609494476a22f741.html?x="+uuid.uuid4().hex
 while time.time()<deadline:
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"Cache-Control":"no-cache"}),timeout=20) as r:
    if r.status==200 and r.read().decode().strip()=="google-site-verification: google609494476a22f741.html":
     print("GSC_HTML_VIDEO_PUBLIC_PASS");break
  except Exception:pass
  time.sleep(5)
 else:raise SystemExit("GSC_HTML_VIDEO_PUBLIC_TIMEOUT")
finally:req("DELETE",BASE+"schedule/%s/"%sid,allowed=(200,202,204,404))
