"""Render the existing card's tracking control using native HTML disclosure."""
from html import escape
from ua_tracking_links import normalize, reference_kind, tracking_links

START = '<!-- UA-ART-MULTI-TRACKING-001:START -->'
END = '<!-- UA-ART-MULTI-TRACKING-001:END -->'

CSS = '''<style>
.ua-multi-track{width:100%;min-width:0;color:#b9c5d4;font-size:12px;line-height:1.5}
.ua-multi-track *{box-sizing:border-box}.ua-multi-track summary{cursor:pointer;min-height:44px;padding:10px 12px;border:1px solid #715431;border-radius:10px;color:#ffc878;background:#192b40;font-weight:700;overflow-wrap:anywhere}
.ua-multi-track summary b{color:#eef3f8;margin-right:10px;font:inherit}
.ua-multi-track .ua-tracking-panel{padding:12px 0 2px}.ua-multi-track p{margin:6px 0}
.ua-multi-track .ua-tracking-sources{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.ua-multi-track a,.ua-multi-track button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:9px 12px;border:1px solid #52647a;border-radius:9px;color:#ffe0ac;background:#14263c;text-decoration:underline;font:inherit;cursor:pointer;white-space:normal}
.ua-multi-track :is(summary,a,button):focus-visible{outline:2px solid #ffc05a;outline-offset:3px}
.ua-multi-track code{color:#f3f6fb;overflow-wrap:anywhere;user-select:all;font-size:13px}
.ua-multi-track .ua-tracking-number{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.ua-multi-track .ua-tracking-feedback{min-height:1.5em}
.ua-multi-track [hidden]{display:none}
</style>'''

# The click is the clipboard permission gesture. Rejection leaves manual copy
# available, and normal links work even when JavaScript is disabled.
SCRIPT = '''<script>(function(){
var script=document.currentScript,root=script.previousElementSibling;
if(!root||!root.classList.contains('ua-multi-track'))return;
var button=root.querySelector('[data-copy-tracking]');if(!button)return;
button.hidden=false;
button.addEventListener('click',function(){
 var feedback=root.querySelector('[role="status"]');
 var code=root.querySelector('code');
 function say(ok){
  var lang=document.documentElement.lang;
  var messages=ok?{ru:'Номер скопирован',uk:'Номер скопійовано',ka:'ნომერი დაკოპირებულია'}:
   {ru:'Выделите и скопируйте номер выше',uk:'Виділіть і скопіюйте номер вище',ka:'მონიშნეთ და დააკოპირეთ ნომერი ზემოთ'};
  feedback.textContent=messages[lang]||messages.uk;
 }
 if(!navigator.clipboard||!navigator.clipboard.writeText){say(false);return;}
 navigator.clipboard.writeText(code.textContent).then(function(){say(true);},function(){say(false);});
});})();</script>'''


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
    content = [opening, '<details><summary>', label, ': <b>', escape(number), '</b>',
               text('Отследить', 'Відстежити', 'თვალყურის დევნება'), '</summary>',
               '<div class="ua-tracking-panel"><div class="ua-tracking-number"><code translate="no">',
               escape(number), '</code><button type="button" data-copy-tracking hidden>',
               text('Скопировать номер', 'Скопіювати номер', 'ნომრის კოპირება'), '</button></div>',
               '<p class="ua-tracking-feedback" role="status" aria-live="polite"></p>',
               '<div class="ua-tracking-sources">']
    for name, href, mode in tracking_links(number):
        content.append('<a href="%s" target="_blank" rel="noopener noreferrer" data-tracking-mode="%s">%s ↗</a>'
                       % (escape(href, quote=True), mode, escape(name)))
    content.extend(['</div><p>', text(
        'Track-Trace подставит номер. Для SeaRates и ShipsGo скопируйте его выше и вставьте в поиск.',
        'Track-Trace підставить номер. Для SeaRates і ShipsGo скопіюйте його вище та вставте в пошук.',
        'Track-Trace ნომერს ავტომატურად ჩასვამს. SeaRates-ისა და ShipsGo-სთვის დააკოპირეთ ნომერი და ჩასვით ძიებაში.'),
        '</p><p>', text('Если груз не найден, выберите перевозчика в сервисе или другой источник. Сервис может потребовать вход.',
        'Якщо вантаж не знайдено, виберіть перевізника в сервісі або інше джерело. Сервіс може вимагати вхід.',
        'თუ ტვირთი ვერ მოიძებნა, სერვისში აირჩიეთ გადამზიდავი ან სხვა წყარო. შესაძლოა საჭირო იყოს ანგარიშში შესვლა.'),
        '</p></div></details></div>', SCRIPT, END])
    return ''.join(content)
