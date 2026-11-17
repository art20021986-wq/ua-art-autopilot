"""Кабинет менеджера сайта в «Мій кабінет» (AUTOSEARCH-003, владелец 17.11, макет 33-AUTOSEARCH-MANAGERS.png, «Да»).
Используется только при сборке пакета; на сервер ставится готовая страница.

cabinet(page): под «Мої ставки» — раздел, который видит только менеджер сайта (GET /api/auction/alerts отвечает 200):
«👥 Мої клієнти» с «➕ Додати клієнта» (ПІБ и телефон — клиентов видят только менеджер и владелец); «🔍 Запит на пошук
для клієнта» (клиент, марка, модель, рік від/до, пробіг до, ціна до $, паливо, колір, «Посилання на групу WhatsApp»,
«💾 Зберегти запит»); «Запити моїх клієнтів» с «🗑»; «📬 Повідомлення для груп клієнтів» (приветствие, новые лоты,
«📲 Відправити в групу WhatsApp», «✅ Відправлено», «👥 Відкрити групу»). Клиент аукциона раздела не видит.
Свой стиль и свой скрипт (ua-manager-v2); остальная страница не меняется; каждое место — ровно один раз.
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
    '<section id="mr" hidden><h2>🧑‍💼 ' + _t('Кабінет менеджера', 'Кабинет менеджера', 'მენეჯერის კაბინეტი') + '</h2>'
    '<div class="cab-card cab-in"><p class="mr-sub">' + _t('Менеджер', 'Менеджер', 'მენეჯერი')
    + ': <b id="mr-me"></b></p><b>👥 ' + _t('Мої клієнти', 'Мои клиенты', 'ჩემი კლიენტები') + '</b>'
    '<div id="mr-people"></div><form id="mr-add" class="mr-grid">'
    + _field('ПІБ клієнта', 'ФИО клиента', 'კლიენტის სახელი', '<input id="mr-pname" maxlength="80" required>')
    + _field('Телефон', 'Телефон', 'ტელეფონი', '<input id="mr-pphone" type="tel" inputmode="tel" placeholder="+380…" required>')
    + '<button type="submit" id="mr-padd">➕ ' + _t('Додати клієнта', 'Добавить клиента', 'კლიენტის დამატება')
    + '</button><p id="mr-pmsg" class="mr-msg" role="status"></p></form></div>'
    '<div class="cab-card cab-in"><b>🔍 ' + _t('Запит на пошук для клієнта', 'Запрос на поиск для клиента',
                                             'ძიების მოთხოვნა კლიენტისთვის') + '</b><form id="mr-form" class="mr-grid">'
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
    + '</b><div id="mr-list"></div></div>'
    '<div class="cab-card cab-in"><b>📬 ' + _t('Повідомлення для груп клієнтів', 'Сообщения для групп клиентов',
                                              'შეტყობინებები კლიენტების ჯგუფებისთვის')
    + '</b> <span id="mr-new" class="mr-new" hidden></span><div id="mr-msgs"></div><p class="mr-hint">'
    + _t('Нові лоти з’являються тут самі після кожного оновлення аукціону. «Відправити» відкриває WhatsApp з готовим '
         'текстом — оберіть групу клієнта.',
         'Новые лоты появляются здесь сами после каждого обновления аукциона. «Отправить» открывает WhatsApp с готовым '
         'текстом — выберите группу клиента.',
         'ახალი ლოტები აქ თავად ჩნდება აუქციონის ყოველი განახლების შემდეგ. «გაგზავნა» ხსნის WhatsApp-ს მზა ტექსტით — '
         'აირჩიეთ კლიენტის ჯგუფი.') + '</p></div></section>')

STYLE = ('<style id="ua-manager-v2">.mr-sub{margin:0 0 10px;opacity:.85}.mr-grid{display:grid;grid-template-columns:1fr 1fr;'
         'gap:8px 10px}.mr-grid label{display:grid;gap:4px;font-size:13px}.mr-grid .mr-wide{grid-column:1/-1}'
         '.mr-grid select,.mr-grid input{padding:9px 10px;border-radius:10px;border:1px solid #2a3b55;background:#0B1524;'
         'color:#fff;font:inherit;min-width:0}#mr-save{grid-column:1/-1;justify-self:start;padding:10px 18px;'
         'border-radius:10px;border:0;background:#f2b544;color:#0B1524;font-weight:800;cursor:pointer}'
         '.mr-msg{grid-column:1/-1;margin:0;min-height:1em;color:#fcd34d}.mr-row{display:flex;justify-content:space-between;'
         'align-items:center;gap:10px;padding:9px 0;border-top:1px solid #2a3b55}.mr-row small{display:block;opacity:.7}'
         '.mr-del{padding:7px 12px;border-radius:10px;border:1px solid #2a3b55;background:transparent;color:#fff;'
         'cursor:pointer}.mr-new{font-size:12px;font-weight:800;padding:2px 9px;border-radius:99px;background:#3b2f0b;'
         'color:#fcd34d}.mr-m{border-top:1px solid #2a3b55;padding:10px 0}.mr-h{font-size:13px;font-weight:700;'
         'margin-bottom:4px}.mr-t{white-space:pre-wrap;background:#0B1524;border:1px solid #2a3b55;border-radius:10px;'
         'padding:8px 10px;font-size:14px}.mr-b{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}.mr-wa{padding:8px 12px;'
         'border-radius:10px;background:#1f7a4d;color:#fff!important;font-weight:700;text-decoration:none}.mr-gr{'
         'padding:8px 12px;border-radius:10px;border:1px solid #2a3b55;color:#fff!important;text-decoration:none}'
         '.mr-ok{color:#86efac;font-weight:700;font-size:13px;margin-top:6px}.mr-hint{opacity:.7;font-size:13px;'
         'margin:8px 0 0}#mr-add{margin:8px 0 4px}#mr-padd{grid-column:1/-1;justify-self:start;padding:9px 16px;'
         'border-radius:10px;border:0;background:#f2b544;color:#0B1524;font-weight:800;cursor:pointer}'
         '#mr-people .mr-row{font-size:14px}@media(max-width:520px){.mr-grid{grid-template-columns:1fr}}</style>')

# [uk, ru, ka] for the texts the script writes
TEXT = {
    'any': ['Будь-який', 'Любой', 'ნებისმიერი'],
    'pick': ['Оберіть клієнта', 'Выберите клиента', 'აირჩიეთ კლიენტი'],
    'none': ['Поки немає.', 'Пока нет.', 'ჯერ არ არის.'],
    'sent': ['надіслано в групу {n}', 'отправлено в группу {n}', 'ჯგუფში გაგზავნილია {n}'],
    'more': ['ще {n} підходящих — на сайті', 'ещё {n} подходящих — на сайте', 'კიდევ {n} შესაფერისი — საიტზე'],
    'new': ['{n} нових', '{n} новых', '{n} ახალი'],
    'welcome': ['привітання', 'приветствие', 'მისალმება'],
    'lot': ['новий лот', 'новый лот', 'ახალი ლოტი'],
    'send': ['📲 Відправити в групу WhatsApp', '📲 Отправить в группу WhatsApp', '📲 გაგზავნა WhatsApp ჯგუფში'],
    'open': ['👥 Відкрити групу', '👥 Открыть группу', '👥 ჯგუფის გახსნა'],
    'done': ['✅ Відправлено', '✅ Отправлено', '✅ გაგზავნილია'],
    'from': ['від', 'от', 'დან'], 'to': ['до', 'до', 'მდე'],
    'maker': ['Оберіть марку або модель.', 'Выберите марку или модель.', 'აირჩიეთ მარკა ან მოდელი.'],
    'client': ['Оберіть клієнта.', 'Выберите клиента.', 'აირჩიეთ კლიენტი.'],
    'name': ['Напишіть ПІБ клієнта.', 'Напишите ФИО клиента.', 'დაწერეთ კლიენტის სახელი.'],
    'phone': ['Телефон не схожий на номер. Приклад: +380991112233', 'Телефон не похож на номер. Пример: +380991112233',
              'ტელეფონი არასწორია. მაგალითი: +380991112233'],
    'phone_exists': ['Такий клієнт у вас уже є.', 'Такой клиент у вас уже есть.', 'ასეთი კლიენტი უკვე გყავთ.'],
    'added': ['Клієнта додано.', 'Клиент добавлен.', 'კლიენტი დამატებულია.'],
    'no_clients': ['Спочатку додайте клієнта.', 'Сначала добавьте клиента.', 'ჯერ დაამატეთ კლიენტი.'],
    'group_link': ['Вставте посилання-запрошення групи WhatsApp (https://chat.whatsapp.com/…).',
                   'Вставьте ссылку-приглашение группы WhatsApp (https://chat.whatsapp.com/…).',
                   'ჩასვით WhatsApp ჯგუფის მოწვევის ბმული (https://chat.whatsapp.com/…).'],
    'limit': ['У клієнта вже 10 запитів.', 'У клиента уже 10 запросов.', 'კლიენტს უკვე 10 მოთხოვნა აქვს.'],
    'saved': ['Запит збережено. Привітання для групи — нижче, у «Повідомлення для груп клієнтів».',
              'Запрос сохранён. Приветствие для группы — ниже, в «Сообщения для групп клиентов».',
              'მოთხოვნა შენახულია. ჯგუფის მისალმება — ქვემოთ, «შეტყობინებები კლიენტების ჯგუფებისთვის».'],
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
    '<script id="ua-manager-v2-js">(function(){"use strict";var T=' + json.dumps(TEXT, ensure_ascii=False)
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
    'opt($("mr-client"),st.clients.map(function(c){return [String(c.id),c.name+" · "+c.phone];}),"pick");'
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
    'function render(){if(!st)return;$("mr").hidden=false;$("mr-me").textContent=st.manager;var pb=$("mr-people");'
    'pb.textContent="";if(!st.clients.length)pb.appendChild(el("div","mr-row",t("none")));st.clients.forEach(function(c){'
    'pb.appendChild(el("div","mr-row",c.name+" · "+c.phone));});var box=$("mr-list");'
    'box.textContent="";if(!st.requests.length)box.appendChild(el("div","mr-row",t("none")));'
    'st.requests.forEach(function(r){var del=el("button","mr-del","🗑");del.type="button";'
    'del.addEventListener("click",function(){call("delete",{id:r.id});});'
    'box.appendChild(el("div","mr-row",null,[el("div",null,num(r.id)+" · "+r.client_name+" · "+desc(r.criteria),'
    '[el("small",null,t("sent",{n:r.sent})+(r.more?" · "+t("more",{n:r.more}):""))]),del]));});'
    'var mb=$("mr-msgs");mb.textContent="";$("mr-new").hidden=!st.messages.length;'
    '$("mr-new").textContent=t("new",{n:st.messages.length});if(!st.messages.length)mb.appendChild(el("div","mr-m",t("none")));'
    # a message: the WhatsApp share link opens in a new tab (the official wa.me «share»); the tap marks it as sent
    'st.messages.forEach(function(m){var wa=el("a","mr-wa",t("send")),gr=el("a","mr-gr",t("open")),box;'
    'wa.href=m.share;wa.target="_blank";wa.rel="noopener";gr.href=m.group_link;gr.target="_blank";gr.rel="noopener";'
    'box=el("div","mr-m",null,[el("div","mr-h",num(m.id)+" · "+m.client_name+" · "+t(m.kind)),el("div","mr-t",m.text),'
    'el("div","mr-b",null,[wa,gr])]);wa.addEventListener("click",function(){box.appendChild(el("div","mr-ok",t("done")));'
    'call("sent",m.lot?{id:m.id,lot:m.lot}:{id:m.id},true).catch(function(){});});mb.appendChild(box);});}'
    'function msg(k){$("mr-msg").textContent=k?t(k):"";}'
    'function call(a,b,quiet){return fetch(API+"/"+a,{method:"POST",credentials:"same-origin",'
    'headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})}).then(function(r){'
    'return r.json().then(function(d){if(!r.ok)throw d;if(!quiet){st=d;render();}return d;});})'
    '.catch(function(e){var k=e&&e.error;msg(T[k]?k:"error");throw e;});}'
    'function init(){if(!$("mr"))return;fetch(API,{credentials:"same-origin",cache:"no-store"}).then(function(r){'
    'return r.ok?r.json():null;}).then(function(d){if(d){st=d;lists();render();}}).catch(function(){});'
    '$("mr-maker").addEventListener("change",models);'
    '$("mr-add").addEventListener("submit",function(e){e.preventDefault();$("mr-pmsg").textContent="";'
    'fetch(API+"/contact",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},'
    'body:JSON.stringify({name:$("mr-pname").value,phone:$("mr-pphone").value})}).then(function(r){return r.json()'
    '.then(function(d){if(!r.ok)throw d;st=d;lists();render();$("mr-pname").value="";$("mr-pphone").value="";'
    '$("mr-pmsg").textContent=t("added");});}).catch(function(e){var k=e&&e.error;'
    '$("mr-pmsg").textContent=t(T[k]?k:"error");});});'
    '$("mr-form").addEventListener("submit",function(e){e.preventDefault();msg("");'
    'var v={contact:$("mr-client").value,maker:$("mr-maker").value,title:$("mr-title").value,'
    'year_from:$("mr-year-from").value,year_to:$("mr-year-to").value,km_max:$("mr-km").value,'
    'usd_max:$("mr-usd").value,fuel:$("mr-fuel").value,color:$("mr-color").value,group_link:$("mr-group").value.trim()};'
    'if(!st.clients.length){msg("no_clients");return;}if(!v.contact){msg("client");return;}if(!v.maker&&!v.title){msg("maker");return;}'
    'call("add",v).then(function(){msg("saved");$("mr-group").value="";}).catch(function(){});});'
    'if(window.MutationObserver)new MutationObserver(function(){if(st){lists();render();}})'
    '.observe(document.documentElement,{attributes:true,attributeFilter:["lang"]});}'
    'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();'
    '})();</script>')


def _once(page, mark, code):
    if page.count(mark) != 1:
        raise ValueError(code)


def cabinet(page):
    """«Мій кабінет» (without any earlier manager section) with the site manager's section after «Мої ставки»."""
    for mark in (BIDS, HEAD_END, BODY_END):
        _once(page, mark, 'CABINET_PAGE_UNEXPECTED')
    if 'id="ua-manager-v' in page:
        raise ValueError('CABINET_ALREADY_HAS_MANAGER')
    return (page.replace(BIDS, BIDS + SECTION).replace(HEAD_END, STYLE + HEAD_END)
            .replace(BODY_END, SCRIPT + BODY_END))
