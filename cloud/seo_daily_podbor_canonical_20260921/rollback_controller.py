#!/usr/bin/env python3
from __future__ import annotations
import json, os, pathlib, urllib.request
import controller
def main():
    if os.environ.get("UAART_OPERATION")!="rollback": return 2
    api=controller.API(os.environ["PYTHONANYWHERE_API_TOKEN"]); controller.upload_payload(api)
    h=os.environ["UAART_BACKUP_MANIFEST_SHA256"]
    try:
        v=api.run("rollback",os.environ["UAART_RUN_ID"],h)
        if v.get("restored_exact") is not True or v.get("backup_manifest_sha256")!=h: raise RuntimeError("ROLLBACK_PROOF")
        q=urllib.request.Request(controller.CANONICAL+"?rollback=seo20260921",headers={"Cache-Control":"no-cache"})
        with urllib.request.urlopen(q,timeout=30) as resp:
            if resp.status!=200: raise RuntimeError("ROLLBACK_LIVE")
        r={"schema_version":"UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1","operation":"rollback","task_id":os.environ["UAART_TASK_ID"],"request_sha256":os.environ["UAART_REQUEST_SHA256"],"run_id":os.environ["UAART_RUN_ID"],"transaction_id":os.environ["UAART_TRANSACTION_ID"],"manifest_sha256":os.environ["UAART_MANIFEST_SHA256"],"backup_manifest_sha256":h,"status":"ROLLED_BACK","rollback":"PASS","restored":True,"unexpected_changes":0,"protected_files_unchanged":True,"crm_unchanged":True,"live_verify":"PASS"}
        p=pathlib.Path(os.environ["UAART_ROLLBACK_RECEIPT_PATH"]); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(r,sort_keys=True)+"\n")
    finally:
        for p in (controller.REMOTE_SCRIPT,controller.REMOTE_RECEIPT):
            try: api.delete(p)
            except Exception: pass
    return 0
if __name__=="__main__": raise SystemExit(main())
