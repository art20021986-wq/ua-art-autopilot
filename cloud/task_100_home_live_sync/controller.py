#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, json, mimetypes, os, pathlib, time, urllib.error, urllib.parse, urllib.request, uuid

ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
REMOTE="/home/Carix/autopilot_inbox/cloud/task_100_home_live_sync"
BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
FILES={"remote_patch.py":HERE/"remote_patch.py","home_counter_guard.py":ROOT/"cloud/task_093_home_stage_counter_sync/home_counter_guard.py"}
RECEIPT=REMOTE+"/receipt.json"
EVIDENCE=HERE/"evidence.json"
MAX=12*1024*1024

class E(RuntimeError): pass
class API:
    def __init__(self):
        self.token=(os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
        if not self.token: raise E("TOKEN_MISSING")
    def request(self,method,url,data=None,headers=None,allowed=(200,),timeout=90):
        h={"Authorization":"Token "+self.token,"User-Agent":"ua-art-task100/1"}; h.update(headers or {})
        req=urllib.request.Request(url,data=data,headers=h,method=method)
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r: status=int(r.status); body=r.read(MAX+1)
        except urllib.error.HTTPError as x: status=int(x.code); body=x.read(MAX+1)
        except Exception as x: raise E("NETWORK:"+type(x).__name__) from x
        if len(body)>MAX: raise E("RESPONSE_TOO_LARGE")
        if status not in allowed: raise E("HTTP_%d:%s"%(status,urllib.parse.urlsplit(url).path))
        return status,body
    def file_url(self,p):
        if not p.startswith(REMOTE+"/"): raise E("PATH_SCOPE")
        return BASE+"files/path"+urllib.parse.quote(p,safe="/")
    def read(self,p,missing=False):
        s,b=self.request("GET",self.file_url(p),allowed=(200,404))
        if s==404:
            if missing:return None
            raise E("MISSING:"+p)
        return b
    def delete_file(self,p): self.request("DELETE",self.file_url(p),allowed=(204,404))
    def upload(self,p,data):
        boundary="----task100-"+uuid.uuid4().hex; name=pathlib.PurePosixPath(p).name; mime=mimetypes.guess_type(name)[0] or "application/octet-stream"
        body=(("--%s\r\n"%boundary)+('Content-Disposition: form-data; name="content"; filename="%s"\r\nContent-Type: %s\r\n\r\n'%(name,mime))).encode()+data+("\r\n--%s--\r\n"%boundary).encode()
        for i in range(1,6):
            s,_=self.request("POST",self.file_url(p),body,{"Content-Type":"multipart/form-data; boundary="+boundary},allowed=(200,201,429,500,502,503,504))
            if s in (200,201):
                if self.read(p)!=data: raise E("UPLOAD_READBACK:"+name)
                return
            time.sleep(i*3)
        raise E("UPLOAD_FAILED:"+name)
    def schedule(self,command):
        when=dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=1)
        form=urllib.parse.urlencode({"command":command,"description":"TASK100 homepage counts + WhatsApp opacity","enabled":"true","interval":"daily","hour":when.hour,"minute":when.minute}).encode()
        _,b=self.request("POST",BASE+"schedule/",form,{"Content-Type":"application/x-www-form-urlencoded"},allowed=(200,201,202))
        try: v=json.loads(b.decode()); ident=v.get("id") if isinstance(v,dict) else None
        except Exception: ident=None
        if not isinstance(ident,int): raise E("SCHEDULE_ID")
        return ident
    def delete_schedule(self,i): self.request("DELETE",BASE+"schedule/%d/"%i,allowed=(200,202,204,404))
def main():
    EVIDENCE.parent.mkdir(parents=True,exist_ok=True)
    out={"status":"FAIL","production_write":False}
    api=API()
    try:
        api.delete_file(RECEIPT)
        for name,path in FILES.items():
            data=path.read_bytes(); compile(data.decode("utf-8"),name,"exec"); api.upload(REMOTE+"/"+name,data)
        ident=api.schedule("cd %s && python3.10 remote_patch.py"%REMOTE)
        try:
            deadline=time.monotonic()+600
            while time.monotonic()<deadline:
                raw=api.read(RECEIPT,missing=True)
                if raw:
                    out=json.loads(raw.decode("utf-8")); break
                time.sleep(5)
            else: raise E("RECEIPT_TIMEOUT")
        finally: api.delete_schedule(ident)
        if out.get("status")!="PASS": raise E("REMOTE_FAIL:"+",".join(out.get("errors") or []))
        counts=out.get("counts") or {}
        if counts.get("all")!=sum(int(counts.get(k,0)) for k in ("kiev","georgia","sea","korea")): raise E("COUNT_INVARIANT")
        if int(counts.get("all",0))<16: raise E("TOTAL_BELOW_16")
        if out.get("whatsapp_opacity")!=0.90 or out.get("crm_write") is not False or out.get("crm_file_unchanged") is not True: raise E("SAFETY_RESULT")
    except Exception as x:
        if out.get("status")=="PASS": out={"status":"FAIL","production_write":out.get("production_write",False),"errors":[type(x).__name__+":"+str(x)]}
        elif "errors" not in out: out["errors"]=[type(x).__name__+":"+str(x)]
    EVIDENCE.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,sort_keys=True))
    return 0 if out.get("status")=="PASS" else 1
if __name__=="__main__": raise SystemExit(main())
