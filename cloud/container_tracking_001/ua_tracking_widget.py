"""Render a shipment badge and a single native tracking link."""
from html import escape
from ua_tracking_links import normalize, reference_kind, tracking_links

# Keep deployed markers so existing cards can be upgraded idempotently.
START = '<!-- UA-ART-MULTI-TRACKING-001:START -->'
END = '<!-- UA-ART-MULTI-TRACKING-001:END -->'

CSS = '''<style>
.ua-multi-track{width:100%;min-width:0;color:#b9c5d4;font-size:12px;line-height:1.5}
.ua-multi-track *{box-sizing:border-box}
.ua-multi-track .ua-stage-v1-container-row{display:flex;width:100%;justify-content:space-between;gap:8px;white-space:normal}
.ua-multi-track .ua-stage-v1-badge{min-width:0;flex:0 1 auto;white-space:normal;overflow-wrap:anywhere}
.ua-multi-track .ua-stage-v1-track-link{min-width:0;flex:0 1 auto;min-height:44px;white-space:normal;line-height:1.3;text-align:right}
.ua-multi-track p{margin:6px 0}
</style>'''


def text(ru, uk, ka):
    return '<span data-ru="%s" data-uk="%s" data-ka="%s">%s</span>' % (
        escape(ru, quote=True), escape(uk, quote=True), escape(ka, quote=True), escape(ru))


def render_tracking(value):
    number = normalize(value)
    opening = START + CSS + '<div class="ua-multi-track" data-ua-multi-tracking="1">'
    if not number:
        message = text('Номер отправки ещё не указан', 'Номер відправлення ще не вказано',
                       'გზავნილის ნომერი ჯერ არ არის მითითებული') if not value else text(
            'Номер отправки уточняется', 'Номер відправлення уточнюється', 'გზავნილის ნომერი ზუსტდება')
        return opening + '<p>' + message + '</p></div>' + END
    kind = reference_kind(number)
    label = text('Контейнер', 'Контейнер', 'კონტეინერი') if kind == 'container' else (
        'B/L' if kind == 'one_bl' else text('Номер отправки', 'Номер відправлення', 'გზავნილის ნომერი'))
    href = tracking_links(number)[0][1]
    return ''.join([
        opening, '<div class="ua-stage-v1-container-row"><span class="ua-stage-v1-badge">',
        label, ': <b translate="no">', escape(number), '</b></span>',
        '<a class="ua-stage-v1-track-link" href="', escape(href, quote=True),
        '" target="_blank" rel="noopener noreferrer" data-tracking-mode="direct">',
        text('Отследить контейнер', 'Відстежити контейнер', 'კონტეინერის თვალყურის დევნება'),
        '</a></div></div>', END])
