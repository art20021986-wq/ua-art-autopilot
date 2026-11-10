"""Home-page ticker HTML (uk/ru/ka via the site's data-* language attributes).

Pure function of the collected JSON: no network, no site access. Self-contained block:
scoped CSS (pure CSS marquee, pauses on hover, respects reduced motion) + tiny countdown script.
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
        '<img src="%s" alt="%s" width="240" height="180" loading="lazy" decoding="async">'
        '<span class="kt-body"><span class="kt-live">● %s</span>%s'
        '<strong>%s %d</strong>'
        '<span>%s %s · %s %s</span>'
        '<span class="kt-price">%s <b>$%s</b> <small>(%s)</small></span>'
        '<span class="kt-left" data-kt-start="%s">%s <i></i> %s</span></span></a>'
    ) % (LINK, escape(it['photo']), escape(it['title']), _t('tomorrow' if tomorrow else 'auction'), hot,
         escape(it['title']), it['year'], _num(it['mileage_km']), _t('km'), _t('score'), escape(it['score']),
         _t('start'), _num(it['start_price_usd']), _krw(it['start_price_krw']),
         escape(it['auction_start_jst']), _t('left'), _t('hours'))


def render(data, tomorrow=True):
    """Collected JSON (see collect.py) -> HTML block, or '' when there is nothing to show."""
    items = [i for i in data.get('items', []) if i.get('start_price_usd')]
    if not items:
        return ''
    lead = ('<span class="kt-lead">● %s <b>%s</b> %s</span>'
            % (_t('lead'), _num(data['lots_on_date']), _t('cars')))
    track = lead + ''.join(_item(i, tomorrow) for i in items)
    tail = ('<span class="kt-end"><span>%s</span><small>%s</small><a class="kt-btn" href="%s">%s</a></span>'
            % (_t('count', n=_num(data['lots_on_date'])), _t('note'), LINK, _t('want')))
    return ('<section class="korea-ticker" aria-label="Korea online auction">'
            '<style>%s</style><div class="kt-track">%s%s%s%s</div>'
            '<script>%s</script></section>') % (CSS, track, tail, track, tail, JS)


CSS = (
    '.korea-ticker{overflow:hidden;padding:14px 0;background:#0B1524;color:#fff}'
    '.kt-track{display:flex;gap:16px;width:max-content;animation:kt-run 90s linear infinite}'
    '.korea-ticker:hover .kt-track{animation-play-state:paused}'
    '@keyframes kt-run{to{transform:translateX(-50%)}}'
    '@media (prefers-reduced-motion:reduce){.kt-track{animation:none;overflow-x:auto}}'
    '.kt-item{display:flex;gap:12px;align-items:center;color:inherit;text-decoration:none;'
    'background:#13233a;border-radius:12px;padding:8px 14px 8px 8px}'
    '.kt-item img{width:240px;height:180px;object-fit:cover;border-radius:8px}'
    '.kt-body{display:flex;flex-direction:column;gap:4px;font-size:14px;min-width:190px}'
    '.kt-body strong{font-size:18px}.kt-live{color:#ff5a5a;font-weight:600}'
    '.kt-hot{color:#ffb020}.kt-price b{font-size:22px;color:#4ade80}.kt-left{opacity:.8}'
    '.kt-lead{display:flex;align-items:center;gap:8px;padding:0 22px;border-radius:12px;'
    'font-size:20px;font-weight:700;color:#0B1524;white-space:nowrap;'
    'background:linear-gradient(135deg,#ffd200,#ff8a00)}'
    '.kt-lead b{font-size:34px}'
    '.kt-end{display:flex;flex-direction:column;justify-content:center;gap:8px;max-width:300px;'
    'padding:0 12px;font-size:15px}'
    '.kt-btn{display:inline-block;background:#4ade80;color:#0B1524;font-weight:700;'
    'padding:10px 16px;border-radius:10px;text-decoration:none;text-align:center}'
    '@media (max-width:600px){.kt-item img{width:180px;height:135px}}'
)

# Countdown «до торгів N год»: start time is Japan/Korea time (UTC+9).
JS = (
    "(function(){var n=Date.now();document.querySelectorAll('.korea-ticker [data-kt-start]')"
    ".forEach(function(e){var s=e.getAttribute('data-kt-start').replace(/\\//g,'-').replace(' ','T')+':00+09:00';"
    "var h=Math.round((Date.parse(s)-n)/36e5);var i=e.querySelector('i');"
    "if(h>0&&i){i.textContent=h;}else{e.style.display='none';}});})();"
)
