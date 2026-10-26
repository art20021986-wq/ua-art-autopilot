"""Markup of the home page AUTO.RIA reviews block and footer badge (AUTORIA-REVIEWS-001).

Owner-approved 2026-10-26. Pure functions of reviews_data: no page parsing here. Texts carry data-ru/data-uk
for the home language switch (Georgian falls back to Ukrainian there); reviews stay verbatim in Ukrainian.
"""
from html import escape

import reviews_data as data

MARK = 'ua-autoria-reviews-001'
LOGO = '/video/brand/autoria-logo.svg'
LINK = 'href="%s" target="_blank" rel="noopener noreferrer"' % escape(data.DEALER_URL)

CSS = '''<style id="%s">
.ua-reviews p{margin:0}
.ua-reviews h2{margin:6px 0 8px}
.ua-reviews-lead{color:var(--muted);font-size:15px;line-height:1.5;max-width:720px}
.ua-reviews-stats{list-style:none;margin:18px 0 0;padding:0;display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.ua-reviews-stats li{padding:14px 10px;border:1px solid #314862;border-radius:14px;background:rgba(7,17,30,.6);text-align:center}
.ua-reviews-stats b{display:block;color:var(--gold);font-size:28px;line-height:1.1}
.ua-reviews-stats span{color:#9fb0c4;font-size:12px;line-height:1.3}
.ua-reviews-list{margin:14px 0 0;display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.ua-review{margin:0;padding:16px;border:1px solid #314862;border-radius:14px;background:var(--card);display:flex;flex-direction:column;gap:8px}
.ua-review-stars{color:var(--gold);letter-spacing:2px}
.ua-review blockquote{margin:0;color:#dce4ef;font-size:14px;line-height:1.5;flex:1}
.ua-review figcaption{color:#9fb0c4;font-size:12px}
.ua-reviews-button{margin-top:16px;display:flex;align-items:center;justify-content:center;gap:12px;min-height:56px;padding:8px 16px;border-radius:14px;background:#fff;color:#0d2a4a;font-weight:800;font-size:15px;text-decoration:none}
.ua-reviews-button img,.ua-autoria-badge img{display:block;height:30px;width:auto}
.ua-reviews-note{margin-top:8px!important;color:#9fb0c4;font-size:12px;text-align:center}
.ua-autoria-badge{margin-top:16px;display:inline-flex;align-items:center;gap:10px;padding:7px 12px;border-radius:10px;background:#fff;color:#0d2a4a;font-size:13px;font-weight:700;text-decoration:none}
@media (max-width:700px){
.ua-reviews-stats{gap:8px}
.ua-reviews-stats b{font-size:22px}
.ua-reviews-stats span{font-size:11px}
.ua-reviews-list{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;margin-right:-16px;padding-right:16px}
.ua-review{flex:0 0 84%%;scroll-snap-align:start}
}
</style>''' % MARK


def _attrs(ru, uk):
    return 'data-ru="%s" data-uk="%s">%s' % (escape(ru), escape(uk), escape(uk))


def _logo(height):
    return '<img src="%s" alt="AUTO.RIA" width="%d" height="%d" loading="lazy" decoding="async">' % (
        LOGO, round(height * 135 / 40), height)


def _review(author, date, stars, text):
    return ('<figure class="ua-review"><div class="ua-review-stars" role="img" aria-label="%d / 5">%s</div>'
            '<blockquote lang="uk">«%s»</blockquote><figcaption>%s · %s</figcaption></figure>'
            % (stars, '★' * stars, escape(text), escape(author), escape(date)))


def block():
    stats = ''.join('<li><b>%s</b><span %s</span></li>' % (escape(number), _attrs(ru, uk)) for number, ru, uk in data.STATS)
    reviews = ''.join(_review(*review) for review in data.REVIEWS)
    return ('<section class="ua-reviews section-frame" id="vidguky">'
            '<span class="section-kicker" %s</span><h2 %s</h2><p class="ua-reviews-lead" %s</p>'
            '<ul class="ua-reviews-stats">%s</ul><div class="ua-reviews-list">%s</div>'
            '<a class="ua-reviews-button" %s><span %s</span>%s</a><p class="ua-reviews-note" %s</p></section>'
            % (_attrs('ОТЗЫВЫ И ИСТОРИЯ ПРОДАЖ', 'ВІДГУКИ ТА ІСТОРІЯ ПРОДАЖІВ'),
               _attrs('Проверьте нас на AUTO.RIA', 'Перевірте нас на AUTO.RIA'),
               _attrs('Отзывы там оставляют покупатели, мы не можем их изменить или удалить. '
                      'Там же — все авто, которые мы уже продали.',
                      'Відгуки там залишають покупці, ми не можемо їх змінити чи видалити. '
                      'Там же — всі авто, які ми вже продали.'),
               stats, reviews, LINK, _attrs('Все отзывы и проданные авто', 'Усі відгуки та продані авто'), _logo(30),
               _attrs('Откроется наша страница на AUTO.RIA', 'Відкриється наша сторінка на AUTO.RIA')))


def badge():
    return '<a class="ua-autoria-badge" %s><span %s</span>%s</a>' % (LINK, _attrs('Мы на', 'Ми на'), _logo(26))
