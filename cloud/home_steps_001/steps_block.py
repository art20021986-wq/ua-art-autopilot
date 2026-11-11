"""Markup of steps 2–5 in the home «5 кроків» block (ORDER-PROCESS-001, owner 2026-11-11): country switcher, Korea
steps, other-countries note, signature, CSS and the switcher script. No page parsing here.

Every text element holds its three languages in data-ru / data-uk / data-ka with the Ukrainian text inside (one text
node per element), as the site's language script expects. Numbers are separate elements without language data, so
kr_prices can update them. The Korea steps are shown by default; the switcher shows the other countries' steps
(the ones already on the page, marked data-ua-for="other") with a note instead.
"""
import kr_prices
import steps_text as T

MARK = 'ua-home-steps-001'
FORM = 'podbor.html#zayavka'


def text(tag, words, cls='', extra=''):
    ru, uk, ka = words
    for value in words:
        if any(c in value for c in '<>"&'):
            raise ValueError('HOME_STEPS_TEXT')
    return '<%s%s%s data-ru="%s" data-uk="%s" data-ka="%s">%s</%s>' % (
        tag, ' class="%s"' % cls if cls else '', extra, ru, uk, ka, uk, tag)


def num(key):
    return '<span class="ua-kr-n" %s="%s">%s</span>' % (kr_prices.ATTR, key, kr_prices.initial(key))


def usd(key):
    return num(key) + T.USD


def switcher():
    ru, uk, ka = T.SWITCH_LABEL
    buttons = ''.join(
        '<button type="button" data-ua-country="%s" aria-pressed="%s" data-ru="%s" data-uk="%s" data-ka="%s">%s'
        '</button>' % (key, 'true' if key == 'korea' else 'false', c_ru, c_uk, c_ka, c_uk)
        for key, c_ru, c_uk, c_ka in T.COUNTRIES)
    return ('<div class="ua-cc" role="group" aria-label="%s" data-ru-aria="%s" data-uk-aria="%s" data-ka-aria="%s">'
            '%s</div>' % (uk, ru, uk, ka, buttons))


def _step(number, title, short, body):
    return ('<li class="ua-kr-step" data-ua-for="korea"><i>%d</i>%s%s<details class="ua-step-more">%s<div>%s</div>'
            '</details></li>' % (number, text('b', title), short, text('summary', T.MORE), body))


def _note(words, cls='ua-kr-note'):
    return text('p', words, cls)


def step2():
    body = (''.join(text('p', line) for line in T.S2_LINES) + text('p', T.S2_PAY, 'ua-step-pay')
            + text('p', T.S2_AFTER) + text('p', T.S2_TOTAL, 'ua-step-pay') + _note(T.S2_DEPOSIT))
    return _step(2, T.S2_TITLE, text('small', T.S2_SHORT), body)


def _item(key, unit, title, lines, note):
    head = '<strong>%s — %s%s</strong>' % (text('span', title), usd(key), ' ' + text('span', unit) if unit else '')
    if key in T.BULLETED:
        body = '<ul>%s</ul>' % ''.join(text('li', line) for line in lines)
    else:
        body = ''.join(text('p', line) for line in lines)
    if key == 'container':
        body += '<p>%s %s</p>' % (text('span', T.CONTAINER_SHARE), usd('car_container'))
    if note:
        title_words, words = note
        body += '<div class="ua-kr-note">%s%s</div>' % (text('strong', title_words) if title_words else '',
                                                        text('p', words))
    return '<li>%s%s</li>' % (head, body)


def step3():
    short = '<small>%s · %s</small>' % (usd('total'), text('span', T.S3_SHORT))
    body = ('<p>%s <strong>%s</strong> %s</p>' % (text('span', T.S3_LEAD), usd('total'), text('span', T.S3_RATE))
            + '<p>%s %s</p>' % (text('span', T.S3_MONTH), num('month'))
            + text('p', T.S3_INCLUDES)
            + '<ol class="ua-kr-list">%s</ol>' % ''.join(_item(*item) for item in T.S3_ITEMS)
            + _note(T.S3_FIXED, 'ua-kr-note ua-kr-key') + text('p', T.S3_CAR) + _note(T.S3_OPEN))
    return _step(3, T.S3_TITLE, short, body)


def step4():
    stages = ''.join('<li>%s %s</li>' % (text('strong', title), text('span', words)) for title, words in T.S4_STAGES)
    return _step(4, T.S4_TITLE, text('small', T.S4_SHORT), '<ol class="ua-kr-list">%s</ol>' % stages)


def step5():
    return _step(5, T.S5_TITLE, text('small', T.S5_SHORT), _note(T.S5_DUTY) + text('p', T.S5_PARKING))


def korea_steps():
    return step2() + step3() + step4() + step5()


def other_note():
    ru, uk, ka = T.BUTTON
    return ('<div class="ua-cc-other" data-ua-for="other" hidden>%s<a class="button gold" href="%s" data-ru="%s" '
            'data-uk="%s" data-ka="%s">%s</a></div>' % (text('p', T.OTHER_NOTE), FORM, ru, uk, ka, uk))


def signature():
    first, team, line = T.SIGN
    return '<p class="ua-steps-sign">%s%s%s</p>' % (text('span', first), text('strong', team), text('span', line))


# Switcher: the pressed country decides which steps are shown; Korea is the page's default.
SWITCH_SCRIPT = ("<script>document.addEventListener('click',function(e){var b=e.target.closest&&"
                 "e.target.closest('.ua-cc [data-ua-country]');if(!b)return;var s=b.closest('.ua-how'),"
                 "k=b.getAttribute('data-ua-country')==='korea';"
                 "s.querySelectorAll('.ua-cc [data-ua-country]').forEach(function(x){"
                 "x.setAttribute('aria-pressed',String(x===b));});"
                 "s.querySelectorAll('[data-ua-for]').forEach(function(n){"
                 "n.hidden=(n.getAttribute('data-ua-for')==='korea')!==k;});});</script>")

CSS = ('<style id="%s">'
       '.ua-how [hidden]{display:none!important}'
       '.ua-cc{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 14px;margin:14px 0 0}'
       '.ua-cc button{font:inherit;font-size:14px;font-weight:600;color:#9fb0c4;background:none;border:0;'
       'border-bottom:2px solid transparent;padding:8px 2px;min-height:44px;cursor:pointer}'
       '.ua-cc button[data-ua-country="korea"]{font-size:22px;font-weight:800;color:var(--gold)}'
       '.ua-cc button[aria-pressed="true"]{color:var(--gold);border-bottom-color:var(--gold)}'
       '.ua-cc button:focus-visible{outline:2px solid var(--gold);outline-offset:3px;border-radius:6px}'
       '.ua-how li:has(>details[open]){grid-column:1/-1}'
       '.ua-kr-n{font-weight:800;color:#fff;white-space:nowrap}'
       '.ua-step-more strong{color:#fff}'
       '.ua-how .ua-step-more li{display:list-item;padding:0;border:0;border-radius:0;background:none;'
       'font-size:16px;line-height:1.6;color:#e6edf5}'
       '.ua-how .ua-kr-list{list-style:decimal;margin:0;padding-left:22px;display:grid;gap:14px}'
       '.ua-how .ua-kr-list>li::marker{color:var(--gold);font-weight:800}'
       '.ua-how .ua-kr-list ul{list-style:disc;margin:4px 0 0;padding-left:20px}'
       '.ua-step-more .ua-kr-list p{margin:4px 0 0}'
       '.ua-step-more .ua-kr-note{margin:8px 0 0;padding:12px 14px;border-left:3px solid var(--gold);'
       'border-radius:10px;background:rgba(232,163,61,.12);color:#f5dfb5}'
       '.ua-step-more .ua-kr-note p{margin:4px 0 0;color:#f5dfb5}'
       '.ua-step-more .ua-kr-note strong{color:var(--gold)}'
       '.ua-step-more .ua-kr-key{font-weight:800;color:var(--gold)}'
       '.ua-cc-other{display:grid;gap:10px;justify-items:start;margin:12px 0 0}'
       '.ua-cc-other p{margin:0;font-size:16px;line-height:1.6;color:#e6edf5}'
       '.ua-cc-other .button{min-height:48px;padding:0 22px}'
       '.ua-steps-sign{display:grid;gap:2px;margin:18px 0 0;font-size:15px;line-height:1.5;color:#9fb0c4}'
       '.ua-steps-sign strong{color:var(--gold)}'
       '@media (max-width:700px){.ua-cc-other .button{justify-self:stretch;text-align:center}}'
       '</style>' % MARK)
