"""Home-page ticker HTML (uk/ru/ka via the site's data-* language attributes).

Pure function of the collected JSON: no network, no site access. Self-contained block:
scoped CSS + a small script. A slider (owner 2026-11-10): one card on from the next every 2 seconds, arrows to page
by hand; a touch, hover or arrow pauses the automatic step for a few seconds; reduced motion: no automatic step.
"""
from html import escape

LINK = 'korea.html#online'  # Korea page, «Дивитися онлайн» (agreed placement)

T = {
    'tomorrow': ('Завтра аукціон', 'Завтра аукцион', 'ხვალ აუქციონი'),
    'auction': ('Аукціон', 'Аукцион', 'აუქციონი'),
    'start': ('старт', 'старт', 'საწყისი'),
    'left': ('до торгів', 'до торгов', 'ვაჭრობამდე'),
    'hours': ('год', 'ч', 'სთ'),
    'hot': ('Нижче звичайної ціни', 'Ниже обычной цены', 'ჩვეულებრივ ფასზე იაფი'),
    'score': ('оцінка', 'оценка', 'შეფასება'),
    'km': ('км', 'км', 'კმ'),
    'count': ('Завтра на торгах {n} авто — доступ після договору',
              'Завтра на торгах {n} авто — доступ после договора',
              'ხვალ ვაჭრობაზე {n} ავტო — წვდომა ხელშეკრულების შემდეგ'),
    'lead': ('Завтра на торгах', 'Завтра на торгах', 'ხვალ ვაჭრობაზე'),
    'cars': ('авто', 'авто', 'ავტო'),
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
}


def _t(key, **fmt):
    """Span with the site's three-language attributes; Ukrainian is the default text."""
    uk, ru, ka = (s.format(**fmt) for s in T[key])
    return '<span data-uk="%s" data-ru="%s" data-ka="%s">%s</span>' % (
        escape(uk), escape(ru), escape(ka), escape(uk))


def _num(n):
    return '{:,}'.format(n).replace(',', ' ')


def _krw(n):
    return '₩%s млн' % ('%.1f' % (n / 1e6)).replace('.', ',')


def _item(it, tomorrow):
    hot = '<b class="kt-hot">🔥 %s</b>' % _t('hot') if it['hot'] else ''
    return (
        '<a class="kt-item" href="%s">'
        '<img src="%s" alt="%s" width="240" height="180" decoding="async">'
        '<span class="kt-body"><span class="kt-live">● %s</span>%s'
        '<strong>%s %d</strong>'
        '<span>%s %s · %s %s</span>'
        '<span class="kt-price">%s <b>$%s</b> <small>(%s)</small></span>'
        '<span class="kt-left" data-kt-start="%s">%s <i></i> %s</span></span></a>'
    ) % (LINK, escape(it['photo']), escape(it['title']), _t('tomorrow' if tomorrow else 'auction'), hot,
         escape(it['title']), it['year'], _num(it['mileage_km']), _t('km'), _t('score'), escape(it['score']),
         _t('start'), _num(it['start_price_usd']), _krw(it['start_price_krw']),
         escape(it['auction_start_jst']), _t('left'), _t('hours'))


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


def render(data, tomorrow=True):
    """Collected JSON (see collect.py) -> HTML block, or '' when there is nothing to show."""
    items = [i for i in data.get('items', []) if i.get('start_price_usd')]
    if not items:
        return ''
    lead = ('<span class="kt-lead">● %s <b>%s</b> %s</span>'
            % (_t('lead'), _num(data['lots_on_date']), _t('cars')))
    own = [c for c in data.get('own', []) if c.get('price_usd') and c.get('photo')]
    track = lead + ''.join(_own(i) if 'stage' in i else _item(i, tomorrow) for i in _mix(items, own))
    tail = ('<span class="kt-end"><span>%s</span><small>%s</small><a class="kt-btn" href="%s">%s</a></span>'
            % (_t('count', n=_num(data['lots_on_date'])), _t('note'), LINK, _t('want')))
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
    '.kt-hot{color:#ffb020}.kt-price b{font-size:22px;color:#4ade80}.kt-left{opacity:.8}'
    '.kt-lead{display:flex;align-items:center;gap:8px;padding:0 22px;border-radius:12px;'
    'font-size:20px;font-weight:700;color:#0B1524;white-space:nowrap;'
    'background:linear-gradient(135deg,#ffd200,#ff8a00)}'
    '.kt-lead b{font-size:34px}'
    '.kt-end{display:flex;flex-direction:column;justify-content:center;gap:8px;max-width:300px;'
    'padding:0 12px;font-size:15px}'
    '.kt-btn{display:inline-block;background:#4ade80;color:#0B1524;font-weight:700;'
    'padding:10px 16px;border-radius:10px;text-decoration:none;text-align:center}'
    '@media (max-width:600px){.kt-track{padding:0 40px;gap:12px}.kt-item,.kt-lead,.kt-end{scroll-margin-left:40px}'
    '.kt-item{flex-direction:column;align-items:stretch;width:74vw;padding:8px}'
    '.korea-ticker .kt-item img{width:100%!important;height:auto!important;aspect-ratio:4/3}'
    '.kt-body{min-width:0}.kt-lead{width:60vw;flex-wrap:wrap;justify-content:center;white-space:normal;'
    'text-align:center}.kt-arrow{width:38px;height:38px;font-size:26px;line-height:34px}'
    '.kt-prev{left:2px}.kt-next{right:2px}}'
)

# Countdown «до торгів N год» (start time is Japan/Korea time, UTC+9) and the slider: a step every STEP_MS,
# arrows step by one card, any touch/hover/arrow pauses the automatic step for PAUSE_MS.
STEP_MS, PAUSE_MS = 2000, 6000
JS = (
    "(function(){var n=Date.now();document.querySelectorAll('.korea-ticker [data-kt-start]')"
    ".forEach(function(e){var s=e.getAttribute('data-kt-start').replace(/\\//g,'-').replace(' ','T')+':00+09:00';"
    "var h=Math.round((Date.parse(s)-n)/36e5);var i=e.querySelector('i');"
    "if(h>0&&i){i.textContent=h;}else{e.style.display='none';}});"
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
