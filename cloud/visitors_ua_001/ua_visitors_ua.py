"""«🇺🇦 Посетители из Украины» — the report (owner «да» 2026-11-26), read-only over the own counter's analytics.db.

Only visits whose browser time zone is Ukraine's (the counter records it since this release; no IP, no personal data);
staff devices are never recorded (the «не считать меня» link). For a period: totals (people, visits, engaged, «зашёл и
вышел», contact taps, enquiries, sources, devices) and, per anonymous visitor, the source, device, the route of pages
with minutes, the number of actions and how the visit ended. Pure text out (HTML for Telegram), no writes.
"""
import datetime
from html import escape
import os
import sqlite3
import time

BAZA = os.path.join('/home/Carix', 'analytics.db')
UKRAINE_TZ = ('Europe/Kyiv', 'Europe/Kiev', 'Europe/Uzhgorod', 'Europe/Zaporozhye')
VIEWS = ('page', 'card', 'diag')
CONTACTS = ('whatsapp', 'telegram', 'phone')
QUIET = ('start', 'scroll', 'page', 'card', 'diag')
FORM_WORDS = ('пропозиц', 'предложен', 'заявк', 'надісл', 'отправ')
PER_PAGE = 8
DEVICES = {'m': '📱', 'd': '💻', 't': '📱'}


def kyiv():
    from zoneinfo import ZoneInfo
    return ZoneInfo('Europe/Kyiv')


def bounds(period, now=None):
    """(start, end, title) in seconds for today / yesterday / 7d / 30d, days by Kyiv time."""
    zone = kyiv()
    today = datetime.datetime.fromtimestamp(now or time.time(), zone).date()

    def midnight(day):
        return datetime.datetime(day.year, day.month, day.day, tzinfo=zone).timestamp()
    days = {'today': (0, 'Сегодня'), 'yesterday': (1, 'Вчера'), '7d': (6, 'Неделя'), '30d': (29, 'Месяц')}
    back, title = days[period]
    start = today - datetime.timedelta(days=back)
    end = today if period == 'yesterday' else today + datetime.timedelta(days=1)
    return midnight(start), midnight(end), title


def range_bounds(first, last):
    """(start, end, title) for a custom period of dates (inclusive)."""
    zone = kyiv()
    start = datetime.datetime(first.year, first.month, first.day, tzinfo=zone).timestamp()
    stop = last + datetime.timedelta(days=1)
    end = datetime.datetime(stop.year, stop.month, stop.day, tzinfo=zone).timestamp()
    return start, end, '%s–%s' % (first.strftime('%d.%m'), last.strftime('%d.%m.%Y'))


def page_name(path, names):
    """A short human name of a page (the counter's own naming when available)."""
    if names:
        try:
            return names(path)
        except Exception:
            pass
    return (path or '').split('?')[0].rsplit('/', 1)[-1] or 'Главная'


def collect(start, end, db=BAZA):
    """[{visitor}] for visits in Ukraine that started in [start, end)."""
    con = sqlite3.connect('file:%s?mode=ro' % db, uri=True, timeout=10)
    try:
        columns = {r[1] for r in con.execute('PRAGMA table_info(sessions)')}
        if 'tz' not in columns:
            return []
        marks = ','.join('?' * len(UKRAINE_TZ))
        sessions = con.execute('SELECT sid, vid, nachalo, istochnik, utm_source, dv FROM sessions '
                               'WHERE nachalo>=? AND nachalo<? AND tz IN (%s) ORDER BY nachalo' % marks,
                               (start, end) + UKRAINE_TZ).fetchall()
        people = {}
        for sid, vid, began, source, utm, device in sessions:
            events = con.execute('SELECT ts, tip, stranica, znachenie FROM events WHERE sid=? ORDER BY ts, id',
                                 (sid,)).fetchall()
            person = people.setdefault(vid, {'first': began, 'source': source or 'Прямой / неизвестный',
                                             'device': device or '', 'visits': 0, 'events': []})
            person['visits'] += 1
            person['events'] += events
        return list(people.values())
    finally:
        con.close()


def summarize(person, names=None):
    """Route with minutes, actions, duration and outcome of one visitor."""
    events = sorted(person['events'])
    route, actions, contact, form = [], 0, False, False
    views = [e for e in events if e[1] in VIEWS]
    for n, (ts, tip, path, value) in enumerate(views):
        nxt = views[n + 1][0] if n + 1 < len(views) else (events[-1][0] if events else ts)
        name = page_name(path, names)
        minutes = (nxt - ts) // 60
        step = '%s (%d мин)' % (name, minutes) if minutes >= 1 else name
        if not route or route[-1] != step:
            route.append(step)
    for ts, tip, path, value in events:
        if tip in QUIET:
            continue
        actions += 1
        contact = contact or tip in CONTACTS
        form = form or tip == 'zayavka' or (tip == 'knopka' and any(w in (value or '').lower() for w in FORM_WORDS))
    duration = (events[-1][0] - events[0][0]) if events else 0
    deep = any(t == 'scroll' for _, t, _, _ in events)
    engaged = duration >= 10 or len(views) >= 2 or actions > 0 or deep
    outcome = ('📝 отправил заявку' if form else '📞 нажал «связаться»' if contact
               else '🔥 заинтересовался' if engaged else '👋 зашёл и вышел')
    return {'route': route, 'actions': actions, 'duration': duration, 'contact': contact, 'form': form,
            'engaged': engaged, 'outcome': outcome}


def build(start, end, title, page=0, db=BAZA, names=None):
    """(HTML text, number of pages)."""
    people = collect(start, end, db)
    if not people:
        return ('🇺🇦 <b>Посетители из Украины</b> · %s\n\nЗа этот период посетителей из Украины нет '
                '(учёт по часовому поясу идёт с установки отчёта).' % escape(title)), 1
    rows = [(p, summarize(p, names)) for p in people]
    rows.sort(key=lambda r: -r[0]['first'])
    total, visits = len(rows), sum(p['visits'] for p, _ in rows)
    engaged = sum(1 for _, s in rows if s['engaged'])
    contact = sum(1 for _, s in rows if s['contact'])
    form = sum(1 for _, s in rows if s['form'])
    sources, devices = {}, {}
    for p, _ in rows:
        sources[p['source']] = sources.get(p['source'], 0) + 1
        icon = DEVICES.get(p['device'], '❔')
        devices[icon] = devices.get(icon, 0) + 1
    head = ['🇺🇦 <b>Посетители из Украины</b> · %s' % escape(title),
            'Людей: <b>%d</b> · визитов: %d' % (total, visits),
            '🔥 Заинтересовались: %d · 👋 Зашли и вышли: %d' % (engaged, total - engaged),
            '📞 Нажали «связаться»: %d · 📝 Заявки: %d' % (contact, form),
            'Откуда: ' + ' · '.join('%s %d' % (escape(k), v) for k, v in sorted(sources.items(), key=lambda x: -x[1])),
            ' · '.join('%s %d' % (k, v) for k, v in sorted(devices.items(), key=lambda x: -x[1])), '']
    pages = max(1, -(-total // PER_PAGE))
    page = min(max(page, 0), pages - 1)
    zone = kyiv()
    lines = []
    for n, (p, s) in enumerate(rows[page * PER_PAGE:(page + 1) * PER_PAGE], start=page * PER_PAGE + 1):
        when = datetime.datetime.fromtimestamp(p['first'], zone).strftime('%d.%m %H:%M')
        route = ' → '.join(s['route'][:8]) or '—'
        minutes = s['duration'] // 60
        lasted = ('%d мин' % minutes) if minutes else ('%d сек' % s['duration'])
        lines.append('%d. %s %s · %s\n   %s\n   ⏱ %s · действий: %d · %s' % (
            n, DEVICES.get(p['device'], '❔'), when, escape(p['source']), escape(route), lasted, s['actions'],
            s['outcome']))
    foot = ['', 'Стр. %d из %d' % (page + 1, pages)] if pages > 1 else []
    return '\n'.join(head + lines + foot), pages
