"""«Вхід для клієнтів» on the Korea auctions page (JPAUTO-KOREA-001, owner 2026-11-10).

apply(html) on video/korea.html (with the lot list of KOREA-LOTS-PAGE): at the top of the lot list a small line —
«Вхід для клієнтів» for visitors, «Ви увійшли: <ім'я> · ліміт ставок … $ · Вийти» for a logged-in client — and the
login window (phone + password). It talks only to /api/auction/* (ua_auction_web) and tells the page who is logged in
through window.uaAuctionClient and the 'ua-auction-client' event (the bid step uses them). remove(html) takes it back.
"""
import json

MARK = '<!--UA-KOREA-LOGIN-V1-->'
END = '<!--/UA-KOREA-LOGIN-V1-->'
AFTER = '<section class="kr-sec" id="lots">'


def _t(uk, ru, ka, tag='span', attrs=''):
    return '<%s%s data-uk="%s" data-ru="%s" data-ka="%s">%s</%s>' % (tag, attrs, uk, ru, ka, uk, tag)


STYLE = ('<style id="ua-korea-login-v1">'
         '.kc-bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:flex-end;margin-bottom:10px}'
         '.kc-bar a,.kc-bar button{color:#f2b544;font-weight:700;background:none;border:0;cursor:pointer;font:inherit;'
         'text-decoration:underline}'
         '.kc-dialog{width:min(420px,94vw);border:0;border-radius:16px;padding:20px;background:#0B1524;color:#fff}'
         '.kc-dialog::backdrop{background:rgba(0,0,0,.7)}.kc-dialog form{display:grid;gap:10px}'
         '.kc-dialog input{width:100%;box-sizing:border-box;padding:12px;border-radius:10px;border:1px solid #2a3b55;'
         'background:#13233a;color:#fff;font-size:16px}.kc-error{color:#ff6b6b;min-height:1.2em}'
         '</style>')

BAR = (
    '<div class="kc-bar" id="kc-bar">'
    '<button type="button" id="kc-open">' + _t('Вхід для клієнтів', 'Вход для клиентов', 'კლიენტების შესვლა') + '</button>'
    '<span id="kc-who" hidden>' + _t('Ви увійшли:', 'Вы вошли:', 'თქვენ შეხვედით:') + ' <b id="kc-name"></b> · '
    + _t('ліміт ставок', 'лимит ставок', 'ფსონების ლიმიტი') + ' <b id="kc-limit"></b> $ · '
    '<button type="button" id="kc-out">' + _t('Вийти', 'Выйти', 'გასვლა') + '</button></span></div>'
    '<dialog class="kc-dialog" id="kc-dialog"><form id="kc-form">'
    + _t('Вхід для клієнтів', 'Вход для клиентов', 'კლიენტების შესვლა', 'h3')
    + _t('Логін і пароль видає менеджер після договору.', 'Логин и пароль выдаёт менеджер после договора.',
         'ლოგინს და პაროლს მენეჯერი გასცემს ხელშეკრულების შემდეგ.', 'p')
    + '<input name="phone" type="tel" autocomplete="username" placeholder="+380…" required>'
    '<input name="password" type="password" autocomplete="current-password" placeholder="Пароль" required>'
    '<span class="kc-error" id="kc-error"></span>'
    '<button class="kr-btn" type="submit">' + _t('Увійти', 'Войти', 'შესვლა') + '</button>'
    '<button type="button" class="kr-btn ghost" id="kc-close">' + _t('Закрити', 'Закрыть', 'დახურვა') + '</button>'
    '</form></dialog>')

ERRORS = {'login': ['Невірний логін або пароль', 'Неверный логин или пароль', 'არასწორი ლოგინი ან პაროლი'],
          'too_many': ['Забагато спроб. Спробуйте за 15 хвилин', 'Слишком много попыток. Попробуйте через 15 минут',
                       'ძალიან ბევრი მცდელობა. სცადეთ 15 წუთში'],
          'other': ['Не вдалося увійти. Спробуйте ще раз', 'Не удалось войти. Попробуйте ещё раз',
                    'შესვლა ვერ მოხერხდა. სცადეთ თავიდან']}

SCRIPT = (
    '<script>(function(){"use strict";var E=' + json.dumps(ERRORS, ensure_ascii=False) + ';'
    'function $(i){return document.getElementById(i);}'
    'function lang(){var l=document.documentElement.lang||"uk";return l==="ru"?1:l==="ka"?2:0;}'
    'function show(c){window.uaAuctionClient=c||null;$("kc-open").hidden=!!c;$("kc-who").hidden=!c;'
    'if(c){$("kc-name").textContent=c.name;$("kc-limit").textContent=Number(c.limit_usd).toLocaleString("uk-UA");}'
    'document.dispatchEvent(new CustomEvent("ua-auction-client",{detail:c||null}));}'
    'function post(a,b){return fetch("/api/auction/"+a,{method:"POST",credentials:"same-origin",'
    'headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})});}'
    'fetch("/api/auction/me",{credentials:"same-origin"}).then(function(r){return r.ok?r.json():{};})'
    '.then(function(d){show(d.client);}).catch(function(){show(null);});'
    '$("kc-open").addEventListener("click",function(){$("kc-error").textContent="";$("kc-dialog").showModal();});'
    '$("kc-close").addEventListener("click",function(){$("kc-dialog").close();});'
    '$("kc-out").addEventListener("click",function(){post("logout").then(function(){show(null);});});'
    '$("kc-form").addEventListener("submit",function(e){e.preventDefault();var f=e.target;'
    'post("login",{phone:f.phone.value,password:f.password.value}).then(function(r){'
    'return r.json().then(function(d){if(r.ok){f.reset();$("kc-dialog").close();show(d.client);}'
    'else{$("kc-error").textContent=(E[d.error]||E.other)[lang()];}});})'
    '.catch(function(){$("kc-error").textContent=E.other[lang()];});});'
    '})();</script>')

BLOCK = MARK + STYLE + BAR + SCRIPT + END


def apply(html):
    """Korea page with the client login line at the top of the lot list; any other page unchanged."""
    if not isinstance(html, str) or html.count(AFTER) != 1 or MARK in html:
        return html
    at = html.index(AFTER) + len(AFTER)
    return html[:at] + BLOCK + html[at:]


def remove(html):
    if MARK not in html:
        return html
    start = html.index(MARK)
    return html[:start] + html[html.index(END, start) + len(END):]
