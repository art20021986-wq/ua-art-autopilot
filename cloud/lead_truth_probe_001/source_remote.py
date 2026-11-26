"""Read-only probe (coordinator 2026-11-26 for the owner: «мне никто не написал и не позвонил … за месяц»).

1. GA4, 30 days: generate_lead (form) and contact (button) events by date, page and source; users by country, city and
   channel; totals — to separate real enquiries from tests and button taps.
2. The site enquiries in the order database (read through the installed order package, read-only): number, date,
   schema, page, ad source, and only a yes/no test mark (the name or phone of a test) — no names or phones.
3. Where the contact buttons lead: the Telegram pages (t.me) and the WhatsApp link, fetched from the server.
R2 (coordinator 2026-11-26, owner: «Оставь мне только статистику из Украины … кто сколько раз клацал … что смотрел»):
the own counter's database (analytics.db) — tables, columns, row counts, how visitors and sessions are keyed, whether it
keeps a country, address, browser or time zone (names of fields and counts only), and three anonymous sample routes; GA4
30 days for Ukraine only (sessions and events by city, source, landing page, device; engagement).
Nothing is written outside this run's own receipt.
"""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import sqlite3
import subprocess
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
KEYS = tuple(HOME / ('uaart-autopilot-110fb4d36d23' + ext) for ext in ('.json', '', '.txt'))
PROPERTY = 'properties/560695713'
DATA = 'https://analyticsdata.googleapis.com/v1beta/%s:runReport' % PROPERTY
LINKS = ('https://t.me/UA_artcompany_LLC_bot', 'https://t.me/uaart_auto', 'https://wa.me/380992222002')
COMPANY_PHONE = '+380992222002'
TEST = re.compile(r'(?i)тест|test|claude|перевір|провер|smoke')
ORDERS = r'''
import json, re, sys
sys.path.insert(0, sys.argv[1])
from ua_order import host
loaded = host.current()
repo = None
for owner in (loaded, getattr(loaded, 'service', None)):
    for name in ('repository', 'repo', 'store', 'storage'):
        candidate = getattr(owner, name, None) if owner is not None else None
        if candidate is not None and hasattr(candidate, 'list_requests'):
            repo = candidate
            break
    if repo:
        break
if repo is None:
    print(json.dumps({'error': 'NO_REPOSITORY', 'loaded': type(loaded).__name__}))
    raise SystemExit(0)
test = re.compile(sys.argv[2])
phone = sys.argv[3]
rows, before = [], None
while True:
    page, before = repo.list_requests(before=before, limit=20)
    for item in page:
        data = item.get('data') or {}
        name = str(data.get('customer_name') or data.get('name') or '')
        contact = data.get('contact') or {}
        phones = [str(v) for v in (contact.values() if isinstance(contact, dict) else [])]
        attribution = data.get('attribution') or {}
        rows.append({'number': item.get('number'), 'created_at': item.get('created_at'), 'channel': item.get('channel'),
                     'schema': data.get('schema_version'), 'source_path': data.get('source_path'),
                     'telegram': bool(item.get('telegram_user_id')),
                     'ad_source': sorted(attribution) if isinstance(attribution, dict) else [],
                     'gclid_test': 'TEST' in str(attribution.get('gclid', '')) if isinstance(attribution, dict) else False,
                     'test_mark': bool(test.search(name)) or any(p.replace(' ', '') == phone for p in phones)})
    if before is None or len(rows) > 400:
        break
print(json.dumps({'requests': rows}))
'''


def ga4(days=30):
    key = next((k for k in KEYS if k.is_file()), None)
    if not key:
        return {'error': 'KEY_MISSING'}
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    credentials = service_account.Credentials.from_service_account_file(
        str(key), scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    credentials.refresh(Request())

    def run(dimensions, metrics, limit=50, events=None):
        body = {'dateRanges': [{'startDate': '%ddaysAgo' % (days - 1), 'endDate': 'today'}],
                'dimensions': [{'name': n} for n in dimensions], 'metrics': [{'name': n} for n in metrics],
                'limit': limit, 'orderBys': [{'metric': {'metricName': metrics[0]}, 'desc': True}]}
        if events:
            body['dimensionFilter'] = {'filter': {'fieldName': 'eventName', 'inListFilter': {'values': list(events)}}}
        request = urllib.request.Request(DATA, data=json.dumps(body).encode(), method='POST', headers={
            'Authorization': 'Bearer ' + credentials.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                rows = json.loads(response.read()).get('rows', [])
            return [[c.get('value') for c in r.get('dimensionValues', []) + r.get('metricValues', [])] for r in rows]
        except urllib.error.HTTPError as error:
            return {'http': error.code, 'error': error.read(300).decode('utf-8', 'replace')}
    leads = ('generate_lead', 'contact')
    return {'lead_events': run(['date', 'eventName', 'pagePath', 'sessionSourceMedium', 'country'], ['eventCount'], 100,
                               leads),
            'lead_event_devices': run(['eventName', 'deviceCategory', 'city'], ['eventCount'], 50, leads),
            'countries': run(['country'], ['activeUsers', 'sessions'], 25),
            'cities': run(['city'], ['activeUsers'], 20),
            'channels': run(['sessionDefaultChannelGroup'], ['activeUsers', 'sessions', 'engagedSessions']),
            'source_medium': run(['sessionSourceMedium'], ['activeUsers', 'sessions'], 25),
            'totals': run([], ['activeUsers', 'sessions', 'engagedSessions', 'averageSessionDuration'], 1)}


def orders():
    result = subprocess.run(['python3.10', '-c', ORDERS, str(HOME), TEST.pattern, COMPANY_PHONE], capture_output=True,
                            text=True, timeout=120, check=False, cwd=str(HOME))
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {'error': 'EXIT_%s' % result.returncode, 'stderr': result.stderr[-300:].replace(str(HOME), '~')}


def links():
    found = {}
    for url in LINKS:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (UAART link check)'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read(300000).decode('utf-8', 'replace')
                final = response.url
            meta = dict(re.findall(r'<meta property="og:(title|description)" content="([^"]*)"', text))
            extra = re.findall(r'class="tgme_page_extra">\s*([^<]{0,80})', text)
            found[url] = {'status': 200, 'final': final[:120], 'title': meta.get('title', '')[:120],
                          'description': meta.get('description', '')[:160], 'extra': [e.strip() for e in extra][:2],
                          'bot_or_user': 'tgme_action_button_new' in text}
        except Exception as error:
            found[url] = {'error': type(error).__name__ + ':' + str(error)[:100]}
    return found


def own_counter():
    db = HOME / 'analytics.db'
    if not db.is_file():
        return {'error': 'MISSING'}
    con = sqlite3.connect('file:%s?mode=ro' % db, uri=True, timeout=10)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        value = {t: {'columns': [r[1] for r in con.execute('PRAGMA table_info("%s")' % t.replace('"', ''))],
                     'rows': con.execute('SELECT count(*) FROM "%s"' % t.replace('"', '')).fetchone()[0]}
                 for t in tables}
        samples = []
        if 'events' in tables:
            cols = value['events']['columns']
            sids = [r[0] for r in con.execute('SELECT sid FROM events GROUP BY sid HAVING count(*) >= 4 '
                                              'ORDER BY max(ts) DESC LIMIT 3')]
            for n, sid in enumerate(sids):
                rows = con.execute('SELECT * FROM events WHERE sid=? ORDER BY ts LIMIT 30', (sid,)).fetchall()
                samples.append([{c: (str(v)[:60] if c not in ('vid', 'sid') else 'visitor-%d' % n)
                                 for c, v in zip(cols, r)} for r in rows])
        if 'sessions' in tables:
            cols = value['sessions']['columns']
            value['sessions']['sample'] = [{c: (str(v)[:80] if c not in ('vid', 'sid') else '…') for c, v in zip(cols, r)}
                                           for r in con.execute('SELECT * FROM sessions ORDER BY rowid DESC LIMIT 3')]
        return {'tables': value, 'sample_routes': samples}
    finally:
        con.close()


def ga4_ukraine(days=30):
    key = next((k for k in KEYS if k.is_file()), None)
    if not key:
        return {'error': 'KEY_MISSING'}
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    credentials = service_account.Credentials.from_service_account_file(
        str(key), scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    credentials.refresh(Request())
    ukraine = {'filter': {'fieldName': 'country', 'stringFilter': {'value': 'Ukraine'}}}

    def run(dimensions, metrics, limit=60):
        body = {'dateRanges': [{'startDate': '%ddaysAgo' % (days - 1), 'endDate': 'today'}],
                'dimensions': [{'name': n} for n in dimensions], 'metrics': [{'name': n} for n in metrics],
                'limit': limit, 'dimensionFilter': ukraine,
                'orderBys': [{'metric': {'metricName': metrics[0]}, 'desc': True}]}
        request = urllib.request.Request(DATA, data=json.dumps(body).encode(), method='POST', headers={
            'Authorization': 'Bearer ' + credentials.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                rows = json.loads(response.read()).get('rows', [])
            return [[c.get('value') for c in r.get('dimensionValues', []) + r.get('metricValues', [])] for r in rows]
        except urllib.error.HTTPError as error:
            return {'http': error.code, 'error': error.read(300).decode('utf-8', 'replace')}
    return {'totals': run([], ['activeUsers', 'sessions', 'engagedSessions', 'averageSessionDuration',
                               'screenPageViews', 'eventCount'], 1),
            'sessions': run(['date', 'city', 'deviceCategory', 'sessionSourceMedium', 'landingPage'],
                            ['sessions', 'engagedSessions', 'screenPageViews', 'userEngagementDuration'], 120),
            'events': run(['eventName'], ['eventCount', 'totalUsers'], 40),
            'pages': run(['pagePath'], ['screenPageViews', 'activeUsers', 'userEngagementDuration'], 40),
            'campaign_terms': run(['sessionGoogleAdsQuery', 'sessionGoogleAdsAdGroupName'], ['sessions',
                                                                                             'engagedSessions'], 40)}


def guarded(step):
    try:
        return step()
    except Exception as error:
        return {'error': type(error).__name__ + ':' + str(error)[:160]}


def report():
    return {'status': 'PASS', 'own_counter': guarded(own_counter), 'ga4_ukraine': guarded(ga4_ukraine)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (300, 320))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
