"""JPAUTO-KOREA-001 (owner 2026-11-10): every lot of the coming Korea auction days, open to every visitor.

apply(html) on video/korea.html:
  1. after the «Два способи купити авто» block — the lot list (#lots): search by make, model, year, mileage and
     price, cards, and a lot card with photos, data and «Зв'язатися з менеджером» (the site's manager dialog,
     with the chosen lot). Data: /video/korea/lots.json, written by the server job (korea_auction.public).
     A link korea.html#lot-<id> (the home ticker) opens that lot's card.
     Owner 2026-11-11: the auction days on top (weekday, date, number of cars; «Усі дні» first), the auction day
     and time on every card, «За датою торгів» in the sorting, and the VIN in the lot card.
     Owner 2026-11-11: the lot card opens on screen where the visitor is (fixed, centred), from its top.
     Owner 2026-11-12: each opened lot has its own link (#lot-<id> in the address), the weekday goes with its date
     (Пт 13.11, in uk/ru/ka without the browser's locale data) and the card shows the VIN, not the lot number.
  2. the «Дивитися онлайн» buttons lead to the list instead of opening the dialog and read «Дивитися аукціони»
     (owner 2026-11-10).
remove(html) takes both back. A page with an older version of the list gets the new one in its place.
Lots whose start price is not known yet show «Ціна — на торгах» (never «$0»); an empty score is not shown. Texts carry the site's data-uk / data-ru / data-ka attributes (ua-site-languages.js
translates them, also in the cards the script adds).
"""
import json
import re

MARK = '<!--UA-KOREA-LOTS-V1-->'
END = '<!--/UA-KOREA-LOTS-V1-->'
AFTER = '<section class="kr-sec"><div class="kr-card kr-two">'
WATCH_FROM = '<a class="kr-btn" href="#online" data-quick-lead-auction="korea" data-quick-lead-title="— аукціони Кореї онлайн">'
WATCH_TO = '<a class="kr-btn" href="#lots" data-ua-kr-lots="1">'
DATA = '/video/korea/lots.json'
LABEL_FROM = '<span data-uk="Дивитися онлайн" data-ru="Смотреть онлайн" data-ka="ონლაინ ნახვა">Дивитися онлайн</span>'
LABEL_TO = ('<span data-uk="Дивитися аукціони" data-ru="Смотреть аукционы" data-ka="აუქციონების ნახვა">'
            'Дивитися аукціони</span>')


def _t(uk, ru, ka, tag='span', attrs=''):
    return '<%s%s data-uk="%s" data-ru="%s" data-ka="%s">%s</%s>' % (tag, attrs, uk, ru, ka, uk, tag)


# Labels the script puts into cards: [uk, ru, ka].
LABELS = {
    'year': ['Рік', 'Год', 'წელი'], 'km': ['км', 'км', 'კმ'], 'mileage': ['Пробіг', 'Пробег', 'გარბენი'],
    'engine': ['Двигун', 'Двигатель', 'ძრავი'], 'gear': ['КПП', 'КПП', 'გადაცემათა კოლოფი'],
    'trim': ['Комплектація', 'Комплектация', 'კომპლექტაცია'], 'score': ['Оцінка', 'Оценка', 'შეფასება'],
    'house': ['Аукціон', 'Аукцион', 'აუქციონი'],
    'start': ['Початок торгів (час Кореї)', 'Начало торгов (время Кореи)', 'ვაჭრობის დაწყება (კორეის დრო)'],
    'price': ['Стартова ціна', 'Стартовая цена', 'საწყისი ფასი'],
    'contact': ['Зв\'язатися з менеджером', 'Связаться с менеджером', 'მენეჯერთან დაკავშირება'],
    'all': ['Усі', 'Все', 'ყველა'],
    'tbd': ['Ціна — на торгах', 'Цена — на торгах', 'ფასი — ვაჭრობაზე'],
    'vin': ['VIN', 'VIN', 'VIN'],
    'days': ['Усі дні', 'Все дни', 'ყველა დღე'],
    'cars': ['авто', 'авто', 'ავტო'],
}
# Weekday names by the page language (uk, ru, ka), Sunday first; dates are written as 13.11 — the page does not
# depend on the browser's locale data (owner 2026-11-12: the weekday with its date; Georgian was shown in English).
WEEKDAYS = [['Нд', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'], ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'],
            ['კვი', 'ორშ', 'სამ', 'ოთხ', 'ხუთ', 'პარ', 'შაბ']]
WEEKDAYS_LONG = [['неділя', 'понеділок', 'вівторок', 'середа', 'четвер', 'пʼятниця', 'субота'],
                 ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'],
                 ['კვირა', 'ორშაბათი', 'სამშაბათი', 'ოთხშაბათი', 'ხუთშაბათი', 'პარასკევი', 'შაბათი']]

STYLE = (
    '<style id="ua-korea-lots-v1">'
    '.kl-filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px}'
    '.kl-filters label{display:grid;gap:4px;font-size:13px;opacity:.9}'
    '.kl-filters select,.kl-filters input{width:100%;min-width:0;box-sizing:border-box;padding:10px;border-radius:10px;'
    'border:1px solid #2a3b55;background:#0B1524;color:#fff;font-size:15px}'
    '.kl-count{margin:6px 0 14px;opacity:.9}.kl-count b{color:#f2b544}'
    '.kl-days{display:flex;gap:8px;overflow-x:auto;padding:2px 0 12px;scrollbar-width:thin}'
    '.kl-day{flex:0 0 auto;display:grid;gap:2px;min-width:92px;padding:8px 12px;border-radius:12px;cursor:pointer;'
    'text-align:center;background:#13233a;border:1px solid #2a3b55;color:#fff;font:inherit}'
    '.kl-day b{font-size:15px}.kl-day b::first-letter,.kl-when::first-letter{text-transform:uppercase}.kl-day small{opacity:.8;font-size:12px}'
    '.kl-day[aria-pressed="true"]{background:#f2b544;border-color:#f2b544;color:#0B1524}'
    '.kl-when{color:#f2b544;font-size:13px!important;opacity:1!important}'
    '.kl-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}'
    '@media(max-width:600px){.kl-filters{grid-template-columns:1fr 1fr}.kl-grid{grid-template-columns:1fr 1fr;gap:10px}'
    '.kl-item b{font-size:15px}}'
    '.kl-item{display:grid;gap:6px;text-align:left;padding:0 0 12px;border-radius:14px;overflow:hidden;cursor:pointer;'
    'background:#13233a;border:1px solid #23344f;color:#fff;font:inherit}'
    '.kl-item img{width:100%;aspect-ratio:4/3;object-fit:cover;display:block;background:#0B1524}'
    '.kl-item>b,.kl-item>span{padding:0 12px}.kl-item>b{font-size:17px}.kl-item>span{opacity:.85;font-size:14px}'
    '.kl-usd{color:#4ade80;font-weight:800;font-size:18px}.kl-tbd{color:#f2b544;font-weight:700}'
    '.kl-more{margin:16px auto 0;display:block;border:0;cursor:pointer}.kl-more[hidden]{display:none}'
    '.kl-dialog{position:fixed;width:min(760px,96vw);max-height:92vh;padding:0;border:0;border-radius:18px;'
    'background:#0B1524;color:#fff}.kl-dialog::backdrop{background:rgba(0,0,0,.7)}'
    '.kl-photos{display:flex;gap:6px;overflow-x:auto;scroll-snap-type:x mandatory}'
    '.kl-photos img{flex:0 0 100%;width:100%;aspect-ratio:4/3;object-fit:cover;scroll-snap-align:start}'
    '.kl-body{padding:16px 18px 20px;display:grid;gap:10px}.kl-body h3{margin:0;font-size:22px}'
    '.kl-specs{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0}.kl-specs dt{opacity:.75}'
    '.kl-specs dd{margin:0;font-weight:600}'
    '.kl-close{position:absolute;z-index:1;top:8px;right:8px;border:0;border-radius:50%;width:38px;height:38px;'
    'font-size:22px;cursor:pointer;background:rgba(11,21,36,.85);color:#fff}'
    '</style>')

SECTION = (
    '<section class="kr-sec" id="lots">'
    + _t('Лоти найближчих торгів', 'Лоты ближайших торгов', 'უახლოესი ვაჭრობის ლოტები', 'h2')
    + _t('Ціни — стартові в Кореї. Ваша ціна під ключ — у менеджера.',
         'Цены — стартовые в Корее. Ваша цена под ключ — у менеджера.',
         'ფასები — საწყისი კორეაში. თქვენი ფასი გასაღებით — მენეჯერთან.', 'p')
    + '<div class="kl-days" id="kl-days" role="group"></div>'
    '<div class="kl-filters">'
    '<label>' + _t('Марка', 'Марка', 'მარკა') + '<select id="kl-maker"></select></label>'
    '<label>' + _t('Модель', 'Модель', 'მოდელი') + '<select id="kl-model"></select></label>'
    '<label>' + _t('Рік від', 'Год от', 'წელი დან') + '<input id="kl-year" type="number" inputmode="numeric"></label>'
    '<label>' + _t('Пробіг до, км', 'Пробег до, км', 'გარბენი მდე, კმ')
    + '<input id="kl-km" type="number" inputmode="numeric"></label>'
    '<label>' + _t('Ціна до, $', 'Цена до, $', 'ფასი მდე, $') + '<input id="kl-usd" type="number" inputmode="numeric">'
    '</label>'
    '<label>' + _t('Сортування', 'Сортировка', 'დალაგება') + '<select id="kl-sort">'
    + _t('Спочатку дешевші', 'Сначала дешевле', 'ჯერ იაფი', 'option', ' value="usd"')
    + _t('За датою торгів', 'По дате торгов', 'ვაჭრობის თარიღით', 'option', ' value="date"')
    + _t('Спочатку новіші', 'Сначала новее', 'ჯერ ახალი', 'option', ' value="year"')
    + _t('Менший пробіг', 'Меньший пробег', 'ნაკლები გარბენი', 'option', ' value="km"')
    + '</select></label></div>'
    '<p class="kl-count">' + _t('Знайдено авто:', 'Найдено авто:', 'ნაპოვნია ავტომობილი:') + ' <b id="kl-n">0</b></p>'
    '<div class="kl-grid" id="kl-grid"></div>'
    '<button class="kr-btn kl-more" id="kl-more" type="button" hidden>'
    + _t('Показати ще', 'Показать ещё', 'მეტის ჩვენება') + '</button>'
    '<dialog class="kl-dialog" id="kl-card"><button class="kl-close" type="button" data-kl-close aria-label="×">×</button>'
    '<div id="kl-card-body"></div></dialog>'
    '</section>')

SCRIPT = (
    '<script>(function(){"use strict";'
    'var L=' + json.dumps(LABELS, ensure_ascii=False) + ',WD=' + json.dumps(WEEKDAYS, ensure_ascii=False) + ',WDL=' + json.dumps(WEEKDAYS_LONG, ensure_ascii=False)
    + ',PAGE=24,lots=[],shown=0,'
    'list=[],day="";'
    'function when(s,i,long){var p=/^(\\d{4})\\/(\\d\\d)\\/(\\d\\d)/.exec(s||"");if(!p)return "";'
    'var w=new Date(Date.UTC(+p[1],+p[2]-1,+p[3],12)).getUTCDay();return (long?WDL:WD)[i][w]+(long?", ":" ")+p[3]+"."+p[2];}'
    'function tri(f){var v=[0,1,2].map(f);return \'<span data-uk="\'+esc(v[0])+\'" data-ru="\'+esc(v[1])'
    '+\'" data-ka="\'+esc(v[2])+\'">\'+esc(v[0])+"</span>";}'
    'function stamp(s){return tri(function(i){return when(s,i)'
    '+" · "+String(s).slice(11,16);});}'
    'function days(){var c={};lots.forEach(function(l){var d=l.auction_start.slice(0,10);c[d]=(c[d]||0)+1;});'
    'var ks=Object.keys(c).sort();if(ks.indexOf(day)<0)day="";'
    '$("kl-days").innerHTML=\'<button class="kl-day" type="button" data-kl-day="" aria-pressed="\'+(day==="")+\'">\''
    '+"<b>"+t("days")+"</b><small>"+n(lots.length)+" "+t("cars")+"</small></button>"'
    '+ks.map(function(d){return \'<button class="kl-day" type="button" data-kl-day="\'+d+\'" aria-pressed="\''
    '+(day===d)+\'"><b>\'+tri(function(i){return when(d,i);})+"</b>"'
    '+"<small>"+n(c[d])+" "+t("cars")+"</small></button>";}).join("");}'
    'function $(i){return document.getElementById(i);}'
    'function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'
    '"\\"":"&quot;"}[c];});}'
    'function t(k){var v=L[k];return \'<span data-uk="\'+esc(v[0])+\'" data-ru="\'+esc(v[1])+\'" data-ka="\'+esc(v[2])'
    '+\'">\'+esc(v[0])+"</span>";}'
    'function n(x){return Number(x||0).toLocaleString("uk-UA");}'
    'function opt(sel,values){var keep=sel.value;sel.innerHTML="<option value=\\"\\">"+L.all[0]+"</option>"'
    '+values.map(function(v){return "<option>"+esc(v)+"</option>";}).join("");sel.value=values.indexOf(keep)<0?"":keep;'
    'sel.options[0].setAttribute("data-uk",L.all[0]);sel.options[0].setAttribute("data-ru",L.all[1]);'
    'sel.options[0].setAttribute("data-ka",L.all[2]);}'
    'function uniq(a){return a.filter(function(v,i){return v&&a.indexOf(v)===i;}).sort();}'
    'function models(){var m=$("kl-maker").value;opt($("kl-model"),uniq(lots.filter(function(l){'
    'return !m||l.maker===m;}).map(function(l){return l.title;})));}'
    'function today(){return lots.filter(function(l){return !day||l.auction_start.slice(0,10)===day;});}'
    'function card(l){return \'<button class="kl-item" type="button" data-kl-lot="\'+esc(l.id)+\'">\''
    '+(l.photos[0]?\'<img loading="lazy" decoding="async" alt="" src="\'+esc(l.photos[0])+\'">\':"")'
    '+\'<span class="kl-when">\'+stamp(l.auction_start)+"</span>"'
    '+"<b>"+esc(l.title)+" "+l.year+"</b><span>"+n(l.mileage_km)+" "+t("km")'
    '+(l.score?" · "+t("score")+" "+esc(l.score):"")+"</span>"+price(l,false)+"</button>";}'
    'function price(l,full){return l.start_usd?\'<span class="kl-usd">$\'+n(l.start_usd)'
    '+(full?" <small>(₩"+n(l.start_krw)+")</small>":"")+"</span>":\'<span class="kl-tbd">\'+t("tbd")+"</span>";}'
    'function filter(){var m=$("kl-maker").value,md=$("kl-model").value,y=+$("kl-year").value||0,'
    'km=+$("kl-km").value||0,usd=+$("kl-usd").value||0,s=$("kl-sort").value;'
    'list=today().filter(function(l){return (!m||l.maker===m)&&(!md||l.title===md)&&l.year>=y&&(!km||l.mileage_km<=km)'
    '&&(!usd||(l.start_usd&&l.start_usd<=usd));});'
    'list.sort(function(a,b){return s==="year"?b.year-a.year:s==="km"?a.mileage_km-b.mileage_km:'
    's==="date"?(a.auction_start<b.auction_start?-1:a.auction_start>b.auction_start?1:0):'
    '(a.start_usd||1e12)-(b.start_usd||1e12);});'
    '$("kl-n").textContent=n(list.length);$("kl-grid").innerHTML="";shown=0;more();}'
    'function more(){$("kl-grid").insertAdjacentHTML("beforeend",list.slice(shown,shown+PAGE).map(card).join(""));'
    'shown+=PAGE;$("kl-more").hidden=shown>=list.length;}'
    'function row(k,v){return v?rowh(k,esc(v)):"";}function rowh(k,h){return "<dt>"+t(k)+"</dt><dd>"+h+"</dd>";}'
    'function open(id){var l=lots.filter(function(x){return x.id===id;})[0];if(!l)return;'
    '$("kl-card-body").innerHTML=\'<div class="kl-photos">\'+l.photos.map(function(p){return \'<img alt="" loading="lazy" decoding="async" src="\''
    '+esc(p)+\'">\';}).join("")+\'</div><div class="kl-body"><h3>\'+esc(l.title)+" "+l.year+"</h3>"'
    '+price(l,true)'
    '+\'<dl class="kl-specs">\'+row("mileage",n(l.mileage_km)+" км")+row("engine",l.engine_cc?n(l.engine_cc)+" см³":"")'
    '+row("vin",l.vin)+row("gear",l.transmission)+row("trim",l.trim)+row("score",l.score)+row("house",l.house)'
    '+rowh("start",tri(function(i){return when(l.auction_start,i,true)+", "+String(l.auction_start).slice(11,16);}))+"</dl>"'
    '+\'<a class="kr-btn" href="#lots" data-quick-lead-auction="korea" data-quick-lead-lot="\'+esc(l.id)'
    '+\'" data-quick-lead-lot-title="\'+esc(l.title+" "+l.year)+\'" data-quick-lead-title="— \'+esc(l.title+" "+l.year)'
    '+\'">\'+t("contact")+"</a></div>";$("kl-card").showModal();$("kl-card").scrollTop=0;'
    'if(location.hash!=="#lot-"+id)history.replaceState(null,"","#lot-"+id);}'
    'document.addEventListener("click",function(e){var c=e.target.closest&&e.target.closest("[data-kl-lot]");'
    'if(c){open(c.getAttribute("data-kl-lot"));return;}'
    'var dd=e.target.closest&&e.target.closest("[data-kl-day]");'
    'if(dd){day=dd.getAttribute("data-kl-day");days();filter();return;}'
    'if(e.target.closest&&(e.target.closest("[data-kl-close]")||e.target.closest("[data-quick-lead-lot]")))'
    '$("kl-card").close();});'
    '["kl-year","kl-km","kl-usd","kl-sort","kl-model"].forEach(function(i){$(i).addEventListener("change",filter);});'
    '$("kl-maker").addEventListener("change",function(){models();filter();});'
    '$("kl-more").addEventListener("click",more);'
    'fetch("' + DATA + '",{cache:"no-cache"}).then(function(r){return r.ok?r.json():{lots:[]};})'
    '.then(function(d){lots=d.lots||[];days();opt($("kl-maker"),uniq(lots.map(function(l){return l.maker;})));models();'
    'filter();hash();}).catch(function(){});'
    'function hash(){var m=/^#lot-(\\d+)$/.exec(location.hash);if(m&&lots.length){'
    '$("lots").scrollIntoView();open(m[1]);}}'
    'window.addEventListener("hashchange",hash);'
    '$("kl-card").addEventListener("close",function(){if(/^#lot-/.test(location.hash))'
    'history.replaceState(null,"",location.pathname+location.search+"#lots");});'
    '})();</script>')

BLOCK = MARK + STYLE + SECTION + SCRIPT + END


# Other releases put their own marked blocks inside the list section (the client login UA-KOREA-LOGIN-V1 and the
# bid UA-KOREA-BID-V1, right after its opening tag). Replacing this list keeps them as they are, in their order.
LIST_OPEN = '<section class="kr-sec" id="lots">'
NESTED = re.compile(r'<!--(UA-[A-Z0-9-]+-V\d+)-->.*?<!--/\1-->', re.S)


def nested(block):
    """The other releases' marked blocks inside an installed list block, in page order."""
    return ''.join(m.group(0) for m in NESTED.finditer(block[len(MARK):]))


def with_nested(block, kept):
    """This list block with the kept blocks back right after the list section's opening tag."""
    at = block.index(LIST_OPEN) + len(LIST_OPEN)
    return block[:at] + kept + block[at:]


def apply(html):
    """Korea page with the lot list and the «Дивитися онлайн» buttons leading to it; any other page unchanged."""
    if not isinstance(html, str):
        return html
    if MARK in html:  # an installed list (this or an older version): the block is replaced in place
        start = html.index(MARK)
        end = html.index(END, start) + len(END)
        return html[:start] + with_nested(BLOCK, nested(html[start:end])) + html[end:]
    if html.count(AFTER) != 1:
        return html
    start = html.index(AFTER)
    end = html.index('</section>', start) + len('</section>')
    return (html[:end] + BLOCK + html[end:]).replace(WATCH_FROM, WATCH_TO).replace(LABEL_FROM, LABEL_TO)


def remove(html):
    """The page without this release's additions."""
    if MARK not in html:
        return html
    start = html.index(MARK)
    end = html.index(END, start) + len(END)
    return (html[:start] + html[end:]).replace(WATCH_TO, WATCH_FROM).replace(LABEL_TO, LABEL_FROM)
