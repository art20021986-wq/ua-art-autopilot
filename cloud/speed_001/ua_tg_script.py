"""SPEED-001: Telegram's Mini App script moves from <head> to just before the first inline script that uses it.

In <head> the synchronous script blocks every visitor's first paint (~1.5 s on a phone). The page's own
inline scripts read window.Telegram.WebApp; scripts between the old and new place are deferred, modules or
do not use it, so inside Telegram the script still runs before its first user. Idempotent; a page without
the tag in <head> or without a user of it is returned unchanged.
"""
import re

TAG = re.compile(r'<script src=([\'"])https://telegram\.org/js/telegram-web-app\.js\1>\s*</script>\n?')
SCRIPT = re.compile(r'<script\b([^>]*)>(.*?)</script\s*>', re.S | re.I)
USES = re.compile(r'\bTelegram\.WebApp\b')


def place(html):
    if not isinstance(html, str):
        return html
    tags = list(TAG.finditer(html))
    body = re.search(r'<body\b', html, re.I)
    if len(tags) != 1 or not body or tags[0].start() > body.start():
        return html
    tag = tags[0]
    for script in SCRIPT.finditer(html, tag.end()):
        if not USES.search(script.group(2)):
            continue
        if script.start() < body.start() or 'src=' in script.group(1):
            return html  # a user in <head> or an external user: keep the original order
        return html[:tag.start()] + html[tag.end():script.start()] + tag.group(0).rstrip('\n') + html[script.start():]
    return html
