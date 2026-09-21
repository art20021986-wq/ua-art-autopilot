#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, hashlib, json, os, pathlib, re, shutil, sys, tempfile
TASK_ID="SEO-DAILY-PODBOR-CANONICAL-20260921"
TARGET=pathlib.Path("/home/Carix/video/podbor.html")
BACKUP_ROOT=pathlib.Path("/home/Carix/archive/backups/SEO-DAILY-PODBOR-CANONICAL-20260921")
RECEIPT=pathlib.Path("/home/Carix/uploads/seo_daily_podbor_canonical_20260921.json")
CANONICAL="https://www.uaart.com.ua/video/podbor.html"
LINK_RE=re.compile(r'<link\b(?=[^>]*\brel\s*=\s*["\']canonical["\'])[^>]*>', re.I)
HREF_RE=re.compile(r'\bhref\s*=\s*["\']([^"\']+)["\']', re.I)
def sha(b): return hashlib.sha256(b).hexdigest()
def atomic(path,b):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".uaart-seo-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(b); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
def receipt(v): atomic(RECEIPT,(json.dumps(v,ensure_ascii=False,sort_keys=True)+"\n").encode())
def split_head(text):
    m=re.search(r'</head\s*>',text,re.I)
    if not m: raise RuntimeError("HEAD_END_MISSING")
    return text[:m.end()],text[m.end():]
def canon_values(head):
    out=[]
    for tag in LINK_RE.findall(head):
        m=HREF_RE.search(tag); out.append(m.group(1) if m else "")
    return out
def candidate(before):
    text=before.decode("utf-8")
    head,tail=split_head(text)
    stripped=LINK_RE.sub("",head)
    link='<link rel="canonical" href="%s">'%CANONICAL
    m=re.search(r'</head\s*>',stripped,re.I)
    new_head=stripped[:m.start()]+link+"\n"+stripped[m.start():]
    if LINK_RE.sub("",new_head)!=stripped: raise RuntimeError("SANDBOX_NONCANONICAL_DRIFT")
    if canon_values(new_head)!=[CANONICAL]: raise RuntimeError("SANDBOX_CANONICAL_INVALID")
    new=(new_head+tail).encode("utf-8")
    if split_head(new.decode("utf-8"))[1]!=tail: raise RuntimeError("SANDBOX_BODY_DRIFT")
    return new
def manifest_path(run_id): return BACKUP_ROOT/run_id/"manifest.json"
def backup_path(run_id): return BACKUP_ROOT/run_id/"podbor.html"
def load_manifest(run_id,expected):
    p=manifest_path(run_id); raw=p.read_bytes()
    if sha(raw)!=expected: raise RuntimeError("BACKUP_MANIFEST_SHA_MISMATCH")
    v=json.loads(raw.decode())
    if v.get("task_id")!=TASK_ID or v.get("run_id")!=run_id: raise RuntimeError("BACKUP_MANIFEST_IDENTITY")
    return v
def main():
    if len(sys.argv)<3: raise RuntimeError("ARGS")
    mode,run_id=sys.argv[1],sys.argv[2]
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,100}',run_id): raise RuntimeError("RUN_ID")
    if mode=="backup":
        before=TARGET.read_bytes()
        cand=candidate(before)
        bpath=backup_path(run_id); atomic(bpath,before)
        if bpath.read_bytes()!=before: raise RuntimeError("BACKUP_READBACK")
        m={"task_id":TASK_ID,"run_id":run_id,"target":str(TARGET),"backup":str(bpath),"before_sha256":sha(before),"candidate_sha256":sha(cand),"created_at":dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")}
        raw=(json.dumps(m,ensure_ascii=False,sort_keys=True)+"\n").encode(); atomic(manifest_path(run_id),raw)
        value={"task_id":TASK_ID,"mode":"BACKUP","status":"PASS","backup_manifest_sha256":sha(raw),"before_sha256":sha(before),"candidate_sha256":sha(cand),"canonical_before":canon_values(split_head(before.decode("utf-8"))[0]),"sandbox_validation":"PASS","unexpected_changes":0}
    elif mode=="install":
        if len(sys.argv)!=4: raise RuntimeError("INSTALL_ARGS")
        expected=sys.argv[3]; m=load_manifest(run_id,expected)
        before=TARGET.read_bytes()
        if sha(before)!=m["before_sha256"] or backup_path(run_id).read_bytes()!=before: raise RuntimeError("PREIMAGE_CHANGED")
        cand=candidate(before)
        if sha(cand)!=m["candidate_sha256"]: raise RuntimeError("CANDIDATE_DRIFT")
        atomic(TARGET,cand)
        after=TARGET.read_bytes()
        if after!=cand: raise RuntimeError("PRODUCTION_READBACK")
        value={"task_id":TASK_ID,"mode":"INSTALL","status":"PASS","backup_manifest_sha256":expected,"before_sha256":sha(before),"after_sha256":sha(after),"canonical_after":canon_values(split_head(after.decode("utf-8"))[0]),"sandbox_validation":"PASS","production_write":True,"unexpected_changes":0}
    elif mode=="rollback":
        if len(sys.argv)!=4: raise RuntimeError("ROLLBACK_ARGS")
        expected=sys.argv[3]; m=load_manifest(run_id,expected)
        original=backup_path(run_id).read_bytes()
        if sha(original)!=m["before_sha256"]: raise RuntimeError("BACKUP_CORRUPT")
        atomic(TARGET,original)
        restored=TARGET.read_bytes()
        if restored!=original: raise RuntimeError("ROLLBACK_READBACK")
        value={"task_id":TASK_ID,"mode":"ROLLBACK","status":"PASS","backup_manifest_sha256":expected,"restored_exact":True,"restored_sha256":sha(restored),"protected_files_unchanged":True,"crm_unchanged":True,"unexpected_changes":0}
    else: raise RuntimeError("MODE")
    receipt(value)
if __name__=="__main__":
    try: main()
    except Exception as e:
        receipt({"task_id":TASK_ID,"mode":sys.argv[1] if len(sys.argv)>1 else "UNKNOWN","status":"FAIL","error":type(e).__name__+":"+str(e)})
        raise
