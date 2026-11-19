"""The yellow tile's week (KOREA-WEEKTILE-001, owner 2026-11-19: not 3 days ahead but the week, by the auction
schedule): today and the next 6 days (Korea time), each with its listed car count, or what the Korea page day buttons
say for it — «Лоти з'являться за 1–2 дні», «Вихідний» or the holiday — and its auction houses: the listed ones with
their start, else the schedule's. Pure function of the published lot list, the schedule and the holidays.
"""
from datetime import datetime, timedelta

from .holidays import HOLIDAYS
from .selection import auction_date, houses

DAYS = 7


def _state(date, count, first, holidays):
    """As the Korea page day button: cars listed; a holiday; Saturday/Sunday off; a later weekday «soon»; today 0."""
    if count:
        return 'cars'
    if date in holidays:
        return 'holiday'
    if datetime.strptime(date, '%Y/%m/%d').weekday() >= 5:
        return 'dayoff'
    return 'cars' if first else 'soon'


def week(lots, schedule, today, holidays=HOLIDAYS):
    """[{'date', 'lots', 'state', 'houses': [{'name', 'start'?}], 'holiday'?}] for today and the next DAYS - 1 days."""
    counts = {}
    for lot in lots:
        counts[auction_date(lot)] = counts.get(auction_date(lot), 0) + 1
    start = datetime.strptime(today, '%Y/%m/%d')
    out = []
    for n in range(DAYS):
        day = start + timedelta(days=n)
        date = day.strftime('%Y/%m/%d')
        state = _state(date, counts.get(date, 0), n == 0, holidays)
        listed = [{'name': name, 'start': at} for name, at in houses(lots, date)]
        planned = [{'name': name} for name in (schedule or [[]] * 7)[day.weekday()]] if state in ('cars', 'soon') else []
        entry = {'date': date, 'lots': counts.get(date, 0), 'state': state, 'houses': listed or planned}
        if state == 'holiday':
            entry['holiday'] = list(holidays[date])
        out.append(entry)
    return out
