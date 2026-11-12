"""Home page: the «Кредит і лізинг» block right above the «5 кроків» purchase steps (HOME-FINANCE-001).

The block goes right before the steps section and one CSS block before </head>; every other byte stays. Each anchor
must occur exactly once and the release must not be live yet, otherwise nothing is changed.
"""
import re

import finance_block

STEPS = '<section class="ua-how section-frame">'
HEAD = re.compile(r'(?=</head\s*>)', re.I)
# Public proof that this release is live.
CHECK = 'class="ua-fin section-frame"'


def build(source):
    text = source.decode('utf-8')
    if finance_block.MARK in text or CHECK in text or text.count(STEPS) != 1 or len(HEAD.findall(text)) != 1:
        raise ValueError('HOME_FINANCE_ANCHOR')
    text = text.replace(STEPS, finance_block.section() + STEPS, 1)
    text = HEAD.sub(lambda m: finance_block.CSS, text, count=1)
    return text.encode('utf-8')
