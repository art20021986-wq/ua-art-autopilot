"""Read-only weekly probe on the server (KOREA-WEEK-001, owner 2026-11-12: check every week how many Korea online
auctions run and whether new ones were added).

Uses the collector already installed on the server (/home/Carix/korea_auction) with the owner's login file, as the
hourly job does: reads the Korea search form (auction groups, their labels, which are checked by default), then
searches each group on its own and reports every auction (house + day) of the coming 7 days, its lots and whether the
site collector (default groups only) sees it. No lot page, no bid; nothing is written except this receipt.
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


def search_group(browser, collect, group):
    """All lots of one auction group: the collector's own search with only that group checked."""
    original = collect._search_form_data

    def one_group(html):
        action, data = original(html)
        return action, [(k, v) for k, v in data if k not in ('auction_group[]', 'auction[]')] + [('auction_group[]', group)]

    collect._search_form_data = one_group
    try:
        return collect.fetch_all_lots(browser)
    finally:
        collect._search_form_data = original


def report():
    sys.path.insert(0, str(ROOT))
    from korea_auction import collect, job, session
    from korea_auction.selection import JST
    import week

    browser = session.Session()
    browser.login(*job.read_login())
    _, page = browser.fetch(collect.SEARCH_PAGE)
    form_groups = week.groups(page)
    lots_by_group, totals = {}, {}
    for group in form_groups:
        totals[group['value']], lots_by_group[group['value']] = search_group(browser, collect, group['value'])
    today = datetime.now(JST).strftime('%Y/%m/%d')
    default = [g['value'] for g in form_groups if g['checked']]
    return {'status': 'PASS', 'no_bid_placed': True, 'today_kst': today, 'groups': [
                dict(g, lots_total=totals[g['value']], lots_parsed=len(lots_by_group[g['value']])) for g in form_groups],
            'default_groups': default, 'week': week.week(lots_by_group, default, today),
            'requests': browser.requests}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (300, 310))
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
