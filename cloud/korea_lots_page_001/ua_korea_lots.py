"""JPAUTO-KOREA-001 (owner 2026-11-10): every lot of the next Korea auction day, open to every visitor.

apply(html) on video/korea.html:
  1. after the «Два способи купити авто» block — the lot list (#lots): search by make, model, year, mileage and
     price, cards, and a lot card with photos, data and «Зв'язатися з менеджером» (the site's manager dialog,
     with the chosen lot). Data: /video/korea/lots.json, written by the server job (korea_auction.public).
     A link korea.html#lot-<id> (the home ticker) opens that lot's card.
  2. the «Дивитися онлайн» buttons lead to the list instead of opening the dialog and read «Дивитися аукціони»
     (owner 2026-11-10).
remove(html) takes both back. Texts carry the site's data-uk / data-ru / data-ka attributes (ua-site-languages.js
translates them, also in the cards the script adds).
"""
import json

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
    'house': ['Аукціон', 'Аукцион', 'აუქციონი'], 'lot': ['Лот №', 'Лот №', 'ლოტი №'],
    'start': ['Початок торгів (час Кореї)', 'Начало торгов (время Кореи)', 'ვაჭრობის დაწყება (კორეის დრო)'],
    'price': ['Стартова ціна', 'Стартовая цена', 'საწყისი ფასი'],
    'contact': ['Зв\'язатися з менеджером', 'Связаться с менеджером', 'მენეჯერთან დაკავშირება'],
    'all': ['Усі', 'Все', 'ყველა'],
}

STYLE = (
    '<style id="ua-korea-lots-v1">'
    '.kl-filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px}'
    '.kl-filters label{display:grid;gap:4px;font-size:13px;opacity:.9}'
    '.kl-filters select,.kl-filters input{width:100%;min-width:0;box-sizing:border-box;padding:10px;border-radius:10px;'
    'border:1px solid #2a3b55;background:#0B1524;color:#fff;font-size:15px}'
    '.kl-count{margin:6px 0 14px;opacity:.9}.kl-count b{color:#f2b544}'
    '.kl-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}'
    '@media(max-width:600px){.kl-filters{grid-template-columns:1fr 1fr}.kl-grid{grid-template-columns:1fr 1fr;gap:10px}'
    '.kl-item b{font-size:15px}}'
    '.kl-item{display:grid;gap:6px;text-align:left;padding:0 0 12px;border-radius:14px;overflow:hidden;cursor:pointer;'
    'background:#13233a;border:1px solid #23344f;color:#fff;font:inherit}'
    '.kl-item img{width:100%;aspect-ratio:4/3;object-fit:cover;display:block;background:#0B1524}'
    '.kl-item>b,.kl-item>span{padding:0 12px}.kl-item>b{font-size:17px}.kl-item>span{opacity:.85;font-size:14px}'
    '.kl-usd{color:#4ade80;font-weight:800;font-size:18px}'
    '.kl-more{margin:16px auto 0;display:block;border:0;cursor:pointer}'
    '.kl-dialog{position:relative;width:min(760px,96vw);max-height:92vh;padding:0;border:0;border-radius:18px;'
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
    + '<div class="kl-filters">'
    '<label>' + _t('Марка', 'Марка', 'მარკა') + '<select id="kl-maker"></select></label>'
    '<label>' + _t('Модель', 'Модель', 'მოდელი') + '<select id="kl-model"></select></label>'
    '<label>' + _t('Рік від', 'Год от', 'წელი დან') + '<input id="kl-year" type="number" inputmode="numeric"></label>'
    '<label>' + _t('Пробіг до, км', 'Пробег до, км', 'გარბენი მდე, კმ')
    + '<input id="kl-km" type="number" inputmode="numeric"></label>'
    '<label>' + _t('Ціна до, $', 'Цена до, $', 'ფასი მდე, $') + '<input id="kl-usd" type="number" inputmode="numeric">'
    '</label>'
    '<label>' + _t('Сортування', 'Сортировка', 'დალაგება') + '<select id="kl-sort">'
    + _t('Спочатку дешевші', 'Сначала дешевле', 'ჯერ იაფი', 'option', ' value="usd"')
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
    'var L=' + json.dumps(LABELS, ensure_ascii=False) + ',PAGE=24,lots=[],shown=0,list=[];'
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
    'function card(l){return \'<button class="kl-item" type="button" data-kl-lot="\'+esc(l.id)+\'">\''
    '+(l.photos[0]?\'<img loading="lazy" decoding="async" alt="" src="\'+esc(l.photos[0])+\'">\':"")'
    '+"<b>"+esc(l.title)+" "+l.year+"</b><span>"+n(l.mileage_km)+" "+t("km")+" · "+t("score")+" "+esc(l.score)'
    '+\'</span><span class="kl-usd">$\'+n(l.start_usd)+"</span></button>";}'
    'function filter(){var m=$("kl-maker").value,md=$("kl-model").value,y=+$("kl-year").value||0,'
    'km=+$("kl-km").value||0,usd=+$("kl-usd").value||0,s=$("kl-sort").value;'
    'list=lots.filter(function(l){return (!m||l.maker===m)&&(!md||l.title===md)&&l.year>=y&&(!km||l.mileage_km<=km)'
    '&&(!usd||(l.start_usd&&l.start_usd<=usd));});'
    'list.sort(function(a,b){return s==="year"?b.year-a.year:s==="km"?a.mileage_km-b.mileage_km:'
    '(a.start_usd||1e12)-(b.start_usd||1e12);});'
    '$("kl-n").textContent=n(list.length);$("kl-grid").innerHTML="";shown=0;more();}'
    'function more(){$("kl-grid").insertAdjacentHTML("beforeend",list.slice(shown,shown+PAGE).map(card).join(""));'
    'shown+=PAGE;$("kl-more").hidden=shown>=list.length;}'
    'function row(k,v){return v?"<dt>"+t(k)+"</dt><dd>"+esc(v)+"</dd>":"";}'
    'function open(id){var l=lots.filter(function(x){return x.id===id;})[0];if(!l)return;'
    '$("kl-card-body").innerHTML=\'<div class="kl-photos">\'+l.photos.map(function(p){return \'<img alt="" src="\''
    '+esc(p)+\'">\';}).join("")+\'</div><div class="kl-body"><h3>\'+esc(l.title)+" "+l.year+"</h3>"'
    '+\'<span class="kl-usd">$\'+n(l.start_usd)+" <small>(₩"+n(l.start_krw)+")</small></span>"'
    '+\'<dl class="kl-specs">\'+row("mileage",n(l.mileage_km)+" км")+row("engine",l.engine_cc?n(l.engine_cc)+" см³":"")'
    '+row("gear",l.transmission)+row("trim",l.trim)+row("score",l.score)+row("house",l.house)+row("lot",l.lot_no)'
    '+row("start",l.auction_start)+"</dl>"'
    '+\'<a class="kr-btn" href="#lots" data-quick-lead-auction="korea" data-quick-lead-lot="\'+esc(l.id)'
    '+\'" data-quick-lead-lot-title="\'+esc(l.title+" "+l.year)+\'" data-quick-lead-title="— \'+esc(l.title+" "+l.year)'
    '+\'">\'+t("contact")+"</a></div>";$("kl-card").showModal();}'
    'document.addEventListener("click",function(e){var c=e.target.closest&&e.target.closest("[data-kl-lot]");'
    'if(c){open(c.getAttribute("data-kl-lot"));return;}'
    'if(e.target.closest&&(e.target.closest("[data-kl-close]")||e.target.closest("[data-quick-lead-lot]")))'
    '$("kl-card").close();});'
    '["kl-year","kl-km","kl-usd","kl-sort","kl-model"].forEach(function(i){$(i).addEventListener("change",filter);});'
    '$("kl-maker").addEventListener("change",function(){models();filter();});'
    '$("kl-more").addEventListener("click",more);'
    'fetch("' + DATA + '",{cache:"no-cache"}).then(function(r){return r.ok?r.json():{lots:[]};})'
    '.then(function(d){lots=d.lots||[];opt($("kl-maker"),uniq(lots.map(function(l){return l.maker;})));models();'
    'filter();hash();}).catch(function(){});'
    'function hash(){var m=/^#lot-(\\d+)$/.exec(location.hash);if(m&&lots.length){'
    '$("lots").scrollIntoView();open(m[1]);}}'
    'window.addEventListener("hashchange",hash);'
    '})();</script>')

BLOCK = MARK + STYLE + SECTION + SCRIPT + END


def apply(html):
    """Korea page with the lot list and the «Дивитися онлайн» buttons leading to it; any other page unchanged."""
    if not isinstance(html, str) or html.count(AFTER) != 1 or MARK in html:
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
