"""«🔍 Запит на пошук для клієнта» в «Мій кабінет» — только для менеджера (AUTOSEARCH-002, владелец 17.11, макет
cloud/photos/33-AUTOSEARCH-MANAGER.png — «Да»). Используется только при сборке пакета; на сервер ставится готовая страница.

cabinet(page): под «Мої ставки» — раздел, который видит только менеджер (GET /api/auction/alerts отвечает 200):
клиент (свои клиенты; у владельца — все), марка, модель, рік від/до, пробіг до, ціна до $, паливо, колір (списки — как
фильтры korea.html), «Посилання на групу WhatsApp», «💾 Зберегти запит»; «Запити моїх клієнтів» с «🗑». Клиент без прав
менеджера раздела не видит. Свой стиль и свой скрипт; остальная страница не меняется; каждое место — ровно один раз.
"""
import json

BIDS = '<div id="cab-bids"></div>'
HEAD_END = '</head>'
BODY_END = '</body>'
KM_STEPS = (30000, 50000, 75000, 100000, 150000, 200000, 250000, 300000)


def _t(uk, ru, ka):
    return '<span data-uk="%s" data-ru="%s" data-ka="%s">%s</span>' % (uk, ru, ka, uk)


def _field(uk, ru, ka, control, wide=False):
    return '<label%s>' % (' class="mr-wide"' if wide else '') + _t(uk, ru, ka) + control + '</label>'


SECTION = (
    '<section id="mr" hidden><h2>🔍 ' + _t('Запит на пошук для клієнта', 'Запрос на поиск для клиента',
                                           'ძიების მოთხოვნა კლიენტისთვის') + '</h2>'
    '<div class="cab-card cab-in"><p class="mr-sub">' + _t('Менеджер', 'Менеджер', 'მენეჯერი')
    + ': <b id="mr-me"></b></p><form id="mr-form" class="mr-grid">'
    + _field('Клієнт', 'Клиент', 'კლიენტი', '<select id="mr-client" required></select>', True)
    + _field('Марка', 'Марка', 'მარკა', '<select id="mr-maker"></select>')
    + _field('Модель', 'Модель', 'მოდელი', '<select id="mr-title"></select>')
    + _field('Рік від', 'Год от', 'წელი დან', '<select id="mr-year-from"></select>')
    + _field('Рік до', 'Год до', 'წელი მდე', '<select id="mr-year-to"></select>')
    + _field('Пробіг до, км', 'Пробег до, км', 'გარბენი მდე, კმ', '<select id="mr-km"></select>')
    + _field('Ціна до, $', 'Цена до, $', 'ფასი მდე, $', '<input id="mr-usd" type="number" inputmode="numeric" min="0">')
    + _field('Паливо', 'Топливо', 'საწვავი', '<select id="mr-fuel"></select>')
    + _field('Колір', 'Цвет', 'ფერი', '<select id="mr-color"></select>')
    + _field('Посилання на групу WhatsApp', 'Ссылка на группу WhatsApp', 'WhatsApp ჯგუფის ბმული',
             '<input id="mr-group" type="url" inputmode="url" placeholder="https://chat.whatsapp.com/…" required>', True)
    + '<button type="submit" id="mr-save">💾 ' + _t('Зберегти запит', 'Сохранить запрос', 'მოთხოვნის შენახვა')
    + '</button><p id="mr-msg" class="mr-msg" role="status"></p></form></div>'
    '<div class="cab-card cab-in"><b>' + _t('Запити моїх клієнтів', 'Запросы моих клиентов', 'ჩემი კლიენტების მოთხოვნები')
    + '</b><div id="mr-list"></div></div></section>')

STYLE = ('<style id="ua-manager-v1">.mr-sub{margin:0 0 10px;opacity:.85}.mr-grid{display:grid;grid-template-columns:1fr 1fr;'
         'gap:8px 10px}.mr-grid label{display:grid;gap:4px;font-size:13px}.mr-grid .mr-wide{grid-column:1/-1}'
         '.mr-grid select,.mr-grid input{padding:9px 10px;border-radius:10px;border:1px solid #2a3b55;background:#0B1524;'
         'color:#fff;font:inherit;min-width:0}#mr-save{grid-column:1/-1;justify-self:start;padding:10px 18px;'
         'border-radius:10px;border:0;background:#f2b544;color:#0B1524;font-weight:800;cursor:pointer}'
         '.mr-msg{grid-column:1/-1;margin:0;min-height:1em;color:#fcd34d}.mr-row{display:flex;justify-content:space-between;'
         'align-items:center;gap:10px;padding:9px 0;border-top:1px solid #2a3b55}.mr-row small{display:block;opacity:.7}'
         '.mr-del{padding:7px 12px;border-radius:10px;border:1px solid #2a3b55;background:transparent;color:#fff;'
         'cursor:pointer}@media(max-width:520px){.mr-grid{grid-template-columns:1fr}}</style>')

# [uk, ru, ka] for the texts the script writes
TEXT = {
    'any': ['Будь-який', 'Любой', 'ნებისმიერი'],
    'pick': ['Оберіть клієнта', 'Выберите клиента', 'აირჩიეთ კლიენტი'],
    'none': ['Поки немає.', 'Пока нет.', 'ჯერ არ არის.'],
    'found': ['знайдено {n}', 'найдено {n}', 'ნაპოვნია {n}'],
    'from': ['від', 'от', 'დან'], 'to': ['до', 'до', 'მდე'],
    'maker': ['Оберіть марку або модель.', 'Выберите марку или модель.', 'აირჩიეთ მარკა ან მოდელი.'],
    'client': ['Оберіть клієнта.', 'Выберите клиента.', 'აირჩიეთ კლიენტი.'],
    'group_link': ['Вставте посилання-запрошення групи WhatsApp (https://chat.whatsapp.com/…).',
                   'Вставьте ссылку-приглашение группы WhatsApp (https://chat.whatsapp.com/…).',
                   'ჩასვით WhatsApp ჯგუფის მოწვევის ბმული (https://chat.whatsapp.com/…).'],
    'limit': ['У клієнта вже 10 запитів.', 'У клиента уже 10 запросов.', 'კლიენტს უკვე 10 მოთხოვნა აქვს.'],
    'saved': ['Запит збережено. Привітання для групи прийде вам у CRM-бот.',
              'Запрос сохранён. Приветствие для группы придёт вам в CRM-бот.',
              'მოთხოვნა შენახულია. ჯგუფის მისალმება CRM-ბოტში მოგივათ.'],
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
    '<script id="ua-manager-v1-js">(function(){"use strict";var T=' + json.dumps(TEXT, ensure_ascii=False)
    + ',KMS=[' + ','.join(str(k) for k in KM_STEPS) + '],st=null,API="/api/auction/alerts";'
    'function $(i){return document.getElementById(i);}'
    'function L(){var l=document.documentElement.lang||"uk";return l==="ru"?1:l==="ka"?2:0;}'
    'function t(k,v){var s=T[k][L()];for(var x in v||{})s=s.replace("{"+x+"}",v[x]);return s;}'
    'function n(x){return Number(x||0).toLocaleString("uk-UA");}'
    'function cap(w){return w.charAt(0).toUpperCase()+w.slice(1);}'
    # el(tag, class, text, children): data always goes in as text, never as HTML
    'function el(tag,cls,text,kids){var e=document.createElement(tag);if(cls)e.className=cls;'
    'if(text!=null)e.textContent=text;(kids||[]).forEach(function(k){if(k)e.appendChild(k);});return e;}'
    # opt(sel, [[value, label], ...], first): a first option («Будь-який» or «Оберіть клієнта»); the chosen value is kept
    'function opt(sel,items,first){var keep=sel.value;sel.textContent="";[["",t(first||"any")]].concat(items)'
    '.forEach(function(v){var o=document.createElement("option");o.value=v[0];o.textContent=v[1];sel.appendChild(o);});'
    'sel.value=keep;if(sel.selectedIndex<0)sel.value="";}'
    'function models(){var m=$("mr-maker").value,all=st.options.makers,list=[];'
    'Object.keys(all).forEach(function(k){if(!m||k===m)all[k].forEach(function(x){'
    'list.push([x,m&&x.indexOf(m+" ")===0?x.slice(m.length+1):x]);});});opt($("mr-title"),list);}'
    'function lists(){var o=st.options,ys=o.years.map(function(y){return [String(y),String(y)];});'
    'opt($("mr-client"),st.clients.map(function(c){return [c.phone,c.name+" · "+c.phone];}),"pick");'
    'opt($("mr-maker"),Object.keys(o.makers).map(function(k){return [k,k];}));models();'
    'opt($("mr-year-from"),ys);opt($("mr-year-to"),ys);opt($("mr-km"),KMS.map(function(k){return [String(k),n(k)];}));'
    'opt($("mr-fuel"),o.fuels.map(function(f){return [f,cap(t("fuel_"+f))];}));'
    'opt($("mr-color"),o.colors.map(function(c){return [c,cap(t("color_"+c))];}));}'
    'function desc(c){var p=[c.title||c.maker];if(c.year_from&&c.year_to)p.push(c.year_from===c.year_to?c.year_from:'
    'c.year_from+"–"+c.year_to);else if(c.year_from)p.push(t("from")+" "+c.year_from);else if(c.year_to)'
    'p.push(t("to")+" "+c.year_to);if(c.km_max)p.push(t("to")+" "+n(c.km_max)+" км");'
    'if(c.usd_max)p.push(t("to")+" "+n(c.usd_max)+" $");if(c.fuel)p.push(t("fuel_"+c.fuel));'
    'if(c.color)p.push(t("color_"+c.color));return p.join(" · ");}'
    'function num(i){return "№"+("00"+i).slice(-3);}'
    'function render(){if(!st)return;$("mr").hidden=false;$("mr-me").textContent=st.manager;var box=$("mr-list");'
    'box.textContent="";if(!st.requests.length)box.appendChild(el("div","mr-row",t("none")));'
    'st.requests.forEach(function(r){var del=el("button","mr-del","🗑");del.type="button";'
    'del.addEventListener("click",function(){call("delete",{id:r.id});});'
    'box.appendChild(el("div","mr-row",null,[el("div",null,num(r.id)+" · "+r.client_name+" · "+desc(r.criteria),'
    '[el("small",null,t("found",{n:r.found}))]),del]));});}'
    'function msg(k){$("mr-msg").textContent=k?t(k):"";}'
    'function call(a,b){return fetch(API+"/"+a,{method:"POST",credentials:"same-origin",'
    'headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})}).then(function(r){'
    'return r.json().then(function(d){if(!r.ok)throw d;var o=st.options;st=d;st.options=o;render();return d;});})'
    '.catch(function(e){var k=e&&e.error;msg(T[k]?k:"error");throw e;});}'
    'function init(){if(!$("mr"))return;fetch(API,{credentials:"same-origin",cache:"no-store"}).then(function(r){'
    'return r.ok?r.json():null;}).then(function(d){if(d){st=d;lists();render();}}).catch(function(){});'
    '$("mr-maker").addEventListener("change",models);'
    '$("mr-form").addEventListener("submit",function(e){e.preventDefault();msg("");'
    'var v={client:$("mr-client").value,maker:$("mr-maker").value,title:$("mr-title").value,'
    'year_from:$("mr-year-from").value,year_to:$("mr-year-to").value,km_max:$("mr-km").value,'
    'usd_max:$("mr-usd").value,fuel:$("mr-fuel").value,color:$("mr-color").value,group_link:$("mr-group").value.trim()};'
    'if(!v.client){msg("client");return;}if(!v.maker&&!v.title){msg("maker");return;}'
    'call("add",v).then(function(){msg("saved");$("mr-group").value="";}).catch(function(){});});'
    'if(window.MutationObserver)new MutationObserver(function(){if(st){lists();render();}})'
    '.observe(document.documentElement,{attributes:true,attributeFilter:["lang"]});}'
    'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();'
    '})();</script>')


def _once(page, mark, code):
    if page.count(mark) != 1:
        raise ValueError(code)


def cabinet(page):
    """video/kabinet.html (without the AUTOSEARCH-001 section) with the manager section after «Мої ставки»."""
    for mark in (BIDS, HEAD_END, BODY_END):
        _once(page, mark, 'CABINET_PAGE_UNEXPECTED')
    if 'id="ua-manager-v1"' in page:
        raise ValueError('CABINET_ALREADY_HAS_MANAGER')
    return (page.replace(BIDS, BIDS + SECTION).replace(HEAD_END, STYLE + HEAD_END)
            .replace(BODY_END, SCRIPT + BODY_END))
