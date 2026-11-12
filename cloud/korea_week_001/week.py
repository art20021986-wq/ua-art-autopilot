"""Korea online auctions of the week (KOREA-WEEK-001, owner 2026-11-12): pure functions, no network.

- groups(html): the auction groups of the search form, with their label and whether the form checks them by default
  (the site collector searches only the default-checked groups);
- week(lots_by_group, default_groups, today): every auction (house + day) of the coming 7 days, its lots and whether
  the site collector sees it;
- compare(old, new): auctions and groups that appeared or disappeared since the previous weekly report.

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
_BOX = re.compile(r'(?is)<input\b[^>]*\bname="auction_group\[\]"[^>]*>')


def _text(html):
    return ' '.join(unescape(_TAG.sub(' ', html)).split())


def _attr(tag, name):
    found = re.search(r'(?i)\b%s="([^"]*)"' % name, tag)
    return found.group(1) if found else ''


def groups(html):
    """Search form auction groups -> [{'value', 'label', 'checked'}] in page order.

    The label is the <label for=id> text when the box has one, else the text after the box up to the next input."""
    form = html[html.find('id="purchase_search_form"'):]
    out = []
    for match in _BOX.finditer(form):
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


def _day(lot):
    return lot['auction_start'][:10]  # 'YYYY/MM/DD' (Japan/Korea time, as the auction shows it)


def week(lots_by_group, default_groups, today):
    """{group: [lot]} -> auctions (house + day) from today for WEEK_DAYS days, in date order.

    A lot listed in several groups counts once. `on_site` is True when one of its groups is searched by default."""
    end = (datetime.strptime(today, '%Y/%m/%d') + timedelta(days=WEEK_DAYS)).strftime('%Y/%m/%d')
    seen, lots, where = set(), Counter(), {}
    for group, group_lots in sorted(lots_by_group.items()):
        for lot in group_lots:
            key = (_day(lot), lot['house'])
            where.setdefault(key, set()).add(group)
            if today <= key[0] < end and lot['id'] not in seen:
                seen.add(lot['id'])
                lots[key] += 1
    return [{'date': date, 'weekday': datetime.strptime(date, '%Y/%m/%d').strftime('%a'), 'house': house,
             'lots': n, 'groups': sorted(where[(date, house)]),
             'on_site': bool(where[(date, house)] & set(default_groups))}
            for (date, house), n in sorted(lots.items())]


def houses(report):
    """Auction house -> weekdays it ran on, from one weekly report."""
    out = {}
    for auction in report.get('week', []):
        out.setdefault(auction['house'], set()).add(auction['weekday'])
    return out


def compare(old, new):
    """What changed between two weekly reports: houses, house weekdays, form groups."""
    before, after = houses(old), houses(new)
    old_groups = {g['value']: g['label'] for g in old.get('groups', [])}
    new_groups = {g['value']: g['label'] for g in new.get('groups', [])}
    return {
        'new_houses': sorted(set(after) - set(before)),
        'gone_houses': sorted(set(before) - set(after)),
        'new_days': {h: sorted(after[h] - before[h]) for h in sorted(set(after) & set(before)) if after[h] - before[h]},
        'new_groups': {v: new_groups[v] for v in sorted(set(new_groups) - set(old_groups))},
        'gone_groups': {v: old_groups[v] for v in sorted(set(old_groups) - set(new_groups))},
        'auctions_before': len(old.get('week', [])), 'auctions_now': len(new.get('week', [])),
        'not_on_site_now': [a for a in new.get('week', []) if not a['on_site']],
    }


def main(argv):
    old, new = (json.load(open(path, encoding='utf-8')) for path in argv[1:3])
    print(json.dumps(compare(old, new), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(sys.argv)
