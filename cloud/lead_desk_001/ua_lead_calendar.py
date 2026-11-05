"""Working days and the reply deadline of a site enquiry (ORDER-PROCESS-001, owner decisions 2026-11-05).

Pure functions, no I/O. Working days: Monday to Saturday, except Ukrainian public holidays of art. 73 of the
Labour Code (any year; Easter and Trinity by the Orthodox calendar). The client gets a preliminary price within
3 full working days: the day the enquiry arrives is not counted, the deadline is the end of the 3rd working day
after it, Kyiv time.
"""
import datetime
from zoneinfo import ZoneInfo

KYIV = ZoneInfo('Europe/Kyiv')
REPLY_DAYS = 3
FIXED_HOLIDAYS = frozenset(((1, 1), (3, 8), (5, 1), (5, 8), (6, 28), (7, 15), (8, 24), (10, 1), (12, 25)))


def orthodox_easter(year):
    """Julian Easter (Meeus) in the Gregorian calendar; the 13-day shift holds for 1900–2099."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month, day = divmod(d + e + 114, 31)
    return datetime.date(year, month, day + 1) + datetime.timedelta(days=13)


def holidays(year):
    easter = orthodox_easter(year)
    return {datetime.date(year, m, d) for m, d in FIXED_HOLIDAYS} | {easter, easter + datetime.timedelta(days=49)}


def is_working_day(day):
    return day.weekday() != 6 and day not in holidays(day.year)


def deadline(created_at):
    """Unix time of the enquiry → aware datetime: end of the 3rd full working day after the arrival day."""
    day = datetime.datetime.fromtimestamp(created_at, KYIV).date()
    left = REPLY_DAYS
    while left:
        day += datetime.timedelta(days=1)
        left -= is_working_day(day)
    return datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time(), KYIV)


def working_days_left(created_at, now):
    """Working days still to come for the reply, the arrival day not counted: 3 on arrival, 1 on the last day,
    0 once the deadline has passed."""
    arrival = datetime.datetime.fromtimestamp(created_at, KYIV).date()
    first = max(datetime.datetime.fromtimestamp(now, KYIV).date(), arrival + datetime.timedelta(days=1))
    last = (deadline(created_at) - datetime.timedelta(seconds=1)).date()
    return sum(is_working_day(first + datetime.timedelta(days=n)) for n in range((last - first).days + 1))
