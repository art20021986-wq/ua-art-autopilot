"""Read-only Search Console report on the server, where the service account key lives.

GET/query only: properties and permission, sitemaps, top queries and pages for 28 days,
and the index status of key pages. The key itself never leaves the server.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import resource
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
# Uploaded from an iPhone the extension may be dropped.
KEYS = (HOME/'uaart-autopilot-110fb4d36d23.json', HOME/'uaart-autopilot-110fb4d36d23')
SITE = 'https://www.uaart.com.ua/'
SCOPE = 'https://www.googleapis.com/auth/webmasters'
API = 'https://www.googleapis.com/webmasters/v3/sites/'
INSPECT = 'https://searchconsole.googleapis.com/v1/urlInspection/index:inspect'
PAGES = ('video/index.html', 'video/katalog.html', 'video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html',
         'video/seo/ru/avto-iz-korei-v-kiev-pod-kluch.html', 'video/UA-0018.html', 'video/UA-0021.html',
         'video/UA-0023.html')


def token(key):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    credentials = service_account.Credentials.from_service_account_file(str(key), scopes=[SCOPE])
    credentials.refresh(Request())
    return credentials.service_account_email, credentials.token


def call(bearer, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method='POST' if body is not None else 'GET', headers={
        'Authorization': 'Bearer ' + bearer, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        return error.code, {'error': error.read(400).decode('utf-8', 'replace')}


def rows(bearer, dimension, start, end):
    status, value = call(bearer, API + urllib.parse.quote(SITE, safe='') + '/searchAnalytics/query', {
        'startDate': str(start), 'endDate': str(end), 'dimensions': [dimension], 'rowLimit': 50, 'type': 'web'})
    if status != 200:
        return {'http': status, **value}
    return {'http': status, 'rows': [{'key': r['keys'][0], 'clicks': r.get('clicks', 0),
                                      'impressions': r.get('impressions', 0),
                                      'position': round(r.get('position', 0), 1)}
                                     for r in value.get('rows', [])]}


def inspect(bearer, page):
    status, value = call(bearer, INSPECT, {'inspectionUrl': SITE + page, 'siteUrl': SITE, 'languageCode': 'ru'})
    if status != 200:
        return {'http': status, **value}
    index = value.get('inspectionResult', {}).get('indexStatusResult', {})
    return {'http': status, **{k: index.get(k) for k in ('verdict', 'coverageState', 'indexingState',
                                                        'pageFetchState', 'lastCrawlTime', 'googleCanonical')}}


def report():
    keys = [key for key in KEYS if key.is_file()]
    if not keys:
        return {'status': 'FAIL', 'error': 'KEY_MISSING',
                'candidates': sorted(p.name for p in HOME.glob('uaart-autopilot*'))}
    try:
        email, bearer = token(keys[0])
    except ImportError as error:
        return {'status': 'FAIL', 'error': 'GOOGLE_AUTH_MISSING:' + str(error)[:120]}
    except Exception as error:
        return {'status': 'FAIL', 'error': 'TOKEN:' + type(error).__name__ + ':' + str(error)[:160]}
    status, sites = call(bearer, API.rstrip('/'))
    status_map, sitemaps = call(bearer, API + urllib.parse.quote(SITE, safe='') + '/sitemaps')
    end = datetime.date.today() - datetime.timedelta(days=2)
    start = end - datetime.timedelta(days=27)
    value = {'status': 'PASS', 'service_account': email,
             'sites': {'http': status, 'entries': sites.get('siteEntry', sites)},
             'sitemaps': {'http': status_map, 'entries': [{k: s.get(k) for k in ('path', 'lastSubmitted', 'lastDownloaded',
                                                                                'isPending', 'errors', 'warnings', 'contents')}
                                                          for s in sitemaps.get('sitemap', [])] if status_map == 200 else sitemaps},
             'window': [str(start), str(end)], 'queries': rows(bearer, 'query', start, end),
             'pages': rows(bearer, 'page', start, end), 'inspection': {p: inspect(bearer, p) for p in PAGES}}
    full = [e for e in value['sites']['entries'] if isinstance(e, dict) and e.get('siteUrl') == SITE] \
        if isinstance(value['sites']['entries'], list) else []
    value['permission'] = full[0].get('permissionLevel') if full else None
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (20, 25))
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
