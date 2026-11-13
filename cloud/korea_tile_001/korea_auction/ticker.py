"""Home-page ticker HTML (uk/ru/ka via the site's data-* language attributes).

Pure function of the collected JSON: no network, no site access. Self-contained block:
scoped CSS + a small script. A slider (owner 2026-11-10): one card on from the next every 2 seconds, arrows to page
by hand; a touch, hover or arrow pauses the automatic step for a few seconds; reduced motion: no automatic step.
"""
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

LINK = 'korea.html#lots'  # the lot list on the Korea page
LOT_LINK = 'korea.html#lot-%s'  # a lot card opens that lot's card (owner 2026-11-10)

T = {
    'tomorrow': ('Завтра аукціон', 'Завтра аукцион', 'ხვალ აუქციონი'),
    'auction': ('Аукціон', 'Аукцион', 'აუქციონი'),
    'start': ('старт', 'старт', 'საწყისი'),
    'left': ('до торгів', 'до торгов', 'ვაჭრობამდე'),
    # KOREA-TIME-001 (owner 2026-11-12): the auction start in Korea time and Kyiv time; the weekday (owner 2026-11-13)
    'when': ('Торги {d} · {k} Корея · {u} Київ', 'Торги {d} · {k} Корея · {u} Киев',
             'ვაჭრობა {d} · {k} კორეა · {u} კიევი'),
    'hot': ('Нижче звичайної ціни', 'Ниже обычной цены', 'ჩვეულებრივ ფასზე იაფი'),
    'score': ('оцінка', 'оценка', 'შეფასება'),
    'km': ('км', 'км', 'კმ'),
    # the auction lists no lots yet (TICKER-FIX3-001): the tile and the owner's cars only
    'lead_wait': ('Нові лоти аукціону — незабаром', 'Новые лоты аукциона — скоро', 'აუქციონის ახალი ლოტები — მალე'),
    'count_wait': ('Лоти наступних торгів з’являться найближчим часом — доступ після договору',
                   'Лоты следующих торгов появятся в ближайшее время — доступ после договора',
                   'შემდეგი ვაჭრობის ლოტები მალე გამოჩნდება — წვდომა ხელშეკრულების შემდეგ'),
    # KOREA-TILE-001 (owner 2026-11-13): the yellow tile always shows today's car count and the next auction date
    'lead_today': ('Сьогодні на торгах', 'Сегодня на торгах', 'დღეს ვაჭრობაზე'),
    'cars': ('авто', 'авто', 'ავტო'),
    'lead_day': ('Торги {d}', 'Торги {d}', 'ვაჭრობა {d}'),  # «Торги Вт, 17.11» (owner 2026-11-13)
    'access': ('доступ після договору', 'доступ после договора', 'წვდომა ხელშეკრულების შემდეგ'),
    # what the lot score means, on the yellow tile (owner 2026-11-11), per the auction house rules (Auto Hub):
    # first letter = accident grade A-F, second = exterior grade (panels to repair now) A, B, C, D, F (no E)
    'acc': ('1-ша літера оцінки — аварії', '1-я буква оценки — аварии', 'შეფასების 1-ლი ასო — ავარია'),
    'acc_A': ('без аварій, деталі не мінялись', 'без аварий, детали не менялись', 'უავარიო, დეტალები არ შეცვლილა'),
    'acc_B': ('рихтували зовнішні деталі', 'рихтовали наружные детали', 'გარე დეტალები გასწორებულია'),
    'acc_C': ('міняли зовнішні деталі або рихтували каркас', 'меняли наружные детали или рихтовали каркас',
              'გარე დეტალები შეცვლილია ან ჩონჩხი გასწორებულია'),
    'acc_D': ('міняли другорядні деталі каркаса', 'меняли второстепенные детали каркаса',
              'ჩონჩხის მეორეხარისხოვანი დეტალები შეცვლილია'),
    'acc_E': ('міняли основні деталі каркаса', 'меняли основные детали каркаса', 'ჩონჩხის მთავარი დეტალები შეცვლილია'),
    'acc_F': ('утоплений, тотал, розпил', 'утопленник, тотал, распил', 'წყალში ნამყოფი, ტოტალი, ნაწილებისგან აწყობილი'),
    'ext': ('2-га літера — зовнішній вигляд зараз', '2-я буква — внешний вид сейчас', 'მე-2 ასო — გარეგნობა ახლა'),
    'ext_A': ('ремонт не потрібен', 'ремонт не нужен', 'შეკეთება არ სჭირდება'),
    'ext_B': ('1–3 деталі під ремонт', '1–3 детали под ремонт', '1–3 დეტალი შესაკეთებელი'),
    'ext_C': ('4–6 деталей під ремонт', '4–6 деталей под ремонт', '4–6 დეტალი შესაკეთებელი'),
    'ext_D': ('7–9 деталей під ремонт', '7–9 деталей под ремонт', '7–9 დეტალი შესაკეთებელი'),
    'ext_F': ('10 і більше деталей під ремонт', '10 и больше деталей под ремонт', '10 და მეტი დეტალი შესაკეთებელი'),
    'kiev': ('★ У нас · у Києві', '★ У нас · в Киеве', '★ ჩვენთან · კიევში'),
    'georgia': ('★ У нас · в дорозі, у Грузії', '★ У нас · в пути, в Грузии', '★ ჩვენთან · გზაში, საქართველოში'),
    'sea': ('★ У нас · в дорозі, на поромі', '★ У нас · в пути, на пароме', '★ ჩვენთან · გზაში, ბორანზე'),
    'korea': ('★ У нас · викуплено в Кореї', '★ У нас · выкуплено в Корее', '★ ჩვენთან · შეძენილია კორეაში'),
    'turnkey': ('під ключ', 'под ключ', 'გასაღებით'),
    'see': ('Дивитися авто →', 'Смотреть авто →', 'ავტომობილის ნახვა →'),
    'note': ('Ціни — в Кореї. Ваша ціна під ключ — у менеджера',
             'Цены — в Корее. Ваша цена под ключ — у менеджера',
             'ფასები — კორეაში. თქვენი ფასი გასაღებით — მენეჯერთან'),
    'want': ('Хочу так само', 'Хочу так же', 'მეც მინდა'),
    # fuel (owner 2026-11-10: the card shows the fuel type)
    'gasoline': ('бензин', 'бензин', 'ბენზინი'), 'diesel': ('дизель', 'дизель', 'დიზელი'),
    'hybrid': ('гібрид', 'гибрид', 'ჰიბრიდი'), 'electric': ('електро', 'электро', 'ელექტრო'),
    'lpg': ('газ (LPG)', 'газ (LPG)', 'გაზი (LPG)'), 'hydrogen': ('водень', 'водород', 'წყალბადი'),
}


def fuel_key(value):
    """The lot page's fuel text ('Gasoline', 'Gasoline+Electric', 'Diesel', 'LPG' ...) -> a T key, or None."""
    v = (value or '').lower()
    if 'hydrogen' in v:
        return 'hydrogen'
    if 'electric' in v:
        return 'hybrid' if ('gasoline' in v or 'diesel' in v or 'hybrid' in v or 'lpg' in v) else 'electric'
    if 'hybrid' in v:
        return 'hybrid'
    for key in ('diesel', 'lpg', 'gasoline'):
        if key in v:
            return key
    return 'gasoline' if 'petrol' in v else None


def _t(key, **fmt):
    """Span with the site's three-language attributes; Ukrainian is the default text.
    A format value may be a (uk, ru, ka) tuple when it differs by language (a weekday)."""
    uk, ru, ka = (s.format(**{k: v[i] if isinstance(v, tuple) else v for k, v in fmt.items()})
                  for i, s in enumerate(T[key]))
    return '<span data-uk="%s" data-ru="%s" data-ka="%s">%s</span>' % (
        escape(uk), escape(ru), escape(ka), escape(uk))


def _num(n):
    return '{:,}'.format(n).replace(',', ' ')


def _krw(n):
    return '₩%s млн' % ('%.1f' % (n / 1e6)).replace('.', ',')


KST = timezone(timedelta(hours=9))  # the auction lists its start in Korea (= Japan) time


def _zone(*names):
    for name in names:
        try:
            return ZoneInfo(name)
        except Exception:
            continue
    return None


KYIV = _zone('Europe/Kyiv', 'Europe/Kiev')  # older time zone data knows only the old name; summer time included

# short weekday names Monday..Sunday, uk/ru/ka (as Intl/CLDR writes them; the Korea page shows the same «Пт, 13.11»)
WEEKDAYS = (('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд'), ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'),
            ('ორშ', 'სამ', 'ოთხ', 'ხუთ', 'პარ', 'შაბ', 'კვი'))


def _day(at):
    """datetime -> ('Ср, 18.11', 'Ср, 18.11', 'ოთხ, 18.11'): weekday and date per language."""
    return tuple('%s, %s' % (names[at.weekday()], at.strftime('%d.%m')) for names in WEEKDAYS)


def _when(start):
    """'YYYY/MM/DD HH:MM' (Korea) -> «Торги Ср, 18.11 · 12:00 Корея · 05:00 Київ», or '' when it cannot be read."""
    try:
        at = datetime.strptime((start or '')[:16], '%Y/%m/%d %H:%M').replace(tzinfo=KST)
    except ValueError:
        return ''
    if KYIV is None:
        return ''
    kyiv = at.astimezone(KYIV)
    time = kyiv.strftime('%H:%M')
    local = tuple(time if kyiv.date() == at.date() else '%s (%s)' % (time, day) for day in _day(kyiv))
    return '<span class="kt-when">%s</span>' % _t('when', d=_day(at), k=at.strftime('%H:%M'), u=local)


def _item(it, tomorrow):
    hot = '<b class="kt-hot">🔥 %s</b>' % _t('hot') if it['hot'] else ''
    return (
        '<a class="kt-item" href="%s">'
        '<img src="%s" alt="%s" width="240" height="180" decoding="async">'
        '<span class="kt-body"><span class="kt-top"><span class="kt-live">● %s</span>'
        '<span class="kt-clock" data-kt-start="%s">%s <i></i></span></span>%s%s'
        '<strong>%s %d</strong>'
        '<span>%s %s%s · %s %s</span>'
        '<span class="kt-price">%s <b>$%s</b> <small>(%s)</small></span></span></a>'
    ) % (LOT_LINK % escape(it['id']), escape(it['photo']), escape(it['title']), _t('tomorrow' if tomorrow else 'auction'),
         escape(it['auction_start_jst']), _t('left'), _when(it['auction_start_jst']), hot,
         escape(it['title']), it['year'], _num(it['mileage_km']), _t('km'),
         ' · ' + _t(fuel_key(it.get('fuel'))) if fuel_key(it.get('fuel')) else '', _t('score'), escape(it['score']),
         _t('start'), _num(it['start_price_usd']), _krw(it['start_price_krw']))


LEGEND = (('acc', 'ABCDEF'), ('ext', 'ABCDF'))  # score letter groups: T key prefix, letters in order


def _legend():
    """What the lot score letters mean (the yellow tile): one column per letter, a row per value."""
    return '<div class="kt-legend">%s</div>' % ''.join(
        '<div><b>%s</b><dl>%s</dl></div>' % (_t(key), ''.join(
            '<dt>%s</dt><dd>%s</dd>' % (letter, _t('%s_%s' % (key, letter))) for letter in letters))
        for key, letters in LEGEND)


def _own(car):
    """Owner's own car (catalogue): stage, turnkey price, link to its card."""
    stage = car['stage'] if car['stage'] in ('kiev', 'georgia', 'sea', 'korea') else 'sea'
    return (
        '<a class="kt-item kt-own" href="%s">'
        '<img src="%s" alt="%s" width="240" height="180" decoding="async">'
        '<span class="kt-body"><span class="kt-star">%s</span><strong>%s</strong>'
        '<span class="kt-price"><b>$%s</b> %s</span><span class="kt-see">%s</span></span></a>'
    ) % (escape(car['url']), escape(car['photo']), escape(car['title']), _t(stage), escape(car['title']),
         _num(car['price_usd']), _t('turnkey'), _t('see'))


def _mix(lots, own, every=2):
    """Auction lots with an owner's car after every `every` lots (owner cars cycle)."""
    out = []
    for n, lot in enumerate(lots, 1):
        out.append(lot)
        if own and n % every == 0:
            out.append(own[(n // every - 1) % len(own)])
    return out


def _tile(data):
    """KOREA-TILE-001: the yellow tile's lines [(label, value, unit, houses)]: today's car count, always (0 when none),
    then each of the nearest auction days after today (Korea time) with its weekday and listed car count; each line
    with the names of that day's auction houses."""
    out = [(_t('lead_today'), _num(data.get('lots_today') or 0), _t('cars'), data.get('houses_today') or [])]
    for day in data.get('next_days') or []:
        at = datetime.strptime(day['date'], '%Y/%m/%d')
        out.append((_t('lead_day', d=_day(at)), _num(day['lots']), _t('cars'), day.get('houses') or []))
    return out


def _row(label, value, unit, names):
    """One tile line: the day on the left, the car count on the right, the day's auction houses as tags below."""
    houses = ''.join('<span>%s</span>' % escape(n) for n in names)
    return ('<span class="kt-count"><span class="kt-day">%s</span><span class="kt-num"><b>%s</b>%s</span>%s</span>'
            % (label, value, ' ' + unit if unit else '', '<span class="kt-houses">%s</span>' % houses if houses else ''))


def _lines(tile):
    """The tile lines as text, for the closing card: «Сьогодні на торгах 56 авто · Торги Вт, 17.11 3 авто»."""
    return ' · '.join(' '.join(p for p in line[:3] if p) for line in tile)


def render(data, tomorrow=True):
    """Collected JSON (see collect.py) -> HTML block, or '' when there is nothing to show. Without lots (the auction
    lists none yet) the tile with the score legend and the owner's cars (TICKER-FIX3-001)."""
    items = [i for i in data.get('items', []) if i.get('start_price_usd')]
    own = [c for c in data.get('own', []) if c.get('price_usd') and c.get('photo')]
    if not items and not own:
        return ''
    tile = _tile(data)
    counts = ''.join(_row(*line) for line in tile)
    if items:
        track = ('<div class="kt-lead">%s%s</div>' % (counts, _legend())
                 + ''.join(_own(i) if 'stage' in i else _item(i, i.get('tomorrow', tomorrow)) for i in _mix(items, own)))
        count = '%s — %s' % (_lines(tile), _t('access'))
    else:
        track = ('<div class="kt-lead">%s<span class="kt-count">● %s</span>%s</div>'
                 % (counts, _t('lead_wait'), _legend()) + ''.join(_own(c) for c in own))
        count = _t('count_wait')
    tail = ('<span class="kt-end"><span>%s</span><small>%s</small><a class="kt-btn" href="%s">%s</a></span>'
            % (count, _t('note'), LINK, _t('want')))
    return ('<section class="korea-ticker" aria-label="Korea online auction"><style>%s</style>'
            '<button class="kt-arrow kt-prev" type="button" aria-label="‹">‹</button>'
            '<div class="kt-track">%s%s</div>'
            '<button class="kt-arrow kt-next" type="button" aria-label="›">›</button>'
            '<script>%s</script></section>') % (CSS, track, tail, JS)


CSS = (
    '.korea-ticker{position:relative;padding:14px 0;background:#0B1524;color:#fff}'
    '.kt-track{display:flex;gap:16px;overflow-x:auto;scroll-snap-type:x mandatory;scroll-behavior:smooth;'
    'scrollbar-width:none;padding:0 56px}.kt-track::-webkit-scrollbar{display:none}'
    '@media (prefers-reduced-motion:reduce){.kt-track{scroll-behavior:auto}}'
    '.kt-item,.kt-lead,.kt-end{flex:0 0 auto;scroll-snap-align:start;scroll-margin-left:56px}'
    '.kt-arrow{position:absolute;top:50%;z-index:2;transform:translateY(-50%);width:44px;height:44px;'
    'border:0;border-radius:50%;cursor:pointer;font-size:30px;line-height:40px;font-weight:700;color:#0B1524;'
    'background:linear-gradient(135deg,#ffd200,#ff8a00);box-shadow:0 4px 14px rgba(0,0,0,.45)}'
    '.kt-arrow:hover{filter:brightness(1.1)}.kt-prev{left:6px}.kt-next{right:6px}'
    '.kt-item{display:flex;gap:12px;align-items:center;color:inherit;text-decoration:none;'
    'background:#13233a;border-radius:12px;padding:8px 14px 8px 8px}'
    # !important: the site's photo-fit script styles catalogue photos inline; the ticker keeps its own size
    '.korea-ticker .kt-item img{width:240px!important;height:180px!important;max-width:none!important;'
    'min-width:0!important;position:static!important;object-fit:cover!important;border-radius:8px}'
    '.kt-body{display:flex;flex-direction:column;gap:4px;font-size:14px;min-width:190px}'
    '.kt-body strong{font-size:18px}.kt-live{color:#ff5a5a;font-weight:600}'
    '.kt-own{background:#1c1606;border:2px solid #f2b544}'
    '.kt-star{color:#f2b544;font-weight:700}.kt-see{color:#f2b544;font-weight:700}'
    '.kt-hot{color:#ffb020}.kt-price b{font-size:22px;color:#4ade80}'
    '.kt-top{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:4px 12px}'
    '.kt-when{font-size:13px;font-weight:600;color:#ffd200}'
    '.kt-clock{font-size:13px;opacity:.9;white-space:nowrap}.kt-clock i{font-style:normal;font-weight:800;'
    'font-size:16px;color:#ffd200;font-variant-numeric:tabular-nums}'
    '.kt-lead{display:flex;flex-direction:column;justify-content:center;gap:8px;width:640px;padding:10px 18px;'
    'border-radius:12px;color:#0B1524;background:linear-gradient(135deg,#ffd200,#ff8a00)}'
    # tile lines (owner 2026-11-13: day, car count, auction names — neatly): a row per day, thin dividers
    '.kt-count{display:grid;grid-template-columns:1fr auto;align-items:baseline;column-gap:12px;padding:8px 0;'
    'border-top:1px solid rgba(11,21,36,.18);font-size:18px;font-weight:700;line-height:1.2}'
    '.kt-count:first-child{border-top:0;padding-top:0}'
    '.kt-num{white-space:nowrap;font-size:15px}.kt-num b{margin-right:4px;font-size:26px;'
    'font-variant-numeric:tabular-nums}'
    '.kt-houses{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}'
    '.kt-houses span{padding:3px 10px;border-radius:999px;background:rgba(11,21,36,.12);font-size:12.5px;'
    'font-weight:600;white-space:nowrap}'
    '.kt-legend{display:grid;grid-template-columns:1fr 1fr;gap:16px;font-size:12.5px;line-height:1.25}'
    '.kt-legend b{display:block;margin-bottom:4px;font-size:13px}'
    '.kt-legend dl{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;margin:0}'
    '.kt-legend dt{font-weight:800}.kt-legend dd{margin:0}'
    '.kt-end{display:flex;flex-direction:column;justify-content:center;gap:8px;max-width:300px;'
    'padding:0 12px;font-size:15px}'
    '.kt-btn{display:inline-block;background:#4ade80;color:#0B1524;font-weight:700;'
    'padding:10px 16px;border-radius:10px;text-decoration:none;text-align:center}'
    '@media (max-width:600px){.kt-track{padding:0 7vw;gap:10px}.kt-item,.kt-lead,.kt-end{scroll-margin-left:7vw}'
    '.kt-item{flex-direction:column;align-items:stretch;width:86vw;padding:6px}'
    '.korea-ticker .kt-item img{width:100%!important;height:auto!important;aspect-ratio:4/3}'
    '.kt-body{min-width:0}.kt-lead{width:86vw;box-sizing:border-box}'
    '.kt-legend{grid-template-columns:1fr}.kt-arrow{width:38px;height:38px;font-size:26px;line-height:34px}'
    '.kt-prev{left:2px}.kt-next{right:2px}}'
)

# Countdown «до торгів ГГ:ХХ:СС», live every second (owner 2026-11-10; start time is Japan/Korea time, UTC+9),
# and the slider: a step every STEP_MS,
# arrows step by one card, any touch/hover/arrow pauses the automatic step for PAUSE_MS.
STEP_MS, PAUSE_MS = 2000, 6000
JS = (
    "(function(){var clocks=[].map.call(document.querySelectorAll('.korea-ticker [data-kt-start]'),function(e){"
    "return [e,Date.parse(e.getAttribute('data-kt-start').replace(/\\//g,'-').replace(' ','T')+':00+09:00')];});"
    "function two(v){return (v<10?'0':'')+v;}"
    "function tick(){var now=Date.now();clocks.forEach(function(c){var left=Math.floor((c[1]-now)/1000);"
    "if(!(left>0)){c[0].style.display='none';return;}"
    "c[0].querySelector('i').textContent=Math.floor(left/3600)+':'+two(Math.floor(left%3600/60))+':'+two(left%60);});}"
    "tick();setInterval(tick,1000);"
    "document.querySelectorAll('.korea-ticker').forEach(function(box){"
    "var t=box.querySelector('.kt-track'),hold=0;"
    "function card(){var c=t.children[0];return c?c.getBoundingClientRect().width+16:300;}"
    "function go(d){var end=t.scrollLeft+t.clientWidth>=t.scrollWidth-4;"
    "if(d>0&&end){t.scrollTo({left:0});}else if(d<0&&t.scrollLeft<=4){t.scrollTo({left:t.scrollWidth});}"
    "else{t.scrollBy({left:d*card()});}}"
    "function pause(){hold=Date.now()+" + str(PAUSE_MS) + ";}"
    "box.querySelector('.kt-prev').addEventListener('click',function(){pause();go(-1);});"
    "box.querySelector('.kt-next').addEventListener('click',function(){pause();go(1);});"
    "['pointerdown','wheel','touchstart','mouseenter','focusin'].forEach(function(ev){"
    "t.addEventListener(ev,pause,{passive:true});});"
    "if(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)return;"
    "setInterval(function(){if(!document.hidden&&Date.now()>hold)go(1);}," + str(STEP_MS) + ");"
    "});})();"
)
