#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, pathlib, py_compile, shutil, sqlite3, tempfile, datetime as dt

TASK_ID="TASK088-GE-PRICE-CRM-STAGE1"
ROOT=pathlib.Path("/home/Carix")
SRC=ROOT/"cars_ui.py"
DB=ROOT/"crm.db"
SAFE=ROOT/"autopilot_inbox/cloud/task_088_ge_price_crm_stage1"
RECEIPT=SAFE/"receipt.json"
BACKUP=SAFE/"backup"
TARGETS=[SRC,DB]

class E(RuntimeError): pass
def now(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write_receipt(v):
    SAFE.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=SAFE)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as h:
            json.dump(v,h,ensure_ascii=False,sort_keys=True,indent=2); h.write("\n"); h.flush(); os.fsync(h.fileno())
        os.replace(tmp,RECEIPT)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

def replace_once(s,a,b,label):
    n=s.count(a)
    if n!=1: raise E(f"{label}_COUNT_{n}")
    return s.replace(a,b,1)

def patch_text(s):
    if '"price_georgia"' in s and '("price_georgia", "Цена Грузии")' in s:
        return s, False
    s=replace_once(s,'("eta_manual", "TEXT")','("eta_manual", "TEXT"), ("price_georgia", "INTEGER")',"ENSURE_COLUMNS")
    s=replace_once(s,'"price_uah": "цена",','"price_uah": "цена Украины", "price_georgia": "цена Грузии",',"LABELS")
    s=replace_once(s,'("price_uah", "Цена продажи"),','("price_uah", "Цена Украины"), ("price_georgia", "Цена Грузии"),',"EDITABLE")
    s=replace_once(s,'MONEY = {"price_uah", "cost_total", "cost_purchase", "cost_fees", "cost_logistics"}','MONEY = {"price_uah", "price_georgia", "cost_total", "cost_purchase", "cost_fees", "cost_logistics"}',"MONEY")
    s=replace_once(s,'NUMERIC = {"engine_cc", "mileage_km", "price_uah"}','NUMERIC = {"engine_cc", "mileage_km", "price_uah", "price_georgia"}',"NUMERIC")
    s=replace_once(s,'elif field == "price_uah":\n        hint = "\\nТолько число, в долларах."','elif field in ("price_uah", "price_georgia"):\n        hint = "\\nТолько число, в долларах."\n        if field == "price_georgia":\n            hint += "\\nПоле необязательное: если цены для Грузии нет, ничего не вводите."',"HINT")
    return s, True

def main():
    base={"task_id":TASK_ID,"status":"FAIL","site_write":False,"publisher_write":False,"stage2_touched":False,"started_at":now()}
    try:
        for p in TARGETS:
            if not p.is_file() or p.is_symlink(): raise E("TARGET_INVALID:"+str(p))
        BACKUP.mkdir(parents=True,exist_ok=True)
        before={str(p):sha(p) for p in TARGETS}
        for p in TARGETS: shutil.copy2(p,BACKUP/p.name)
        text=SRC.read_text(encoding="utf-8")
        patched,changed=patch_text(text)
        fd,tmp=tempfile.mkstemp(suffix=".py",dir=SAFE)
        os.close(fd); tp=pathlib.Path(tmp)
        try:
            tp.write_text(patched,encoding="utf-8")
            py_compile.compile(str(tp),doraise=True)
            if changed: os.replace(tp,SRC)
            else: tp.unlink(missing_ok=True)
        finally: tp.unlink(missing_ok=True)
        with sqlite3.connect(DB) as c:
            cols={r[1] for r in c.execute("PRAGMA table_info(cars)")}
            if "price_georgia" not in cols:
                c.execute("ALTER TABLE cars ADD COLUMN price_georgia INTEGER"); c.commit()
            row=c.execute("SELECT id, price_uah, price_georgia FROM cars ORDER BY id LIMIT 1").fetchone()
            if not row: raise E("NO_CAR_ROW")
            car_id,ua,ge=row
            c.execute("BEGIN")
            sentinel=987654321 if ge!=987654321 else 987654320
            c.execute("UPDATE cars SET price_georgia=? WHERE id=?",(sentinel,car_id))
            got=c.execute("SELECT price_georgia FROM cars WHERE id=?",(car_id,)).fetchone()[0]
            if got!=sentinel: raise E("DB_READBACK_FAIL")
            c.rollback()
            restored=c.execute("SELECT price_uah, price_georgia FROM cars WHERE id=?",(car_id,)).fetchone()
            if restored!=(ua,ge): raise E("DB_ROLLBACK_FAIL")
            cols2={r[1] for r in c.execute("PRAGMA table_info(cars)")}
            if "price_georgia" not in cols2: raise E("COLUMN_MISSING")
        final=SRC.read_text(encoding="utf-8")
        required=['"price_uah": "цена Украины"','"price_georgia": "цена Грузии"','("price_uah", "Цена Украины")','("price_georgia", "Цена Грузии")']
        if any(x not in final for x in required): raise E("UI_MARKERS_MISSING")
        base.update({"status":"PASS","source_changed":changed,"before_sha256":before,"after_sha256":{str(p):sha(p) for p in TARGETS},"db":{"column":"price_georgia","live_transaction_write_readback":"PASS","rollback_to_original":"PASS","test_car_id":car_id},"crm_source":"/home/Carix/cars_ui.py","crm_db":"/home/Carix/crm.db","finished_at":now()})
    except Exception as exc:
        base["error"]=type(exc).__name__+":"+str(exc); base["finished_at"]=now()
    write_receipt(base)
    if base["status"]!="PASS": raise SystemExit(1)

if __name__=="__main__": main()
