"""Build the KOREA-HOW candidate: the home page «5 кроків до вашого авто» block on the Korea page (owner 2026-11-11).

The block is taken as it is on the live home page (video/index.html, read only) and placed on video/korea.html where
the removed deposit and «Як це працює» blocks stood: right before «Аукціони, до яких ви отримуєте доступ». The Korea
page already carries the block's styles (shared with the home page). Nothing else changes.
"""
PAGE = 'video/korea.html'
HOME = 'video/index.html'
SOURCE_FILES = (PAGE, HOME)
DEPENDENCY_SHA256 = {}
START = '<section class="ua-how section-frame">'
END = '</section>'
ANCHOR = '<section class="kr-sec"><h2><span data-uk="Аукціони, до яких'


def block(home):
    """The home page steps block, or ValueError when the home page is not as expected."""
    if home.count(START) != 1:
        raise ValueError('KOREA_HOW_HOME_UNEXPECTED')
    start = home.index(START)
    end = home.index(END, start) + len(END)
    if home.count('<section', start, end) != 1:
        raise ValueError('KOREA_HOW_HOME_UNEXPECTED')
    return home[start:end]


def apply(page, steps):
    if START in page or page.count(ANCHOR) != 1:
        raise ValueError('KOREA_HOW_PAGE_UNEXPECTED')
    at = page.index(ANCHOR)
    return page[:at] + steps + page[at:]


def build(source, dependencies):
    steps = block(source[HOME].decode('utf-8'))
    return {PAGE: apply(source[PAGE].decode('utf-8'), steps).encode('utf-8')}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
