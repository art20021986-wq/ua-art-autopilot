"""The home page top block «Пошук авто на аукціонах світу» (SEARCH-HOME-001 B, owner «Да» 2026-11-27).

Only this: the inside of the auctions section (<section class="ua-kr-auc">, written by ua_korea_home) becomes a search
— a country choice (all countries, Korea, America, Japan, Europe, China, Canada, UAE, Georgia, as the country row
below) and make, model, year from, price to, then «Знайти авто». The section and its class stay, so the home blocks
frame (ua_home_blocks) and the ticker under it stay as they are. The search opens the country's own page: Korea —
and Japan (installed by JAPAN-LHD-001) — the lot list with the criteria in the link
(korea.html / japan.html?maker=&model=&year=&usd=#lots), America — the USA page,
the others — the order form for that country. Countries are radio buttons (native, keyboard and screen-reader ready);
a small script only builds the link. Texts carry the site's data-uk/ru/ka twins.
"""
from html import escape

MARK = 'UA-SEARCH-HOME-V1'
OPEN = '<section class="ua-kr-auc">'
CLOSE = '</section>'
FLAGS = '/video/order/flags/%s.svg'
# country key, (uk, ru, ka), status key, where the search goes
COUNTRIES = (
    ('all', ('Усі країни', 'Все страны', 'ყველა ქვეყანა'), '', 'korea.html'),
    ('korea', ('Корея', 'Корея', 'კორეა'), 'online', 'korea.html'),
    ('usa', ('Америка', 'Америка', 'ამერიკა'), 'online', 'usa.html'),
    ('japan', ('Японія', 'Япония', 'იაპონია'), 'online', 'japan.html'),
    ('europe', ('Європа', 'Европа', 'ევროპა'), 'order', 'podbor.html'),
    ('china', ('Китай', 'Китай', 'ჩინეთი'), 'order', 'podbor.html'),
    ('canada', ('Канада', 'Канада', 'კანადა'), 'order', 'podbor.html'),
    ('uae', ('ОАЕ', 'ОАЭ', 'ემირატები'), 'order', 'podbor.html'),
    ('georgia', ('Грузія', 'Грузия', 'საქართველო'), 'order', 'podbor.html'),
)
STATUS = {'online': ('● онлайн', '● онлайн', '● ონლაინ'), 'soon': ('незабаром', 'скоро', 'მალე'),
          'order': ('під замовлення', 'под заказ', 'შეკვეთით')}
MAKES = ('Hyundai', 'Kia', 'Genesis', 'Toyota', 'Lexus', 'Honda', 'Nissan', 'Mazda', 'Subaru', 'Mitsubishi', 'BMW',
         'Mercedes-Benz', 'Audi', 'Volkswagen', 'Porsche', 'Volvo', 'Land Rover', 'Ford', 'Chevrolet', 'Jeep', 'Tesla',
         'Renault', 'KG Mobility')
YEARS = tuple(range(2026, 2009, -1))
T = {
    'ey': ('● Аукціони онлайн · Корея · Японія · Америка', '● Аукционы онлайн · Корея · Япония · Америка',
           '● აუქციონები ონლაინ · კორეა · იაპონია · ამერიკა'),
    'h2': ('Пошук авто на аукціонах світу', 'Поиск авто на аукционах мира', 'ავტომობილის ძიება მსოფლიოს აუქციონებზე'),
    'sub': ('Оберіть країну або шукайте одразу всюди — тисячі лотів на торгах щодня.',
            'Выберите страну или ищите сразу везде — тысячи лотов на торгах каждый день.',
            'აირჩიეთ ქვეყანა ან მოძებნეთ ყველგან — ათასობით ლოტი ყოველდღე.'),
    'country': ('Країна', 'Страна', 'ქვეყანა'),
    'make': ('Марка', 'Марка', 'მარკა'), 'any_make': ('Усі марки', 'Все марки', 'ყველა მარკა'),
    'model': ('Модель', 'Модель', 'მოდელი'), 'any_model': ('Усі моделі', 'Все модели', 'ყველა მოდელი'),
    'year': ('Рік від', 'Год от', 'წელი დან'), 'any_year': ('Будь-який', 'Любой', 'ნებისმიერი'),
    'usd': ('Ціна до, $', 'Цена до, $', 'ფასი მდე, $'),
    'go': ('🔍 Знайти авто', '🔍 Найти авто', '🔍 ავტომობილის ძიება'),
}
# What the «where is it» line says (the script reads them by <html lang>).
FOUND = {'uk': {'h': 'Є на торгах:', 'cars': 'авто', 'none': 'немає', 'order': 'під замовлення',
                'korea': 'Корея', 'japan': 'Японія', 'usa': 'Америка'},
         'ru': {'h': 'Есть на торгах:', 'cars': 'авто', 'none': 'нет', 'order': 'под заказ',
                'korea': 'Корея', 'japan': 'Япония', 'usa': 'Америка'},
         'ka': {'h': 'ვაჭრობაზეა:', 'cars': 'ავტო', 'none': 'არ არის', 'order': 'შეკვეთით',
                'korea': 'კორეა', 'japan': 'იაპონია', 'usa': 'ამერიკა'}}
# The lot lists the countries' pages already publish (read only when a visitor starts choosing).
LOTS = (('korea', '/video/korea/lots.json', 'korea.html', '🇰🇷'), ('japan', '/video/japan/lots.json', 'japan.html', '🇯🇵'))


def _attrs(texts, prefix='data'):
    return ' '.join('%s-%s="%s"' % (prefix, lang, escape(t, quote=True)) for lang, t in zip(('uk', 'ru', 'ka'), texts))


def _t(tag, texts, extra=''):
    return '<%s %s%s>%s</%s>' % (tag, _attrs(texts), extra, escape(texts[0]), tag)


def _country(n, key, names, status, href):
    icon = ('<span class="sh-all" aria-hidden="true">🌍</span>' if key == 'all'
            else '<img src="%s" width="36" height="24" alt="">' % (FLAGS % key))
    note = _t('small', STATUS[status], ' class="sh-%s"' % status) if status else '<small>&nbsp;</small>'
    return ('<label class="sh-c"><input type="radio" name="sh-country" value="%s" data-href="%s"%s>'
            '<span>%s%s%s</span></label>' % (key, href, ' checked' if n == 0 else '', icon, _t('b', names), note))


def block():
    makes = ''.join('<option value="%s">%s</option>' % (escape(m), escape(m)) for m in MAKES)
    years = ''.join('<option value="%d">%d</option>' % (y, y) for y in YEARS)
    countries = ''.join(_country(n, *c) for n, c in enumerate(COUNTRIES))
    return (
        '<!--%s--><style>%s</style>' % (MARK, CSS)
        + _t('div', T['ey'], ' class="ey"') + _t('h2', T['h2']) + _t('p', T['sub'], ' class="sh-sub"')
        + '<form class="sh-form" action="korea.html" method="get" role="search">'
        + '<fieldset class="sh-cty"><legend class="sh-sr" %s>%s</legend>%s</fieldset>'
          % (_attrs(T['country']), T['country'][0], countries)
        + '<div class="sh-box">'
        + '<label>%s<select name="maker"><option value="" %s>%s</option>%s</select></label>'
          % (_t('span', T['make']), _attrs(T['any_make']), T['any_make'][0], makes)
        + '<label>%s<select name="model"><option value="" %s>%s</option></select></label>'
          % (_t('span', T['model']), _attrs(T['any_model']), T['any_model'][0])
        + '<label>%s<select name="year"><option value="" %s>%s</option>%s</select></label>'
          % (_t('span', T['year']), _attrs(T['any_year']), T['any_year'][0], years)
        + '<label>%s<input name="usd" type="number" inputmode="numeric" min="1000" step="500" placeholder="20000"></label>'
          % _t('span', T['usd'])
        + '<button type="submit" class="sh-go" %s>%s</button></div></form>' % (_attrs(T['go']), T['go'][0])
        + '<div class="sh-found" aria-live="polite" hidden></div>'
        + '<script>%s</script><!--/%s-->' % (JS, MARK))


def apply(html):
    """Home page HTML -> the same with the search inside the auctions section (idempotent)."""
    if not isinstance(html, str) or '<!--%s-->' % MARK in html or html.count(OPEN) != 1:
        return html
    start, end = _inside(html)
    return html[:start] + block() + html[end:]


def _inside(html):
    start = html.index(OPEN) + len(OPEN)
    return start, html.index(CLOSE, start)


def remove(html, before):
    """The page with the search taken out: the auctions section gets back the inside it has in `before` (rollback of
    a page another writer rewrote since the install)."""
    if not isinstance(html, str) or '<!--%s-->' % MARK not in html or html.count(OPEN) != 1 or before.count(OPEN) != 1:
        return html
    start, end = _inside(html)
    old_start, old_end = _inside(before)
    return html[:start] + before[old_start:old_end] + html[end:]


CSS = (
    '.ua-kr-auc{padding:22px 16px 20px}'
    '.ua-kr-auc .ey{color:#ffb020;font-weight:800;letter-spacing:.14em;font-size:12px;text-transform:uppercase}'
    '.ua-kr-auc h2{color:#fff;font-size:clamp(24px,4vw,40px);line-height:1.15;margin:8px 0 6px}'
    '.ua-kr-auc .sh-sub{color:#c9d3e0;margin:0 0 14px;font-size:15px}'
    '.sh-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}'
    '.sh-cty{display:flex;gap:8px;overflow-x:auto;padding:2px 0 10px;margin:0;border:0;scrollbar-width:none}'
    '.sh-cty::-webkit-scrollbar{display:none}'
    '.sh-c{flex:0 0 auto;cursor:pointer}.sh-c input{position:absolute;opacity:0;pointer-events:none}'
    '.sh-c>span{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:78px;padding:8px 8px 6px;'
    'border-radius:12px;border:1px solid #3a4a62;background:#0f1b2d;color:#e6ecf5;font-size:13px;line-height:1.1}'
    '.sh-c b{font-weight:600}.sh-c img{width:36px;height:24px;border-radius:3px;object-fit:cover}'
    '.sh-all{font-size:20px;line-height:24px}.sh-c small{font-size:10px;font-weight:600;color:#8a9ab0}'
    '.sh-c small.sh-online{color:#3ddc84;font-weight:700}'
    '.sh-c input:checked+span{border-color:#ffb020;background:#2a1f05;color:#ffd000;box-shadow:0 0 0 1px #ffb020 inset}'
    '.sh-c input:focus-visible+span{outline:2px solid #ffd000;outline-offset:2px}'
    '.sh-box{background:#fff;border-radius:16px;padding:14px;display:grid;grid-template-columns:1fr 1fr;gap:10px;'
    'box-shadow:0 10px 30px rgba(0,0,0,.35)}'
    '.sh-box label{display:flex;flex-direction:column;gap:4px;font-size:12px;font-weight:700;color:#5a6678}'
    '.sh-box select,.sh-box input{height:44px;border:1px solid #d5dbe4;border-radius:10px;padding:0 10px;font-size:15px;'
    'color:#111;background:#f7f9fc;min-width:0;width:100%;box-sizing:border-box}'
    '.sh-found{margin:12px 2px 0;color:#e6ecf5;font-size:15px;line-height:1.6}.sh-found b{color:#ffd000}'
    '.sh-found a{display:inline-block;margin:2px 10px 2px 0;color:#fff;text-decoration:none;padding:4px 10px;'
    'border-radius:999px;background:#13233a;border:1px solid #3a4a62}.sh-found a.sh-0{opacity:.55}'
    '.sh-go{grid-column:1/-1;height:52px;border:0;border-radius:12px;font-weight:800;font-size:17px;color:#111;'
    'background:linear-gradient(90deg,#ffd000,#ff8a00);cursor:pointer}'
    '@media(min-width:900px){.ua-kr-auc{padding:34px 40px 28px}.sh-cty{flex-wrap:wrap}.sh-c>span{min-width:100px}'
    '.sh-box{grid-template-columns:repeat(4,1fr) 1.2fr;align-items:end}.sh-go{grid-column:auto;height:44px}}'
)
import json as _json
# The link of the chosen country on submit; on the first touch of the form the published lot lists are read once:
# the model list follows the make, and the line under the form says in which countries the choice is and how many.
JS = ("(function(){var f=document.querySelector('.ua-kr-auc .sh-form');if(!f)return;"
      "var W=" + _json.dumps(FOUND, ensure_ascii=False) + ",L=" + _json.dumps(LOTS, ensure_ascii=False) + ","
      "out=document.querySelector('.ua-kr-auc .sh-found'),data=null,loading=null;"
      "function w(){return W[document.documentElement.lang]||W.uk;}"
      "function key(s){return String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');}"
      "function model(l){var t=String(l.title||''),m=String(l.maker||'');return t.toLowerCase().indexOf(m.toLowerCase())===0?t.slice(m.length).trim():t;}"
      "function load(){if(!loading)loading=Promise.all(L.map(function(c){return fetch(c[1],{cache:'no-cache'})"
      ".then(function(r){return r.ok?r.json():{lots:[]};}).then(function(d){return (d&&d.lots)||[];})"
      ".catch(function(){return [];});})).then(function(all){data=all;models();show();});return loading;}"
      "function crit(){return {mk:key(f.elements.maker.value),md:f.elements.model.value,y:+f.elements.year.value||0,"
      "usd:+f.elements.usd.value||0};}"
      "function hit(l,c){return (!c.mk||key(l.maker).indexOf(c.mk)===0)&&(!c.md||model(l)===c.md)&&(!c.y||+l.year>=c.y)"
      "&&(!c.usd||+l.start_usd<=c.usd);}"
      "function models(){if(!data)return;var s=f.elements.model,keep=s.value,mk=key(f.elements.maker.value),seen={};"
      "data.forEach(function(lots){lots.forEach(function(l){if(mk&&key(l.maker).indexOf(mk)===0){var m=model(l);if(m)seen[m]=1;}});});"
      "while(s.options.length>1)s.remove(1);Object.keys(seen).sort().forEach(function(m){s.add(new Option(m,m));});"
      "s.value=seen[keep]?keep:'';}"
      "function q(){var p=[];['maker','model','year','usd'].forEach(function(n){var v=(f.elements[n].value||'').trim();"
      "if(v)p.push(n+'='+encodeURIComponent(v));});return p.length?'?'+p.join('&'):'';}"
      "function show(){var c=crit();if(!data||!(c.mk||c.md||c.y||c.usd)){out.hidden=true;return;}var t=w(),h='<b>'+t.h+'</b> ';"
      "L.forEach(function(x,i){var n=data[i].filter(function(l){return hit(l,c);}).length;"
      "h+='<a class=\"sh-'+(n?'n':'0')+'\" href=\"'+x[2]+q()+'#lots\">'+x[3]+' '+t[x[0]]+' — '+(n?n+' '+t.cars:t.none)+'</a>';});"
      "h+='<a href=\"usa.html\">🇺🇸 '+t.usa+' — '+t.order+'</a>';out.innerHTML=h;out.hidden=false;}"
      "f.addEventListener('focusin',load,{once:true});f.addEventListener('pointerdown',load,{once:true});"
      "f.addEventListener('change',function(e){if(e.target.name==='maker')models();if(data)show();else load();});"
      "f.elements.usd.addEventListener('input',function(){if(data)show();});"
      "new MutationObserver(function(){if(data)show();}).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});"
      "f.addEventListener('submit',function(e){e.preventDefault();var c=f.querySelector('[name=sh-country]:checked'),"
      "key2=c?c.value:'all',href=c?c.getAttribute('data-href'):'korea.html',lang=document.documentElement.lang||'uk';"
      "if(href==='korea.html'||href==='japan.html'){location.href=href+q()+'#lots';}"
      "else if(href==='podbor.html'){location.href='podbor.html?strana='+key2+'&lang='+lang;}"
      "else{location.href=href;}});})();")
