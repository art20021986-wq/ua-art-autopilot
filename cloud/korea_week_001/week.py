"""Korea online auctions of the week (KOREA-WEEK-001, owner 2026-11-12): pure functions, no network.

- schedule(html): the auction days of the search form (one box per weekday, plus Oneprice) with their label, the
  auctions listed under each day and whether the form checks the day by default;
- week(lots, site_lots, today): every auction (house + day) of the coming 7 days, its lots at the auction and how many
  of them the site lot list shows;
- compare(old, new): auctions and schedule entries that appeared or disappeared since the previous weekly report.

Probe R1 (2026-11-12): the search ignores the day boxes (every single day gave the same 434 lots), so the week is
counted from one search — the one the site collector makes — and checked against the published lot list.

Local use: python3 cloud/korea_week_001/week.py PREVIOUS.json CURRENT.json   (two probe reports) -> the changes.
"""
from collections import Counter
from datetime import datetime, timedelta
from html import unescape
import json
import re
import sys

WEEK_DAYS = 7
_TAG = re.compile(r'<[^>]+>')


def _text(html):
    return ' '.join(unescape(_TAG.sub(' ', html)).split())


def _attr(tag, name):
    found = re.search(r'(?i)\b%s="([^"]*)"' % name, tag)
    return found.group(1) if found else ''


def _boxes(form, name):
    """Checkboxes of one name -> [{'value', 'label', 'checked'}]; label = <label for=id> text, else the text after the
    box up to the next input."""
    out = []
    for match in re.finditer(r'(?is)<input\b[^>]*\bname="%s"[^>]*>' % re.escape(name), form):
        tag, box_id = match.group(0), _attr(match.group(0), 'id')
        label = re.search(r'(?is)<label\b[^>]*\bfor="%s"[^>]*>(.*?)</label>' % re.escape(box_id), form) if box_id else None
        if label:
            text = _text(label.group(1))
        else:
            rest = form[match.end():]
            text = _text(rest[:rest.find('<input')] if '<input' in rest else rest[:400])
        out.append({'value': _attr(tag, 'value'), 'label': text[:120],
                    'checked': bool(re.search(r'(?i)\schecked\b', tag))})
    return out


def schedule(html):
    """Search form days -> [{'value', 'label', 'checked', 'auctions': [labels]}]; an auction box 'NNN|G' is under day G."""
    form = html[html.find('id="purchase_search_form"'):]
    form = form[:form.find('</form>')] if '</form>' in form else form
    auctions = _boxes(form, 'auction[]')
    return [dict(day, auctions=[a['label'] for a in auctions if a['value'].rsplit('|', 1)[-1] == day['value']])
            for day in _boxes(form, 'auction_group[]')]


def _day(lot):
    return lot['auction_start'][:10]  # 'YYYY/MM/DD' (Japan/Korea time, as the auction shows it)


def week(lots, site_lots, today):
    """Auctions (house + day) from today for WEEK_DAYS days, in date order: lots at the auction, lots on the site."""
    end = (datetime.strptime(today, '%Y/%m/%d') + timedelta(days=WEEK_DAYS)).strftime('%Y/%m/%d')
    at_auction = Counter((_day(l), l['house']) for l in lots if today <= _day(l) < end)
    on_site = Counter((_day(l), l['house']) for l in site_lots)
    return [{'date': date, 'weekday': datetime.strptime(date, '%Y/%m/%d').strftime('%a'), 'house': house,
             'lots': n, 'on_site': on_site[(date, house)]}
            for (date, house), n in sorted(at_auction.items())]


def _houses(report):
    out = {}
    for auction in report.get('week', []):
        out.setdefault(auction['house'], set()).add(auction['weekday'])
    return out


def _entries(report):
    """Schedule entries: 'day label' and 'day label / auction label'."""
    out = set()
    for day in report.get('schedule', []):
        out.add(day['label'])
        out.update('%s / %s' % (day['label'], a) for a in day.get('auctions', []))
    return out


def compare(old, new):
    """What changed between two weekly reports, and what the site misses now."""
    before, after = _houses(old), _houses(new)
    return {
        'new_houses': sorted(set(after) - set(before)),
        'gone_houses': sorted(set(before) - set(after)),
        'new_days': {h: sorted(after[h] - before[h]) for h in sorted(set(after) & set(before)) if after[h] - before[h]},
        'new_schedule': sorted(_entries(new) - _entries(old)),
        'gone_schedule': sorted(_entries(old) - _entries(new)),
        'auctions_before': len(old.get('week', [])), 'auctions_now': len(new.get('week', [])),
        'site_misses_now': [a for a in new.get('week', []) if a['on_site'] < a['lots']],
    }


def main(argv):
    old, new = (json.load(open(path, encoding='utf-8')) for path in argv[1:3])
    print(json.dumps(compare(old, new), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(sys.argv)
