"""«Мій кабінет» — the auction client's own page, video/kabinet.html (owner 2026-11-12).

page(korea_html) builds it from the live Korea page: the same site header (taken from that page, so the menu and the
language switch stay one), the site's stylesheet and language script, then three parts filled by GET /api/auction/my
for the logged-in client: «Мої дані» (name, login phone, prepayment, «Вийти»), «Мої ставки» (date, car, lot, VIN,
₩ and $, status: waiting for the manager / placed / not placed) and «Куплені авто». Without a login it points to the
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
    'lot': ['лот', 'лот', 'ლოტი'],
    'requested': ['⏳ Чекає менеджера', '⏳ Ждёт менеджера', '⏳ ელოდება მენეჯერს'],
    'placed': ['✅ Поставлено', '✅ Поставлено', '✅ განთავსებულია'],
    'not_placed': ['❌ Не поставлено', '❌ Не поставлено', '❌ არ განთავსდა'],
    'error': ['Не вдалося завантажити. Оновіть сторінку.', 'Не удалось загрузить. Обновите страницу.',
              'ჩატვირთვა ვერ მოხერხდა. განაახლეთ გვერდი.'],
}

STYLE = ('<style id="ua-cabinet-v1">.cab{max-width:860px;margin:0 auto;padding:24px 16px 48px;color:#fff}'
         '.cab h1{margin:0 0 16px}.cab h2{margin:24px 0 10px;font-size:20px}.cab-box{padding:14px;border-radius:12px;'
         'background:#13233a;border:1px solid #2a3b55}.cab-row{padding:10px 0;border-top:1px solid #2a3b55}'
         '.cab-row:first-child{border-top:0}.cab-sub{opacity:.8;font-size:14px}.cab-usd{color:#4ade80;font-weight:700}'
         '.cab a{color:#f2b544}#cab-out{margin-top:12px;padding:10px 18px;border-radius:10px;border:0;background:#f2b544;'
         'color:#0B1524;font-weight:700;cursor:pointer}</style>')

SCRIPT = (
    '<script>(function(){"use strict";var T=' + json.dumps(TEXT, ensure_ascii=False) + ',data=null;'
    'function L(){var l=document.documentElement.lang||"uk";return l==="ru"?1:l==="ka"?2:0;}'
    'function t(k){return T[k][L()];}function n(x){return Number(x||0).toLocaleString("uk-UA");}'
    'function $(id){return document.getElementById(id);}'
    'function row(lines){var d=document.createElement("div");d.className="cab-row";lines.forEach(function(x){'
    'var s=document.createElement("div");if(x[1])s.className=x[1];s.textContent=x[0];d.appendChild(s);});return d;}'
    'function list(id,items,make){var box=$(id);box.textContent="";if(!items.length){box.appendChild(row([[t("none")]]));'
    'return;}items.forEach(function(x){box.appendChild(make(x));});}'
    'function render(){if(!data)return;var c=data.client;$("cab-in").hidden=false;$("cab-login").hidden=true;'
    '$("cab-name").textContent=c.surname+" "+c.name;$("cab-phone").textContent=c.phone;'
    '$("cab-dep").textContent=n(c.deposit_usd);'
    'list("cab-bids",data.bids,function(b){return row([[b.created_at.slice(0,16).replace("T"," ")+" · "+'
    '(T[b.status]?t(b.status):t("not_placed"))],["🚗 "+b.title+" · "+t("lot")+" "+b.lot_id+(b.vin?" · VIN "+b.vin:""),'
    '"cab-sub"],["₩"+n(b.krw)+" ≈ $"+n(b.usd),"cab-usd"]]);});'
    'list("cab-cars",data.cars,function(a){return row([[a.title+" "+(a.year||"")],'
    '[(a.vin?"VIN "+a.vin:"")+(a.stage?" · "+a.stage:""),"cab-sub"]]);});}'
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
    '<div id="cab-login" class="cab-box" hidden><p id="cab-login-text"></p><a href="/video/korea.html">'
    + _t('Аукціони Кореї', 'Аукционы Кореи', 'კორეის აუქციონები') + '</a></div>'
    '<div id="cab-in" hidden>'
    '<h2>' + _t('Мої дані', 'Мои данные', 'ჩემი მონაცემები') + '</h2><div class="cab-box">'
    '<div><b id="cab-name"></b></div><div>' + _t('Логін', 'Логин', 'ლოგინი') + ': <span id="cab-phone"></span></div>'
    '<div>' + _t('Передоплата', 'Предоплата', 'წინასწარი გადახდა') + ': <span id="cab-dep"></span> $</div>'
    '<button type="button" id="cab-out">' + _t('Вийти', 'Выйти', 'გასვლა') + '</button></div>'
    '<h2>' + _t('Мої ставки', 'Мои ставки', 'ჩემი ფსონები') + '</h2><div class="cab-box" id="cab-bids"></div>'
    '<h2>' + _t('Куплені авто', 'Купленные авто', 'ნაყიდი ავტომობილები') + '</h2><div class="cab-box" id="cab-cars"></div>'
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
