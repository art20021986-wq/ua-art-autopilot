"""HOME-STRIP-REMOVE-001 (owner 2026-11-12, «Удали!!!»): the home advantages block (four tiles «Ціна в договорі»,
«Діагностика», «Маршрут онлайн», «Працюємо в Києві») is removed whole. Every other byte stays.
"""
START = '<section class="confidence-strip'
END = '</section>'
# Public proof: the block is gone, the purchase steps that follow are still there.
GONE = ('class="confidence-strip', 'Ціна в договорі', 'Цена в договоре')
CHECK = '<section class="ua-how'


def block(page):
    """(start, end) of the one advantages block; refuses anything else."""
    if page.count(START) != 1:
        raise ValueError('HOME_STRIP_ANCHOR')
    start = page.index(START)
    end = page.index(END, start) + len(END)
    if '<section' in page[start + len(START):end] or 'Ціна в договорі' not in page[start:end]:
        raise ValueError('HOME_STRIP_ANCHOR')
    return start, end


def build(source):
    page = source.decode('utf-8')
    start, end = block(page)
    page = page[:start] + page[end:]
    if CHECK not in page or any(w in page for w in GONE):
        raise ValueError('HOME_STRIP_ANCHOR')
    return page.encode('utf-8')
