"""Build the KOREA-HOW-SYNC candidate: the Korea page keeps its «5 кроків до вашого авто» block current (owner 2026-11-11).

The block stays in the page HTML (search engines, no-script visitors). A small script right after it loads the
home page (video/index.html, the one source of the block) and puts the home block in its place; on any failure
the page keeps its own copy. The site language script translates the new block itself (it watches added nodes).
Only video/korea.html changes.
"""
PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
DEPENDENCY_SHA256 = {}
START = '<section class="ua-how section-frame">'
END = '</section>'
MARK = 'id="ua-how-sync"'
HOME_URL = '/video/index.html'
SCRIPT = ('<script ' + MARK + '>(function(){var s=document.querySelector("section.ua-how");'
          'if(!s||!window.fetch||!window.DOMParser)return;'
          'fetch("' + HOME_URL + '",{cache:"no-cache"}).then(function(r){return r.ok?r.text():"";})'
          '.then(function(h){var n=h&&new DOMParser().parseFromString(h,"text/html").querySelector("section.ua-how");'
          'if(n)s.replaceWith(document.importNode(n,true));}).catch(function(){});})();</script>')


def apply(page):
    if page.count(START) != 1 or MARK in page:
        raise ValueError('KOREA_HOW_SYNC_PAGE_UNEXPECTED')
    end = page.index(END, page.index(START)) + len(END)
    return page[:end] + SCRIPT + page[end:]


def build(source, dependencies):
    return {PAGE: apply(source[PAGE].decode('utf-8')).encode('utf-8')}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
