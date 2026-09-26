import datetime as dt,json,os,pathlib,time,urllib.error,urllib.parse,urllib.request,uuid
TASK_ID='CRM-CONSISTENCY-PREVIEW-20260926'
REMOTE_SCRIPT='/home/Carix/uploads/crm_consistency_preview_20260926.py'
REMOTE_RECEIPT='/home/Carix/uploads/crm_consistency_preview_20260926.json'
BASE='https://www.pythonanywhere.com/api/v0/user/Carix/'
MAX=4*1024*1024
class E(RuntimeError):pass
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
        cmd="cd /home/Carix/uploads && python3.10 crm_consistency_preview_20260926.py %s %s%s"%(mode,run_id,arg)
        i=self.schedule(cmd + " > /dev/null 2>&1")
        try:
            end=time.monotonic()+240
            while time.monotonic()<end:
                raw=self.read(REMOTE_RECEIPT,missing=True)
                if raw:
                    v=json.loads(raw.decode())
                    if v.get("run_id")!=run_id: raise E("RECEIPT_RUN_ID")
                    return v
                time.sleep(5)
            raise E("REMOTE_TIMEOUT")
        finally:
            self.req("DELETE",BASE+"schedule/%d/"%i,allowed=(200,202,204,404))
