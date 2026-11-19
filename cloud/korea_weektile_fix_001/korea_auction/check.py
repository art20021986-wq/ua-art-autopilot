"""KOREA-WEEKTILE-001 (owner 2026-11-19: «so that this never happens again»): the check before the ticker is written.

Pure function: the ticker data against the published lot list (lots.json, what the Korea page shows) and the Korea
date. Every ticker car must be in the list and not on a past day, «Завтра» only on the next day; the tile's week must
start today and give the list's car count for each day. The job writes the ticker only when nothing is found.
"""
from .selection import auction_date, day_after


def problems(data, lots, today):
    """-> list of short problem codes (empty: the ticker may be written)."""
    ids = {lot['id'] for lot in lots}
    counts = {}
    for lot in lots:
        counts[auction_date(lot)] = counts.get(auction_date(lot), 0) + 1
    found = []
    for item in data.get('items', []):
        day = item['auction_start_jst'][:10]
        if item['id'] not in ids:
            found.append('CAR_NOT_IN_LIST:' + item['id'])
        if day < today:
            found.append('CAR_PAST_DAY:' + item['id'])
        if bool(item.get('tomorrow')) != (day == day_after(today)):
            found.append('CAR_TOMORROW_WRONG:' + item['id'])
    week = data.get('week') or []
    if not week or week[0]['date'] != today:
        found.append('TILE_TODAY_WRONG')
    for day in week:
        if day['lots'] != counts.get(day['date'], 0):
            found.append('TILE_COUNT_WRONG:' + day['date'])
    if data.get('lots_today', 0) != counts.get(today, 0):
        found.append('TILE_TODAY_COUNT_WRONG')
    return found
