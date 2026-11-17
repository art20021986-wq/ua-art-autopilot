"""«🔔 Автопошук» в «Мій кабінет» и учёт просмотров лотов на korea.html (AUTOSEARCH-001, владелец 17.11, макет
cloud/photos/33-AUTOSEARCH.png — «Да»). Используется только при сборке пакета; на сервер ставятся готовые страницы.

cabinet(page): в video/kabinet.html под «Мої ставки» — раздел с формой (марка, модель, рік від/до, пробіг до,
ціна до $, паливо, колір — те же списки, что фильтры korea.html), «💾 Зберегти пошук», «Мої пошуки N з 10» с «🗑»,
«📲 Підключити Telegram» / «✅ Підключено · Відключити». Свой стиль и свой скрипт; остальная страница не меняется.
korea(page): при открытии карточки лота вошедшим клиентом — POST /api/auction/alerts/seen (лот и название).
Каждая вставка — по точному месту, которое должно встретиться ровно один раз.
"""
import json

BIDS = '<div id="cab-bids"></div>'
HEAD_END = '</head>'
BODY_END = '</body>'
LOT_OPENED = '$("kl-card").showModal();$("kl-card").scrollTop=0;'
SEEN = ('if(window.uaAuctionClient)fetch("/api/auction/alerts/seen",{method:"POST",credentials:"same-origin",'
        'headers:{"Content-Type":"application/json"},body:JSON.stringify({lot:l.id,title:l.title+" "+l.year})})'
        '.catch(function(){});')
KM_STEPS = (30000, 50000, 75000, 100000, 150000, 200000, 250000, 300000)


def _t(uk, ru, ka):
    return '<span data-uk="%s" data-ru="%s" data-ka="%s">%s</span>' % (uk, ru, ka, uk)


def _field(uk, ru, ka, control):
    return '<label>' + _t(uk, ru, ka) + control + '</label>'


SECTION = (
    '<h2 id="as-head">🔔 ' + _t('Автопошук', 'Автопоиск', 'ავტოძიება') + '</h2>'
    '<div id="as" class="cab-card cab-in">'
    '<p class="as-sub">' + _t('Нові лоти аукціонів Кореї за вашими умовами — одразу в Telegram.',
                              'Новые лоты аукционов Кореи по вашим условиям — сразу в Telegram.',
                              'კორეის აუქციონების ახალი ლოტები თქვენი პირობებით — მაშინვე Telegram-ში.') + '</p>'
    '<form id="as-form" class="as-grid">'
    + _field('Марка', 'Марка', 'მარკა', '<select id="as-maker"></select>')
    + _field('Модель', 'Модель', 'მოდელი', '<select id="as-title"></select>')
    + _field('Рік від', 'Год от', 'წელი დან', '<select id="as-year-from"></select>')
    + _field('Рік до', 'Год до', 'წელი მდე', '<select id="as-year-to"></select>')
    + _field('Пробіг до, км', 'Пробег до, км', 'გარბენი მდე, კმ', '<select id="as-km"></select>')
    + _field('Ціна до, $', 'Цена до, $', 'ფასი მდე, $', '<input id="as-usd" type="number" inputmode="numeric" min="0">')
    + _field('Паливо', 'Топливо', 'საწვავი', '<select id="as-fuel"></select>')
    + _field('Колір', 'Цвет', 'ფერი', '<select id="as-color"></select>')
    + '<button type="submit" id="as-save">💾 ' + _t('Зберегти пошук', 'Сохранить поиск', 'ძიების შენახვა')
    + '</button><p id="as-msg" class="as-msg" role="status"></p></form></div>'
    '<div class="cab-card cab-in"><b>' + _t('Мої пошуки', 'Мои поиски', 'ჩემი ძიებები') + '</b> '
    '<span id="as-count" class="as-count"></span><div id="as-list"></div></div>'
    '<div class="cab-card cab-in"><b>Telegram</b><div class="as-tg">'
    '<span id="as-tg-on" class="cab-chip ok" hidden>✅ ' + _t('Підключено', 'Подключено', 'დაკავშირებულია') + '</span>'
    '<button type="button" id="as-tg-off" class="as-ghost" hidden>' + _t('Відключити', 'Отключить', 'გათიშვა')
    + '</button><button type="button" id="as-tg" hidden>📲 ' + _t('Підключити Telegram', 'Подключить Telegram',
                                                                 'Telegram-ის დაკავშირება') + '</button></div></div>')

STYLE = ('<style id="ua-autosearch-v1">.as-sub{margin:0 0 10px;opacity:.8}.as-grid{display:grid;grid-template-columns:1fr 1fr;'
         'gap:8px 10px}.as-grid label{display:grid;gap:4px;font-size:13px}.as-grid select,.as-grid input{padding:9px 10px;'
         'border-radius:10px;border:1px solid #2a3b55;background:#0B1524;color:#fff;font:inherit;min-width:0}'
         '#as-save,#as-tg{grid-column:1/-1;justify-self:start;padding:10px 18px;border-radius:10px;border:0;'
         'background:#f2b544;color:#0B1524;font-weight:800;cursor:pointer}#as-save:disabled{opacity:.5;cursor:default}'
         '.as-msg{grid-column:1/-1;margin:0;min-height:1em;color:#fcd34d}.as-count{opacity:.7;font-size:13px}'
         '.as-row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 0;'
         'border-top:1px solid #2a3b55}.as-row small{display:block;opacity:.7}.as-ghost,.as-del{padding:7px 12px;'
         'border-radius:10px;border:1px solid #2a3b55;background:transparent;color:#fff;cursor:pointer}'
         '.as-tg{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin-top:10px}'
         '.as-tg [hidden]{display:none!important}@media(max-width:520px){.as-grid{grid-template-columns:1fr}}</style>')

# [uk, ru, ka] for the texts the script writes
TEXT = {
    'any': ['Будь-який', 'Любой', 'ნებისმიერი'],
    'of': ['{a} з {b}', '{a} из {b}', '{a} / {b}'],
    'none': ['Поки немає.', 'Пока нет.', 'ჯერ არ არის.'],
    'sent': ['надіслано {n}', 'отправлено {n}', 'გაგზავნილია {n}'],
    'from': ['від', 'от', 'დან'], 'to': ['до', 'до', 'მდე'],
    'maker': ['Оберіть марку або модель.', 'Выберите марку или модель.', 'აირჩიეთ მარკა ან მოდელი.'],
    'limit': ['Можна зберегти до 10 пошуків.', 'Можно сохранить до 10 поисков.', 'შეიძლება 10-მდე ძიების შენახვა.'],
    'saved': ['Збережено. Нові авто прийдуть у Telegram.', 'Сохранено. Новые авто придут в Telegram.',
              'შენახულია. ახალი ავტომობილები Telegram-ში მოვა.'],
    'need_tg': ['Збережено. Підключіть Telegram, щоб отримувати авто.',
                'Сохранено. Подключите Telegram, чтобы получать авто.',
                'შენახულია. დააკავშირეთ Telegram, რომ მიიღოთ ავტომობილები.'],
    'error': ['Не вдалося. Спробуйте ще раз.', 'Не удалось. Попробуйте ещё раз.', 'ვერ მოხერხდა. სცადეთ ისევ.'],
    'fuel_gasoline': ['бензин', 'бензин', 'ბენზინი'], 'fuel_diesel': ['дизель', 'дизель', 'დიზელი'],
    'fuel_hybrid': ['гібрид', 'гибрид', 'ჰიბრიდი'], 'fuel_electric': ['електро', 'электро', 'ელექტრო'],
    'fuel_lpg': ['газ (LPG)', 'газ (LPG)', 'გაზი (LPG)'], 'fuel_hydrogen': ['водень', 'водород', 'წყალბადი'],
    'color_white': ['білий', 'белый', 'თეთრი'], 'color_black': ['чорний', 'черный', 'შავი'],
    'color_gray': ['сірий', 'серый', 'ნაცრისფერი'], 'color_silver': ['сріблястий', 'серебристый', 'ვერცხლისფერი'],
    'color_blue': ['синій', 'синий', 'ლურჯი'], 'color_red': ['червоний', 'красный', 'წითელი'],
    'color_brown': ['коричневий', 'коричневый', 'ყავისფერი'], 'color_beige': ['бежевий', 'бежевый', 'კრემისფერი'],
    'color_green': ['зелений', 'зеленый', 'მწვანე'], 'color_yellow': ['жовтий', 'желтый', 'ყვითელი'],
    'color_orange': ['помаранчевий', 'оранжевый', 'ნარინჯისფერი'], 'color_other': ['інший', 'другой', 'სხვა'],
}

SCRIPT = (
    '<script id="ua-autosearch-v1-js">(function(){"use strict";var T=' + json.dumps(TEXT, ensure_ascii=False)
    + ',KMS=[' + ','.join(str(k) for k in KM_STEPS) + '],st=null,API="/api/auction/alerts";'
    'function $(i){return document.getElementById(i);}'
    'function L(){var l=document.documentElement.lang||"uk";return l==="ru"?1:l==="ka"?2:0;}'
    'function t(k,v){var s=T[k][L()];for(var x in v||{})s=s.replace("{"+x+"}",v[x]);return s;}'
    'function n(x){return Number(x||0).toLocaleString("uk-UA");}'
    'function cap(w){return w.charAt(0).toUpperCase()+w.slice(1);}'
    # el(tag, class, text, children): data always goes in as text, never as HTML
    'function el(tag,cls,text,kids){var e=document.createElement(tag);if(cls)e.className=cls;'
    'if(text!=null)e.textContent=text;(kids||[]).forEach(function(k){if(k)e.appendChild(k);});return e;}'
    # opt(sel, [[value, label], ...]): «Будь-який» first; the chosen value is kept
    'function opt(sel,items){var keep=sel.value;sel.textContent="";[["",t("any")]].concat(items).forEach(function(v){'
    'var o=document.createElement("option");o.value=v[0];o.textContent=v[1];sel.appendChild(o);});'
    'sel.value=keep;if(sel.selectedIndex<0)sel.value="";}'
    'function models(){var m=$("as-maker").value,all=st.options.makers,list=[];'
    'Object.keys(all).forEach(function(k){if(!m||k===m)all[k].forEach(function(x){'
    'list.push([x,m&&x.indexOf(m+" ")===0?x.slice(m.length+1):x]);});});opt($("as-title"),list);}'
    'function lists(){var o=st.options,ys=o.years.map(function(y){return [String(y),String(y)];});'
    'opt($("as-maker"),Object.keys(o.makers).map(function(k){return [k,k];}));models();'
    'opt($("as-year-from"),ys);opt($("as-year-to"),ys);opt($("as-km"),KMS.map(function(k){return [String(k),n(k)];}));'
    'opt($("as-fuel"),o.fuels.map(function(f){return [f,cap(t("fuel_"+f))];}));'
    'opt($("as-color"),o.colors.map(function(c){return [c,cap(t("color_"+c))];}));}'
    'function desc(c){var p=[c.title||c.maker];if(c.year_from&&c.year_to)p.push(c.year_from===c.year_to?c.year_from:'
    'c.year_from+"–"+c.year_to);else if(c.year_from)p.push(t("from")+" "+c.year_from);else if(c.year_to)'
    'p.push(t("to")+" "+c.year_to);if(c.km_max)p.push(t("to")+" "+n(c.km_max)+" км");'
    'if(c.usd_max)p.push(t("to")+" "+n(c.usd_max)+" $");if(c.fuel)p.push(t("fuel_"+c.fuel));'
    'if(c.color)p.push(t("color_"+c.color));return p.join(" · ");}'
    'function render(){if(!st)return;var box=$("as-list");box.textContent="";'
    '$("as-count").textContent=t("of",{a:st.searches.length,b:st.limit});'
    'if(!st.searches.length)box.appendChild(el("div","as-row",t("none")));'
    'st.searches.forEach(function(s){var del=el("button","as-del","🗑");del.type="button";'
    'del.addEventListener("click",function(){call("delete",{id:s.id});});'
    'box.appendChild(el("div","as-row",null,[el("div",null,desc(s.criteria),[el("small",null,t("sent",{n:s.sent}))]),'
    'del]));});$("as-save").disabled=st.searches.length>=st.limit;'
    '$("as-tg-on").hidden=$("as-tg-off").hidden=!st.telegram;$("as-tg").hidden=st.telegram;}'
    'function set(d){var o=st&&st.options;st=d;if(!st.options)st.options=o;render();}'
    'function msg(k){$("as-msg").textContent=k?t(k):"";}'
    'function call(a,b){return fetch(API+"/"+a,{method:"POST",credentials:"same-origin",'
    'headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})}).then(function(r){'
    'return r.json().then(function(d){if(!r.ok)throw d;if(a!=="telegram")set(d);return d;});})'
    '.catch(function(e){msg(e&&e.error==="maker"?"maker":e&&e.error==="limit"?"limit":"error");throw e;});}'
    'function load(){fetch(API,{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.ok?r.json():null;})'
    '.then(function(d){if(d){st=d;lists();render();}}).catch(function(){});}'
    'function init(){if(!$("as"))return;load();$("as-maker").addEventListener("change",models);'
    '$("as-form").addEventListener("submit",function(e){e.preventDefault();msg("");'
    'var v={maker:$("as-maker").value,title:$("as-title").value,year_from:$("as-year-from").value,'
    'year_to:$("as-year-to").value,km_max:$("as-km").value,usd_max:$("as-usd").value,fuel:$("as-fuel").value,'
    'color:$("as-color").value};if(!v.maker&&!v.title){msg("maker");return;}'
    'call("add",v).then(function(){msg(st.telegram?"saved":"need_tg");}).catch(function(){});});'
    '$("as-tg").addEventListener("click",function(){call("telegram").then(function(d){location.href=d.url;})'
    '.catch(function(){});});$("as-tg-off").addEventListener("click",function(){call("unlink").catch(function(){});});'
    # back from Telegram: show «✅ Підключено»
    'document.addEventListener("visibilitychange",function(){if(!document.hidden&&st&&!st.telegram)'
    'fetch(API,{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.ok?r.json():null;})'
    '.then(function(d){if(d)set(d);}).catch(function(){});});'
    'if(window.MutationObserver)new MutationObserver(function(){if(st){lists();render();}})'
    '.observe(document.documentElement,{attributes:true,attributeFilter:["lang"]});}'
    'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();'
    '})();</script>')


def _once(page, mark, code):
    if page.count(mark) != 1:
        raise ValueError(code)


def cabinet(page):
    """video/kabinet.html with the «🔔 Автопошук» section after «Мої ставки»."""
    for mark in (BIDS, HEAD_END, BODY_END):
        _once(page, mark, 'CABINET_PAGE_UNEXPECTED')
    if 'id="ua-autosearch-v1"' in page:
        raise ValueError('CABINET_ALREADY_HAS_AUTOSEARCH')
    return (page.replace(BIDS, BIDS + SECTION).replace(HEAD_END, STYLE + HEAD_END)
            .replace(BODY_END, SCRIPT + BODY_END))


def korea(page):
    """video/korea.html: a logged-in client's opened lot is counted (owner 2026-11-17 «Да»)."""
    _once(page, LOT_OPENED, 'KOREA_LOT_CARD')
    if SEEN in page:
        raise ValueError('KOREA_ALREADY_COUNTS_VIEWS')
    return page.replace(LOT_OPENED, LOT_OPENED + SEEN)
