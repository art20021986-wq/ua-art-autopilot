"""Build the KOREA-HOW-SYNC candidate: the Korea page keeps its «5 кроків до вашого авто» block current (owner 2026-11-11).

The block stays in the page HTML (search engines, no-script visitors). A small script right after it loads the
home page (video/index.html, the one source of the block) and puts the home block in its place with the Korea part
only (owner 2026-11-11): the country switcher and the other-countries parts are left out, the block styles from the
home head are added once, the block scripts run. Without these parts the whole block is shown. On any failure the
page keeps its own copy. The site language script translates the new block itself (it watches added nodes).
Only video/korea.html changes.
"""
PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
DEPENDENCY_SHA256 = {}
START = '<section class="ua-how section-frame">'
END = '</section>'
MARK = 'id="ua-how-sync"'
HOME_URL = '/video/index.html'
# Home block parts (ORDER-PROCESS-001, cloud/home_steps_001): the country switcher .ua-cc and data-ua-for="korea" /
# "other" parts; the block CSS sits in the home head as <style id="ua-home-step...">; the block scripts sit inside it.
DROP = '.ua-cc,[data-ua-for]:not([data-ua-for="korea"])'
STYLES = 'head style[id^="ua-home-step"]'
SCRIPT = ('<script ' + MARK + '>(function(){var s=document.querySelector("section.ua-how");'
          'if(!s||!window.fetch||!window.DOMParser)return;'
          'fetch("' + HOME_URL + '",{cache:"no-cache"}).then(function(r){return r.ok?r.text():"";})'
          '.then(function(h){var d=h&&new DOMParser().parseFromString(h,"text/html"),'
          'n=d&&d.querySelector("section.ua-how");if(!n)return;'
          'd.querySelectorAll(\'' + STYLES + '\').forEach(function(c){'
          'if(!document.getElementById(c.id))document.head.appendChild(document.importNode(c,true));});'
          'n.querySelectorAll(\'' + DROP + '\').forEach(function(e){e.remove();});'
          'var b=document.importNode(n,true);s.replaceWith(b);'
          'b.querySelectorAll("script").forEach(function(o){var x=document.createElement("script");'
          'x.textContent=o.textContent;o.replaceWith(x);});}).catch(function(){});})();</script>')


def apply(page):
    if page.count(START) != 1 or MARK in page:
        raise ValueError('KOREA_HOW_SYNC_PAGE_UNEXPECTED')
    end = page.index(END, page.index(START)) + len(END)
    return page[:end] + SCRIPT + page[end:]


def build(source, dependencies):
    return {PAGE: apply(source[PAGE].decode('utf-8')).encode('utf-8')}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
