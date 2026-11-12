"""Read-only weekly probe on the server (KOREA-WEEK-001, owner 2026-11-12: check every week how many Korea online
auctions run and whether new ones were added).

Uses the collector already installed on the server (/home/Carix/korea_auction) with the owner's login file, as the
hourly job does: reads the Korea search form (auction days and the auctions under each), runs the collector's own
search once and reports every auction (house + day) of the coming 7 days with its lots, and how many of them the
published lot list (video/korea/lots.json) shows. R2: the search ignores the day boxes (R1: every day gave the same
lots), so no per-day search. No lot page, no bid; nothing is written except this receipt.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import resource
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/Carix')
LONG_NUMBER = re.compile(r'\d{5,}')


def site_lots():
    """The lots the site shows now (read only); [] when the list is missing or unreadable."""
    try:
        return json.loads((ROOT / 'video/korea/lots.json').read_text(encoding='utf-8')).get('lots', [])
    except (OSError, ValueError):
        return []


def report():
    sys.path.insert(0, str(ROOT))
    from korea_auction import collect, job, session
    from korea_auction.selection import JST
    import week

    browser = session.Session()
    browser.login(*job.read_login())
    _, page = browser.fetch(collect.SEARCH_PAGE)
    total, lots = collect.fetch_all_lots(browser)
    today = datetime.now(JST).strftime('%Y/%m/%d')
    shown = site_lots()
    return {'status': 'PASS', 'no_bid_placed': True, 'today_kst': today, 'schedule': week.schedule(page),
            'lots_total': total, 'lots_parsed': len(lots), 'site_lots': len(shown),
            'week': week.week(lots, shown, today), 'requests': browser.requests}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (120, 130))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
