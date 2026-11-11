"""Home page «5 кроків» block: steps 2–5 with the country switcher and the Korea terms (ORDER-PROCESS-001, owner
2026-11-11; texts in steps_text.py).

Inside the block only: the switcher goes under the heading, the Korea steps 2–5 before today's steps 2–5, which stay
byte for byte but are marked data-ua-for="other" hidden (shown when another country is chosen), and the note,
signature and scripts after the list. One CSS block goes before </head>. Step 1 and every other byte stay. Each anchor
must occur exactly once and the release must not be live yet, otherwise nothing is changed.
"""
import re

import kr_prices
import steps_block

START = '<section class="ua-how section-frame">'
HEADING = ('<h2 data-ru="5 шагов до вашего авто" data-uk="5 кроків до вашого авто" '
           'data-ka="5 ნაბიჯი თქვენს ავტომობილამდე">5 кроків до вашого авто</h2>')
OLD_STEPS = tuple('<li><i>%d</i>' % n for n in (2, 3, 4, 5))
HIDDEN = '<li data-ua-for="other" hidden><i>%d</i>'
END = '</ol></section>'
HEAD = re.compile(r'(?=</head\s*>)', re.I)
# Public proof that this release is live.
CHECK = 'data-ua-country="korea"'


def _block(text):
    if text.count(START) != 1:
        raise ValueError('HOME_STEPS_BLOCK')
    start = text.index(START)
    end = text.index(END, start) + len(END)
    return start, end


def build(source):
    text = source.decode('utf-8')
    if steps_block.MARK in text or len(HEAD.findall(text)) != 1:
        raise ValueError('HOME_STEPS_ANCHOR')
    start, end = _block(text)
    block = text[start:end]
    for anchor in (HEADING,) + OLD_STEPS:
        if block.count(anchor) != 1:
            raise ValueError('HOME_STEPS_ANCHOR')
    block = block.replace(HEADING, HEADING + steps_block.switcher(), 1)
    block = block.replace(OLD_STEPS[0], steps_block.korea_steps() + OLD_STEPS[0], 1)
    for number, anchor in enumerate(OLD_STEPS, 2):
        block = block.replace(anchor, HIDDEN % number, 1)
    block = block[:-len('</section>')] + (steps_block.other_note() + steps_block.signature()
                                          + steps_block.SWITCH_SCRIPT + kr_prices.SCRIPT + '</section>')
    text = text[:start] + block + text[end:]
    text = HEAD.sub(lambda m: steps_block.CSS, text, count=1)
    return text.encode('utf-8')
