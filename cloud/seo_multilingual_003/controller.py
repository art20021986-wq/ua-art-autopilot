#!/usr/bin/env python3
import json, os, time, urllib.parse, urllib.request, urllib.error, uuid, socket
TOKEN=(os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
LOCAL="cloud/seo_multilingual_003/patcher.py"
REMOTE="/home/Carix/autopilot_inbox/cloud/seo_multilingual_003/patcher.py"
RECEIPT="/home/Carix/archive/reports/SEO_MULTILINGUAL_003.json"
if not TOKEN: raise SystemExit("MISSING_TOKEN")
def call(method,url,data=None,headers=None,allowed=(200,)):
 h={"Authorization":"Token "+TOKEN,"User-Agent":"ua-art-seo-multilingual-003/2"};h.update(headers or {})
 try:
  with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=h,method=method),timeout=45) as r:return r.status,r.read()
 except urllib.error.HTTPError as e:
  body=e.read()
  if e.code in allowed or e.code>=500:return e.code,body
  raise
 except (TimeoutError,socket.timeout) as e:return 0,str(e).encode()
 except Exception as e:return 0,str(e).encode()
def furl(p):return BASE+"files/path"+urllib.parse.quote(p,safe="/")
raw=open(LOCAL,"rb").read();bd="----seo"+uuid.uuid4().hex
body=(("--"+bd+"\r\nContent-Disposition: form-data; name=\"content\"; filename=\"patcher.py\"\r\nContent-Type: text/x-python\r\n\r\n").encode()+raw+("\r\n--"+bd+"--\r\n").encode())
st,_=call("POST",furl(REMOTE),body,{"Content-Type":"multipart/form-data; boundary="+bd},(200,201))
if st not in (200,201):raise SystemExit("UPLOAD_FAILED_"+str(st))
call("DELETE",furl(RECEIPT),allowed=(200,204,404))
run=time.gmtime(time.time()+60)
form=urllib.parse.urlencode({"command":"python3.10 "+REMOTE,"description":"seo-multilingual-003-once","enabled":"true","interval":"daily","hour":run.tm_hour,"minute":run.tm_min}).encode()
st,b=call("POST",BASE+"schedule/",form,{"Content-Type":"application/x-www-form-urlencoded"},(200,201,202))
if st not in (200,201,202):raise SystemExit("TRIGGER_FAILED_"+str(st))
sid=json.loads(b.decode()).get("id")
if not sid:raise SystemExit("NO_TRIGGER")
try:
 deadline=time.time()+420
 while time.time()<deadline:
  st,b=call("GET",furl(RECEIPT),allowed=(200,404))
  if st==200:
   v=json.loads(b.decode());print(json.dumps(v,ensure_ascii=False))
   if v.get("status")!="PASS":raise SystemExit("PRODUCTION_NOT_PASS")
   print("SEO_MULTILINGUAL_003_PASS");raise SystemExit(0)
  time.sleep(5)
 raise SystemExit("RECEIPT_TIMEOUT")
finally:
 call("DELETE",BASE+"schedule/%s/"%sid,allowed=(200,202,204,404,500,502,503,504))
