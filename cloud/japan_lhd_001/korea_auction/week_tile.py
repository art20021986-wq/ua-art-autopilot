"""The yellow tile's week (KOREA-WEEKTILE-001, owner 2026-11-19: not 3 days ahead but the week, by the auction
schedule): today and the next 6 days (Korea time), each with its listed car count, or what the Korea page day buttons
say for it — «Лоти з'являться за 1–2 дні», «Вихідний» or the holiday — and its auction houses: the listed ones with
their start, else the schedule's. Owner 2026-11-19: «Лоти з'являться» only when the schedule has an auction that day
and no later day is listed yet; otherwise «Аукціонів немає». Pure function of the lot list, schedule and holidays.
"""
from datetime import datetime, timedelta

from . import house_days
from .holidays import HOLIDAYS
from .selection import auction_date, houses

DAYS = 7


def _state(date, count, first, holidays, planned, later):
    """As the Korea page day button: cars listed; a holiday; Saturday/Sunday off; today 0; a later weekday «soon» when
    the schedule has an auction and no later day is listed, else «none»."""
    if count:
        return 'cars'
    if date in holidays:
        return 'holiday'
    if datetime.strptime(date, '%Y/%m/%d').weekday() >= 5:
        return 'dayoff'
    if first:
        return 'cars'
    return 'soon' if planned and not later else 'none'


def week(lots, schedule, today, holidays=HOLIDAYS, history=None):
    """[{'date', 'lots', 'state', 'houses': [{'name', 'start'?}], 'holiday'?}] for today and the next DAYS - 1 days.
    KOREA-TOP-TILE-001 (owner 2026-11-26): a day not listed yet shows its expected houses with their start — from the
    search form schedule and the houses seen on that weekday before (house_days.py)."""
    counts = {}
    for lot in lots:
        counts[auction_date(lot)] = counts.get(auction_date(lot), 0) + 1
    start = datetime.strptime(today, '%Y/%m/%d')
    out = []
    for n in range(DAYS):
        day = start + timedelta(days=n)
        date = day.strftime('%Y/%m/%d')
        seen = house_days.expected(history, day.weekday(), today)
        names = list(dict.fromkeys((schedule or [[]] * 7)[day.weekday()] + list(seen)))
        state = _state(date, counts.get(date, 0), n == 0, holidays, bool(names) or not schedule,
                       any(d > date for d in counts))
        listed = [{'name': name, 'start': at} for name, at in houses(lots, date)]
        planned = ([dict({'name': name}, **({'start': date + ' ' + seen[name]} if name in seen else {}))
                    for name in names] if state in ('cars', 'soon') else [])
        # KOREA-PLAN-DAYS-001 (owner 2026-11-26): by start time; a house without a known start goes last
        planned.sort(key=lambda house: ('start' not in house, house.get('start', '')))
        entry = {'date': date, 'lots': counts.get(date, 0), 'state': state, 'houses': listed or planned}
        if state == 'holiday':
            entry['holiday'] = list(holidays[date])
        out.append(entry)
    return out
