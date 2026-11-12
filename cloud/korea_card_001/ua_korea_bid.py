"""«Розмістити ставку» in the lot card for a logged-in client (JPAUTO-KOREA-001 step В, owner 2026-11-10).

apply(html) on video/korea.html (with the lot list and «Вхід для клієнтів»): a small script. When a lot card opens and
a client is logged in (window.uaAuctionClient, set by the login line), the card shows the bid form instead of
«Зв'язатися з менеджером»: the amount in ₩ (whole 10 000 ₩, from start + 50 000 ₩), «≈ $» by the NBU rate of the lot
list and the client's limit; «Розмістити ставку» asks to confirm, then POSTs /api/auction/bid and shows the result.
Visitors keep «Зв'язатися з менеджером». remove(html) takes it back.
"""
import json

MARK = '<!--UA-KOREA-BID-V1-->'
END = '<!--/UA-KOREA-BID-V1-->'
AFTER = '<!--/UA-KOREA-LOGIN-V1-->'

# [uk, ru, ka]
TEXT = {
    'amount': ['Ваша ставка, ₩', 'Ваша ставка, ₩', 'თქვენი ფსონი, ₩'],
    'min': ['Мінімум', 'Минимум', 'მინიმუმ'],
    'limit': ['ваш ліміт', 'ваш лимит', 'თქვენი ლიმიტი'],
    'place': ['Розмістити ставку', 'Разместить ставку', 'ფსონის განთავსება'],
    'confirm': ['Ставка ₩{krw} ≈ ${usd} на {title}. Підтвердити?', 'Ставка ₩{krw} ≈ ${usd} на {title}. Подтвердить?',
                'ფსონი ₩{krw} ≈ ${usd} — {title}. დაადასტურებთ?'],
    'sending': ['Розміщуємо ставку на аукціоні…', 'Размещаем ставку на аукционе…', 'ფსონს ვათავსებთ აუქციონზე…'],
    'placed': ['✅ Ставку розміщено на аукціоні. Менеджер бачить її.', '✅ Ставка размещена на аукционе. Менеджер её видит.',
               '✅ ფსონი განთავსებულია აუქციონზე. მენეჯერი ხედავს მას.'],
    'failed': ['❌ Аукціон не прийняв ставку. Менеджер уже знає і зв\'яжеться з вами.',
               '❌ Аукцион не принял ставку. Менеджер уже знает и свяжется с вами.',
               '❌ აუქციონმა ფსონი არ მიიღო. მენეჯერმა იცის და დაგიკავშირდებათ.'],
    'too_low': ['Сума нижча за мінімальну.', 'Сумма ниже минимальной.', 'თანხა მინიმალურზე ნაკლებია.'],
    'step': ['Сума має бути кратна 10 000 ₩.', 'Сумма должна быть кратна 10 000 ₩.', 'თანხა უნდა იყოს 10 000 ₩-ის ჯერადი.'],
    'limit_over': ['Сума вища за ваш ліміт.', 'Сумма выше вашего лимита.', 'თანხა თქვენს ლიმიტზე მეტია.'],
    'day_limit': ['На сьогодні ставки вичерпано, спробуйте завтра.', 'На сегодня ставки исчерпаны, попробуйте завтра.',
                  'დღევანდელი ფსონები ამოწურულია, სცადეთ ხვალ.'],
    'no_start_price': ['Ставка стане доступною, коли з\'явиться стартова ціна.',
                       'Ставка станет доступна, когда появится стартовая цена.',
                       'ფსონი ხელმისაწვდომი იქნება საწყისი ფასის გამოჩენისას.'],
    'other': ['Не вдалося. Спробуйте ще раз або напишіть менеджеру.', 'Не удалось. Попробуйте ещё раз или напишите менеджеру.',
              'ვერ მოხერხდა. სცადეთ თავიდან ან მისწერეთ მენეჯერს.'],
}

STYLE = ('<style id="ua-korea-bid-v1">.kb-form{display:grid;gap:8px;padding:12px;border-radius:12px;background:#13233a;'
         'border:1px solid #f2b544}.kb-form input{padding:12px;border-radius:10px;border:1px solid #2a3b55;'
         'background:#0B1524;color:#fff;font-size:18px;width:100%;box-sizing:border-box}.kb-hint{font-size:13px;opacity:.85}'
         '.kb-usd{color:#4ade80;font-weight:800}.kb-msg{font-weight:700}</style>')

SCRIPT = (
    '<script>(function(){"use strict";var T=' + json.dumps(TEXT, ensure_ascii=False) + ',data=null;'
    'var ERR={too_low:"too_low",step:"step",limit:"limit_over",day_limit:"day_limit",no_start_price:"no_start_price"};'
    'function L(){var l=document.documentElement.lang||"uk";return l==="ru"?1:l==="ka"?2:0;}'
    'function t(k,v){var s=T[k][L()];for(var x in v||{})s=s.replace("{"+x+"}",v[x]);return s;}'
    'function n(x){return Number(x).toLocaleString("uk-UA");}'
    'function lots(){return data||(data=fetch("/video/korea/lots.json",{cache:"no-cache"}).then(function(r){'
    'return r.json();}));}'
    'function form(card){var c=window.uaAuctionClient,a=card.querySelector("[data-quick-lead-lot]");'
    'if(!c||!a||card.querySelector(".kb-form"))return;var id=a.getAttribute("data-quick-lead-lot"),'
    'title=a.getAttribute("data-quick-lead-lot-title")||"";lots().then(function(d){'
    'var lot=(d.lots||[]).filter(function(x){return x.id===id;})[0];if(!lot)return;var box=document.createElement("div");'
    'box.className="kb-form";if(!lot.start_krw){box.innerHTML=\'<span class="kb-msg"></span>\';'
    'box.firstChild.textContent=t("no_start_price");a.parentNode.insertBefore(box,a);return;}'
    'var min=lot.start_krw+50000,rate=d.nbu.krw_uah/d.nbu.usd_uah;'
    'box.innerHTML=\'<label><span class="kb-l"></span><input type="number" inputmode="numeric" step="10000"></label>\''
    '+\'<span class="kb-hint"></span><span class="kb-usd"></span><button class="kr-btn" type="button"></button>\''
    '+\'<span class="kb-msg" hidden></span>\';'
    'var inp=box.querySelector("input"),usd=box.querySelector(".kb-usd"),btn=box.querySelector("button"),'
    'msg=box.querySelector(".kb-msg");box.querySelector(".kb-l").textContent=t("amount");inp.min=min;inp.value=min;'
    'box.querySelector(".kb-hint").textContent=t("min")+" ₩"+n(min)+" · "+t("limit")+" $"+n(c.limit_usd);'
    'btn.textContent=t("place");function upd(){usd.textContent="≈ $"+n(Math.round((+inp.value||0)*rate));}'
    'inp.addEventListener("input",upd);upd();'
    'btn.addEventListener("click",function(){var krw=+inp.value||0;'
    'if(!confirm(t("confirm",{krw:n(krw),usd:n(Math.round(krw*rate)),title:title})))return;'
    'btn.disabled=true;msg.hidden=false;msg.textContent=t("sending");'
    'fetch("/api/auction/bid",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},'
    'body:JSON.stringify({lot:id,krw:krw})}).then(function(r){return r.json();}).then(function(r){'
    'msg.textContent=r.status==="placed"?t("placed"):r.status==="failed"?t("failed"):t(ERR[r.error]||"other");'
    'btn.disabled=r.status==="placed";}).catch(function(){msg.textContent=t("other");btn.disabled=false;});});'
    'a.style.display="none";a.parentNode.insertBefore(box,a);});}'
    'function init(){var card=document.getElementById("kl-card");if(!card||!window.MutationObserver)return;'
    'new MutationObserver(function(){if(card.open)form(card);}).observe(card,{attributes:true,attributeFilter:["open"]});'
    'document.addEventListener("ua-auction-client",function(){if(card.open)form(card);});}'
    'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();'
    '})();</script>')

BLOCK = MARK + STYLE + SCRIPT + END


def apply(html):
    """Korea page with the bid form for logged-in clients; any other page unchanged."""
    if not isinstance(html, str) or html.count(AFTER) != 1 or MARK in html:
        return html
    at = html.index(AFTER) + len(AFTER)
    return html[:at] + BLOCK + html[at:]


def remove(html):
    if MARK not in html:
        return html
    start = html.index(MARK)
    return html[:start] + html[html.index(END, start) + len(END):]
