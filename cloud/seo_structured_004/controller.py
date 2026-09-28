#!/usr/bin/env python3
import json, os, socket, time, urllib.error, urllib.parse, urllib.request, uuid
TOKEN=(os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip();BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
LOCAL="cloud/seo_structured_004/probe.py";REMOTE="/home/Carix/autopilot_inbox/cloud/seo_structured_004/probe.py";RECEIPT="/home/Carix/archive/reports/SEO_STRUCTURED_004_GATE_A.json";COMMAND="python3.10 "+REMOTE
if not TOKEN:raise SystemExit("MISSING_TOKEN")
def call(method,url,data=None,headers=None,allowed=(200,)):
 h={"Authorization":"Token "+TOKEN,"User-Agent":"ua-art-seo-structured-004-gate-a/1"};h.update(headers or {})
 try:
  with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=h,method=method),timeout=45) as r:return r.status,r.read()
 except urllib.error.HTTPError as e:
  b=e.read()
  if e.code in allowed or e.code>=500:return e.code,b
  raise
 except (TimeoutError,socket.timeout):return 0,b"timeout"
def furl(p):return BASE+"files/path"+urllib.parse.quote(p,safe="/")
raw=open(LOCAL,"rb").read();bd="----seo"+uuid.uuid4().hex
body=(("--"+bd+"\r\nContent-Disposition: form-data; name=\"content\"; filename=\"probe.py\"\r\nContent-Type: text/x-python\r\n\r\n").encode()+raw+("\r\n--"+bd+"--\r\n").encode())
st,_=call("POST",furl(REMOTE),body,{"Content-Type":"multipart/form-data; boundary="+bd},(200,201))
if st not in (200,201):raise SystemExit("UPLOAD_"+str(st))
call("DELETE",furl(RECEIPT),allowed=(200,204,404))
run=time.gmtime(time.time()+60);form=urllib.parse.urlencode({"command":COMMAND,"description":"seo-structured-004-gate-a","enabled":"true","interval":"daily","hour":run.tm_hour,"minute":run.tm_min}).encode()
st,b=call("POST",BASE+"schedule/",form,{"Content-Type":"application/x-www-form-urlencoded"},(200,201,202))
if st not in (200,201,202):raise SystemExit("TRIGGER_"+str(st))
sid=json.loads(b.decode()).get("id")
try:
 deadline=time.time()+360
 while time.time()<deadline:
  st,b=call("GET",furl(RECEIPT),allowed=(200,404,500,502,503,504))
  if st==200:
   v=json.loads(b.decode());print(json.dumps(v,ensure_ascii=False))
   if v.get("status")!="PASS":raise SystemExit("GATE_A_FAIL")
   print("SEO_STRUCTURED_004_GATE_A_PASS");raise SystemExit(0)
  time.sleep(5)
 raise SystemExit("RECEIPT_TIMEOUT")
finally:
 if sid:call("DELETE",BASE+"schedule/%s/"%sid,allowed=(200,202,204,404,500,502,503,504))
