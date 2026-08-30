#!/usr/bin/env python3
"""TASK 095 v3: bounded catalog visibility/image repair with rollback."""
from __future__ import annotations
import argparse, contextlib, datetime as dt, fcntl, hashlib, json, os, pathlib, re, shutil, tempfile, time

CID = "CATALOG-VISUAL-ACCEPTANCE-REPAIR-095-V1.0"
ROOT = pathlib.Path("/home/Carix")
VIDEO, SITE = ROOT / "video", ROOT / "site"
VCAT, SCAT, GOLDEN = VIDEO / "katalog.html", SITE / "katalog.html", ROOT / "catalog_design_golden.html"
TARGETS = (VCAT, SCAT, GOLDEN)
DB, LOCK = ROOT / "crm.db", ROOT / ".ua_art_publish_transaction.lock"
REMOTE = ROOT / "autopilot_inbox/cloud/task_095_catalog_visual_repair"
BACKUPS, LAST = ROOT / "rezerv_publikacii/TASK095_V3", REMOTE / "last_success_v3.json"
RECEIPTS = {m: REMOTE / f"{m}_v3_receipt.json" for m in ("install", "postcheck", "rollback")}
IDS = tuple(f"UA-{n:04d}" for n in range(1, 14))
COUNTS = {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2}
PHOTOS = {i: f"/video/foto/{i}/001.jpg" for i in IDS}
PHOTOS["UA-0012"] = "/video/foto/UA-0012/003.jpg"
STYLE_ID = "ua095-catalog-visibility-lock-v3"
STYLE = f'''<style id="{STYLE_ID}">
section.content-page.catalog-page{{display:block!important;visibility:visible!important;opacity:1!important}}
section.content-page.catalog-page[data-ua-dubl="1"]{{display:block!important}}
.ua-cat-fallback-v1{{display:none!important}}
</style>'''
STYLE_RE = re.compile(r'<style\b(?=[^>]*\bid=["\']'+re.escape(STYLE_ID)+r'["\'])[^>]*>.*?</style\s*>', re.I|re.S)
FALLBACK_RE = re.compile(r'<!--\s*UA-ART-CATALOG-CARD-FALLBACK-V1:START\s*-->.*?<!--\s*UA-ART-CATALOG-CARD-FALLBACK-V1:END\s*-->', re.I|re.S)
ARTICLE_RE = re.compile(r'<article\b(?=[^>]*class=["\'][^"\']*\bcatalog-card\b)[^>]*>.*?</article\s*>', re.I|re.S)

class E(RuntimeError): pass

def now(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def read(p): return p.read_bytes()
def digest(v): return hashlib.sha256(v if isinstance(v,bytes) else v.encode()).hexdigest()
def write(p,b,mode=None):
    h=tempfile.NamedTemporaryFile(dir=p.parent,prefix='.'+p.name+'.',suffix='.095v3',delete=False); q=pathlib.Path(h.name)
    try:
        with h: h.write(b); h.flush(); os.fsync(h.fileno())
        if mode is not None: os.chmod(q,mode)
        os.replace(q,p)
    finally: q.unlink(missing_ok=True)
def jwrite(p,v): p.parent.mkdir(parents=True,exist_ok=True); write(p,(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode(),0o644)

@contextlib.contextmanager
def locked():
    f=open(LOCK,'a+'); end=time.monotonic()+180
    try:
        while True:
            try: fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB); break
            except BlockingIOError:
                if time.monotonic()>end: raise E('LOCK_TIMEOUT')
                time.sleep(.25)
        yield
    finally:
        try: fcntl.flock(f.fileno(),fcntl.LOCK_UN)
        finally: f.close()

def set_attr(tag,name,value):
    tag=re.sub(r'\s+'+re.escape(name)+r'\s*=\s*(["\']).*?\1','',tag,flags=re.I|re.S)
    return tag[:-1]+f' {name}="{value}">'
def card_id(block):
    m=re.search(r'\b(?:data-ua-kod|data-ua-card)\s*=\s*["\'](UA-\d{4,})["\']',block,re.I) or re.search(r'\b(UA-\d{4,})\b',block,re.I)
    if not m: raise E('CARD_ID')
    return m.group(1).upper()
def add_style(s):
    s=STYLE_RE.sub(STYLE,s,count=1) if STYLE_RE.search(s) else re.sub(r'</head\s*>',STYLE+'\n</head>',s,count=1,flags=re.I)
    if s.count(f'id="{STYLE_ID}"')!=1: raise E('STYLE_COUNT')
    return FALLBACK_RE.sub('',s)
def patch_card(block):
    ident=card_id(block); src=PHOTOS.get(ident)
    if not src: raise E('PHOTO_MAP:'+ident)
    p=VIDEO/src[len('/video/'):]
    if not p.is_file() or p.stat().st_size<512: raise E('PHOTO_FILE:'+ident)
    m=re.search(r'<img\b(?=[^>]*\bsrc\s*=)[^>]*>',block,re.I|re.S)
    if not m: raise E('IMG:'+ident)
    tag=set_attr(set_attr(m.group(0),'src',src),'loading','eager')
    tag=re.sub(r'\s+(?:srcset|data-src|data-srcset)\s*=\s*(["\']).*?\1','',tag,flags=re.I|re.S)
    return block[:m.start()]+tag+block[m.end():]
def patch_live(s):
    s=add_style(s); ms=list(ARTICLE_RE.finditer(s))
    if len(ms)!=13: raise E(f'CARD_COUNT:{len(ms)}')
    out=[]; pos=0
    for m in ms: out += [s[pos:m.start()],patch_card(m.group(0))]; pos=m.end()
    s=''.join(out)+s[pos:]; audit(s); return s
def patch_golden(s):
    s=add_style(s)
    if len(ARTICLE_RE.findall(s))<10: raise E('GOLDEN_CARDS')
    return s

def audit(s):
    errs=[]; ids=[]; c={"all":0,"kiev":0,"georgia":0,"sea":0,"korea":0}
    if s.count(f'id="{STYLE_ID}"')!=1: errs.append('STYLE')
    if FALLBACK_RE.search(s): errs.append('FALLBACK')
    for b in ARTICLE_RE.findall(s):
        i=card_id(b); ids.append(i)
        st=re.search(r'\bdata-stage\s*=\s*["\'](kiev|georgia|sea|korea)["\']',b,re.I)
        if st: c[st.group(1).lower()]+=1
        else: errs.append('STAGE:'+i)
        im=re.search(r'<img\b(?=[^>]*\bsrc\s*=)[^>]*>',b,re.I|re.S)
        sm=re.search(r'\bsrc\s*=\s*(["\'])(.*?)\1',im.group(0),re.I|re.S) if im else None
        if not sm or sm.group(2)!=PHOTOS.get(i): errs.append('IMAGE:'+i)
        if not im or not re.search(r'\bloading\s*=\s*["\']eager["\']',im.group(0),re.I): errs.append('EAGER:'+i)
    c['all']=len(ids)
    if tuple(sorted(ids))!=IDS: errs.append('IDS')
    if c!=COUNTS: errs.append('COUNTS:'+json.dumps(c,sort_keys=True))
    if errs: raise E('AUDIT:'+';'.join(errs))
    return {'status':'PASS','ids':ids,'counts':c,'cards':len(ids),'style':STYLE_ID}
def backup():
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'); root=BACKUPS/(stamp+'-'+digest(read(VCAT))[:12]); root.mkdir(parents=True)
    man={}
    for p in TARGETS:
        q=root/p.relative_to(ROOT); q.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,q)
        man[str(p)]={'backup':str(q),'sha256':digest(read(p)),'mode':p.stat().st_mode&0o777}
    return root,man
def restore(man):
    done=[]
    for t,x in man.items():
        p,q=pathlib.Path(t),pathlib.Path(x['backup']); b=read(q)
        if BACKUPS not in q.parents or digest(b)!=x['sha256']: raise E('ROLLBACK_GUARD:'+t)
        write(p,b,int(x['mode'])); done.append(t)
    return done

def install():
    with locked():
        db=digest(read(DB)); root,man=backup()
        try:
            cand={VCAT:patch_live(read(VCAT).decode('utf-8','replace')),SCAT:patch_live(read(SCAT).decode('utf-8','replace')),GOLDEN:patch_golden(read(GOLDEN).decode('utf-8','replace'))}
            for p,s in cand.items(): write(p,s.encode(),int(man[str(p)]['mode']))
            audits={str(p):audit(read(p).decode('utf-8','replace')) for p in (VCAT,SCAT)}
            if digest(read(DB))!=db: raise E('DB_CHANGED')
        except Exception: restore(man); raise
        jwrite(LAST,{'manifest':man,'db':db,'backup_root':str(root)})
    return {'status':'PASS','production_write':True,'crm_write':False,'media_write':False,'backup_root':str(root),'audits':audits,'errors':[]}
def postcheck():
    with locked():
        x=json.loads(LAST.read_text());
        if digest(read(DB))!=x['db']: raise E('DB_CHANGED')
        audits={str(p):audit(read(p).decode('utf-8','replace')) for p in (VCAT,SCAT)}
    return {'status':'PASS','production_write':False,'crm_write':False,'media_write':False,'audits':audits,'errors':[]}
def rollback():
    with locked():
        x=json.loads(LAST.read_text()); done=restore(x['manifest'])
        if digest(read(DB))!=x['db']: raise E('DB_CHANGED')
    return {'status':'PASS','production_write':True,'crm_write':False,'media_write':False,'restored':done,'errors':[]}

def main():
    a=argparse.ArgumentParser(); a.add_argument('mode',choices=tuple(RECEIPTS)); mode=a.parse_args().mode
    try: v={'install':install,'postcheck':postcheck,'rollback':rollback}[mode](); v.update({'contract_id':CID,'mode':mode.upper(),'finished_at_utc':now()})
    except Exception as e: v={'contract_id':CID,'status':'FAIL','mode':mode.upper(),'production_write':False,'crm_write':False,'media_write':False,'errors':[type(e).__name__+':'+str(e)],'finished_at_utc':now()}
    jwrite(RECEIPTS[mode],v); print(json.dumps(v,ensure_ascii=False,sort_keys=True)); return 0 if v['status']=='PASS' else 1
if __name__=='__main__': raise SystemExit(main())
