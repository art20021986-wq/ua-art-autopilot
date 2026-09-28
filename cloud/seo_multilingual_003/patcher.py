#!/usr/bin/env python3
import hashlib, html, json, os, pathlib, re, shutil, tempfile, time, urllib.request
ROOT=pathlib.Path("/home/Carix"); V=ROOT/"video"; SEO=V/"seo"; ORIGIN="https://www.uaart.com.ua"
STAMP=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime()); BACK=ROOT/"archive/backups"/("SEO-MULTILINGUAL-003_"+STAMP)
PHONE="+380992222020"; WA="+380992222002"
SLUGS={"hub":{"uk":"avto-z-korei-do-kyieva-pid-kluch","ru":"avto-iz-korei-v-kiev-pod-kluch","ka":"avtomobili-koreidan-sakartveloshi"},
"k5":{"uk":"kia-k5-koreya-kyiv","ru":"kia-k5-koreya-kiev","ka":"kia-k5-koreidan-sakartveloshi"},
"sonata":{"uk":"hyundai-sonata-koreya-kyiv","ru":"hyundai-sonata-koreya-kiev","ka":"hyundai-sonata-koreidan-sakartveloshi"}}
DIR={"uk":"ua","ru":"ru","ka":"gu"}
def url(kind,lang):return f"{ORIGIN}/video/seo/{DIR[lang]}/{SLUGS[kind][lang]}.html"
def atomic(p,b):
 p.parent.mkdir(parents=True,exist_ok=True);fd,t=tempfile.mkstemp(prefix=".seo3-",dir=str(p.parent))
 try:
  with os.fdopen(fd,"wb") as f:f.write(b);f.flush();os.fsync(f.fileno())
  os.replace(t,p)
 finally:
  try:os.unlink(t)
  except FileNotFoundError:pass
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def backup(paths):
 m=[]
 for p in paths:
  d=BACK/p.relative_to(ROOT);d.parent.mkdir(parents=True,exist_ok=True)
  if p.exists():shutil.copy2(p,d);m.append((p,d,True))
  else:m.append((p,d,False))
 return m
def rollback(m):
 for p,d,e in m:
  if e:shutil.copy2(d,p)
  elif p.exists():p.unlink()
def alternates(kind):
 tags=[]
 for l in ("uk","ru","ka"):tags.append(f'<link rel="alternate" hreflang="{l}" href="{url(kind,l)}">')
 tags.append(f'<link rel="alternate" hreflang="x-default" href="{url(kind,"uk")}">')
 return "\n".join(tags)
TEXT={
("hub","uk"):("Авто з Кореї до Києва під ключ — UA ART","Авто з Кореї до Києва під ключ","Підбір, перевірка, купівля та доставка автомобілів з Кореї до Києва й по Україні. Ціна фіксується в договорі; депозит 500 $ входить у вартість.","Організовуємо повний шлях автомобіля: підбір у Кореї, перевірка, купівля, доставка через Грузію, оформлення та передача в Києві. Доставка з Грузії до Києва орієнтовно 10 днів. Оплата — у гривні за курсом НБУ."),
("hub","ru"):("Авто из Кореи в Киев под ключ — UA ART","Авто из Кореи в Киев под ключ","Подбор, проверка, покупка и доставка автомобилей из Кореи в Киев и по Украине. Цена фиксируется в договоре; депозит 500 $ входит в стоимость.","Организуем полный путь автомобиля: подбор в Корее, проверка, покупка, доставка через Грузию, оформление и передача в Киеве. Доставка из Грузии в Киев ориентировочно 10 дней. Оплата — в гривне по курсу НБУ."),
("hub","ka"):("ავტომობილი კორეიდან საქართველოში — UA ART","ავტომობილები კორეიდან საქართველოში","კორეიდან ავტომობილის შერჩევა, შემოწმება, შეძენა და საქართველოში მიწოდება. საქართველოს ფასი ცალკე განისაზღვრება ავტომობილის ბარათში.","UA ART გთავაზობთ კორეაში ავტომობილის შერჩევასა და შემოწმებას, შეძენას და საქართველოში მიწოდებას. ავტომობილის უკრაინისა და საქართველოს ფასები დამოუკიდებელია; საქართველოს ფასი, როცა მითითებულია, ცალკე ჩანს."),
("k5","uk"):("Kia K5 з Кореї до Києва — ціна та доставка | UA ART","Kia K5 з Кореї до Києва","Kia K5 з Кореї: актуальні автомобілі, LPG/LPi, перевірка, пробіг, ціна та доставка до Києва.","Kia K5 — один з основних напрямків UA ART. На сайті показуємо реальні автомобілі, їхній рік, пробіг, паливо, етап доставки та актуальну ціну. Для конкретного K5 перевіряйте фактичні дані в картці автомобіля."),
("k5","ru"):("Kia K5 из Кореи в Киев — цена и доставка | UA ART","Kia K5 из Кореи в Киев","Kia K5 из Кореи: актуальные автомобили, LPG/LPi, проверка, пробег, цена и доставка в Киев.","Kia K5 — одно из основных направлений UA ART. На сайте показываем реальные автомобили, год, пробег, топливо, этап доставки и актуальную цену. Для конкретного K5 используйте фактические данные его карточки."),
("k5","ka"):("Kia K5 კორეიდან საქართველოში — ფასი და ჩამოყვანა | UA ART","Kia K5 კორეიდან საქართველოში","Kia K5 კორეიდან: LPG/LPi, შემოწმება, გარბენი, ფასი და საქართველოში ჩამოყვანა.","Kia K5 UA ART-ის ერთ-ერთი ძირითადი მიმართულებაა. კონკრეტული ავტომობილის ბარათში ვაჩვენებთ რეალურ წელს, გარბენს, საწვავის ტიპს, ტრანსპორტირების ეტაპსა და ხელმისაწვდომ ფასს."),
("sonata","uk"):("Hyundai Sonata з Кореї до Києва — ціна та доставка | UA ART","Hyundai Sonata з Кореї до Києва","Hyundai Sonata з Кореї: LPG/LPi, перевірка, пробіг, актуальна ціна та доставка до Києва.","Hyundai Sonata — популярний корейський седан у каталозі UA ART. Для кожного автомобіля використовуємо фактичні дані картки: рік, пробіг, паливо, етап доставки та ціну."),
("sonata","ru"):("Hyundai Sonata из Кореи в Киев — цена и доставка | UA ART","Hyundai Sonata из Кореи в Киев","Hyundai Sonata из Кореи: LPG/LPi, проверка, пробег, актуальная цена и доставка в Киев.","Hyundai Sonata — популярный корейский седан в каталоге UA ART. Для каждого автомобиля используем фактические данные карточки: год, пробег, топливо, этап доставки и цену."),
("sonata","ka"):("Hyundai Sonata კორეიდან საქართველოში — ფასი და ჩამოყვანა | UA ART","Hyundai Sonata კორეიდან საქართველოში","Hyundai Sonata კორეიდან: LPG/LPi, შემოწმება, გარბენი, ფასი და საქართველოში ჩამოყვანა.","Hyundai Sonata პოპულარული კორეული სედანია. თითოეული ავტომობილისთვის ვიყენებთ მხოლოდ მის რეალურ მონაცემებს: წელს, გარბენს, საწვავს, ტრანსპორტირების ეტაპსა და ფასს.")}
def page(kind,lang):
 title,h1,desc,body=TEXT[(kind,lang)]; canonical=url(kind,lang)
 home={"uk":"Головна","ru":"Главная","ka":"მთავარი"}[lang]; cat={"uk":"Каталог","ru":"Каталог","ka":"კატალოგი"}[lang]; order={"uk":"Підбір авто","ru":"Подбор авто","ka":"ავტომობილის შერჩევა"}[lang]
 bread={"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":home,"item":ORIGIN+"/video/index.html"},{"@type":"ListItem","position":2,"name":h1,"item":canonical}]}
 org={"@context":"https://schema.org","@type":"Organization","name":"UA ART COMPANY","url":ORIGIN,"telephone":PHONE}
 contact={"uk":f"Телефон: {PHONE}. WhatsApp: {WA}. Депозит 500 $ входить у вартість автомобіля.","ru":f"Телефон: {PHONE}. WhatsApp: {WA}. Депозит 500 $ входит в стоимость автомобиля.","ka":f"ტელეფონი: {PHONE}. WhatsApp: {WA}. საქართველოს ფასი მითითებულია ცალკე, როცა ხელმისაწვდომია."}[lang]
 return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}"><meta name="robots" content="index,follow"><link rel="canonical" href="{canonical}">{alternates(kind)}<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}"><meta property="og:url" content="{canonical}"><meta property="og:type" content="website"><script type="application/ld+json">{json.dumps(bread,ensure_ascii=False)}</script><script type="application/ld+json">{json.dumps(org,ensure_ascii=False)}</script><style>body{{font-family:Arial,sans-serif;max-width:960px;margin:auto;padding:18px;line-height:1.55}}nav a{{margin-right:14px}}.cta{{padding:14px;background:#f3f3f3;border-radius:10px;margin-top:18px}}</style></head><body><nav><a href="/video/index.html">{home}</a><a href="/video/katalog.html">{cat}</a><a href="/video/podbor.html">{order}</a></nav><h1>{h1}</h1><p>{body}</p><h2>{cat}</h2><p><a href="/video/katalog.html">{cat}</a> · <a href="/video/podbor.html">{order}</a></p><div class="cta">{contact}</div></body></html>"""
paths=[]
for kind in ("hub","k5","sonata"):
 for lang in ("uk","ru","ka"):paths.append((SEO/DIR[lang]/(SLUGS[kind][lang]+".html"),kind,lang))
sitemap=V/"sitemap.xml"; targets=[x[0] for x in paths]+[sitemap]; manifest=backup(targets)
try:
 for path,kind,lang in paths:atomic(path,page(kind,lang).encode())
 # validate pages before sitemap
 for path,kind,lang in paths:
  s=path.read_text(encoding="utf-8")
  if s.count("<h1>")!=1 or s.count('rel="canonical"')!=1:raise RuntimeError("PAGE_CONTRACT:"+path.name)
  for code in ("uk","ru","ka","x-default"):
   if f'hreflang="{code}"' not in s:raise RuntimeError("HREFLANG:"+path.name+":"+code)
 # canonical sitemap: core + cards + landings
 cards=sorted([p for p in V.glob("UA-*.html") if re.fullmatch(r"UA-[0-9]{4,}\.html",p.name,re.I)])
 core=[V/x for x in ("index.html","katalog.html","podbor.html","info.html")]
 urls=[ORIGIN+"/video/"+p.name for p in core if p.exists()]+[ORIGIN+"/video/"+p.name for p in cards]+[url(k,l) for k in ("hub","k5","sonata") for l in ("uk","ru","ka")]
 urls=list(dict.fromkeys(urls));xml="<?xml version='1.0' encoding='UTF-8'?>\n<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>\n"+"\n".join("<url><loc>%s</loc></url>"%u for u in urls)+"\n</urlset>\n";atomic(sitemap,xml.encode())
 bad=[]
 for u in urls:
  try:
   with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"UA-ART-SEO-003/1"}),timeout=20) as r:
    if r.status!=200:bad.append([u,r.status])
  except Exception as e:bad.append([u,type(e).__name__])
 if bad:raise RuntimeError("LIVE_FAIL:"+json.dumps(bad[:5]))
 receipt={"status":"PASS","task":"SEO-MULTILINGUAL-003","pages":len(paths),"sitemap_urls":len(urls),"backup":str(BACK),"rollback":None}
except Exception as e:
 rollback(manifest);receipt={"status":"FAIL_ROLLED_BACK","task":"SEO-MULTILINGUAL-003","error":str(e),"backup":str(BACK),"rollback":"DONE"}
atomic(ROOT/"archive/reports/SEO_MULTILINGUAL_003.json",(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n").encode());print(json.dumps(receipt,ensure_ascii=False));raise SystemExit(0 if receipt["status"]=="PASS" else 1)
