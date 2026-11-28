"""USA-PAGE-001: the IAAI lot list on video/usa.html, made from the lot list of the live video/japan.html.

The same day buttons, filters, lot cards and lot card #kl-card (the gallery script is already on usa.html); the USA
list /video/usa/lots.json and galleries /video/usa/gallery/<id>.json, the auction start in Kyiv time («Торги Пн, 30.11 ·
16:30 Київ»), «купити зараз $X» (IAAI Buy Now) or «ціна — за запитом», «на ходу» and the damage in the site's words
(as the home ticker's USA cards), no score or auction house. The card's button is «Зв'язатися з менеджером» (lead with
country usa and the lot); «Поділитися» comes from lot-share.js. The block goes right after the calculator section.
Every edit must match the expected number of times, else the build stops (ValueError); a second build changes nothing.
"""
import re

START, END = '<!--UA-USA-LOTS-V1-->', '<!--/UA-USA-LOTS-V1-->'
JAPAN_START, JAPAN_END = '<!--UA-KOREA-LOTS-V1-->', '<!--/UA-KOREA-LOTS-V1-->'
QUICK = '<dialog class="ua-quick-dialog" id="quick-lead-dialog">'
CALC = 'id="usa-result"'  # the calculator's result box: the block goes after the section holding it
SHARE = '<script src="/video/order/lot-share.js?v=share-lots-1" defer></script>'
GALLERY = ("fetch('/video/korea/gallery/' + encodeURIComponent(id)", "fetch('/video/usa/gallery/' + encodeURIComponent(id)")

# Kyiv time of an IAAI start (UTC «YYYY-MM-DDTHH:MMZ») as the Japan list's «YYYY/MM/DD HH:MM», so its days, sorting and
# card text work unchanged; the IAAI words as the Japan list's keys; the condition line.
USA_JS = (
    'var ZN=[["США","Київ"],["США","Киев"],["აშშ","კიევი"]];'
    'function kyiv(s){var at=new Date(s),p=null;if(!/^\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\dZ$/.test(s||"")||isNaN(at))return "";'
    '["Europe/Kyiv","Europe/Kiev"].some(function(z){try{p={};new Intl.DateTimeFormat("en-GB",{timeZone:z,year:"numeric",'
    'month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).formatToParts(at).forEach(function(x){'
    'p[x.type]=x.value;});return true;}catch(e){p=null;return false;}});if(!p||!p.hour)return "";'
    'return p.year+"/"+p.month+"/"+p.day+" "+(p.hour==="24"?"00":p.hour)+":"+p.minute;}'
    'function zones(s,i){return " "+ZN[i][1];}'
    'var NOW=new Date().toISOString().slice(0,16)+"Z",'
    'KO=Date.parse(kyiv(NOW).replace(/\\//g,"-").replace(" ","T")+":00Z")-Date.parse(NOW)||72e5;'
    'function usa(l){var e=/(\\d+(?:\\.\\d+)?)L/.exec(l.engine||""),f=String(l.fuel||"").toLowerCase(),'
    'd=String(l.drive||"").toLowerCase(),g=String(l.transmission||"").toLowerCase(),m=String(l.damage||"").toLowerCase();'
    'l.auction_start=kyiv(l.auction_start);l.engine_cc=e?Math.round(e[1]*1000):0;'
    'l.fuel=/electric/.test(f)?"electric":/hybrid/.test(f)?"hybrid":/diesel/.test(f)?"diesel":/gas|flex/.test(f)?"gasoline":"";'
    'l.drive=/all wheel|4x4|four/.test(d)?"full":/front/.test(d)?"front":/rear/.test(d)?"rear":/4x2/.test(d)?"two":"";'
    'l.transmission=/auto/.test(g)?"AT":/manual/.test(g)?"MT":"";'
    'l.dmg=/dent|scratch/.test(m)?"dmg_minor":/wear/.test(m)?"dmg_wear":/hail/.test(m)?"dmg_hail":"";return l;}'
    'function cond(l){var p=[];if(l.runs)p.push(t("runs"));if(l.dmg)p.push(t(l.dmg));return p.join(" · ");}'
)
EDITS = (
    # the section: title, the price note, no colour filter (the IAAI list has no colour); its own page style
    ('<section class="kr-sec" id="lots"><h2 data-uk="Лоти найближчих торгів" data-ru="Лоты ближайших торгов" '
     'data-ka="უახლოესი ვაჭრობის ლოტები">Лоти найближчих торгів</h2>',
     '<section class="ua-us" id="lots"><h2 data-uk="Зараз на торгах у США" data-ru="Сейчас на торгах в США" '
     'data-ka="ახლა ვაჭრობაზე აშშ-ში">Зараз на торгах у США</h2>', 1),
    ('<p data-uk="Ціни — стартові в Японії. Ваша ціна під ключ — у менеджера." data-ru="Цены — стартовые в Японии. Ваша '
     'цена под ключ — у менеджера." data-ka="ფასები — საწყისი იაპონიაში. თქვენი ფასი გასაღებით — მენეჯერთან.">Ціни — '
     'стартові в Японії. Ваша ціна під ключ — у менеджера.</p>',
     '<p data-uk="Ціни — на аукціоні IAAI. Ваша ціна під ключ — у менеджера." data-ru="Цены — на аукционе IAAI. Ваша '
     'цена под ключ — у менеджера." data-ka="ფასები — IAAI აუქციონზე. თქვენი ფასი გასაღებით — მენეჯერთან.">Ціни — '
     'на аукціоні IAAI. Ваша ціна під ключ — у менеджера.</p>', 1),
    ('<label><span data-uk="Колір" data-ru="Цвет" data-ka="ფერი">Колір</span><select id="kl-color"></select></label>',
     '<select id="kl-color" hidden></select>', 1),
    # the words (as the home ticker's USA cards)
    ('"tbd": ["Ціна — на торгах", "Цена — на торгах", "ფასი — ვაჭრობაზე"]',
     '"tbd": ["ціна — за запитом", "цена — по запросу", "ფასი — მოთხოვნით"], '
     '"buy": ["купити зараз", "купить сейчас", "ახლავე ყიდვა"], "trade": ["Торги", "Торги", "ვაჭრობა"], '
     '"runs": ["на ходу", "на ходу", "მოძრავი"], "state": ["Стан", "Состояние", "მდგომარეობა"], '
     '"dmg_minor": ["дрібні вм’ятини, подряпини", "мелкие вмятины, царапины", "მცირე ჩაღრმავებები, ნაკაწრები"], '
     '"dmg_wear": ["звичайний знос", "обычный износ", "ჩვეულებრივი ცვეთა"], '
     '"dmg_hail": ["сліди граду", "следы града", "სეტყვის კვალი"]', 1),
    # «today» in Kyiv, not in Japan (UTC+9)
    ('324e5', 'KO', 2),
    # the card: «Торги Пн, 30.11 · 16:30 Київ», mileage · condition, the price
    ('function stamp(s){return tri(function(i){return when(s,i)+" · "',
     'function stamp(s){return tri(function(i){return L.trade[i]+" "+when(s,i).replace(" ",", ")+" · "', 1),
    ('(l.score?" · "+t("score")+" "+esc(l.score):"")', '(cond(l)?" · "+cond(l):"")', 1),
    ('function price(l,full){return l.start_usd?\'<span class="kl-usd">$\'+n(l.start_usd)+(full?" <small>(¥"+'
     'n(l.start_jpy)+")</small>":"")+"</span>"',
     'function price(l){return l.start_usd?\'<span class="kl-usd">\'+t("buy")+" $"+n(l.start_usd)+"</span>"', 1),
    # the lot card: the condition in place of score and auction house; the lead's country
    ('row("score",l.score)+row("house",l.house)+', '(cond(l)?rowh("state",cond(l)):"")+', 1),
    ('data-quick-lead-auction="japan"', 'data-quick-lead-auction="usa"', 1),
    # the list
    ('fetch("/video/japan/lots.json",{cache:"no-cache"})', 'fetch("/video/usa/lots.json",{cache:"no-cache"})', 1),
    ('lots=d.lots||[];', 'lots=(d.lots||[]).map(usa);', 1),
)
JAPAN_TIME = re.compile(r'var ZN=\[\["Японія","Київ"\].*?(?=function tri\(f\))', re.S)  # Japan's zones and kyiv()


def _one(text, piece, name):
    if text.count(piece) != 1:
        raise ValueError('USA_PAGE_ANCHOR:%s:%d' % (name, text.count(piece)))
    return text.index(piece)


def section(source):
    """The Japan page's lot list (style, section, script) and its lead dialog -> the USA block."""
    start, end = _one(source, JAPAN_START, 'japan_lots'), _one(source, JAPAN_END, 'japan_lots_end')
    block = source[start + len(JAPAN_START):end]
    if len(JAPAN_TIME.findall(block)) != 1:
        raise ValueError('USA_PAGE_ANCHOR:japan_time')
    block = JAPAN_TIME.sub(lambda m: USA_JS, block)
    for old, new, count in EDITS:
        if block.count(old) != count:
            raise ValueError('USA_PAGE_ANCHOR:%d:%s' % (block.count(old), old[:40]))
        block = block.replace(old, new)
    button = re.findall(r'\.kr-btn\{[^}]*\}', source)  # the card's and «Показати ще» button look (Korea page style)
    quick = _one(source, QUICK, 'quick_dialog')
    close = source.find('</dialog>', quick)
    if len(button) != 1 or close < 0:
        raise ValueError('USA_PAGE_ANCHOR:button_or_dialog')
    style = '<style id="ua-usa-lots-v1">%s</style>' % button[0]
    return START + style + block + source[quick:close + len('</dialog>')] + END


def build(live_usa_html, source_page):
    """video/usa.html bytes + video/japan.html bytes -> video/usa.html with the IAAI lot list."""
    text, source = live_usa_html.decode('utf-8'), source_page.decode('utf-8')
    if START in text:  # built before: take the old block out, then build again
        start, end = _one(text, START, 'usa_lots'), _one(text, END, 'usa_lots_end')
        text = text[:start] + text[end + len(END):]
    for piece in ('id="lots"', 'id="kl-card"', QUICK):
        if piece in text:
            raise ValueError('USA_PAGE_ALREADY_HAS:' + piece)
    calc = _one(text, CALC, 'usa_result')
    after = text.find('</section>', calc)
    if after < 0:
        raise ValueError('USA_PAGE_ANCHOR:calc_section_end')
    after += len('</section>')
    text = text[:after] + section(source) + text[after:]
    old, new = GALLERY
    if text.count(old) + text.count(new) != 1:
        raise ValueError('USA_PAGE_ANCHOR:gallery')
    text = text.replace(old, new)
    if SHARE not in text:
        _one(text, '</body>', 'body_end')
        text = text.replace('</body>', SHARE + '</body>')
    return text.encode('utf-8')
