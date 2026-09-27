"""Read-only renderer fixture from the repository source audit; never imported in production."""
def sobrat_kartochku(m, kadry, sredn=None):
    nom = nomer(m)
    sredn = sredn or kadry
    nazvanie = " ".join(str(x) for x in [m.get("brand"), m.get("model"), m.get("year")] if x)
    etap_tekst, mozhno_bron = etap_dlinno(m)
    prodana = (m.get("status") or "").lower().startswith("sold")
    video_est = os.path.exists(os.path.join(PAPKA_VID, nom + ".mp4"))

    c = []
    c.append("<!doctype html><html lang='ru'><head><meta charset='utf-8'>")
    c.append("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    c.append("<script src='https://telegram.org/js/telegram-web-app.js'></script>")
    c.append("<title>%s — UA ART COMPANY</title><style>%s</style></head><body>"
             % (ekran(nazvanie), STIL))
    c.append(shapka())

    if not kadry:
        c.append("<div class='blok' style='text-align:center;color:var(--seryj)'>"
                 "Фотографии готовятся — пришлём в чат, как только появятся.</div>")
    if kadry:
        c.append("<div class='lenta'>")
        for i, k in enumerate(sredn, 1):
            c.append("<div class='kadr'><img src='%s' loading='%s' decoding='async' alt=''>"
                     "<div class='podpis_kadra'>фото %d</div></div>"
                     % (k, "eager" if i <= 2 else "lazy", i))
        c.append("</div>")
        c.append("<div class='schet'>%d фото · листайте вбок, тап — во весь экран</div>" % len(kadry))

    # UA-V105 · подмены роликом проверки больше нет:
    # обычный блок «Видео» строится только из своих роликов машины
    if video_est:
        poster = (" poster='%s'" % sredn[0]) if sredn else ""
        # UA-V97 · ролики горизонтальной лентой, как фотографии
        _vse = ["%s.mp4" % nom]
        try:
            for _f in sorted(os.listdir(PAPKA_VID)):
                if (_f.startswith(nom + "-") and _f.lower().endswith(".mp4")
                        and ".mp4." not in _f):
                    _vse.append(_f)
        except Exception:
            pass
        c.append("<div class='zagolovok'>Видео</div>")
        c.append("<div class='lenta'>")
        for _i, _f in enumerate(_vse, 1):
            c.append("<div class='kadr'>")
            c.append("<video controls playsinline webkit-playsinline preload='metadata'%s"
                     " style='width:100%%;height:auto;display:block;border-radius:14px'>"
                     "<source src='%s' type='video/mp4'>"
                     "<a class='vtoraya' href='%s'>Открыть видео отдельно</a>"
                     "</video>" % (zastavka(_f) or poster, _f, _f))
            c.append("<div class='podpis_kadra'>видео %d</div></div>" % _i)
        c.append("</div>")
        if len(_vse) > 1:
            c.append("<div class='schet'>%d видео · листайте вбок, "
                     "звук касанием</div>" % len(_vse))
        else:
            c.append("<div class='schet'>видео · звук касанием</div>")

    c.append("<div class='blok'>")
    c.append("<div class='nom'>%s</div><h1>%s</h1>" % (ekran(nom), ekran(nazvanie)))
    c.append("<div class='chip'>%s</div>" % ekran(etap_tekst))
    c.append("<div class='cena' style='margin-top:14px'>%s</div>" % cena(m))
    c.append("<div class='tihо'>Под ключ в Киеве. Выкуп на аукционе, доставка, "
             "растаможка и сертификат — доплат нет.</div>")
    c.append("</div>")

    # UA-V61 · верхняя кнопка «Купить авто» убрана, осталась нижняя
    pary = []
    if m.get("mileage_km"):
        try:
            pary.append(("Пробег", "{:,} км".format(int(m["mileage_km"])).replace(",", " ")))
        except Exception:
            pass
    if m.get("engine_cc"):
        pary.append(("Двигатель", "%s см³%s" % (m["engine_cc"],
                                                (", " + str(m["fuel"])) if m.get("fuel") else "")))
    elif m.get("fuel"):
        pary.append(("Топливо", str(m["fuel"])))
    for nazv, pole in (("Коробка", "gearbox"), ("Привод", "drive"), ("Цвет", "color"), ("VIN", "vin")):
        if m.get(pole):
            pary.append((nazv, str(m[pole])))
    if pary:
        c.append("<div class='blok'><div class='zag'>Коротко</div><table class='kratko'>")
        for a, b in pary:
            c.append("<tr><td class='k'>%s</td><td>%s</td></tr>" % (ekran(a), ekran(b)))
        c.append("</table></div>")

    # UA-CARDS-STAGE-ANCHOR-001-V1.1 · permanent visual anchor
    c.append(_ua_delivery_stage_anchor(m))
    def blok_teksta(zagolovok, tekst):
        tekst = (tekst or "").strip()
        if not tekst:
            return
        c.append("<div class='blok'><div class='zag'>%s</div>" % ekran(zagolovok))
        stroki = [s.strip() for s in tekst.replace("\r", "").split("\n")]
        stroki = [s for s in stroki if s]
        spiskom = sum(1 for s in stroki if s[:1] in "-–—•*·") >= 2
        if spiskom:
            for s in stroki:
                s = s.lstrip("-–—•*· ").strip()
                if s:
                    c.append("<div class='tehstr'><div class='m'>•</div><div>%s</div></div>"
                             % ekran(s))
        else:
            c.append("<div class='tehtekst'>%s</div>"
                     % "<br>".join(ekran(s) for s in stroki))
        c.append("</div>")

    sostoyanie = (m.get("condition_text") or "").strip()
    opisanie = (m.get("description") or "").strip()
    # UA-V62 · сначала то, что вписал владелец (condition_text).
    # description — запасной вариант, там лежит короткий автотекст.
    polnoe_opisanie = sostoyanie or opisanie
    blok_teksta("Описание", polnoe_opisanie)

    # UA-V75 · кнопка на отдельную страницу диагностики
    # UA-DIAG-PERMANENT-V1 · never conditional in a card
    c.append("<!--ua-art-diagnostics-permanent-v1-->")
    c.append('<a class="mcf-diag-cta" href="%s-diag.html" style="display:flex;align-items:center;gap:12px;margin:14px 0;padding:15px 16px;border-radius:14px;text-decoration:none;background:linear-gradient(180deg,rgba(212,175,55,.20),rgba(212,175,55,.08));border:1px solid rgba(212,175,55,.55);color:#f4e3ae"><span style="font-size:22px;line-height:1">🔧</span><span style="flex:1"><span style="display:block;font-weight:800;font-size:16px">Открыть комплексную диагностику →</span><span style="display:block;font-size:13px;opacity:.85;margin-top:3px">ЛКП · OBD · ходовая · фото · видео</span></span><span style="font-size:20px;opacity:.8">›</span></a>' % nom)

    if prodana:
        c.append("<a class='dejstvie' href='podbor.html?v=%d'>Хочу такую же под заказ</a>"
                 % int(time.time()))
    else:
        # UA-FIXCTA-V2: одна CTA на страницу, текст по стадии
        _st_cta = ((m.get("status") or m.get("stage") or "")).strip()
        if _st_cta in ("ge_waiting", "sea_loaded", "kr_bought"):
            c.append("<a class='dejstvie kn_kupit' href='%s'>Забронировать авто за 500 $</a>"
                     % v_bota("bron_" + nom))
            c.append('<p class="cta-note" style="margin:8px 0 0;text-align:center;font-size:14px;color:#c8d2e1;background:none;border:0">500 $ входит в стоимость автомобиля</p>')
        else:
            c.append("<a class='dejstvie kn_kupit' href='%s'>Купить авто</a>"
                     % v_bota("kupit_" + nom))
        c.append("<a class='vtoraya' id='vopros' href='%s'>Задать вопрос по этой машине</a>"
                 % v_bota("vopros_" + nom))
    c.append("<a class='vtoraya' href='katalog.html?v=%d'>← Все машины</a>" % int(time.time()))
    c.append(USPEH_BLOK)
    c.append(podval(" · " + ekran(nom)))
    c.append("<script>(function(){"
             "document.querySelectorAll('.kn_kupit').forEach(function(kp){"
             "kp.addEventListener('click',function(e){e.preventDefault();"
             "otpravit_zayavku({t:'kupit',nom:'%(n)s'},'Заявка на покупку принята',"
             "'Менеджер Артём свяжется с вами в течение часа, подтвердит наличие "
             "и подготовит договор с фиксированной ценой.', kp.getAttribute('href'));});});"
             "var b=document.getElementById('bron');"
             "if(b){b.addEventListener('click',function(e){e.preventDefault();"
             "otpravit_zayavku({t:'bron',nom:'%(n)s'},'Бронь принята',"
             "'Автомобиль забронирован за вами. Менеджер Артём свяжется в течение часа "
             "и подтвердит договор с фиксированной ценой.', b.getAttribute('href'));});}"
             "var v=document.getElementById('vopros');"
             "if(v){v.addEventListener('click',function(e){e.preventDefault();"
             "otpravit_zayavku({t:'vopros',nom:'%(n)s'},'Вопрос отправлен',"
             "'Менеджер Артём ответит вам в чате в ближайшее время.', v.getAttribute('href'));});}"
             "})();</script>" % {"n": nom})

    if kadry:
        c.append("<div id='lupa'><img id='bolshoe' src='' alt=''></div><div id='lupaschet'></div>")
        c.append("<script>var kadry=%s;var tek=0;" % json.dumps(kadry))
        c.append("""
var sloj=document.getElementById('lupa'),bol=document.getElementById('bolshoe'),
    sch=document.getElementById('lupaschet');
function pokazat(i){tek=(i+kadry.length)%kadry.length;bol.src=kadry[tek];
 sloj.style.display='flex';sch.style.display='block';sch.textContent=(tek+1)+' / '+kadry.length;
 document.body.style.overflow='hidden';}
function zakryt(){sloj.style.display='none';sch.style.display='none';document.body.style.overflow='';}
document.querySelectorAll('.lenta img').forEach(function(el,i){
 el.addEventListener('click',function(){pokazat(i);});});
var x0=null;
sloj.addEventListener('touchstart',function(e){x0=e.touches[0].clientX;});
sloj.addEventListener('touchend',function(e){if(x0===null)return;
 var dx=e.changedTouches[0].clientX-x0;
 if(Math.abs(dx)>50){pokazat(dx<0?tek+1:tek-1);}else{zakryt();}x0=null;});
sloj.addEventListener('click',function(e){if(e.target===sloj)zakryt();});
""")
        c.append("</script>")
    c.append(CHAT_KNOPKA)
    c.append(SKRIPT_TG)
    c.append("</body></html>")
    return "".join(c)
