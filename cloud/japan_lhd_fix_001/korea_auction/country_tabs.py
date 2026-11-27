"""Country switch on the home ticker's week tile (SEARCH-HOME-001, owner «Да» 2026-11-26 12:19 UTC).

Only this: wraps the Korea week (built by ticker.py, unchanged) in a tab panel and adds two more — America (Copart,
IAAI: auctions Monday to Friday, US Eastern dates) and Japan (coming soon). WAI-ARIA tabs pattern
(https://www.w3.org/WAI/ARIA/apg/patterns/tabs/); scoped CSS and a small script. The tile clocks are the ticker's own
(data-kt-tz is updated by the ticker script). Pure function of its inputs: no network, no site access.
"""
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

DAYS = 7
US_HOUSES = ('Copart', 'IAAI')
US_ZONE = 'America/New_York'
WEEKDAYS = (('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд'), ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'),
            ('ორშ', 'სამ', 'ოთხ', 'ხუთ', 'პარ', 'შაბ', 'კვი'))
T = {
    'head': ('Розклад торгів · оберіть країну', 'Расписание торгов · выберите страну', 'ვაჭრობის განრიგი · აირჩიეთ ქვეყანა'),
    'korea': ('🇰🇷 Корея', '🇰🇷 Корея', '🇰🇷 კორეა'),
    'usa': ('🇺🇸 Америка', '🇺🇸 Америка', '🇺🇸 ამერიკა'),
    'japan': ('🇯🇵 Японія', '🇯🇵 Япония', '🇯🇵 იაპონია'),
    'tz_usa': ('США (Нью-Йорк)', 'США (Нью-Йорк)', 'აშშ (ნიუ-იორკი)'),
    'tz_kyiv': ('Київ', 'Киев', 'კიევი'),
    'today': ('Сьогодні, {d}', 'Сегодня, {d}', 'დღეს, {d}'),
    'trade': ('Торги', 'Торги', 'ვაჭრობა'),
    'dayoff': ('Вихідний', 'Выходной', 'დასვენების დღე'),
    'japan_soon': ('Аукціони Японії — незабаром', 'Аукционы Японии — скоро', 'იაპონიის აუქციონები — მალე'),
}


def _span(texts):
    uk, ru, ka = texts
    return '<span data-uk="%s" data-ru="%s" data-ka="%s">%s</span>' % (escape(uk), escape(ru), escape(ka), escape(uk))


def _day(at):
    return tuple('%s, %s' % (names[at.weekday()], at.strftime('%d.%m')) for names in WEEKDAYS)


def us_week(now):
    """[(date, trading)] for today and the next DAYS - 1 days, US Eastern dates; trading Monday to Friday."""
    start = now.astimezone(ZoneInfo(US_ZONE)).date()
    return [(start + timedelta(days=n), (start + timedelta(days=n)).weekday() < 5) for n in range(DAYS)]


def _us_panel(now):
    rows = []
    for n, (date, trading) in enumerate(us_week(now)):
        day = _day(date)
        label = _span(tuple(t.format(d=d) for t, d in zip(T['today'], day))) if n == 0 else _span(day)
        houses = ('<span class="kt-houses">%s</span>' % ''.join('<span>%s</span>' % h for h in US_HOUSES)
                  if trading else '')
        rows.append('<span class="kt-wd kt-wd-%s"><span class="kt-day">%s</span><span class="kt-num">%s</span>%s</span>'
                    % ('cars' if trading else 'dayoff', label, _span(T['trade' if trading else 'dayoff']), houses))
    clocks = '<span class="kt-time">%s <b data-kt-tz="%s">--:--</b> · %s <b data-kt-tz="Europe/Kyiv">--:--</b></span>' % (
        _span(T['tz_usa']), US_ZONE, _span(T['tz_kyiv']))
    return clocks + ''.join(rows)


def wrap(korea, now, japan=None):
    """Korea week tile inner HTML -> the same tile with the country tabs (Korea selected). JAPAN-LHD-001: `japan`, the
    Japan tab's inner HTML (ticker.py: the Japan week, left-hand drive only); without it «Аукціони Японії — незабаром»."""
    panels = (('korea', korea), ('usa', _us_panel(now)),
              ('japan', japan or '<span class="kt-count">%s</span>' % _span(T['japan_soon'])))
    tabs = ''.join('<button type="button" role="tab" id="kt-tab-%s" aria-controls="kt-panel-%s" aria-selected="%s"'
                   ' tabindex="%s">%s</button>' % (key, key, 'true' if n == 0 else 'false', '0' if n == 0 else '-1',
                                                   _span(T[key])) for n, (key, _) in enumerate(panels))
    bodies = ''.join('<div role="tabpanel" id="kt-panel-%s" aria-labelledby="kt-tab-%s"%s>%s</div>'
                     % (key, key, '' if n == 0 else ' hidden', body) for n, (key, body) in enumerate(panels))
    return ('<style>%s</style><span class="kt-cty-h">%s</span><div class="kt-cty" role="tablist">%s</div>%s'
            '<script>%s</script>' % (CSS, _span(T['head']), tabs, bodies, JS))


CSS = ('.kt-cty-h{font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#3a2a00}'
       '.kt-cty{display:flex;gap:6px;margin:4px 0 6px}'
       '.kt-cty button{flex:1;padding:8px 4px;border-radius:10px;border:1.5px solid rgba(11,21,36,.35);'
       'background:rgba(255,255,255,.25);color:#0B1524;font:800 14px/1.1 inherit;cursor:pointer}'
       '.kt-cty button[aria-selected=true]{background:#0B1524;color:#ffd200;border-color:#0B1524}'
       '.kt-cty button:focus-visible{outline:2px solid #0B1524;outline-offset:2px}')
JS = ("(function(){[].forEach.call(document.querySelectorAll('.korea-ticker .kt-cty'),function(list){"
      "var tabs=[].slice.call(list.querySelectorAll('[role=tab]'));"
      "function pick(t){tabs.forEach(function(x){var on=x===t;x.setAttribute('aria-selected',on);"
      "x.tabIndex=on?0:-1;document.getElementById(x.getAttribute('aria-controls')).hidden=!on;});}"
      "tabs.forEach(function(t,i){t.addEventListener('click',function(){pick(t);});"
      "t.addEventListener('keydown',function(e){var d=e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0;"
      "if(d){e.preventDefault();var n=tabs[(i+d+tabs.length)%tabs.length];pick(n);n.focus();}});});});})();")
