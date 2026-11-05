#!/usr/bin/env python3
"""LEAD-RADAR-001 probe: which public Telegram sources are readable and how often people ask for cars.

Read-only. Prints only counts, page structure and redacted short fragments (no names, no digits).
"""
import collections
import datetime as dt
import html
import re
import sys
import time
import urllib.request

UA = 'Mozilla/5.0 (compatible; UA-ART-lead-radar-probe/1)'
DISCOVERY = (
    'https://uk.tgstat.com/ratings/chats/transport/public?sort=members',
    'https://uk.tgstat.com/ratings/channels/transport?sort=members',
    'https://uk.tgstat.com/tag/auto-sale',
    'https://tglist.com.ua/en/catalog/transport',
)
SEED = ('usa_tachki', 'importcars_usa', 'carplates', 'grandcarua', 'avtofromtheusa', 'USA_ADVISOR')
WANT = re.compile(
    r'(куплю|купити|купить|шукаю|ищу|підібрати|подобрать|підбір|подбор|порадьте|посоветуйте|'
    r'пригнати|пригнать|пригон|розмитн|растамож|хочу (авто|машин)|потрібн\w* (авто|машин)|нужн\w* (авто|машин)|'
    r'в кредит|лізинг|лизинг|до \d+ ?(тис|тыс|k|к)\b)', re.I)
SKIP_USER = re.compile(r'^(joinchat|addstickers|share|proxy|s|c|iv|tgstat|telegram|durov)$', re.I)


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'uk,ru;q=0.8'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read(3_000_000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception as e:  # network errors are data for the probe
        return type(e).__name__, ''


def text_of(fragment):
    fragment = re.sub(r'<br\s*/?>', ' ', fragment)
    return html.unescape(re.sub(r'<[^>]+>', '', fragment)).strip()


def redact(s):
    s = re.sub(r'\d', '#', s)
    s = re.sub(r'@\w+', '@user', s)
    return s[:90]


def messages(page):
    out = []
    for block in re.split(r'(?=<div class="tgme_widget_message_wrap)', page)[1:]:
        post = re.search(r'data-post="([^"]+)"', block)
        when = re.search(r'<time[^>]*datetime="([^"]+)"', block)
        body = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, re.S)
        replies = re.search(r'tgme_widget_message_replies[^>]*>', block)
        out.append({'post': post.group(1) if post else '', 'time': when.group(1) if when else '',
                    'text': text_of(body.group(1)) if body else '', 'has_replies': bool(replies),
                    'reply_snip': re.sub(r'\s+', ' ', block[replies.start():replies.start() + 200]) if replies else ''})
    return out


def recent(m, days=3):
    try:
        t = dt.datetime.fromisoformat(m['time'])
    except ValueError:
        return False
    return t > dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)


def main():
    users = collections.OrderedDict((u, 'seed') for u in SEED)
    for url in DISCOVERY:
        status, page = get(url)
        found = re.findall(r'(?:t\.me/|tgstat\.com/(?:uk/)?(?:channel|chat)/@?|href="/(?:channel|chat)/@)([A-Za-z]\w{3,31})', page)
        found = [u for u in found if not SKIP_USER.match(u)]
        print('DISCOVERY', url, status, 'bytes', len(page), 'usernames', len(set(found)))
        for u in found:
            users.setdefault(u, url.split('/')[2])
    print('CANDIDATES', len(users))
    total_hits = 0
    samples = []
    class_counter = collections.Counter()
    discussion_checked = 0
    for name in list(users)[:60]:
        status, page = get('https://t.me/s/' + name)
        msgs = messages(page)
        kind = 'channel_preview' if msgs else ('no_preview' if status == 200 else 'error')
        fresh = [m for m in msgs if recent(m)]
        hits = [m for m in fresh if WANT.search(m['text'])]
        with_replies = [m for m in msgs if m['has_replies']]
        comment_hits = 0
        comments_seen = 0
        for m in with_replies[-3:]:
            if not m['post']:
                continue
            s2, p2 = get('https://t.me/%s?embed=1&discussion=1&comments_limit=50' % m['post'])
            if discussion_checked < 2:
                class_counter.update(re.findall(r'class="([a-z_]+)', p2))
                print('DISCUSSION_STATUS', s2, 'bytes', len(p2), 'reply_snip', redact(m['reply_snip']))
            discussion_checked += 1
            cm = messages(p2)
            comments_seen += len(cm)
            for c in cm:
                if recent(c) and WANT.search(c['text']):
                    comment_hits += 1
                    if len(samples) < 25:
                        samples.append('COMMENT ' + redact(c['text']))
            time.sleep(0.5)
        for m in hits:
            if len(samples) < 25:
                samples.append('POST ' + redact(m['text']))
        total_hits += len(hits) + comment_hits
        last = msgs[-1]['time'][:10] if msgs else ''
        print('SOURCE %-28s %-15s via=%-14s posts=%d fresh=%d hits=%d with_comments=%d comments=%d comment_hits=%d last=%s'
              % (name, kind, users[name], len(msgs), len(fresh), len(hits), len(with_replies), comments_seen, comment_hits, last))
        time.sleep(0.7)
    print('DISCUSSION_CLASSES', class_counter.most_common(25))
    print('TOTAL_HITS_3_DAYS', total_hits)
    for s in samples:
        print('SAMPLE', s)


if __name__ == '__main__':
    sys.exit(main())
