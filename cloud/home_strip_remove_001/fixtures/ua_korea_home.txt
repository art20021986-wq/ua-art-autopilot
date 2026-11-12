"""JPAUTO-KOREA-001: home page additions (owner 2026-11-10).

apply(html) on the home page (the «Авто під замовлення» hero with the country flags):
  1. under the Korea flag — the «● Аукціони онлайн» mark;
  2. the Korea flag leads to the Korea online auctions page (korea.html) instead of the selection form;
  3. right after the hero — the slot of the Korea auction ticker. The ticker itself is a separate
     file (/video/korea/ticker.html) refreshed 3 times a day; a tiny loader inserts it, and the slot
     stays empty (invisible) if the file is missing;
  4. the page order (owner 2026-11-10): «Аукціони онлайн» block, the ticker, the hero (individual order:
     its button reads «Індивідуальне замовлення»), cars in stock (#stages), then the remaining blocks.
     Applied only to the known structure; any other structure keeps its order;
  5. the hero has no «Написати в Telegram» button; the auctions block button reads «Дивитися аукціони»;
     the hero photo stands on its own right above the cars in stock (owner 2026-11-10).
Each addition is applied once and independently (a page from an earlier version gets the missing ones);
remove() takes all of them back. Any other page is returned unchanged.
"""
MARK = '<!--UA-KOREA-AUCTION-V1-->'
FLAG = '<a href="podbor.html?strana=korea'
HERO = '<section class="hero ua-order-first">'
TICKER_SRC = '/video/korea/ticker.html'
FLAG_FROM = '<a href="podbor.html?strana=korea&amp;lang=uk" data-order-country="korea">'
FLAG_TO = '<a href="korea.html" data-order-country="korea" data-ua-kr-flag="1">'

BADGE = ('<span class="ua-kr-live" data-uk="● Аукціони онлайн" data-ru="● Аукционы онлайн" '
         'data-ka="● აუქციონები ონლაინ">● Аукціони онлайн</span>')
STYLE = ('<style id="ua-korea-auction-v1">'
         '.ua-kr-live{display:block;margin-top:4px;font-size:12px;font-weight:700;color:#ff4d4d;'
         'text-align:center;white-space:nowrap;animation:ua-kr-blink 1.6s ease-in-out infinite}'
         '@keyframes ua-kr-blink{50%{opacity:.45}}'
         '@media (max-width:600px){.ua-kr-live{white-space:normal;font-size:10px;line-height:1.15;'
         'text-align:center}}'
         '@media (prefers-reduced-motion:reduce){.ua-kr-live{animation:none}}'
         '#ua-korea-ticker:empty{display:none}</style>')
SLOT = ('<div id="ua-korea-ticker"></div><script>(function(){var s=document.getElementById(\'ua-korea-ticker\');'
        'fetch(\'' + TICKER_SRC + '\',{cache:\'no-cache\'}).then(function(r){return r.ok?r.text():\'\';})'
        '.then(function(h){if(!h)return;var t=document.createElement(\'template\');t.innerHTML=h;'
        't.content.querySelectorAll(\'script\').forEach(function(o){var n=document.createElement(\'script\');'
        'n.textContent=o.textContent;o.replaceWith(n);});s.appendChild(t.content);})'
        '.catch(function(){});})();</script>')
LAYOUT = '<!--UA-HOME-ORDER-V1-->'
MAIN = '<main id="main-content">'
STAGES = '<section id="stages"'
PICK_FROM = ('<a class="button gold" href="podbor.html" data-ru="Подобрать авто" data-uk="Підібрати авто" '
             'data-ka="ავტომობილის შერჩევა">Підібрати авто</a>')
PICK_TO = ('<a class="button gold" href="podbor.html" data-ru="Индивидуальный заказ" data-uk="Індивідуальне замовлення" '
           'data-ka="ინდივიდუალური შეკვეთა">Індивідуальне замовлення</a>')

TELEGRAM = ('<a class="button ua-write" href="https://t.me/UA_artcompany_LLC_bot" target="_blank" '
            'rel="noopener noreferrer" data-ru="Написать в Telegram" data-uk="Написати в Telegram" '
            'data-ka="მოგვწერეთ Telegram-ში">Написати в Telegram</a>')


def _t(tag, uk, ru, ka, attrs=''):
    return '<%s%s data-uk="%s" data-ru="%s" data-ka="%s">%s</%s>' % (tag, attrs, uk, ru, ka, uk, tag)


AUCTIONS = (
    LAYOUT + '<section class="ua-kr-auc"><style>'
    '.ua-kr-auc{padding:22px 20px 16px;background:linear-gradient(135deg,#1a0f00,#0B1524 60%);'
    'border-bottom:1px solid #2a3a52}'
    '.ua-kr-auc .ey{color:#ff5a5a;font-weight:800;letter-spacing:.14em;font-size:13px;text-transform:uppercase}'
    '.ua-kr-auc h2{color:#fff;font-size:clamp(24px,4vw,40px);margin:8px 0 6px}'
    '.ua-kr-auc p{color:#c9d3e0;margin:0 0 14px;max-width:760px}'
    '.ua-kr-auc a.go{display:inline-block;padding:14px 26px;border-radius:12px;font-weight:800;color:#111;'
    'text-decoration:none;background:linear-gradient(90deg,#ffd000,#ff8a00)}'
    '@media(min-width:900px){.ua-kr-auc{padding:34px 60px 24px}}</style>'
    + _t('div', '● Аукціони онлайн · Корея · незабаром Японія', '● Аукционы онлайн · Корея · скоро Япония',
         '● აუქციონები ონლაინ · კორეა · მალე იაპონია', ' class="ey"')
    + _t('h2', 'Авто з аукціонів Кореї — нові лоти щодня', 'Авто с аукционов Кореи — новые лоты каждый день',
         'ავტომობილები კორეის აუქციონებიდან — ახალი ლოტები ყოველდღე')
    + _t('p', 'Лоти завтрашніх торгів, ціни в Кореї та курс НБУ. Купуємо за договором під ваш бюджет.',
         'Лоты завтрашних торгов, цены в Корее и курс НБУ. Покупаем по договору под ваш бюджет.',
         'ხვალინდელი ვაჭრობის ლოტები, ფასები კორეაში და ეროვნული ბანკის კურსი. '
         'ვყიდულობთ ხელშეკრულებით თქვენს ბიუჯეტზე.')
    + _t('a', 'Дивитися онлайн', 'Смотреть онлайн', 'ონლაინ ნახვა', ' class="go" href="korea.html"')
    + '</section>')


# The home blocks inside <main>, each found by how it starts; a block runs up to the next one.
BLOCKS = {'auctions': LAYOUT, 'ticker': MARK, 'hero': HERO, 'advantages': '<section class="confidence-strip',
          'steps': '<section class="ua-how', 'reviews': '<section class="ua-reviews', 'stages': STAGES}
ORIGINAL = ('hero', 'ticker', 'advantages', 'steps', 'reviews', 'stages')  # the page as the CRM writes it
# The page order (owner 2026-11-10). To move blocks, change only this line.
ORDER = ('auctions', 'ticker', 'hero', 'stages', 'advantages', 'steps', 'reviews')


def _blocks(html):
    """(start, end, {name: text}) of <main>, or None when the page is not the known structure."""
    if html.count(MAIN) != 1:
        return None
    start = html.index(MAIN) + len(MAIN)
    end = html.index('</main>', start)
    body = html[start:end]
    if any(body.count(mark) > 1 for mark in BLOCKS.values()):
        return None
    found = sorted((body.index(mark), name) for name, mark in BLOCKS.items() if mark in body)
    if not found or found[0][0] != 0:
        return None
    bounds = [i for i, _ in found] + [len(body)]
    return start, end, {name: body[bounds[n]:bounds[n + 1]] for n, (_, name) in enumerate(found)}


def _arrange(html, order, extra=None):
    """The page with its blocks in `order` (every block of the page must be named there)."""
    found = _blocks(html)
    if found is None:
        return html
    start, end, blocks = found
    blocks.update(extra or {})
    if set(blocks) != set(order):
        return html
    return html[:start] + ''.join(blocks[name] for name in order) + html[end:]


def _ordered(html):
    """Original order -> ORDER with the auctions block; the hero button reads «Індивідуальне замовлення»."""
    if LAYOUT in html:
        return html
    new = _arrange(html, ORDER, {'auctions': AUCTIONS})
    return new if new is html else new.replace(PICK_FROM, PICK_TO, 1)


def _unordered(html):
    """Inverse of _ordered (the page keeps the mark, flag link and ticker slot)."""
    html = _photo_back(html).replace(GO_TO, GO_FROM, 1)
    found = _blocks(html) if LAYOUT in html else None
    if found is None:
        return html
    blocks = found[2]
    if blocks.get('auctions') != AUCTIONS:
        return html
    new = _arrange(html.replace(AUCTIONS, '', 1), ORIGINAL)
    return new.replace(PICK_TO, PICK_FROM + ('' if PICK_TO + TELEGRAM in new else TELEGRAM), 1)


GO_FROM = _t('a', 'Дивитися онлайн', 'Смотреть онлайн', 'ონლაინ ნახვა', ' class="go" href="korea.html"')
GO_TO = _t('a', 'Дивитися аукціони', 'Смотреть аукционы', 'აუქციონების ნახვა', ' class="go" href="korea.html"')


PHOTO = '<!--UA-HOME-PHOTO-V1--><div class="ua-home-photo">'
PHOTO_END = '</div><!--/UA-HOME-PHOTO-V1-->'
PHOTO_STYLE = ('<style id="ua-home-photo-v1">.ua-home-photo{display:flex;justify-content:center;background:#060f1b}'
               '.ua-home-photo picture{display:block;width:100%;max-width:885px}'
               '.ua-home-photo img{display:block;width:100%;height:auto}'
               '.ua-order-first:not(:has(>picture)){display:block}'
               '.ua-order-first:not(:has(>picture)) .ua-order-shade{display:none}</style>')


def _photo_moved(html):
    """The hero photo as its own block right before the cars in stock (#stages)."""
    if PHOTO in html or LAYOUT not in html or html.count(STAGES) != 1 or HERO not in html:
        return html
    hero = html.index(HERO) + len(HERO)
    if not html.startswith('<picture>', hero):
        return html
    end = html.index('</picture>', hero) + len('</picture>')
    picture = html[hero:end]
    html = html[:hero] + html[end:]
    at = html.index(STAGES)
    return html[:at] + PHOTO + PHOTO_STYLE + picture + PHOTO_END + html[at:]


def _photo_back(html):
    if PHOTO not in html:
        return html
    start = html.index(PHOTO)
    end = html.index(PHOTO_END, start) + len(PHOTO_END)
    picture = html[start + len(PHOTO) + len(PHOTO_STYLE):end - len(PHOTO_END)]
    html = html[:start] + html[end:]
    hero = html.index(HERO) + len(HERO)
    return html[:hero] + picture + html[hero:]


def _without_telegram(html):
    """The ordered page: no Telegram button in the hero (it follows the individual order button), the auctions
    block button reads «Дивитися аукціони»."""
    if LAYOUT not in html:
        return html
    return html.replace(PICK_TO + TELEGRAM, PICK_TO, 1).replace(GO_FROM, GO_TO, 1)


def apply(html):
    """Home page with the Korea mark, flag link and ticker slot; anything else unchanged."""
    if not isinstance(html, str) or HERO not in html or (FLAG not in html and FLAG_TO not in html):
        return html
    if html.count(FLAG_FROM) == 1:
        html = html.replace(FLAG_FROM, FLAG_TO)
    if BADGE not in html:
        start = html.index(FLAG_TO) if FLAG_TO in html else html.index(FLAG)
        end_a = html.index('</a>', start)
        html = html[:end_a] + BADGE + html[end_a:]
    if MARK not in html:
        hero = html.index(HERO)
        end_hero = html.index('</section>', hero) + len('</section>')
        html = html[:end_hero] + MARK + STYLE + SLOT + html[end_hero:]
    return _photo_moved(_without_telegram(_ordered(html)))


def remove(html):
    """The page without this release's additions (rollback of a home page another writer rewrote since)."""
    html = _unordered(html)
    return html.replace(MARK + STYLE + SLOT, '', 1).replace(BADGE, '', 1).replace(FLAG_TO, FLAG_FROM, 1)
