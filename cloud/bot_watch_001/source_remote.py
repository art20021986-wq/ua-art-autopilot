"""Read-only bot watch on the server (BOT-WATCH, owner 2026-11-27: «если будут признаки атаки, сразу мне дай
информацию, делай мне отчет по атакам каждые 3 дня»).

Per UTC day from the web app access logs (current, .1, rotated .gz; the server keeps about 10 days):
requests, distinct addresses, honest robots, page views by people (no pictures or scripts), the busiest non-robot
address by page views (masked to /24, with its browser line), addresses over HEAVY page views, server errors (5xx), rate-limited answers (429), counter beacons (POST /ua/a/e) and order
submissions (POST /api/orders/submit). From analytics.db opened read-only: counter events recorded per day,
so beacons minus recorded shows what the counter guard left out. Addresses are counted in memory and never
saved; only a masked /24 of the busiest one is returned. Nothing is written outside this run's own receipt.
"""
import argparse
from collections import Counter
import datetime
import gzip
import ipaddress
import json
import os
from pathlib import Path
import re
import resource
import sqlite3

HERE = Path(__file__).resolve().parent
LOG = Path('/var/log/www.uaart.com.ua.access.log')
DB = Path('/home/Carix/analytics.db')
HEAVY = 300  # page views a day from one non-robot address (pictures and scripts are not counted)
ASSET = re.compile(r'\.(?:jpe?g|png|webp|gif|svg|ico|css|js|woff2?|ttf|mp4|webm|json|txt|xml|map)$', re.I)
ROBOT = re.compile(r'(?<!cu)bot|crawl|spider|slurp|python|curl|wget|headless|externalhit|okhttp|scrapy|lighthouse|'
                   r'go-http|axios|node-fetch|libwww|ua-?art|^-?$', re.I)  # ua-art: our own checks
LINE = re.compile(r'^(\S+) .*?\[(\d{2}/\w{3}/\d{4}):[^\]]*\] "(\S+) (\S+)[^"]*" (\d{3}) \S+ "[^"]*" "([^"]*)"')


def log_texts():
    texts = []
    for suffix in [''] + ['.1'] + ['.%d.gz' % n for n in range(2, 15)]:
        path = Path(str(LOG) + suffix)
        try:
            raw = path.read_bytes()
            if suffix.endswith('.gz'):
                raw = gzip.decompress(raw)
        except (OSError, EOFError):
            if suffix in ('', '.1'):
                continue
            break
        texts.append(raw.decode('utf-8', 'replace'))
    return texts


def masked(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return 'unknown'
    prefix = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network('%s/%d' % (ip, prefix), strict=False))


def day_key(stamp):
    return datetime.datetime.strptime(stamp, '%d/%b/%Y').date().isoformat()


def access(texts):
    days = {}
    for text in texts:
        for line in text.splitlines():
            match = LINE.match(line)
            if not match:
                continue
            address, stamp, method, path, status, agent = match.groups()
            try:
                day = day_key(stamp)
            except ValueError:
                continue
            d = days.setdefault(day, {'requests': 0, 'robot_requests': 0, 'errors_5xx': 0, 'limited_429': 0,
                                      'beacons': 0, 'order_submits': 0, 'people_pages': 0, 'by_address': Counter(),
                                      'agents': {}, 'addresses': set()})
            d['requests'] += 1
            d['addresses'].add(address)
            clean = path.split('?', 1)[0]
            if ROBOT.search(agent):
                d['robot_requests'] += 1
            elif method == 'POST' or not ASSET.search(clean):
                d['people_pages'] += 1
                d['by_address'][address] += 1
                d['agents'].setdefault(address, agent[:90])
            if status.startswith('5'):
                d['errors_5xx'] += 1
            if status == '429':
                d['limited_429'] += 1
            if method == 'POST' and clean == '/ua/a/e':
                d['beacons'] += 1
            if method == 'POST' and clean == '/api/orders/submit':
                d['order_submits'] += 1
    result = {}
    for day, d in sorted(days.items()):
        busiest = d['by_address'].most_common(1)
        result[day] = {key: d[key] for key in ('requests', 'robot_requests', 'errors_5xx', 'limited_429',
                                               'beacons', 'order_submits', 'people_pages')}
        result[day].update(addresses=len(d['addresses']),
                           heavy_addresses=sum(1 for n in d['by_address'].values() if n > HEAVY),
                           busiest={'network': masked(busiest[0][0]), 'requests': busiest[0][1],
                                    'agent': d['agents'][busiest[0][0]]} if busiest else None)
    return result


def recorded(days):
    """Counter events stored per UTC day (read-only)."""
    if not DB.exists():
        return {}
    con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True, timeout=10)
    try:
        start = datetime.datetime.fromisoformat(min(days)).replace(tzinfo=datetime.timezone.utc).timestamp() if days else 0
        rows = con.execute("SELECT date(ts, 'unixepoch'), COUNT(*) FROM events WHERE ts>=? GROUP BY 1", (start,))
        return dict(rows.fetchall())
    finally:
        con.close()


def report():
    days = access(log_texts())
    stored = recorded(days)
    for day, value in days.items():
        value['recorded'] = stored.get(day, 0)
    return {'status': 'PASS', 'days': days}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (120, 130))
    work = HERE/'runs'/args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work/'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work/'.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
