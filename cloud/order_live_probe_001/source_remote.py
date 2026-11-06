"""Read-only probe of the public order page after ORDER-CONTACT: what a phone browser is served.

Fetches the order page, its script, form module and strings from the public site (no cookies, no form submission),
reports HTTP status, cache headers, the script and module versions referenced, and whether the thank-you markers are
present. Nothing is written outside this run's own receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import urllib.request

HERE = Path(__file__).resolve().parent
SITE = 'https://www.uaart.com.ua'
PHONE = ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
         'Version/18.0 Mobile/15E148 Safari/604.1')
PATHS = ('/video/podbor.html', '/podbor.html', '/video/order/order.js?v=20261106.2',
         '/video/order/preferences-form.js?v=20261106.2', '/video/order/order-strings.json?v=20261106.2')
MARKERS = ('order.js?v=20261106.2', 'data-label="thanks"', 'id="contact-fields"', 'data-label="reply_time"',
           "form.requestSubmit()", "persist,$('contact-fields')", "[this.contact,['contact']]", '"thanks":',
           'data-label="saved"', 'order.js?v=20261106.1')


def fetch(path):
    request = urllib.request.Request(SITE + path, headers={'User-Agent': PHONE})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(2 * 1024 * 1024)
            text = body.decode('utf-8', 'replace')
            return {'status': response.status, 'final_url': response.url, 'bytes': len(body),
                    'sha256': hashlib.sha256(body).hexdigest(),
                    'cache_control': response.headers.get('Cache-Control'), 'expires': response.headers.get('Expires'),
                    'last_modified': response.headers.get('Last-Modified'), 'etag': response.headers.get('ETag'),
                    'versions': sorted(set(re.findall(r'order/[a-z.-]+\?v=[0-9.]+|\./[a-z-]+\.js\?v=[0-9.]+', text))),
                    'markers': {m: m in text for m in MARKERS}}
    except Exception as error:
        return {'error': type(error).__name__ + ':' + str(error)[:160]}


def report():
    return {'status': 'PASS', 'public': {path: fetch(path) for path in PATHS}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (60, 70))
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
