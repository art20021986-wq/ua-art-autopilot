"""Build the KOREA-TERMS candidate: the Korea page without its own terms blocks (owner 2026-11-11).

video/korea.html: the yellow «Депозит 2000 $ — входить у вартість авто» block and the «Як це працює» block (4 steps)
are removed; the home page keeps the terms (5 points). Nothing else changes.
"""
PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
DEPENDENCY_SHA256 = {}
DEPOSIT = '<section class="kr-sec"><div class="kr-deposit">'
STEPS = '<section class="kr-sec"><h2><span data-uk="Як це працює"'
END = '</section>'


def cut(page):
    """(start, end) of the two adjacent blocks, or ValueError when the page is not as expected."""
    start = page.find(DEPOSIT)
    if page.count(DEPOSIT) != 1 or page.count(STEPS) != 1:
        raise ValueError('KOREA_TERMS_PAGE_UNEXPECTED')
    steps = page.index(END, start) + len(END)
    if not page.startswith(STEPS, steps):
        raise ValueError('KOREA_TERMS_PAGE_UNEXPECTED')
    end = page.index(END, steps) + len(END)
    if page.count('<section', start, end) != 2:
        raise ValueError('KOREA_TERMS_PAGE_UNEXPECTED')
    return start, end


def apply(page):
    start, end = cut(page)
    return page[:start] + page[end:]


def build(source, dependencies):
    return {PAGE: apply(source[PAGE].decode('utf-8')).encode('utf-8')}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
