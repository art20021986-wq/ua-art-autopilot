#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, hashlib, json, mimetypes, os, pathlib, tempfile, time, urllib.error, urllib.parse, urllib.request, uuid
from typing import Any, Mapping

TASK_ID="TASK088-GE-PRICE-CRM-STAGE1"
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE_DIR="/home/Carix/autopilot_inbox/cloud/task_088_ge_price_crm_stage1"
REMOTE_SCRIPT=REMOTE_DIR+"/remote_installer.py"
REMOTE_RECEIPT=REMOTE_DIR+"/receipt.json"
RECEIPT_REL="state/receipts/TASK088-GE-PRICE-CRM-STAGE1.json"
EVIDENCE_REL="cloud/task_088_ge_price_crm_stage1/evidence.json"
MAX_BYTES=8*1024*1024

class E(RuntimeError): pass
def now(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def sha(b:bytes)->str: return hashlib.sha256(b).hexdigest()
def atomic(path:pathlib.Path, value:dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as h:
            json.dump(value,h,ensure_ascii=False,sort_keys=True,indent=2); h.write("\n"); h.flush(); os.fsync(h.fileno())
        os.replace(tmp,path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

class API:
    def __init__(self, token): self.token=token
    def req(self, method,url,data=None,headers=None,allowed=(200,)):
        hs={"Authorization":"Token "+self.token,"User-Agent":"ua-art-task088/1"}; hs.update(headers or {})
        r=urllib.request.Request(url,data=data,headers=hs,method=method)
        try:
            with urllib.request.urlopen(r,timeout=90) as x: status,body=x.status,x.read(MAX_BYTES+1)
        except urllib.error.HTTPError as x: status,body=x.code,x.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES or status not in allowed: raise E(f"HTTP_{status}")
        return status,body
    def furl(self,path):
        p=pathlib.PurePosixPath(path); root=pathlib.PurePosixPath(REMOTE_DIR)
        if not p.is_absolute() or root not in p.parents or ".." in p.parts: raise E("REMOTE_SCOPE")
        return BASE+"files/path"+urllib.parse.quote(path,safe="/")
    def read(self,path,missing=False):
        s,b=self.req("GET",self.furl(path),allowed=(200,404))
        if s==404:
            if missing:return None
            raise E("REMOTE_MISSING")
        return b
    def delete(self,path): self.req("DELETE",self.furl(path),allowed=(200,202,204,404))
    def upload(self,path,value):
        boundary="----uaart-"+uuid.uuid4().hex; filename=pathlib.PurePosixPath(path).name
        body=(f"--{boundary}\r\nContent-Disposition: form-data; name=\"content\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()+value+(f"\r\n--{boundary}--\r\n").encode()
        self.req("POST",self.furl(path),body,{"Content-Type":"multipart/form-data; boundary="+boundary},allowed=(200,201))
        if self.read(path)!=value: raise E("UPLOAD_READBACK")
    def trigger(self,command):
        form=urllib.parse.urlencode({"command":command,"description":TASK_ID,"enabled":"true"}).encode()
        s,b=self.req("POST",BASE+"always_on/",form,{"Content-Type":"application/x-www-form-urlencoded"},allowed=(200,201,202,400,403,404,409))
        ident=None
        if s in (200,201,202):
            try: ident=json.loads(b.decode()).get("id")
            except Exception: pass
        if ident: return ("always_on",int(ident))
        at=dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=2)
        form=urllib.parse.urlencode({"command":command,"description":TASK_ID+" fallback","enabled":"true","interval":"daily","hour":at.hour,"minute":at.minute}).encode()
        _,b=self.req("POST",BASE+"schedule/",form,{"Content-Type":"application/x-www-form-urlencoded"},allowed=(200,201,202))
        ident=json.loads(b.decode()).get("id")
        if not ident: raise E("NO_TRIGGER")
        return ("schedule",int(ident))
    def delete_trigger(self,t):
        self.req("DELETE",BASE+f"{t[0]}/{t[1]}/",allowed=(200,202,204,404))
    def run(self):
        self.delete(REMOTE_RECEIPT)
        t=self.trigger(f"cd {REMOTE_DIR} && python3.10 remote_installer.py")
        try:
            end=time.monotonic()+900
            while time.monotonic()<end:
                raw=self.read(REMOTE_RECEIPT,True)
                if raw:
                    v=json.loads(raw.decode("utf-8"))
                    if not isinstance(v,dict): raise E("RECEIPT_INVALID")
                    return v
                time.sleep(5)
            raise E("REMOTE_TIMEOUT")
        finally: self.delete_trigger(t)

def execute(env:Mapping[str,str])->dict[str,Any]:
    token=env.get("PYTHONANYWHERE_API_TOKEN","").strip()
    if not token: raise E("TOKEN_MISSING")
    request_path=env.get("UAART_REQUEST_PATH","")
    request_sha=env.get("UAART_REQUEST_SHA256","")
    run_id=env.get("UAART_RUN_ID","")
    if env.get("UAART_TASK_ID")!=TASK_ID or env.get("UAART_RECEIPT_PATH")!=RECEIPT_REL: raise E("IDENTITY")
    rp=(ROOT/request_path).resolve()
    if not rp.is_relative_to(ROOT.resolve()) or sha(rp.read_bytes())!=request_sha: raise E("REQUEST_IDENTITY")
    api=API(token)
    script=(HERE/"remote_installer.py").read_bytes()
    compile(script.decode("utf-8"),"remote_installer.py","exec")
    api.upload(REMOTE_SCRIPT,script)
    remote=api.run()
    if remote.get("task_id")!=TASK_ID or remote.get("status")!="PASS": raise E("REMOTE_FAIL:"+str(remote.get("error")))
    if remote.get("site_write") is not False or remote.get("publisher_write") is not False or remote.get("stage2_touched") is not False: raise E("SCOPE")
    evidence={"task_id":TASK_ID,"status":"PASS","run_id":run_id,"request_sha256":request_sha,"remote":remote,"finished_at":now()}
    receipt={"task_id":TASK_ID,"status":"FINISHED","task_class":"CRITICAL","production_required":False,"tests":"PASS","live_verify":"PASS","run_id":run_id,"request_sha256":request_sha,"unexpected_changes":0,"site_unchanged":True,"publisher_unchanged":True,"stage2_unchanged":True,"finished_at":now()}
    atomic(ROOT/EVIDENCE_REL,evidence); atomic(ROOT/RECEIPT_REL,receipt)
    return receipt

if __name__=="__main__":
    execute(os.environ)
