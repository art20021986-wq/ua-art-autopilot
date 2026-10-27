"""Insert or refresh the AUTO.RIA reviews block and footer badge on the home page (AUTORIA-REVIEWS-001).

First release: the block goes right after the «5 кроків» section, the badge before the footer signature, the CSS
before </head>. Later releases (texts, data refresh) replace those three fragments in place. Each anchor or
fragment must occur exactly once, otherwise nothing is changed.
"""
import re

import reviews_block

STEPS = re.compile(r'<section class="ua-how section-frame">.*?</section>', re.S)
SIGNATURE = re.compile(r'(?=<div class="signature")')
HEAD = re.compile(r'(?=</head\s*>)', re.I)
BLOCK = re.compile(r'<section class="ua-reviews section-frame" id="vidguky">.*?</section>', re.S)
BADGE = re.compile(r'<a class="ua-autoria-badge" [^>]*>.*?</a>', re.S)
CSS = re.compile(r'<style id="%s">.*?</style>' % reviews_block.MARK, re.S)
# Public proof that this release is live.
CHECK = 'class="ua-autoria-mark"'


def _once(pattern, text, new):
    if len(pattern.findall(text)) != 1:
        raise ValueError('HOME_FRAGMENT_NOT_UNIQUE:' + pattern.pattern[:30])
    return pattern.sub(lambda m: new(m.group()), text, count=1)


def build(source):
    text = source.decode('utf-8')
    if reviews_block.MARK in text:
        text = _once(BLOCK, text, lambda old: reviews_block.block())
        text = _once(BADGE, text, lambda old: reviews_block.badge())
        text = _once(CSS, text, lambda old: reviews_block.CSS)
    else:
        text = _once(STEPS, text, lambda old: old + reviews_block.block())
        text = _once(SIGNATURE, text, lambda old: reviews_block.badge())
        text = _once(HEAD, text, lambda old: reviews_block.CSS)
    return text.encode('utf-8')
