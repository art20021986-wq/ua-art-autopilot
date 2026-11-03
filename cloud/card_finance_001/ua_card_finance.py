"""«Кредити та лізинг» on every car card (FINANCE-001 stage 4): one link next to «ask a question».

Installed as ua_card_finance.py; ua_seo_metadata.normalize calls add() for every card page it writes, so
every card — in stock, on the way, on the ferry, and every future one — gets the link at its publication.
The card page is Russian HTML that the site language script shows in Ukrainian/Georgian: the link carries
data-ru/data-uk/data-ka texts (as the site's other translated elements) and data-uk-href, which
ua_card_lang uses for the Ukrainian page. It opens the finance page with the card code, which the CRM bot
shows as where a partner visit came from. Texts and paths come from ua_finance_partners.
Idempotent: a card that already has the link gets it rewritten, never doubled.
"""
from html import escape
import re

import ua_finance_partners as finance

LINK_ID = 'ua-finance-link'
# The card's «ask a question about this car» link; the finance link goes right after it.
ANCHOR = re.compile(r"<a\b[^>]*\bid=['\"]vopros['\"][^>]*>.*?</a>", re.S)
OWN = re.compile(r'<a\b[^>]*\bid="%s"[^>]*>.*?</a>' % LINK_ID, re.S)
CODE = re.compile(r'(UA-[0-9]{4,})\.html$', re.I)


def link(code):
    def href(lang):
        return '%s?card=%s' % (finance.page_path(lang), code)
    return ('<a class="vtoraya" id="%s" href="%s" data-uk-href="%s" data-ru="%s" data-uk="%s" data-ka="%s">%s</a>' % (
        LINK_ID, escape(href('ru')), escape(href('uk')), escape(finance.BUTTON['ru']), escape(finance.BUTTON['uk']),
        escape(finance.BUTTON['ka']), escape(finance.BUTTON['ru'])))


def add(source, file_name):
    """The card page with the finance link; a page without the «ask a question» link is left as it is."""
    found = CODE.search(str(file_name))
    if not found:
        return source
    value = link(found.group(1).upper())
    if OWN.search(source):
        return OWN.sub(lambda m: value, source, count=1)
    anchor = ANCHOR.search(source)
    if not anchor:
        return source
    return source[:anchor.end()] + value + source[anchor.end():]
