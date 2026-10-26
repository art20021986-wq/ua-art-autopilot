"""Insert the AUTO.RIA reviews block and footer badge into the home page (AUTORIA-REVIEWS-001).

The block goes right after the «5 кроків» section, the badge at the end of the footer contacts, the CSS before
</head>. Each anchor must occur exactly once and the block must not be there yet, otherwise nothing is changed.
"""
import re

import reviews_block

STEPS = re.compile(r'<section class="ua-how section-frame">.*?</section>', re.S)
FOOTER = '<div class="signature"'
HEAD = re.compile(r'</head\s*>', re.I)
# Public proof that the block is live.
CHECK = 'id="%s"' % reviews_block.MARK


def build(source):
    text = source.decode('utf-8')
    if reviews_block.MARK in text or 'ua-reviews' in text:
        raise ValueError('HOME_ALREADY_CHANGED')
    steps = STEPS.findall(text)
    if len(steps) != 1 or text.count(FOOTER) != 1 or len(HEAD.findall(text)) != 1:
        raise ValueError('HOME_FRAGMENT_NOT_UNIQUE')
    text = text.replace(steps[0], steps[0] + reviews_block.block(), 1)
    text = text.replace(FOOTER, reviews_block.badge() + FOOTER, 1)
    text = HEAD.sub(lambda m: reviews_block.CSS + m.group(), text, count=1)
    return text.encode('utf-8')
