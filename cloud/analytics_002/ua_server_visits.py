"""Every visitor by the web server's access log, for the client bot «Аналитика» report.

The access log sees each page request, also from people whose browser blocks or never runs the counter script.
A visitor is one IP address with one browser in one Kyiv day, robots and our own checks left out; the pair is
hashed in memory and never stored. PythonAnywhere keeps the log about ten days, so the daily totals are saved
in server_visits.db and older days come from there.
"""
import datetime
import gzip
import hashlib
from pathlib import Path
import re
import sqlite3
import time

LOG = Path('/var/log/www.uaart.com.ua.access.log')
BAZA = Path('/home/Carix/server_visits.db')
ROTATED = 14
ROBOT = re.compile(r'bot|crawl|spider|slurp|python|curl|wget|headless|ua-?art|task\d|probe|monitor|preview|'
                   r'externalhit|http|java|okhttp|scrapy|lighthouse|go-|axios|node|feed|scan|fetch|meta-|'
                   r'chatgpt|perplexity|claude|^-?$', re.I)
LINE = re.compile(r'^(\S+) .*?\[(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}) ([+-]\d{4})\] "(\S+) (\S+)[^"]*" (\d{3}) '
                  r'\S+ "[^"]*" "([^"]*)"')


def _kiev():
    from zoneinfo import ZoneInfo
    for imya in ("Europe/Kyiv", "Europe/Kiev"):
        try:
            return ZoneInfo(imya)
        except Exception:
            pass
    raise RuntimeError("KIEV_TIMEZONE")


def _texts(log=LOG):
    for suffix in [''] + ['.1'] + ['.%d.gz' % n for n in range(2, ROTATED + 1)]:
        path = Path(str(log) + suffix)
        try:
            raw = path.read_bytes()
            if suffix.endswith('.gz'):
                raw = gzip.decompress(raw)
        except (OSError, EOFError):
            if suffix in ('', '.1'):
                continue
            return
        yield raw.decode('utf-8', 'replace')


def _page(path):
    clean = path.split('?')[0]
    return clean.endswith(('.html', '/')) or '.' not in clean.rsplit('/', 1)[-1]


def from_logs(texts, kiev=None):
    """{Kyiv day 'YYYY-MM-DD': (visitors, page views)} from access log texts."""
    kiev = kiev or _kiev()
    days = {}
    for text in texts:
        for line in text.splitlines():
            match = LINE.search(line)
            if not match:
                continue
            ip, stamp, zone, method, path, status, agent = match.groups()
            if method != 'GET' or status[0] not in '23' or ROBOT.search(agent) or not _page(path) \
                    or path.startswith(('/ua/', '/api/')):
                continue
            moment = datetime.datetime.strptime(stamp + ' ' + zone, '%d/%b/%Y:%H:%M:%S %z')
            day = moment.astimezone(kiev).date().isoformat()
            visitors, views = days.setdefault(day, (set(), [0]))
            visitors.add(hashlib.sha256((ip + '|' + agent).encode()).hexdigest()[:16])
            views[0] += 1
    return {day: (len(visitors), views[0]) for day, (visitors, views) in days.items()}


def _save(found, baza=BAZA):
    connection = sqlite3.connect(str(baza), timeout=10)
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS days(den TEXT PRIMARY KEY, lyudi INTEGER, prosmotry INTEGER, '
                           'obnovleno INTEGER)')
        now = int(time.time())
        oldest = min(found) if found else None
        for day, (people, views) in found.items():
            if day == oldest:
                continue  # the oldest day in the log window is usually cut off by rotation
            connection.execute('INSERT INTO days VALUES(?,?,?,?) ON CONFLICT(den) DO UPDATE SET lyudi=excluded.lyudi, '
                               'prosmotry=excluded.prosmotry, obnovleno=excluded.obnovleno', (day, people, views, now))
        connection.commit()
        return dict((d, (p, v)) for d, p, v in connection.execute('SELECT den, lyudi, prosmotry FROM days'))
    finally:
        connection.close()


def totals(ot, do, log=LOG, baza=BAZA):
    """(visitors summed over days, page views, days) for the Kyiv days touching [ot, do)."""
    kiev = _kiev()
    first = datetime.datetime.fromtimestamp(ot, kiev).date()
    last = datetime.datetime.fromtimestamp(max(ot, do - 1), kiev).date()
    found = from_logs(_texts(log), kiev)
    saved = _save(found, baza)
    people = views = days = 0
    day = first
    while day <= last:
        value = found.get(day.isoformat()) or saved.get(day.isoformat())
        if value:
            people, views, days = people + value[0], views + value[1], days + 1
        day += datetime.timedelta(days=1)
    return people, views, days


def stroki(ot, do):
    """Report lines; empty when the log cannot be read."""
    try:
        people, views, days = totals(ot, do)
    except Exception:
        return []
    if not days:
        return []
    return ['🖥 Все посетители по журналу сервера: %d%s' % (people, ' (сумма по дням)' if days > 1 else '')]
