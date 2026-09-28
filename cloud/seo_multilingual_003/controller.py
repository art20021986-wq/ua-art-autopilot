#!/usr/bin/env python3
# retry after runtime ROOT preflight fix
import json, os, socket, time, urllib.error, urllib.parse, urllib.request, uuid
TOKEN=(os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
LOCAL="cloud/seo_multilingual_003/patcher.py"
REMOTE="/home/Carix/autopilot_inbox/cloud/seo_multilingual_003/patcher.py"
RECEIPT="/home/Carix/archive/reports/SEO_MULTILINGUAL_003.json"
COMMAND="python3.10 "+REMOTE
if not TOKEN: raise SystemExit("MISSING_TOKEN")
def call(method,url,data=None,headers=None,allowed=(200,)):
 h={"Authorization":"Token "+TOKEN,"User-Agent":"ua-art-seo-multilingual-003/3"};h.update(headers or {})
 try:
  with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=h,method=method),timeout=45) as r:return r.status,r.read()
 except urllib.error.HTTPError as e:
  b=e.read()
  if e.code in allowed or e.code>=500:return e.code,b
  raise
 except (TimeoutError,socket.timeout) as e:return 0,str(e).encode()
 except Exception as e:return 0,str(e).encode()
def furl(p):return BASE+"files/path"+urllib.parse.quote(p,safe="/")
def collection(b):
 try:v=json.loads(b.decode())
 except:return []
 if isinstance(v,list):return v
 if isinstance(v,dict):
  for k in ("tasks","objects","results"):
   if isinstance(v.get(k),list):return v[k]
  if all(isinstance(x,dict) for x in v.values()):return list(v.values())
 return []
# Remove only stale triggers for this exact command.
for endpoint in ("always_on","schedule"):
 st,b=call("GET",BASE+endpoint+"/",allowed=(200,404))
 if st==200:
  for item in collection(b):
   if isinstance(item,dict) and str(item.get("command","")).strip()==COMMAND and item.get("id") is not None:
    call("DELETE",BASE+endpoint+"/%s/"%item["id"],allowed=(200,202,204,404,500,502,503,504))
raw=open(LOCAL,"rb").read();bd="----seo"+uuid.uuid4().hex
body=(("--"+bd+"\r\nContent-Disposition: form-data; name=\"content\"; filename=\"patcher.py\"\r\nContent-Type: text/x-python\r\n\r\n").encode()+raw+("\r\n--"+bd+"--\r\n").encode())
uploaded=False
for attempt in range(1,6):
 st,_=call("POST",furl(REMOTE),body,{"Content-Type":"multipart/form-data; boundary="+bd},(200,201,500,502,503,504))
 if st in (200,201):uploaded=True;break
 if attempt<5:time.sleep(min(attempt*3,12))
if not uploaded:raise SystemExit("UPLOAD_FAILED")
call("DELETE",furl(RECEIPT),allowed=(200,204,404,500,502,503,504))
run=time.gmtime(time.time()+120)
form=urllib.parse.urlencode({"command":COMMAND,"description":"seo-multilingual-003-once","enabled":"true","interval":"daily","hour":run.tm_hour,"minute":run.tm_min}).encode()
st,b=call("POST",BASE+"schedule/",form,{"Content-Type":"application/x-www-form-urlencoded"},(200,201,202))
if st not in (200,201,202):raise SystemExit("TRIGGER_FAILED_"+str(st))
try:sid=json.loads(b.decode()).get("id")
except:sid=None
if not sid:raise SystemExit("NO_TRIGGER")
try:
 deadline=time.time()+900
 while time.time()<deadline:
  st,b=call("GET",furl(RECEIPT),allowed=(200,404,500,502,503,504))
  if st==200:
   v=json.loads(b.decode());print(json.dumps(v,ensure_ascii=False))
   if v.get("status")!="PASS":raise SystemExit("PRODUCTION_NOT_PASS")
   print("SEO_MULTILINGUAL_003_PASS");raise SystemExit(0)
  time.sleep(5)
 raise SystemExit("RECEIPT_TIMEOUT")
finally:
 call("DELETE",BASE+"schedule/%s/"%sid,allowed=(200,202,204,404,500,502,503,504))
