"""The Korea page first-screen offer (KOREA-OFFER-001, owner «Да» to the mock-up, 2026-11-25).

One block right after <main>: the approved line and a button that opens the page's existing short lead form
(the quick-lead dialog, as the lot buttons do: data-quick-lead-auction="korea", no lot). Texts carry the site's
data-uk/ru/ka twins, so ru/korea.html (rebuilt from korea.html by the installed ua_korea_ru job) gets Russian.
The lead is counted by quick-lead.js (generate_lead) and reaches the CRM bot like every short form.
"""
NAME = 'video/korea.html'
MARK = 'id="ua-korea-offer"'
TEXT = {'uk': 'Авто з Кореї під ключ · послуга 600 $ · договір',
        'ru': 'Авто из Кореи под ключ · услуга 600 $ · договор',
        'ka': 'ავტომობილი კორეიდან სრული მომსახურებით · მომსახურება 600 $ · ხელშეკრულება'}
BUTTON = {'uk': 'Залишити заявку', 'ru': 'Оставить заявку', 'ka': 'განაცხადის დატოვება'}
ANCHOR = '<main id="main-content">'
BOX = ('margin:14px 16px 0;padding:14px 16px;border:1px solid rgba(212,175,55,.55);border-radius:14px;'
       'background:linear-gradient(180deg,rgba(212,175,55,.18),rgba(212,175,55,.06));display:flex;flex-direction:column;'
       'gap:10px;max-width:1148px;box-sizing:border-box')
LINE = 'color:#f4e3ae;font-weight:700;font-size:16px;line-height:1.35'
LINK = ('display:block;text-align:center;padding:13px;border-radius:12px;background:#e8a33d;color:#111;font-weight:800;'
        'text-decoration:none;font-size:16px')


def langs(values):
    return ' '.join('data-%s="%s"' % (lang, values[lang]) for lang in ('uk', 'ru', 'ka'))


def block():
    return ('<div %s style="%s"><div style="%s" %s>%s</div>'
            '<a href="#" data-quick-lead-auction="korea" data-quick-lead-title="" style="%s" %s>%s</a></div>'
            % (MARK, BOX, LINE, langs(TEXT), TEXT['uk'], LINK, langs(BUTTON), BUTTON['uk']))


def build(value):
    source = value.decode('utf-8')
    if MARK in source:
        raise ValueError('OFFER_ALREADY_THERE')
    if source.count(ANCHOR) != 1 or source.count('<dialog class="ua-quick-dialog"') != 1:
        raise ValueError('KOREA_LAYOUT')
    return source.replace(ANCHOR, ANCHOR + block(), 1).encode('utf-8')
