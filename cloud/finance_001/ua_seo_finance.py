"""The finance landing page body and head (FINANCE-001); ua_seo_landings wraps it like its other pages.

Pure: texts and partners from ua_finance_partners in, HTML out. Partner links are rel="sponsored" (Google's
rule for partner links), open in a new tab and carry data-finance-partner, which the site's own analytics
(/ua/a.js, loaded here as on the site's other pages) records as a «finance» click for the CRM bot.
Structured data: the dealer, breadcrumbs, one LoanOrCredit per partner offer and the visible questions.
"""
from html import escape

import ua_finance_partners as finance
import ua_seo_schema as schema

STYLE = (
    '.fin-intro{max-width:720px;color:#c8d2e1;font-size:17px}'
    '.fin-list{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));margin:0;padding:0;list-style:none}'
    '.fin-card{display:flex;flex-direction:column;gap:12px;padding:20px;border-radius:18px;background:#0f2137;'
    'border:1px solid rgba(240,166,60,.25);box-shadow:0 8px 24px rgba(0,0,0,.25)}'
    '.fin-head{display:flex;align-items:center;gap:14px}'
    '.fin-logo{display:flex;align-items:center;justify-content:center;width:120px;height:56px;padding:6px 10px;'
    'border-radius:12px;background:#fff;box-sizing:border-box}.fin-logo img{display:block;max-width:100%;max-height:44px;height:auto}'
    '.fin-head h3{margin:0;font-size:20px}.fin-kind{display:block;color:#aebed0;font-size:14px;font-weight:400}'
    '.fin-terms{display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}'
    '.fin-terms li{padding:6px 10px;border-radius:10px;background:rgba(76,194,122,.12);border-left:3px solid #4cc27a;'
    'font-size:14px;font-weight:600}'
    '.fin-card .cta{margin:4px 0 0;text-align:center}.fin-lender,.fin-note{margin:0;color:#aebed0;font-size:13px}'
    '.fin-steps{counter-reset:s;list-style:none;padding:0;display:grid;gap:10px}'
    '.fin-steps li{counter-increment:s;position:relative;padding:12px 14px 12px 52px;border-radius:14px;background:#0f2137}'
    '.fin-steps li::before{content:counter(s);position:absolute;left:14px;top:10px;width:26px;height:26px;border-radius:50%;'
    'background:#f0a63c;color:#10161f;font-weight:800;text-align:center;line-height:26px}'
    '@media(max-width:640px){h1{font-size:26px}.fin-list{grid-template-columns:1fr}}')
# The site's own analytics script, as the analytics guard adds it to the site's top-level pages.
ANALYTICS = "<script src='/ua/a.js?v=1' defer></script><!--UA-ANALIT-V1-->"


def _card(lang, partner):
    text, kind = partner[lang], finance.KINDS[partner['kind']][lang]
    width, height = partner['logo_size']
    logo = '<span class="fin-logo"><img src="%s" alt="%s" width="%d" height="%d" decoding="async"></span>' % (
        escape(partner['logo']), escape(partner['name']), width, height)
    terms = ''.join('<li>%s</li>' % escape(term) for term in text['terms'])
    return ('<li class="fin-card"><div class="fin-head">%s<h3>%s<span class="fin-kind">%s</span></h3></div>'
            '<ul class="fin-terms">%s</ul>'
            '<a class="cta" href="%s" target="_blank" rel="sponsored noopener" data-finance-partner="%s">%s</a>'
            '<p class="fin-lender">%s: %s</p></li>') % (
        logo, escape(partner['name']), escape(kind), terms, escape(partner['href'], quote=True),
        escape(partner['id'], quote=True), escape(text['cta']), escape(finance.PAGE[lang]['lender']),
        escape(partner['lender'][lang]))


def _offer(lang, partner, page_url):
    return {'@type': 'LoanOrCredit', '@id': '%s#%s' % (page_url, partner['id']),
            'name': '%s — %s' % (finance.KINDS[partner['kind']][lang], partner['name']),
            'loanType': finance.KINDS[partner['kind']][lang], 'url': page_url, 'areaServed': 'UA',
            'provider': {'@type': 'Organization', 'name': partner['name'], 'url': partner['site']}}


def page(lang, home, home_url, page_url):
    """{'title', 'desc', 'h1', 'body', 'head'} of the finance page in lang (uk or ru)."""
    text = finance.PAGE[lang]
    cards = ''.join(_card(lang, p) for p in finance.PARTNERS)
    steps = ''.join('<li>%s</li>' % escape(step) for step in text['steps'])
    faq = ''.join('<h3>%s</h3><p>%s</p>' % (escape(q), escape(a)) for q, a in text['faq'])
    body = ('<p class="fin-intro">%s</p><h2>%s</h2><ul class="fin-list">%s</ul><p class="fin-note">%s</p>'
            '<h2>%s</h2><ol class="fin-steps">%s</ol>%s'
            '<p><a href="/video/katalog.html">%s</a> · <a href="/video/podbor.html">%s</a></p>') % (
        escape(text['intro']), escape(text['partners']), cards, escape(text['note']), escape(text['how']), steps,
        faq, escape(text['catalog']), escape(text['order']))
    ld = schema.script(schema.dealer(lang), schema.breadcrumbs([(home, home_url), (text['crumb'], page_url)]),
                       *[_offer(lang, p, page_url) for p in finance.PARTNERS], schema.faq(list(text['faq'])))
    return {'title': text['title'], 'desc': text['desc'], 'h1': text['h1'], 'body': body,
            'head': '<style>%s</style>%s%s' % (STYLE, ld, ANALYTICS)}
