"""Where a site enquiry came from: the ad click ids and utm tags the page kept from its landing URL.

Installed as ua_order/attribution.py. contract.normalize takes the optional «attribution» object off
every schema here and keeps the clean values with the request; crm.detail_view shows them to the owner
(with_source: under the text, and under the last message when a long enquiry is sent in parts).
Tracking data never costs a lead: an unknown key or a malformed value is dropped, not rejected.
The click id is kept as sent (case-sensitive) for a later Google Ads conversion import.
"""
from html import escape
import re

# Google Ads click ids and the standard utm tags, with the characters each may hold.
CLICK_IDS = ('gclid', 'gbraid', 'wbraid')
TAGS = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content')
CLICK_ID = re.compile(r'[A-Za-z0-9_-]{10,200}')
TAG = re.compile(r'[^\x00-\x1f\x7f<>]{1,100}')


def split(data):
    """(request without «attribution», its clean values or {})."""
    if not isinstance(data, dict) or 'attribution' not in data:
        return data, {}
    data = dict(data)
    raw = data.pop('attribution')
    if not isinstance(raw, dict):
        return data, {}
    clean = {}
    for key in CLICK_IDS + TAGS:
        value = raw.get(key)
        if isinstance(value, str):
            value = value.strip()
            if (CLICK_ID if key in CLICK_IDS else TAG).fullmatch(value):
                clean[key] = value
    return data, clean


def source(attribution):
    """The owner's one-line answer to «where from»: Google Ads, else the utm source."""
    if any(key in attribution for key in CLICK_IDS):
        return 'Google Ads'
    return attribution.get('utm_source', '')


def lines(attribution):
    """HTML lines for the owner view; nothing for a request without attribution."""
    if not attribution:
        return []
    fields = [('Источник', source(attribution)), ('Кампания', attribution.get('utm_campaign', '')),
              ('Ключ', attribution.get('utm_term', '')), ('Канал', attribution.get('utm_medium', ''))]
    return [f'<b>{escape(key)}:</b> {escape(value)}' for key, value in fields if value]


def with_source(view, attribution):
    """The owner view with the source lines added; a view sent in parts gets them in its last part."""
    extra = '\n'.join(lines(attribution))
    if not extra:
        return view
    view = {**view, 'text': view['text'] + '\n' + extra}
    if 'parts' in view:
        last = view['parts'][-1]
        # Telegram's 4096 limit: a full last part keeps its size and the source becomes one more message.
        tail = [last + '\n' + extra] if len(last) + len(extra) < 4000 else [last, extra]
        view['parts'] = [*view['parts'][:-1], *tail]
    return view
