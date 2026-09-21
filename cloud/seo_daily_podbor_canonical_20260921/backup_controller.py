#!/usr/bin/env python3
from __future__ import annotations
import json, os, pathlib, re
import controller
def main():
    if os.environ.get("UAART_OPERATION")!="backup": return 2
    api=controller.API(os.environ["PYTHONANYWHERE_API_TOKEN"]); controller.upload_payload(api)
    try:
        v=api.run("backup",os.environ["UAART_RUN_ID"])
        h=str(v.get("backup_manifest_sha256",""))
        if not re.fullmatch(r'[0-9a-f]{64}',h) or v.get("sandbox_validation")!="PASS": raise RuntimeError("BACKUP_PROOF")
        r={"schema_version":"UA-ART-PRODUCTION-BACKUP-RECEIPT-1","operation":"backup","task_id":os.environ["UAART_TASK_ID"],"request_sha256":os.environ["UAART_REQUEST_SHA256"],"run_id":os.environ["UAART_RUN_ID"],"transaction_id":os.environ["UAART_TRANSACTION_ID"],"manifest_sha256":os.environ["UAART_MANIFEST_SHA256"],"backup_manifest_sha256":h,"status":"PASS","backup":"PASS","unexpected_changes":0}
        p=pathlib.Path(os.environ["UAART_BACKUP_RECEIPT_PATH"]); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(r,sort_keys=True)+"\n")
    finally:
        for p in (controller.REMOTE_SCRIPT,controller.REMOTE_RECEIPT):
            try: api.delete(p)
            except Exception: pass
    return 0
if __name__=="__main__": raise SystemExit(main())
