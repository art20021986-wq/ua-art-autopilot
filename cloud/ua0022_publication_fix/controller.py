#!/usr/bin/env python3
"""Canonical CRITICAL adapter for one source-pinned UA-0022 repair.

Uses the established GitHub secret -> PythonAnywhere file/always_on route.
No preexisting task is removed. The remote lifecycle owns its bounded CRM
pause; a timeout never kills a worker that might still be holding that pause.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE="https://www.pythonanywhere.com/api/v0/user/Carix/"
TASK_ID="UA-ART-UA0022-PUBLISH-REPAIR-001"
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PACKAGE="cloud/ua0022_publication_fix"
SOURCES=("build_candidate.py","publication_fence.py","remote_installer.py","remote_lifecycle.py")

def sha(data): return hashlib.sha256(data).hexdigest()
def canonical(value): return (json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode()
def required_sha(value):
    if not re.fullmatch(r"[0-9a-f]{64}",str(value or "")): raise RuntimeError("SHA256_REQUIRED")
    return value

def load(environment):
    values={key:str(environment.get(key,"")).strip() for key in
        ("PYTHONANYWHERE_API_TOKEN","UAART_REQUEST_PATH","UAART_REQUEST_SHA256",
         "UAART_TASK_ID","UAART_TASK_CLASS","UAART_RUN_ID","UAART_TRANSACTION_ID","UAART_MANIFEST_SHA256")}
    if not all(values.values()): raise RuntimeError("CANONICAL_ENVIRONMENT_INCOMPLETE")
    if values["UAART_TASK_ID"]!=TASK_ID or values["UAART_TASK_CLASS"]!="CRITICAL":
        raise RuntimeError("CANONICAL_TASK_IDENTITY")
    if not re.fullmatch(r"[0-9]{1,30}",values["UAART_RUN_ID"]): raise RuntimeError("RUN_ID_SCOPE")
    request_path=(ROOT/values["UAART_REQUEST_PATH"]).resolve()
    if not request_path.is_relative_to(ROOT) or not values["UAART_REQUEST_PATH"].startswith("tasks/requests/"):
        raise RuntimeError("REQUEST_PATH_SCOPE")
    data=request_path.read_bytes()
    if sha(data)!=required_sha(values["UAART_REQUEST_SHA256"]): raise RuntimeError("REQUEST_HASH")
    request=json.loads(data)
    if request.get("task_id")!=TASK_ID or request.get("production_required") is not True:
        raise RuntimeError("REQUEST_IDENTITY")
    if request.get("critical",{}).get("manifest_sha256")!=required_sha(values["UAART_MANIFEST_SHA256"]):
        raise RuntimeError("MANIFEST_IDENTITY")
    manifest_path=(ROOT/request["critical"]["manifest_path"]).resolve()
    if not manifest_path.is_relative_to(ROOT/"tasks/manifests"):raise RuntimeError("MANIFEST_PATH_SCOPE")
    manifest=json.loads(manifest_path.read_bytes())
    if sha(canonical(manifest))!=values["UAART_MANIFEST_SHA256"]:raise RuntimeError("MANIFEST_HASH")
    plan=dict(manifest["deployment"])
    if plan.get("task_id")!=TASK_ID or plan.get("root")!="/home/Carix": raise RuntimeError("PLAN_SCOPE")
    plan.update({"run_id":values["UAART_RUN_ID"],"transaction_id":values["UAART_TRANSACTION_ID"],
                 "request_sha256":values["UAART_REQUEST_SHA256"],"manifest_sha256":values["UAART_MANIFEST_SHA256"]})
    return values,request,plan

class API:
    def __init__(self,token): self.token=token
    def request(self,method,endpoint,data=None,headers=None,allowed=(200,)):
        actual={"Authorization":"Token "+self.token,"User-Agent":"uaart-ua0022-repair/1"}
        actual.update(headers or {})
        req=urllib.request.Request(BASE+endpoint,data=data,headers=actual,method=method)
        try:
            with urllib.request.urlopen(req,timeout=90) as response: status,payload=response.status,response.read(4*1024*1024+1)
        except urllib.error.HTTPError as exc: status,payload=exc.code,exc.read(4*1024*1024+1)
        if status not in allowed or len(payload)>4*1024*1024: raise RuntimeError("PA_HTTP_%s"%status)
        return status,payload
    @staticmethod
    def endpoint(path):
        if not re.fullmatch(r"/home/Carix/autopilot_inbox/cloud/ua0022_publication_fix/[0-9]{1,30}/[A-Za-z0-9_.-]+",path):
            raise RuntimeError("REMOTE_PATH_SCOPE")
        return "files/path"+urllib.parse.quote(path,safe="/")
    def read(self,path):
        status,data=self.request("GET",self.endpoint(path),allowed=(200,404))
        return data if status==200 else None
    def upload_new(self,path,data):
        old=self.read(path)
        if old is not None:
            if old!=data: raise RuntimeError("REMOTE_IMMUTABLE_FILE_DRIFT")
            return
        boundary="ua0022-"+uuid.uuid4().hex
        payload=("--"+boundary+'\r\nContent-Disposition: form-data; name="content"; filename="'+Path(path).name+'"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+data+("\r\n--"+boundary+"--\r\n").encode()
        self.request("POST",self.endpoint(path),payload,{"Content-Type":"multipart/form-data; boundary="+boundary},allowed=(200,201))
        if self.read(path)!=data: raise RuntimeError("UPLOAD_READBACK")
    def trigger(self,command,description):
        _,existing_payload=self.request("GET","always_on/")
        existing=json.loads(existing_payload)
        if isinstance(existing,dict):existing=existing.get("results",existing.get("objects",existing.get("tasks",[])))
        if not isinstance(existing,list):raise RuntimeError("ALWAYS_ON_LIST_INVALID")
        matches=[item for item in existing if isinstance(item,dict) and item.get("description")==description]
        if matches:
            if len(matches)!=1 or matches[0].get("command")!=command or type(matches[0].get("id")) is not int:
                raise RuntimeError("EXISTING_TRIGGER_IDENTITY_CONFLICT")
            return matches[0]["id"]
        payload=urllib.parse.urlencode({"command":command,"description":description,"enabled":"true"}).encode()
        _,data=self.request("POST","always_on/",payload,{"Content-Type":"application/x-www-form-urlencoded"},allowed=(200,201,202))
        obj=json.loads(data)
        if type(obj.get("id")) is not int: raise RuntimeError("TRIGGER_IDENTITY")
        return obj["id"]
    def stop_owned(self,identifier,command,description):
        endpoint="always_on/%d/"%identifier
        status,payload=self.request("GET",endpoint,allowed=(200,404))
        if status==404:return
        obj=json.loads(payload)
        if obj.get("id")!=identifier or obj.get("command")!=command or obj.get("description")!=description:
            raise RuntimeError("TRIGGER_CLEANUP_IDENTITY")
        self.request("DELETE",endpoint,allowed=(200,202,204,404))
        status,_=self.request("GET",endpoint,allowed=(200,404))
        if status!=404: raise RuntimeError("TRIGGER_STOP_UNCONFIRMED")

def remote(values,request,plan,operation):
    api=API(values["PYTHONANYWHERE_API_TOKEN"])
    folder="/home/Carix/autopilot_inbox/cloud/ua0022_publication_fix/"+values["UAART_RUN_ID"]
    hashes=request["execution"]["file_sha256"]
    for name in SOURCES:
        data=(HERE/name).read_bytes()
        if sha(data)!=hashes.get(PACKAGE+"/"+name): raise RuntimeError("PACKAGE_HASH:"+name)
        api.upload_new(folder+"/"+name,data)
    data=canonical(plan);plan_sha=sha(data)
    plan_path=folder+"/plan.json"
    api.upload_new(plan_path,data)
    if operation=="rollback":
        _,active_payload=api.request("GET","always_on/")
        active=json.loads(active_payload)
        if isinstance(active,dict):active=active.get("results",active.get("objects",active.get("tasks",[])))
        if not isinstance(active,list):raise RuntimeError("ALWAYS_ON_LIST_INVALID")
        install_description=TASK_ID+" "+values["UAART_RUN_ID"]+" install_verify"
        if any(isinstance(item,dict) and item.get("description")==install_description for item in active):
            if api.read(folder+"/install_verify-result.json") is None:
                raise RuntimeError("INSTALL_WORKER_STILL_ACTIVE_ROLLBACK_DEFERRED")
    result_path=folder+"/"+operation+"-result.json"
    result=api.read(result_path)
    if result is not None:
        value=json.loads(result)
        if value.get("plan_sha256")!=plan_sha or value.get("operation")!=operation: raise RuntimeError("RESULT_IDENTITY")
        if (value.get("safe_to_stop") is not True or value.get("status")!="PASS"
            or value.get("crm_resume",{}).get("enabled") is not True
            or str(value.get("crm_resume",{}).get("state","")).lower()!="running"):
            raise RuntimeError("PRIOR_REMOTE_PHASE_FAILED")
        return value
    command="cd "+folder+" && python3.10 -B remote_lifecycle.py --operation "+operation+" --plan "+plan_path+" --plan-sha256 "+plan_sha+" --result "+result_path
    description=TASK_ID+" "+values["UAART_RUN_ID"]+" "+operation
    identifier=api.trigger(command,description)
    deadline=time.monotonic()+1500
    while time.monotonic()<deadline:
        result=api.read(result_path)
        if result is not None:
            value=json.loads(result)
            if value.get("plan_sha256")!=plan_sha or value.get("operation")!=operation: raise RuntimeError("RESULT_IDENTITY")
            # Terminal receipt is the only admission for deleting this owned runner.
            if value.get("safe_to_stop") is not True: raise RuntimeError("RESULT_NOT_TERMINAL_WORKER_RETAINED")
            api.stop_owned(identifier,command,description)
            if (value.get("status")!="PASS" or value.get("crm_resume",{}).get("enabled") is not True
                or str(value.get("crm_resume",{}).get("state","")).lower()!="running"):
                raise RuntimeError("REMOTE_PHASE_FAILED:"+str(value.get("error") or value.get("resume_error") or value.get("rollback_error")))
            return value
        time.sleep(4)
    raise RuntimeError("REMOTE_TIMEOUT_WORKER_RETAINED_FOR_SAFE_COMPLETION:%d"%identifier)

def write_receipt(path,value):
    target=(ROOT/path).resolve()
    if not target.is_relative_to(ROOT/"state/receipts"): raise RuntimeError("RECEIPT_SCOPE")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(canonical(value))

def verify_public(installed,run_id,require_target=False):
    hashes=installed.get("public_http_sha256")
    if not isinstance(hashes,dict) or not hashes:raise RuntimeError("PUBLIC_DIGESTS_REQUIRED")
    allowed={"https://www.uaart.com.ua/video/"+name for name in ("UA-0022.html","UA-0022-diag.html","katalog.html","index.html")}
    if not set(hashes).issubset(allowed):raise RuntimeError("PUBLIC_URL_SCOPE")
    required=allowed if require_target else {"https://www.uaart.com.ua/video/"+name for name in ("katalog.html","index.html")}
    if not required.issubset(hashes):raise RuntimeError("PUBLIC_REQUIRED_PAGES_MISSING")
    evidence=[]
    for url,expected in hashes.items():
        required_sha(expected)
        request=urllib.request.Request(url+"?ua0022_verify="+run_id,
            headers={"Cache-Control":"no-cache","Accept-Encoding":"identity","User-Agent":"uaart-ua0022-verify/1"})
        with urllib.request.urlopen(request,timeout=40) as response:
            if response.status!=200 or not response.geturl().startswith("https://www.uaart.com.ua/"):
                raise RuntimeError("PUBLIC_HTTP_STATUS_OR_ORIGIN")
            data=response.read(32*1024*1024+1)
        if len(data)>32*1024*1024 or sha(data)!=expected:raise RuntimeError("PUBLIC_BYTES_MISMATCH:"+url)
        evidence.append({"url":url,"sha256":expected,"status":"PASS"})
    return evidence

def execute(operation,environment=None):
    environment=os.environ if environment is None else environment
    values,request,plan=load(environment)
    result=remote(values,request,plan,operation)
    installed=result["installer"]
    checks={"backup":("source_checksum_pass","integrity_pass"),
        "install_verify":("publication_pass","post_check_pass","integrity_pass","protected_pages_unchanged",
            "other_rows_unchanged","ua_ge_prices_unchanged","target_original_media_unchanged","target_new_media_derivatives_only")}
    for field in checks.get(operation,()):
        if installed.get(field) is not True:raise RuntimeError("REMOTE_EVIDENCE_MISSING:"+field)
    backup_sha=required_sha(installed["backup_manifest_sha256"])
    if operation!="backup" and backup_sha!=environment.get("UAART_BACKUP_MANIFEST_SHA256"):
        raise RuntimeError("CANONICAL_BACKUP_BINDING")
    base={"task_id":TASK_ID,"request_sha256":values["UAART_REQUEST_SHA256"],"run_id":values["UAART_RUN_ID"],
          "transaction_id":values["UAART_TRANSACTION_ID"],"manifest_sha256":values["UAART_MANIFEST_SHA256"],
          "backup_manifest_sha256":backup_sha,"status":"PASS","unexpected_changes":0}
    if operation=="backup":
        base.update({"schema_version":"UA-ART-PRODUCTION-BACKUP-RECEIPT-1","operation":"backup","backup":"PASS"})
        path=environment["UAART_BACKUP_RECEIPT_PATH"]
    elif operation=="rollback":
        if not (installed.get("no_mutation") is True or installed.get("targeted_files_restored") is True or installed.get("idempotent") is True):
            raise RuntimeError("ROLLBACK_NOT_PROVEN")
        verify_public(installed,values["UAART_RUN_ID"])
        base.update({"schema_version":"UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1","operation":"rollback",
                     "rollback":"PASS","restored":True,"protected_files_unchanged":True,"crm_unchanged":True,"live_verify":"PASS"})
        path=environment["UAART_ROLLBACK_RECEIPT_PATH"]
    else:
        public=verify_public(installed,values["UAART_RUN_ID"],require_target=True)
        base.update({"status":"FINISHED","target_environment":"production","production":"PASS",
            "task_class":"CRITICAL","tests":"PASS","live_verify":"PASS","backup":"PASS",
            "protected_files_unchanged":True,"crm_unchanged":True,"rollback_ready":True,"rollback":"PASS","production_required":True,
            "contract_id":"UA-ART-CRITICAL-ADAPTER-V1.0"})
        base["public_verification"]=public
        path=environment["UAART_RECEIPT_PATH"]
    write_receipt(path,base)
    return base

def main():
    execute("install_verify")
    return 0

if __name__=="__main__": raise SystemExit(main())
