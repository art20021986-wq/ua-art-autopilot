"""The auction's weekly schedule (KOREA-WEEKTILE-001, owner 2026-11-19: the yellow tile shows the week ahead by the
auction schedule): which auction houses hold an auction on each weekday, read from the Korea search form each run.

Pure function, no network. The form lists a box per weekday (auction_group[] 1-6 = Mon-Sat) and under it the day's
houses: a name with its lot count once lots are listed, a grey name before (probe KOREA-WEEK2-PROBE-20261119). The
schedule changes from week to week (K-Car Se-Jong moved from Tuesday to Thursday), so it is never written by hand.
"""
from html import unescape
import re

_DAY = re.compile(r'(?is)name="auction_group\[\]"[^>]*\bvalue="([1-6])".*?<ul class="auction-venue-list">(.*?)</ul>')
_NAME = re.compile(r'(?is)<span class="(?:gray|vehicle-stock-val)">(.*?)</span>')
_NOTE = re.compile(r'\s*\([^)]*\)\s*$')  # «AutoPlus(Weekly)» -> «AutoPlus», as the lot list names the house


def _name(html):
    return _NOTE.sub('', ' '.join(unescape(re.sub(r'<[^>]+>', ' ', html)).split()))


def parse(html):
    """Search page -> [[house, ...] for Monday .. Sunday] (Sunday: no auction); empty lists when not found."""
    week = [[] for _ in range(7)]
    for value, venues in _DAY.findall(html or ''):
        week[int(value) - 1] = list(dict.fromkeys(n for n in map(_name, _NAME.findall(venues)) if n))
    return week
