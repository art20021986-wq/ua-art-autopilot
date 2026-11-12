"""«Розмістити ставку» in the lot card for a logged-in client (JPAUTO-KOREA-001; owner 2026-11-12, variant А).

The block between the UA-KOREA-BID-V1 marks of video/korea.html (the marks stay, so a page builder that re-adds a
missing block finds this one). When a lot card opens and a client is logged in (window.uaAuctionClient, set by the
login line), the card shows the bid form instead of «Зв'язатися з менеджером»: the amount in ₩ (whole 10 000 ₩, from
start + 50 000 ₩) and «≈ $» by the NBU rate of the lot list. «Розмістити ставку» asks to confirm, then POSTs
/api/auction/bid: the bid becomes a request, a manager places it on the auction themselves, and the client follows it
in «Мій кабінет». Visitors keep «Зв'язатися з менеджером». replace(html) puts this block in place of the installed one.
"""
import json

MARK = '<!--UA-KOREA-BID-V1-->'
END = '<!--/UA-KOREA-BID-V1-->'
AFTER = '<!--/UA-KOREA-LOGIN-V1-->'

# [uk, ru, ka]
TEXT = {
    'amount': ['Ваша ставка, ₩', 'Ваша ставка, ₩', 'თქვენი ფსონი, ₩'],
    'min': ['Мінімум', 'Минимум', 'მინიმუმ'],
    'place': ['Розмістити ставку', 'Разместить ставку', 'ფსონის განთავსება'],
    'confirm': ['Ставка ₩{krw} ≈ ${usd} на {title}. Підтвердити?', 'Ставка ₩{krw} ≈ ${usd} на {title}. Подтвердить?',
                'ფსონი ₩{krw} ≈ ${usd} — {title}. დაადასტურებთ?'],
    'sending': ['Надсилаємо заявку…', 'Отправляем заявку…', 'ვაგზავნით განაცხადს…'],
    'requested': ['✅ Заявку прийнято. Менеджер поставить ставку на аукціоні. Статус — у «Мій кабінет».',
                  '✅ Заявка принята. Менеджер поставит ставку на аукционе. Статус — в «Мой кабинет».',
                  '✅ განაცხადი მიღებულია. მენეჯერი განათავსებს ფსონს აუქციონზე. სტატუსი — «ჩემი კაბინეტი».'],
    'too_low': ['Сума нижча за мінімальну.', 'Сумма ниже минимальной.', 'თანხა მინიმალურზე ნაკლებია.'],
    'step': ['Сума має бути кратна 10 000 ₩.', 'Сумма должна быть кратна 10 000 ₩.', 'თანხა უნდა იყოს 10 000 ₩-ის ჯერადი.'],
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
    'var ERR={too_low:"too_low",step:"step",day_limit:"day_limit",no_start_price:"no_start_price"};'
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
    'box.querySelector(".kb-hint").textContent=t("min")+" ₩"+n(min);'
    'btn.textContent=t("place");function upd(){usd.textContent="≈ $"+n(Math.round((+inp.value||0)*rate));}'
    'inp.addEventListener("input",upd);upd();'
    'btn.addEventListener("click",function(){var krw=+inp.value||0;'
    'if(!confirm(t("confirm",{krw:n(krw),usd:n(Math.round(krw*rate)),title:title})))return;'
    'btn.disabled=true;msg.hidden=false;msg.textContent=t("sending");'
    'fetch("/api/auction/bid",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},'
    'body:JSON.stringify({lot:id,krw:krw})}).then(function(r){return r.json();}).then(function(r){'
    'msg.textContent=r.status==="requested"?t("requested"):t(ERR[r.error]||"other");'
    'btn.disabled=r.status==="requested";}).catch(function(){msg.textContent=t("other");btn.disabled=false;});});'
    'a.style.display="none";a.parentNode.insertBefore(box,a);});}'
    'function init(){var card=document.getElementById("kl-card");if(!card||!window.MutationObserver)return;'
    'new MutationObserver(function(){if(card.open)form(card);}).observe(card,{attributes:true,attributeFilter:["open"]});'
    'document.addEventListener("ua-auction-client",function(){if(card.open)form(card);});}'
    'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();'
    '})();</script>')

BLOCK = MARK + STYLE + SCRIPT + END


def replace(html):
    """The page with this block in place of the installed one; KOREA_BID_BLOCK if there is not exactly one."""
    if html.count(MARK) != 1 or html.count(END) != 1:
        raise ValueError('KOREA_BID_BLOCK')
    start = html.index(MARK)
    return html[:start] + BLOCK + html[html.index(END, start) + len(END):]
