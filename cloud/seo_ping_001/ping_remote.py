"""SEO-PING-001 on the server: tell IndexNow and Google that the two finance pages changed (owner «Да» 2026-11-04).

Uses the site's own installed notifiers (ua_indexnow: the two page URLs; ua_google_sitemap: Search Console re-reads
the sitemap), exactly as a landing refresh does when the sitemap changes. Both are best effort and never raise.
No site, CRM, source or bot write; only this run's receipt.
"""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import sys

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
URLS = ('https://www.uaart.com.ua/video/seo/ua/kredyt-lizynh-avto.html',
        'https://www.uaart.com.ua/video/seo/ru/kredit-lizing-avto.html')


def report(home=HOME):
    sys.path.insert(0, str(home))
    try:
        import ua_google_sitemap
        import ua_indexnow
    finally:
        sys.path.remove(str(home))
    indexnow, google = ua_indexnow.submit(URLS), ua_google_sitemap.submit()
    passed = indexnow.get('status') == 'PASS' and google.get('status') == 'PASS'
    return {'status': 'PASS' if passed else 'FAIL', 'urls': list(URLS), 'indexnow': indexnow, 'google': google}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (60, 70))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-ping.json'
    if receipt.exists():
        return 0  # one notice per run: a retried trigger never sends twice
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:160]}
    value.update(run_id=args.run, mode='ping', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-ping.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
