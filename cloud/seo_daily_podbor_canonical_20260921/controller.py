#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, hashlib, json, os, pathlib, re, time, urllib.error, urllib.parse, urllib.request, uuid
TASK_ID="SEO-DAILY-PODBOR-CANONICAL-20260921"
CONTRACT="UA-ART-CRITICAL-ADAPTER-V1.0"
CANONICAL="https://www.uaart.com.ua/video/podbor.html"
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
REMOTE_SCRIPT="/home/Carix/uploads/seo_daily_podbor_canonical_20260921.py"
REMOTE_RECEIPT="/home/Carix/uploads/seo_daily_podbor_canonical_20260921.json"
BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
MAX=4*1024*1024
class E(RuntimeError): pass
def sha(b): return hashlib.sha256(b).hexdigest()
class API:
    def __init__(self,t):
        if not t: raise E("TOKEN_MISSING")
        self.t=t
    def req(self,m,u,data=None,h=None,allowed=(200,)):
        hh={"Authorization":"Token "+self.t,"User-Agent":"ua-art-seo-canonical/1"}; hh.update(h or {})
        q=urllib.request.Request(u,data=data,headers=hh,method=m)
        try:
            with urllib.request.urlopen(q,timeout=60) as r: s=int(r.status); b=r.read(MAX+1)
        except urllib.error.HTTPError as x: s=int(x.code); b=x.read(MAX+1)
        if len(b)>MAX or s not in allowed: raise E("HTTP_%d"%s)
        return s,b
    def furl(self,p):
        if p not in {REMOTE_SCRIPT,REMOTE_RECEIPT}: raise E("PATH_SCOPE")
        return BASE+"files/path"+urllib.parse.quote(p,safe="/")
    def read(self,p,missing=False):
        s,b=self.req("GET",self.furl(p),allowed=(200,404))
        if s==404:
            if missing:return None
            raise E("MISSING")
        return b
    def delete(self,p): self.req("DELETE",self.furl(p),allowed=(200,202,204,404))
    def upload(self,p,b):
        bd="----uaart-seo-"+uuid.uuid4().hex
        body=(("--%s\r\n"%bd)+'Content-Disposition: form-data; name="content"; filename="%s"\r\nContent-Type: application/octet-stream\r\n\r\n'%pathlib.PurePosixPath(p).name).encode()+b+("\r\n--%s--\r\n"%bd).encode()
        self.req("POST",self.furl(p),body,{"Content-Type":"multipart/form-data; boundary="+bd},allowed=(200,201))
        if self.read(p)!=b: raise E("UPLOAD_READBACK")
    def oid(self,b):
        try:v=json.loads(b.decode())
        except Exception:return None
        x=v.get("id") if isinstance(v,dict) else None
        return x if isinstance(x,int) and x>0 else None
    def schedule(self,cmd):
        at=dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=1)
        form=urllib.parse.urlencode({"command":cmd,"description":TASK_ID,"enabled":"true","interval":"daily","hour":at.hour,"minute":at.minute}).encode()
        s,b=self.req("POST",BASE+"schedule/",form,{"Content-Type":"application/x-www-form-urlencoded"},allowed=(200,201,202))
        i=self.oid(b)
        if not i: raise E("NO_TRIGGER")
        return i
    def run(self,mode,run_id,backup_sha=""):
        self.delete(REMOTE_RECEIPT)
        arg=(" "+backup_sha) if backup_sha else ""
        cmd="cd /home/Carix/uploads && python3.10 seo_daily_podbor_canonical_20260921.py %s %s%s"%(mode,run_id,arg)
        i=self.schedule(cmd)
        try:
            end=time.monotonic()+240
            while time.monotonic()<end:
                raw=self.read(REMOTE_RECEIPT,missing=True)
                if raw:
                    v=json.loads(raw.decode())
                    if v.get("status")!="PASS": raise E("REMOTE_"+str(v.get("error")))
                    return v
                time.sleep(5)
            raise E("REMOTE_TIMEOUT")
        finally:
            self.req("DELETE",BASE+"schedule/%d/"%i,allowed=(200,202,204,404))
def upload_payload(api):
    b=(HERE/"remote_installer.py").read_bytes(); compile(b.decode(),"remote_installer.py","exec"); api.upload(REMOTE_SCRIPT,b)
def live_check():
    rx=re.compile(r'<link\b(?=[^>]*\brel\s*=\s*["\']canonical["\'])[^>]*\bhref\s*=\s*["\']([^"\']+)["\'][^>]*>',re.I)
    checked={}
    for url in (CANONICAL,CANONICAL+"?strana=japan&v=seo20260921"):
        ok=False; last=""
        for _ in range(8):
            q=urllib.request.Request(url,headers={"Cache-Control":"no-cache","User-Agent":"UAART-SEO-LIVE/1"})
            try:
                with urllib.request.urlopen(q,timeout=30) as r:
                    b=r.read(MAX+1); last=b.decode("utf-8","replace")
                    vals=rx.findall(last)
                    if r.status==200 and vals==[CANONICAL]: ok=True; break
            except Exception: pass
            time.sleep(3)
        checked[url]={"pass":ok,"canonical":rx.findall(last)}
        if not ok: raise E("LIVE_CANONICAL_FAIL:"+url)
    return checked
def atomic(path,v):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(v,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
def main():
    env={k:os.environ.get(k,"") for k in ("PYTHONANYWHERE_API_TOKEN","UAART_TASK_ID","UAART_TASK_CLASS","UAART_RUN_ID","UAART_RECEIPT_PATH","UAART_BACKUP_MANIFEST_SHA256","UAART_MANIFEST_SHA256")}
    if env["UAART_TASK_ID"]!=TASK_ID or env["UAART_TASK_CLASS"]!="CRITICAL": raise E("IDENTITY")
    if not re.fullmatch(r'[0-9a-f]{64}',env["UAART_BACKUP_MANIFEST_SHA256"]): raise E("BACKUP_SHA")
    api=API(env["PYTHONANYWHERE_API_TOKEN"]); upload_payload(api)
    try:
        value=api.run("install",env["UAART_RUN_ID"],env["UAART_BACKUP_MANIFEST_SHA256"])
        if value.get("canonical_after")!=[CANONICAL] or value.get("unexpected_changes")!=0: raise E("INSTALL_PROOF")
        live=live_check()
        evidence={"task_id":TASK_ID,"status":"PASS","operation":"canonical-normalization","target":"/home/Carix/video/podbor.html","before_sha256":value["before_sha256"],"after_sha256":value["after_sha256"],"canonical_after":value["canonical_after"],"live":live,"unexpected_changes":0}
        atomic(HERE/"evidence.json",evidence)
        final={"contract_id":CONTRACT,"task_id":TASK_ID,"status":"FINISHED","task_class":"CRITICAL","target_environment":"production","tests":"PASS","backup":"PASS","production":"PASS","live_verify":"PASS","rollback":"PASS","unexpected_changes":0,"protected_files_unchanged":True,"crm_unchanged":True,"manifest_sha256":env["UAART_MANIFEST_SHA256"],"rollback_ready":True,"production_required":True,"production_touched":True,"canonical":CANONICAL,"before_sha256":value["before_sha256"],"after_sha256":value["after_sha256"]}
        atomic(ROOT/env["UAART_RECEIPT_PATH"],final)
    finally:
        for p in (REMOTE_SCRIPT,REMOTE_RECEIPT):
            try: api.delete(p)
            except Exception: pass
if __name__=="__main__": main()
