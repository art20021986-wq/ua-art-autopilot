"""Markup of the home page AUTO.RIA reviews block and footer badge (AUTORIA-REVIEWS-001).

Owner-approved 2026-10-26. Pure functions of reviews_data: no page parsing here. Texts carry data-ru/data-uk
/data-ka for the home language switch; reviews stay verbatim in Ukrainian. Clicks are counted by autoria_click.
Release 3 (owner 2026-10-27): no AUTO.RIA logo; a text mark in AUTO.RIA brand colours and font (Roboto, as on auto.ria.com).
"""
from html import escape

import autoria_click
import reviews_data as data

MARK = 'ua-autoria-reviews-001'

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
.ua-autoria-mark{display:inline-flex;border-radius:6px;overflow:hidden;color:#fff;font:700 16px/1 Roboto,Arial,sans-serif}
.ua-autoria-mark span{padding:7px 8px}
.ua-autoria-mark span:first-child{background:#db5c4c}
.ua-autoria-mark span+span{background:#003b56}
.ua-autoria-badge .ua-autoria-mark{font-size:14px}
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


def _attrs(ru, uk, ka):
    return 'data-ru="%s" data-uk="%s" data-ka="%s">%s' % (escape(ru), escape(uk), escape(ka), escape(uk))


def _link(placement):
    return 'href="%s" target="_blank" rel="noopener noreferrer" %s="%s"' % (
        escape(data.DEALER_URL), autoria_click.ATTRIBUTE, placement)


# Not a [data-ru] node: the language switch leaves it as is.
MARK_HTML = '<span class="ua-autoria-mark"><span>AUTO</span><span>.RIA</span></span>'


def _review(author, date, stars, text):
    return ('<figure class="ua-review"><div class="ua-review-stars" role="img" aria-label="%d / 5">%s</div>'
            '<blockquote lang="uk">«%s»</blockquote><figcaption>%s · %s</figcaption></figure>'
            % (stars, '★' * stars, escape(text), escape(author), escape(date)))


def block():
    stats = ''.join('<li><b>%s</b><span %s</span></li>' % (escape(number), _attrs(ru, uk, ka)) for number, ru, uk, ka in data.STATS)
    reviews = ''.join(_review(*review) for review in data.REVIEWS)
    return ('<section class="ua-reviews section-frame" id="vidguky">'
            '<span class="section-kicker" %s</span><h2 %s</h2><p class="ua-reviews-lead" %s</p>'
            '<ul class="ua-reviews-stats">%s</ul><div class="ua-reviews-list">%s</div>'
            '<a class="ua-reviews-button" %s><span %s</span>%s</a><p class="ua-reviews-note" %s</p>%s</section>'
            % (_attrs('ОТЗЫВЫ И ИСТОРИЯ ПРОДАЖ', 'ВІДГУКИ ТА ІСТОРІЯ ПРОДАЖІВ', 'შეფასებები და გაყიდვების ისტორია'),
               _attrs('Проверьте нас на AUTO.RIA', 'Перевірте нас на AUTO.RIA', 'შეგვამოწმეთ AUTO.RIA‑ზე'),
               _attrs('Отзывы там оставляют покупатели, мы не можем их изменить или удалить. '
                      'Там же — все авто, которые мы уже продали.',
                      'Відгуки там залишають покупці, ми не можемо їх змінити чи видалити. '
                      'Там же — всі авто, які ми вже продали.',
                      'შეფასებებს იქ მყიდველები ტოვებენ, ჩვენ მათ ვერ შევცვლით და ვერ წავშლით. '
                      'იქვეა ყველა ავტომობილი, რომელიც უკვე გავყიდეთ.'),
               stats, reviews, _link(autoria_click.BLOCK),
               _attrs('Все отзывы и проданные авто', 'Усі відгуки та продані авто', 'ყველა შეფასება და გაყიდული ავტომობილი'),
               MARK_HTML,
               _attrs('Откроется наша страница на AUTO.RIA', 'Відкриється наша сторінка на AUTO.RIA',
                      'გაიხსნება ჩვენი გვერდი AUTO.RIA‑ზე'),
               autoria_click.SCRIPT))


def badge():
    return '<a class="ua-autoria-badge" %s><span %s</span>%s</a>' % (
        _link(autoria_click.BADGE), _attrs('Мы на', 'Ми на', 'გვიპოვეთ'), MARK_HTML)
