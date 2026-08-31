#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, fcntl, hashlib, importlib.util, json, os, pathlib, re, shutil, sqlite3, sys, tempfile

ROOT=pathlib.Path("/home/Carix")
REMOTE=ROOT/"autopilot_inbox/cloud/task_100_home_live_sync"
GUARD_SOURCE=REMOTE/"home_counter_guard.py"
DB=ROOT/"crm.db"
VIDEO_HOME=ROOT/"video/index.html"
SITE_HOME=ROOT/"site/index.html"
VIDEO_CATALOG=ROOT/"video/katalog.html"
LOCK=ROOT/".ua_art_production_writer.lock"
BACKUPS=ROOT/"backups/task_100_home_live_sync"
RECEIPT=REMOTE/"receipt.json"
MARK_START="<!-- TASK100-WHATSAPP-OPACITY:START -->"
MARK_END="<!-- TASK100-WHATSAPP-OPACITY:END -->"
WA_SCRIPT=r'''<!-- TASK100-WHATSAPP-OPACITY:START -->
<script id="task100-whatsapp-opacity">
(function(){
"use strict";
function apply(){
  var nodes=[].slice.call(document.querySelectorAll('a[href*="wa.me"],a[href*="whatsapp.com"]'));
  var fixed=nodes.filter(function(a){
    var s=getComputedStyle(a), r=a.getBoundingClientRect();
    return s.position==="fixed" && r.width>=40 && r.height>=40 && r.width<=120 && r.height<=120;
  });
  if(fixed.length===1){fixed[0].style.opacity="0.90"; fixed[0].setAttribute("data-task100-opacity","0.90");}
}
if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",apply,{once:true});}else{apply();}
}());
</script>
<!-- TASK100-WHATSAPP-OPACITY:END -->'''

def sha(b): return hashlib.sha256(b).hexdigest()
def read(p):
    b=p.read_bytes()
    if len(b)>12*1024*1024: raise RuntimeError("FILE_TOO_LARGE:"+str(p))
    return b
def atomic(p,b,mode=None):
    h=tempfile.NamedTemporaryFile(dir=p.parent,prefix="."+p.name+".",suffix=".task100.tmp",delete=False)
    t=pathlib.Path(h.name)
    try:
        with h:
            h.write(b); h.flush(); os.fsync(h.fileno())
        if mode is not None: os.chmod(t,mode)
        os.replace(t,p)
    finally: t.unlink(missing_ok=True)
def write_receipt(v):
    REMOTE.mkdir(parents=True,exist_ok=True)
    atomic(RECEIPT,(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode(),0o644)
def load_guard():
    spec=importlib.util.spec_from_file_location("task100_guard",GUARD_SOURCE)
    if not spec or not spec.loader: raise RuntimeError("GUARD_IMPORT")
    m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); return m
def db_snapshot(guard):
    raw=read(DB)
    con=sqlite3.connect("file:%s?mode=ro"%DB,uri=True,timeout=30); con.row_factory=sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        quick=con.execute("PRAGMA quick_check").fetchone()[0]
        rows=[dict(r) for r in con.execute("SELECT * FROM cars WHERE published=1 ORDER BY auto_number,id")]
    finally: con.close()
    if quick!="ok": raise RuntimeError("CRM_QUICK_CHECK:"+str(quick))
    counts=guard.counts_from_rows(rows)
    ids=sorted(str(r.get("auto_number") or "").strip().upper() for r in rows)
    return {"file_sha256":sha(raw),"counts":counts,"ids":ids}
def catalog_snapshot():
    s=read(VIDEO_CATALOG).decode("utf-8","replace")
    openings=re.findall(r'<(?:a|article)\b(?=[^>]*\bdata-ua-card\s*=)[^>]*>',s,re.I|re.S)
    aliases={"kiev":"kiev","kyiv":"kiev","georgia":"georgia","gruzia":"georgia","sea":"sea","more":"sea","korea":"korea"}
    cards={}
    for op in openings:
        mi=re.search(r'\bdata-ua-card\s*=\s*["\'](UA-[0-9]{4,})["\']',op,re.I)
        ms=re.search(r'\bdata-(?:ua-card-stage|etap|stage)\s*=\s*["\']([^"\']+)["\']',op,re.I)
        if not mi or not ms: continue
        uid=mi.group(1).upper(); stage=aliases.get(ms.group(1).casefold())
        if not stage: raise RuntimeError("CATALOG_STAGE:"+uid)
        if uid in cards: raise RuntimeError("CATALOG_DUPLICATE:"+uid)
        cards[uid]=stage
    counts={"all":len(cards),"kiev":0,"georgia":0,"sea":0,"korea":0}
    for stage in cards.values(): counts[stage]+=1
    if counts["all"]!=sum(counts[k] for k in ("kiev","georgia","sea","korea")): raise RuntimeError("CATALOG_COUNT_INVARIANT")
    return {"counts":counts,"ids":sorted(cards)}
def patch_wa(source):
    region=re.compile(re.escape(MARK_START)+r".*?"+re.escape(MARK_END),re.S)
    if region.search(source): return region.sub(WA_SCRIPT,source,count=1)
    matches=list(re.finditer(r"</body\s*>",source,re.I))
    if len(matches)!=1: raise RuntimeError("BODY_END_COUNT:"+str(len(matches)))
    m=matches[0]; return source[:m.start()]+WA_SCRIPT+"\n"+source[m.start():]
def patch_home(guard,source,counts):
    out=guard.patch_home(source,counts)
    out=patch_wa(out)
    if out.count('id="task100-whatsapp-opacity"')!=1: raise RuntimeError("WA_PATCH_COUNT")
    return out
def main():
    result={"status":"FAIL","production_write":False,"crm_write":False,"media_write":False}
    before_files={}
    try:
        guard=load_guard()
        with open(LOCK,"a+") as lh:
            fcntl.flock(lh.fileno(),fcntl.LOCK_EX)
            db=db_snapshot(guard); cat=catalog_snapshot()
            if db["counts"]!=cat["counts"]: raise RuntimeError("CRM_CATALOG_COUNT_MISMATCH:"+json.dumps({"crm":db["counts"],"catalog":cat["counts"]},sort_keys=True))
            if db["ids"]!=cat["ids"]: raise RuntimeError("CRM_CATALOG_ID_MISMATCH")
            if db["counts"]["all"]<16: raise RuntimeError("PUBLISHED_TOTAL_BELOW_16:"+str(db["counts"]["all"]))
            targets=[p for p in (VIDEO_HOME,SITE_HOME) if p.is_file()]
            if VIDEO_HOME not in targets: raise RuntimeError("VIDEO_HOME_MISSING")
            candidates={}
            for p in targets:
                src=read(p).decode("utf-8","replace")
                candidates[p]=patch_home(guard,src,db["counts"]).encode()
                audit=guard.audit_home(candidates[p].decode("utf-8"),db["counts"])
                if audit.get("status")!="PASS": raise RuntimeError("HOME_AUDIT:"+",".join(audit.get("errors") or []))
            stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup=BACKUPS/stamp; backup.mkdir(parents=True,exist_ok=False)
            for p in candidates:
                b=read(p); dest=backup/p.relative_to(ROOT); dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dest)
                before_files[str(p)]={"sha256":sha(b),"backup":str(dest),"mode":p.stat().st_mode&0o777}
            changed=[]
            try:
                for p,b in candidates.items():
                    if read(p)!=b: atomic(p,b,before_files[str(p)]["mode"]); changed.append(str(p))
                db_after=db_snapshot(guard)
                if db_after["file_sha256"]!=db["file_sha256"]: raise RuntimeError("CRM_FILE_CHANGED")
                for p in candidates:
                    s=read(p).decode("utf-8","replace")
                    if guard.audit_home(s,db["counts"]).get("status")!="PASS": raise RuntimeError("POST_HOME_AUDIT")
                    if s.count('id="task100-whatsapp-opacity"')!=1: raise RuntimeError("POST_WA_PATCH")
            except Exception:
                for ptxt,meta in before_files.items():
                    p=pathlib.Path(ptxt); atomic(p,read(pathlib.Path(meta["backup"])),meta["mode"])
                raise
            result.update(status="PASS",production_write=True,counts=db["counts"],ids=db["ids"],changed_files=changed,backup_root=str(backup),whatsapp_opacity=0.90,crm_file_unchanged=True)
    except Exception as e:
        result["errors"]=[type(e).__name__+":"+str(e)]
    write_receipt(result)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0 if result["status"]=="PASS" else 1
if __name__=="__main__": raise SystemExit(main())
