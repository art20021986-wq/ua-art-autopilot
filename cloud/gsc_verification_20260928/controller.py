#!/usr/bin/env python3
import os, urllib.request, urllib.parse, uuid, time
TOKEN=(os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
if not TOKEN: raise SystemExit("PYTHONANYWHERE_API_TOKEN_MISSING")
BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
LOCAL="cloud/gsc_verification_20260928/install_remote.py"
REMOTE="/home/Carix/autopilot_inbox/cloud/gsc_verification_20260928/install_remote.py"
def req(method,url,data=None,headers=None,allowed=(200,)):
    h={"Authorization":"Token "+TOKEN,"User-Agent":"ua-art-gsc-verification/1"}; h.update(headers or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=h,method=method),timeout=70) as r: return r.status,r.read()
    except urllib.error.HTTPError as e:
        if e.code in allowed:return e.code,e.read()
        raise
def fileurl(p): return BASE+"files/path"+urllib.parse.quote(p,safe="/")
value=open(LOCAL,"rb").read(); boundary="----gsc"+uuid.uuid4().hex
body=(("--"+boundary+"\r\nContent-Disposition: form-data; name=\"content\"; filename=\"install_remote.py\"\r\nContent-Type: text/x-python\r\n\r\n").encode()+value+("\r\n--"+boundary+"--\r\n").encode())
req("POST",fileurl(REMOTE),body,{"Content-Type":"multipart/form-data; boundary="+boundary},(200,201))
moment=time.gmtime(time.time()+60)
form=urllib.parse.urlencode({"command":"python3.10 "+REMOTE,"description":"gsc-html-verification-once","enabled":"true","interval":"daily","hour":moment.tm_hour,"minute":moment.tm_min}).encode()
status,raw=req("POST",BASE+"schedule/",form,{"Content-Type":"application/x-www-form-urlencoded"},(200,201,202))
import json
sid=json.loads(raw.decode()).get("id")
if not sid: raise SystemExit("NO_SCHEDULED_EXECUTOR")
try:
    deadline=time.time()+180
    url="https://www.uaart.com.ua/google609494476a22f741.html?verify="+uuid.uuid4().hex
    while time.time()<deadline:
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"Cache-Control":"no-cache"}),timeout=20) as r:
                b=r.read().decode().strip()
                if r.status==200 and b=="google-site-verification: google609494476a22f741.html":
                    print("GSC_HTML_PUBLIC_PASS"); break
        except Exception: pass
        time.sleep(5)
    else: raise SystemExit("GSC_HTML_PUBLIC_TIMEOUT")
finally:
    req("DELETE",BASE+"schedule/%s/"%sid,allowed=(200,202,204,404))
