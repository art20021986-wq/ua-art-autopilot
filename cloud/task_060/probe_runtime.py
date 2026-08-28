#!/usr/bin/env python3
"""TASK 060: run one bounded capability probe in the PythonAnywhere safe inbox."""
from __future__ import annotations
import datetime as dt, json, os, pathlib, time, urllib.parse, urllib.request

BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
RECEIPT="/home/Carix/autopilot_inbox/cloud/task_060/runtime_probe.json"
OUT=pathlib.Path("cloud/task_060/evidence/runtime_capabilities.json")
CODE=(
'import importlib.util,json,pathlib,shutil,sys;'
'mods=["PIL","pytesseract","cv2","easyocr","rapidocr_onnxruntime","onnxruntime","torch"];'
'r={"python":sys.version.split()[0],"modules":{m:bool(importlib.util.find_spec(m)) for m in mods},'
'"binaries":{b:shutil.which(b) for b in ["tesseract","ffmpeg"]}};'
'pathlib.Path("'+RECEIPT+'").write_text(json.dumps(r,sort_keys=True),encoding="utf-8")'
)
COMMAND="python3.10 -c "+repr(CODE)

class API:
    def __init__(self):
        self.token=os.environ["PYTHONANYWHERE_API_TOKEN"]
    def request(self,method,url,data=None,allowed=(200,)):
        headers={"Authorization":"Token "+self.token,"User-Agent":"ua-art-task060-probe/1"}
        if data is not None: headers["Content-Type"]="application/x-www-form-urlencoded"
        req=urllib.request.Request(url,data=data,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=60) as resp:
                return resp.status,resp.read(100000)
        except urllib.error.HTTPError as exc:
            body=exc.read(100000)
            if exc.code in allowed: return exc.code,body
            raise
    def file_url(self,path):
        return BASE+"files/path"+urllib.parse.quote(path,safe="/")
    def read(self):
        status,body=self.request("GET",self.file_url(RECEIPT),allowed=(200,404))
        return body if status==200 else None
    def delete_receipt(self):
        self.request("DELETE",self.file_url(RECEIPT),allowed=(204,404))
    def create(self):
        form=urllib.parse.urlencode({"command":COMMAND,"description":"TASK 060 OCR runtime probe","enabled":"true"}).encode()
        status,body=self.request("POST",BASE+"always_on/",form,allowed=(200,201,202,400,403,404,409))
        value=json.loads(body.decode()) if status in (200,201,202) and body else {}
        ident=value.get("id")
        if isinstance(ident,int): return ("always_on",ident)
        run_at=dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=2)
        form=urllib.parse.urlencode({"command":COMMAND,"description":"TASK 060 OCR runtime probe fallback",
                                    "enabled":"true","interval":"daily","hour":run_at.hour,"minute":run_at.minute}).encode()
        status,body=self.request("POST",BASE+"schedule/",form,allowed=(200,201,202,400,403,404,409))
        value=json.loads(body.decode()) if status in (200,201,202) and body else {}
        ident=value.get("id")
        if not isinstance(ident,int): raise RuntimeError("TRIGGER_ID_MISSING")
        return ("schedule",ident)
    def delete(self,trigger):
        kind,ident=trigger
        endpoint="always_on" if kind=="always_on" else "schedule"
        self.request("DELETE",BASE+endpoint+"/%d/"%ident,allowed=(200,202,204,404))

def main():
    api=API(); trigger=None
    try:
        api.delete_receipt()
        trigger=api.create()
        deadline=time.monotonic()+360
        raw=None
        while time.monotonic()<deadline:
            raw=api.read()
            if raw: break
            time.sleep(3)
        if not raw: raise RuntimeError("PROBE_TIMEOUT")
        value=json.loads(raw.decode("utf-8"))
        value.update({"task_id":"task_060","mode":"READ_ONLY_RUNTIME_CAPABILITIES","production_touched":False,
                      "recorded_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()})
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(json.dumps({"status":"PASS","production_touched":False}))
    finally:
        if trigger is not None:
            try: api.delete(trigger)
            except Exception: pass
        try: api.delete_receipt()
        except Exception: pass
if __name__=="__main__": main()
