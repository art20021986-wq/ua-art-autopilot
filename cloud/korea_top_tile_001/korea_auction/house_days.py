"""Which auction houses hold an auction on each weekday and when they start (KOREA-TOP-TILE-001, owner 2026-11-26:
the tile shows, for a coming day, the day's auctions and their start — not «lots in 1–2 days»).

Learnt from the auction's own lot lists: every run records, per weekday, each house seen with its start time
('HH:MM' Korea) and the date it was seen; a house not seen on that weekday for KEEP_DAYS is dropped. The search form
names some of them ahead (schedule.py) but not all — AutoPlus on Friday shows there only once its lots are listed,
though it runs every Friday (13.11: 56 lots, 20.11: 46) — so the two are joined for the tile. Pure functions.
"""
from datetime import datetime, timedelta

from .selection import auction_date

KEEP_DAYS = 15  # a weekly auction is seen again within a week; one missed week is forgiven
# Seen in the published lot lists (video/korea/lots.json) 16-26.11.2026 and confirmed twice or by the search form:
# weekday (Monday 0) -> house -> start, date. The job learns every other house as its lots are listed.
SEED = {
    '0': {'AutoPlus': {'start': '12:00', 'seen': '2026/11/16'}},
    '2': {'Auto Hub Auction': {'start': '13:00', 'seen': '2026/11/18'}},
    '3': {'AutoPlus': {'start': '12:00', 'seen': '2026/11/26'}, 'K-Car O-San': {'start': '13:00', 'seen': '2026/11/26'},
          'K-Car Se-Jong': {'start': '13:00', 'seen': '2026/11/26'}},
    '4': {'AutoPlus': {'start': '12:00', 'seen': '2026/11/20'}},
}


def _weekday(date):
    return str(datetime.strptime(date, '%Y/%m/%d').weekday())


def update(history, lots):
    """history (as above) with the houses and earliest starts of these lots recorded. -> new history"""
    out = {day: dict(houses) for day, houses in (history or {}).items()}
    first = {}
    for lot in lots:
        if lot.get('house'):
            key = (auction_date(lot), lot['house'])
            first[key] = min(first.get(key, lot['auction_start']), lot['auction_start'])
    for (date, house), start in sorted(first.items()):
        known = out.setdefault(_weekday(date), {}).get(house)
        if not known or known['seen'] <= date:
            out[_weekday(date)][house] = {'start': start[11:16], 'seen': date}
    return out


def expected(history, weekday, today):
    """{house: 'HH:MM'} seen on this weekday (Monday 0) within KEEP_DAYS before `today` ('YYYY/MM/DD')."""
    since = (datetime.strptime(today, '%Y/%m/%d') - timedelta(days=KEEP_DAYS)).strftime('%Y/%m/%d')
    return {house: seen['start'] for house, seen in sorted((history or {}).get(str(weekday), {}).items())
            if seen['seen'] >= since}
