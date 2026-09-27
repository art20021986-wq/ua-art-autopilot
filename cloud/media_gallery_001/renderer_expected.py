"""Read-only renderer fixture from the repository source audit; never imported in production."""
def sobrat_kartochku(m, kadry, sredn=None):
    from ua_media_gallery import photos, videos, poster_url, assets
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
        c.append(photos(kadry, sredn, nazvanie))

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
        c.append(videos(_vse, [poster_url(zastavka(_f) or poster) for _f in _vse], nazvanie))

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

    c.append(assets())
    c.append(CHAT_KNOPKA)
    c.append(SKRIPT_TG)
    c.append("</body></html>")
    return "".join(c)
