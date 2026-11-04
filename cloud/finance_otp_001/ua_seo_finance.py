"""The finance landing page body and head (FINANCE-001, FINANCE-OTP-001); ua_seo_landings wraps it like its other pages.

Pure: texts and partners from ua_finance_partners in, HTML out. One section per kind (credit, then leasing), each
with its own heading, anchor, partner cards and steps, then a credit-or-leasing comparison and the visible
questions. A partner has either a link (rel="sponsored", new tab, data-finance-partner, which the site's own
analytics /ua/a.js records as a «finance» click for the CRM bot) or the partner's own calculator widget, embedded
exactly as the partner gives it in a box that reserves its height (no layout shift while it loads). A partner's key
condition (credit for a car still on its way) is highlighted in the partner's colour above its card.
Structured data: the dealer, breadcrumbs, one LoanOrCredit per partner offer and the visible questions.
"""
from html import escape

import ua_finance_partners as finance
import ua_seo_schema as schema

STYLE = (
    '.fin-intro{max-width:720px;color:#c8d2e1;font-size:17px}'
    '.fin-jump{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}'
    '.fin-jump a{padding:10px 16px;border:1px solid rgba(240,166,60,.45);border-radius:12px;text-decoration:none;font-weight:700}'
    '.fin-section{scroll-margin-top:16px}'
    '.fin-list{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));margin:0;padding:0;list-style:none}'
    '.fin-card{--acc:#f0a63c;display:flex;flex-direction:column;gap:12px;padding:20px;border-radius:18px;background:#0f2137;'
    'border:1px solid var(--acc);border-top-width:4px;box-shadow:0 8px 24px rgba(0,0,0,.25)}'
    # The card is a flex column, which would stretch the logo across the card: keep its own proportions.
    '.fin-logo{display:block;align-self:flex-start;width:auto;height:30px;max-width:100%;object-fit:contain}'
    '.fin-card h3{margin:0;font-size:20px}.fin-kind{color:#aebed0;font-size:15px;font-weight:400}'
    '.fin-terms{display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}'
    '.fin-terms li{padding:6px 10px;border-radius:10px;background:rgba(255,255,255,.06);border-left:3px solid var(--acc);'
    'font-size:14px;font-weight:600}'
    '.fin-card .cta{margin:4px 0 0;text-align:center}.fin-lender,.fin-note,.fin-lead{margin:0;color:#aebed0;font-size:13px}'
    '.fin-lead{margin:0 0 14px;font-size:15px}'
    # A partner's key condition: filled in the partner's colour with dark text (contrast 6.4:1, above WCAG AA 4.5:1).
    '.fin-highlight{--acc:#f0a63c;margin:0 0 16px;padding:16px 18px;border-radius:16px;background:var(--acc);color:#0b1a10}'
    '.fin-highlight b{display:block;margin:0 0 4px;font-size:18px}.fin-highlight p{margin:0;font-size:15px;font-weight:600}'
    # The partner's calculator: its own heights (desktop / phone) are reserved before it loads.
    '.fin-widget{margin:16px 0 0;min-height:var(--h-desktop);border-radius:18px;overflow:hidden}'
    '.fin-steps{counter-reset:s;list-style:none;padding:0;display:grid;gap:10px}'
    '.fin-steps li{counter-increment:s;position:relative;padding:12px 14px 12px 52px;border-radius:14px;background:#0f2137}'
    '.fin-steps li::before{content:counter(s);position:absolute;left:14px;top:10px;width:26px;height:26px;border-radius:50%;'
    'background:#f0a63c;color:#10161f;font-weight:800;text-align:center;line-height:26px}'
    '.fin-compare{overflow-x:auto}'
    '@media(max-width:640px){h1{font-size:26px}.fin-list{grid-template-columns:1fr}.fin-widget{min-height:var(--h-mobile)}}')
# The site's own analytics script, as the analytics guard adds it to the site's top-level pages.
ANALYTICS = "<script src='/ua/a.js?v=1' defer></script><!--UA-ANALIT-V1-->"


def _accent(partner):
    return ' style="--acc:%s"' % escape(partner['color'], quote=True) if partner.get('color') else ''


def _action(lang, partner):
    """The partner's link button, or nothing when the partner's calculator is on the page instead."""
    if 'href' not in partner:
        return ''
    return '<a class="cta" href="%s" target="_blank" rel="sponsored noopener" data-finance-partner="%s">%s</a>' % (
        escape(partner['href'], quote=True), escape(partner['id'], quote=True), escape(partner[lang]['cta']))


def _card(lang, partner, lender):
    width, height = partner['logo_size']
    logo = '<img class="fin-logo" src="%s" alt="%s" width="%d" height="%d" decoding="async">' % (
        escape(partner['logo']), escape(partner['logo_alt']), width, height)
    terms = ''.join('<li>%s</li>' % escape(term) for term in partner[lang]['terms'])
    return ('<li class="fin-card"%s>%s<h3>%s <span class="fin-kind">· %s</span></h3>'
            '<ul class="fin-terms">%s</ul>%s<p class="fin-lender">%s: %s</p></li>') % (
        _accent(partner), logo, escape(partner['name']), escape(finance.KINDS[partner['kind']][lang]), terms,
        _action(lang, partner), escape(lender), escape(partner['lender'][lang]))


def _highlight(lang, partner):
    """The partner's key condition, highlighted above the cards (when the partner has one)."""
    if 'highlight' not in partner[lang]:
        return ''
    title, text = partner[lang]['highlight']
    return '<div class="fin-highlight"%s><b>%s</b><p>%s</p></div>' % (_accent(partner), escape(title), escape(text))


def _widget(partner):
    """The partner's calculator, the partner's own embed code (it draws itself where its script stands)."""
    widget = partner.get('widget')
    if not widget:
        return ''
    return ('<div class="fin-widget" style="--h-desktop:%dpx;--h-mobile:%dpx">'
            '<script defer src="%s" data-key="%s" data-height-desktop="%d" data-height-mobile="%d"></script></div>') % (
        widget['desktop'], widget['mobile'], escape(widget['src'], quote=True), escape(widget['key'], quote=True),
        widget['desktop'], widget['mobile'])


def _section(lang, kind, anchor, text, partners):
    highlights = ''.join(_highlight(lang, p) for p in partners)
    cards = ''.join(_card(lang, p, text['lender']) for p in partners)
    widgets = ''.join(_widget(p) for p in partners)
    steps = ''.join('<li>%s</li>' % escape(step) for step in text['steps'])
    return ('<section class="fin-section" id="%s" aria-labelledby="%s-h"><h2 id="%s-h">%s</h2><p class="fin-lead">%s</p>%s'
            '<ul class="fin-list">%s</ul>%s<h3>%s</h3><ol class="fin-steps">%s</ol></section>') % (
        anchor, anchor, anchor, escape(text['h2']), escape(text['lead']), highlights, cards, widgets,
        escape(text['how']), steps)


def _compare(table):
    head = ''.join('<th scope="col">%s</th>' % escape(cell) for cell in table['head'])
    rows = ''.join('<tr><th scope="row">%s</th>%s</tr>' % (escape(row[0]), ''.join('<td>%s</td>' % escape(c) for c in row[1:]))
                   for row in table['rows'])
    return '<h2>%s</h2><div class="fin-compare"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (
        escape(table['h2']), head, rows)


def _offer(lang, partner, page_url, anchor):
    kind = finance.KINDS[partner['kind']][lang]
    return {'@type': 'LoanOrCredit', '@id': '%s#%s' % (page_url, partner['id']),
            'name': '%s — %s' % (kind, partner['name']), 'loanType': kind, 'url': '%s#%s' % (page_url, anchor),
            'areaServed': 'UA', 'provider': {'@type': partner['org'], 'name': partner['name'], 'url': partner['site']}}


def page(lang, home, home_url, page_url):
    """{'title', 'desc', 'h1', 'body', 'head'} of the finance page in lang (uk or ru)."""
    text = finance.PAGE[lang]
    sections = [(kind, anchor, [p for p in finance.PARTNERS if p['kind'] == kind]) for kind, anchor in finance.SECTIONS]
    sections = [item for item in sections if item[2]]
    jump = ''.join('<a href="#%s">%s</a>' % (anchor, escape(finance.KINDS[kind][lang])) for kind, anchor, _ in sections)
    body = ('<p class="fin-intro">%s</p><nav class="fin-jump" aria-label="%s">%s</nav>%s<p class="fin-note">%s</p>%s'
            '<h2>%s</h2>%s<p><a href="/video/katalog.html">%s</a> · <a href="/video/podbor.html">%s</a></p>') % (
        escape(text['intro']), escape(text['jump'], quote=True), jump,
        ''.join(_section(lang, kind, anchor, text['sections'][kind], partners) for kind, anchor, partners in sections),
        escape(text['note']), _compare(text['compare']), escape(text['faq_h2']),
        ''.join('<h3>%s</h3><p>%s</p>' % (escape(q), escape(a)) for q, a in text['faq']),
        escape(text['catalog']), escape(text['order']))
    offers = [_offer(lang, p, page_url, anchor) for _, anchor, partners in sections for p in partners]
    ld = schema.script(schema.dealer(lang), schema.breadcrumbs([(home, home_url), (text['crumb'], page_url)]),
                       *offers, schema.faq(list(text['faq'])))
    return {'title': text['title'], 'desc': text['desc'], 'h1': text['h1'], 'body': body,
            'head': '<style>%s</style>%s%s' % (STYLE, ld, ANALYTICS)}
