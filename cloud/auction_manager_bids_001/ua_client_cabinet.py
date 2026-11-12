"""«Мій кабінет» — the auction client's own page, video/kabinet.html (owner 2026-11-12).

page(korea_html) builds it from the live Korea page: the same site header (taken from that page, so the menu and the
language switch stay one), the site's stylesheet and language script, then three parts filled by GET /api/auction/my
for the logged-in client (owner 2026-11-12: clearly split, by stages): a short line with the client's data and
«Вийти»; «🚗 Мої авто» — a card per car: photo, title, VIN / price (no lot number, owner 2026-11-12), «Де зараз авто» (the delivery stages,
done / current / next), «Оплати» (paid of total with a bar, each payment with a coloured status: paid, days left,
overdue, penalty accrued) and the contract's penalty terms for late payment; «🔨 Мої ставки» — a card per bid with a
coloured status (waiting for the manager / placed / not placed). The numbers and stages come from the contract
accounting (ua_auction_cars); the page only shows them, always as text. Without a login it points to the
Korea page, where the client logs in. Private: not indexed, not in the sitemap. Texts in uk / ru / ka.
link(html) adds «Мій кабінет» to the login line of the Korea page.
"""
import json
import re

PATH = 'video/kabinet.html'
HREF = '/video/kabinet.html'
HEADER = re.compile(r'<header class="site-header">.*?</header>', re.S)
LANG_SCRIPT = re.compile(r'<script id="ua-art-site-languages" src="[^"]+"[^>]*></script>')
STYLESHEET = re.compile(r'<link rel="stylesheet" href="ua-v[0-9]+\.css[^"]*">')
# The login line of the Korea page (UA-KOREA-LOGIN-V1): «Мій кабінет» goes before «Вийти».
LOGIN_OUT = '<b id="kc-name"></b> · <button type="button" id="kc-out">'
CABINET_LINK = ('<b id="kc-name"></b> · <a id="kc-cab" href="' + HREF + '"><span data-uk="Мій кабінет" data-ru="Мой кабинет" '
                'data-ka="ჩემი კაბინეტი">Мій кабінет</span></a> · <button type="button" id="kc-out">')


def _t(uk, ru, ka):
    return '<span data-uk="%s" data-ru="%s" data-ka="%s">%s</span>' % (uk, ru, ka, uk)


# [uk, ru, ka] for the texts the script writes
TEXT = {
    'login': ['Ви ще не увійшли. Увійдіть на сторінці аукціонів Кореї («Вхід для клієнтів»).',
              'Вы ещё не вошли. Войдите на странице аукционов Кореи («Вход для клиентов»).',
              'ჯერ არ შესულხართ. შედით კორეის აუქციონების გვერდზე («კლიენტების შესვლა»).'],
    'none': ['Поки немає.', 'Пока нет.', 'ჯერ არ არის.'],
    'stages': ['Де зараз авто', 'Где сейчас авто', 'სად არის ახლა ავტომობილი'],
    'payments': ['Оплати', 'Оплаты', 'გადახდები'],
    'paid_of': ['Сплачено ${p} з ${a}', 'Оплачено ${p} из ${a}', 'გადახდილია ${p} / ${a}'],
    'price': ['Ціна авто', 'Цена авто', 'ავტომობილის ფასი'],
    'pay_services': ['Послуги компанії', 'Услуги компании', 'კომპანიის მომსახურება'],
    'pay_deposit': ['Передоплата', 'Предоплата', 'წინასწარი გადახდა'],
    'pay_car': ['Вартість авто', 'Стоимость авто', 'ავტომობილის ღირებულება'],
    'pay_logistics': ['Логістика', 'Логистика', 'ლოჯისტიკა'],
    'pay_customs': ['Розмитнення', 'Растаможка', 'განბაჟება'],
    'paid': ['✅ сплачено', '✅ оплачено', '✅ გადახდილია'],
    'paid_part': ['сплачено', 'оплачено', 'გადახდილია'],
    'left': ['залишилось {d} роб. дн.', 'осталось {d} раб. дн.', 'დარჩა {d} სამუშაო დღე'],
    'overdue': ['⚠️ прострочено {d} роб. дн.', '⚠️ просрочено {d} раб. дн.', '⚠️ ვადაგადაცილება {d} სამუშაო დღე'],
    'no_due': ['без строку', 'без срока', 'ვადის გარეშე'],
    'penalty_now': ['нараховано пені', 'начислено пени', 'დარიცხული პირგასამტეხლო'],
    'penalty_head': ['⚠️ При несплаті в строк за договором:', '⚠️ При неуплате в срок по договору:',
                     '⚠️ ვადაში გადაუხდელობისას ხელშეკრულებით:'],
    'daily': ['пеня {p} % від простроченої суми за кожен день', 'пеня {p} % от просроченной суммы за каждый день',
              'პირგასამტეხლო {p} % ვადაგადაცილებული თანხიდან ყოველ დღეზე'],
    'annual': ['пеня {p} % річних від простроченої суми за кожен день', 'пеня {p} % годовых от просроченной суммы за каждый день',
               'პირგასამტეხლო წლიური {p} % ვადაგადაცილებული თანხიდან ყოველ დღეზე'],
    'fine': ['штраф {p} %', 'штраф {p} %', 'ჯარიმა {p} %'],
    'fine_after': ['штраф {p} % після {d} роб. днів прострочення', 'штраф {p} % после {d} раб. дней просрочки',
                   'ჯარიმა {p} % {d} სამუშაო დღის ვადაგადაცილების შემდეგ'],
    'clause': ['п.', 'п.', 'პ.'],
    'requested': ['⏳ Чекає менеджера', '⏳ Ждёт менеджера', '⏳ ელოდება მენეჯერს'],
    'placed': ['✅ Поставлено', '✅ Поставлено', '✅ განთავსებულია'],
    'not_placed': ['❌ Не поставлено', '❌ Не поставлено', '❌ არ განთავსდა'],
    'error': ['Не вдалося завантажити. Оновіть сторінку.', 'Не удалось загрузить. Обновите страницу.',
              'ჩატვირთვა ვერ მოხერხდა. განაახლეთ გვერდი.'],
}

STYLE = ('<style id="ua-cabinet-v1">.cab{max-width:860px;margin:0 auto;padding:24px 16px 48px;color:#fff}'
         '.cab h1{margin:0 0 6px}.cab h2{margin:28px 0 12px;font-size:20px}.cab a{color:#f2b544}'
         '.cab-me{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center;padding:14px;border-radius:14px;'
         'background:#13233a;border:1px solid #2a3b55}.cab-me b{font-size:18px}.cab-me span{opacity:.85}'
         '#cab-out{margin-left:auto;padding:8px 16px;border-radius:10px;border:0;background:#f2b544;color:#0B1524;'
         'font-weight:700;cursor:pointer}.cab-card{border-radius:16px;background:#13233a;border:1px solid #2a3b55;'
         'overflow:hidden;margin-bottom:14px}.cab-card img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover}'
         '.cab-in{padding:14px}.cab-title{font-size:18px;font-weight:800}.cab-tags{display:flex;flex-wrap:wrap;gap:6px;'
         'margin:8px 0 2px}.cab-tag{font-size:13px;padding:3px 8px;border-radius:999px;background:#0B1524;'
         'border:1px solid #2a3b55;opacity:.9}.cab-chip{display:inline-block;font-size:13px;font-weight:700;'
         'padding:3px 10px;border-radius:999px;white-space:nowrap}.ok{background:#14532d;color:#86efac}'
         '.wait{background:#3b2f0b;color:#fcd34d}.bad{background:#4c1d1d;color:#fca5a5}.cab-h{margin:16px 0 8px;'
         'font-size:13px;text-transform:uppercase;letter-spacing:.06em;opacity:.7}.cab-steps{list-style:none;'
         'margin:0;padding:0}.cab-steps li{position:relative;padding:0 0 12px 26px}.cab-steps li:before{'
         'content:"";position:absolute;left:6px;top:4px;width:10px;height:10px;border-radius:50%;background:#2a3b55}'
         '.cab-steps li:after{content:"";position:absolute;left:10px;top:16px;bottom:0;width:2px;background:#2a3b55}'
         '.cab-steps li:last-child:after{display:none}.cab-steps .done{opacity:.75}.cab-steps .done:before{'
         'background:#4ade80}.cab-steps .current{font-weight:800;color:#f2b544}.cab-steps .current:before{'
         'background:#f2b544;box-shadow:0 0 0 4px rgba(242,181,68,.25)}.cab-steps .todo{opacity:.5}'
         '.cab-bar{height:8px;border-radius:99px;background:#0B1524;overflow:hidden;margin:6px 0 10px}'
         '.cab-bar i{display:block;height:100%;background:#4ade80}.cab-pay{display:flex;justify-content:space-between;'
         'gap:10px;align-items:center;padding:9px 0;border-top:1px solid #2a3b55}.cab-pay small{display:block;'
         'opacity:.75}.cab-warn{margin-top:12px;padding:10px 12px;border-radius:12px;border:1px solid #b45309;'
         'background:#2a1e05;color:#fcd34d;font-size:14px}.cab-bid{padding:12px 14px}.cab-bid .top{display:flex;'
         'justify-content:space-between;gap:10px;align-items:flex-start}.cab-sub{opacity:.75;font-size:14px;'
         'margin-top:4px}.cab-usd{color:#4ade80;font-weight:800;margin-top:6px}.cab-none{padding:14px;opacity:.75}'
         '</style>')

SCRIPT = (
    '<script>(function(){"use strict";var T=' + json.dumps(TEXT, ensure_ascii=False) + ',data=null;'
    'function L(){var l=document.documentElement.lang||"uk";return l==="ru"?1:l==="ka"?2:0;}'
    'function t(k,v){var s=T[k][L()];for(var x in v||{})s=s.replace("{"+x+"}",v[x]);return s;}'
    'function n(x){return Number(x||0).toLocaleString("uk-UA");}function $(id){return document.getElementById(id);}'
    # el(tag, class, text, children): data always goes in as text, never as HTML
    'function el(tag,cls,text,kids){var e=document.createElement(tag);if(cls)e.className=cls;'
    'if(text!=null)e.textContent=text;(kids||[]).forEach(function(k){if(k)e.appendChild(k);});return e;}'
    'function chip(cls,text){return el("span","cab-chip "+cls,text);}'
    'function tags(list){return el("div","cab-tags",null,list.filter(Boolean).map(function(x){'
    'return el("span","cab-tag",x);}));}'
    'function fill(id,items,make){var box=$(id);box.textContent="";if(!items.length){'
    'box.appendChild(el("div","cab-card cab-none",t("none")));return;}items.forEach(function(x){box.appendChild(make(x));});}'
    'function payment(p){var name=T["pay_"+p.kind]?t("pay_"+p.kind):p.kind,done=p.paid_usd>=p.amount_usd,'
    'late=!done&&p.days_left!=null&&p.days_left<0,state=done?chip("ok",t("paid")):late?chip("bad",'
    't("overdue",{d:-p.days_left})):chip("wait",p.days_left==null?t("no_due"):t("left",{d:p.days_left}));'
    'var note=[];if(!done&&p.paid_usd)note.push(t("paid_part")+" $"+n(p.paid_usd));'
    'if(p.penalty_usd)note.push(t("penalty_now")+" $"+n(p.penalty_usd));'
    'return el("div","cab-pay",null,[el("div",null,name+" · $"+n(p.amount_usd),[note.length?el("small",null,'
    'note.join(" · ")):null]),state]);}'
    'function penalty(q){var parts=[];q=q||{};if(q.daily_percent!=null)parts.push(t("daily",{p:q.daily_percent}));'
    'if(q.annual_percent!=null)parts.push(t("annual",{p:q.annual_percent}));if(q.fine_percent!=null)parts.push('
    'q.fine_after_working_days?t("fine_after",{p:q.fine_percent,d:q.fine_after_working_days}):t("fine",{p:q.fine_percent}));'
    'return parts.length?el("div","cab-warn",t("penalty_head")+" "+parts.join(", ")+(q.clause?" ("+t("clause")+" "+'
    'String(q.clause).replace(/^п\\.\\s*/,"")+")":"")+"."):null;}'
    'function car(a){var pays=a.payments||[],total=0,paid=0;pays.forEach(function(p){total+=p.amount_usd||0;'
    'paid+=Math.min(p.paid_usd||0,p.amount_usd||0);});var bar=el("div","cab-bar",null,[el("i")]);'
    'bar.firstChild.style.width=(total?Math.round(paid*100/total):0)+"%";'
    'var steps=(a.stages||[]).length?el("ol","cab-steps",null,a.stages.map(function(s){'
    'return el("li",s.state,(s.state==="done"?"✓ ":"")+s.label);})):a.stage_label?el("div",null,null,'
    '[chip("wait",a.stage_label)]):null;var img=null;if(a.photo){img=el("img");img.src=a.photo;img.alt="";'
    'img.loading="lazy";img.onerror=function(){img.remove();};}return el("div","cab-card",null,[img,el("div","cab-in",null,[el("div","cab-title",'
    'a.title+(a.year?" "+a.year:"")),tags([a.vin?"VIN "+a.vin:"",'
    'a.price_usd?t("price")+" $"+n(a.price_usd):""]),steps?el("div","cab-h",t("stages")):null,steps,'
    'pays.length?el("div","cab-h",t("payments")):null,pays.length?el("div",null,t("paid_of",{p:n(paid),'
    'a:n(total)})):null,pays.length?bar:null].concat(pays.map(payment)).concat([penalty(a.penalty)]))]);}'
    'function bid(b){var cls=b.status==="placed"?"ok":b.status==="requested"?"wait":"bad";'
    'return el("div","cab-card cab-bid",null,[el("div","top",null,[el("b",null,"🚗 "+b.title),'
    'chip(cls,T[b.status]?t(b.status):t("not_placed"))]),el("div","cab-sub",['
    'b.vin?"VIN "+b.vin:"",b.created_at.slice(0,16).replace("T"," ")].filter(Boolean).join(" · ")),'
    'el("div","cab-usd","₩"+n(b.krw)+" ≈ $"+n(b.usd))]);}'
    'function render(){if(!data)return;var c=data.client;$("cab-in").hidden=false;$("cab-login").hidden=true;'
    '$("cab-name").textContent=c.surname+" "+c.name;$("cab-phone").textContent=c.phone;'
    '$("cab-dep").textContent=n(c.deposit_usd);fill("cab-cars",data.cars,car);fill("cab-bids",data.bids,bid);}'
    'function load(){fetch("/api/auction/my",{credentials:"same-origin",cache:"no-store"}).then(function(r){'
    'if(r.status===401){$("cab-login").hidden=false;$("cab-login-text").textContent=t("login");return null;}'
    'if(!r.ok)throw 0;return r.json();}).then(function(d){if(d){data=d;render();}}).catch(function(){'
    '$("cab-login").hidden=false;$("cab-login-text").textContent=t("error");});}'
    'function init(){load();$("cab-out").addEventListener("click",function(){fetch("/api/auction/logout",'
    '{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:"{}"}).then(function(){'
    'location.href="/video/korea.html";});});if(window.MutationObserver)new MutationObserver(function(){render();'
    'if(!data&&!$("cab-login").hidden)$("cab-login-text").textContent=t("login");}).observe(document.documentElement,'
    '{attributes:true,attributeFilter:["lang"]});}'
    'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();'
    '})();</script>')

MAIN = (
    '<main class="cab">'
    '<h1>' + _t('Мій кабінет', 'Мой кабинет', 'ჩემი კაბინეტი') + '</h1>'
    '<div id="cab-login" class="cab-card cab-in" hidden><p id="cab-login-text"></p><a href="/video/korea.html">'
    + _t('Аукціони Кореї', 'Аукционы Кореи', 'კორეის აუქციონები') + '</a></div>'
    '<div id="cab-in" hidden>'
    '<div class="cab-me"><b id="cab-name"></b><span>' + _t('Логін', 'Логин', 'ლოგინი') + ': <span id="cab-phone">'
    '</span></span><span>' + _t('Передоплата', 'Предоплата', 'წინასწარი გადახდა') + ': <span id="cab-dep"></span> $'
    '</span><button type="button" id="cab-out">' + _t('Вийти', 'Выйти', 'გასვლა') + '</button></div>'
    '<h2>🚗 ' + _t('Мої авто', 'Мои авто', 'ჩემი ავტომობილები') + '</h2><div id="cab-cars"></div>'
    '<h2>🔨 ' + _t('Мої ставки', 'Мои ставки', 'ჩემი ფსონები') + '</h2><div id="cab-bids"></div>'
    '</div></main>')

def page(korea_html):
    """video/kabinet.html built from the live Korea page (its header, stylesheet and language script)."""
    header, languages, sheet = (HEADER.findall(korea_html), LANG_SCRIPT.findall(korea_html),
                                STYLESHEET.findall(korea_html))
    if len(header) != 1 or len(languages) != 1 or len(sheet) != 1:
        raise ValueError('CABINET_KOREA_PAGE_UNEXPECTED')
    return ('<!doctype html><html lang="uk"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="robots" content="noindex, nofollow"><title>Мій кабінет — UA ART COMPANY</title>'
            + sheet[0] + STYLE + languages[0] + '</head>'
            '<body>' + header[0] + MAIN + SCRIPT + '</body></html>')


def link(html):
    """The Korea page with «Мій кабінет» in the login line; KOREA_LOGIN_LINE if that line is not there once."""
    if html.count(LOGIN_OUT) != 1:
        raise ValueError('KOREA_LOGIN_LINE')
    return html.replace(LOGIN_OUT, CABINET_LINK)
