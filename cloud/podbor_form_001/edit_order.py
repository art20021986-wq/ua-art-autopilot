"""Order page: centred other-car button and the other-car form open by default (PODBOR-FORM-001).

Owner request 2026-10-25 («Да+2»: the Ukrainian button text becomes «Обрати інше авто»,
which browser translators render as «другое», not «второй»). The form setup of selectModel moves into openForm (no scroll);
selectModel keeps the scroll, so a click on the button only brings the open form into
view. openDefaultForm opens the other-car form whenever a country is shown and nothing
else is chosen: after the first load (and draft restore), a country click, back/forward
and a new request. Page asset versions are raised so browsers load the new files.
Each original fragment must occur exactly once and an applied fragment is refused.
"""

PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STYLE = 'video/order/order.css'
STRINGS = 'video/order/order-strings.json'

EDITS = {
    PAGE: (
        ('order/order.css?v=20260927.10', 'order/order.css?v=20261025.2'),
        ('order/order.js?v=20261025.1', 'order/order.js?v=20261025.2'),
        ('data-label="other_choose">Обрати інший автомобіль</button>',
         'data-label="other_choose">Обрати інше авто</button>'),
    ),
    SCRIPT: (
        ("function selectModel(key) {\n  if(state.busy||state.receipt||state.pending) return;\n",
         "function openForm(key) {\n  if(state.busy||state.receipt||state.pending) return false;\n"),
        ("  $('pref-notice').hidden=!key;\n  form.scrollIntoView(",
         "  $('pref-notice').hidden=!key;\n  return true;\n}\n"
         "// The other-car form stays open under the models while nothing else is chosen.\n"
         "function openDefaultForm() {\n  if(state.country&&form.hidden&&!state.model&&!state.review) openForm('');\n}\n"
         "function selectModel(key) {\n  if(!openForm(key)) return;\n  form.scrollIntoView("),
        ("      state.country=code;setUrl();render();\n",
         "      state.country=code;setUrl();render();openDefaultForm();\n"),
        ("$('receipt').hidden=true;render();persist();\n});",
         "$('receipt').hidden=true;render();openDefaultForm();persist();\n});"),
        ("  if(state.review) state.review.lang=state.lang;\n  render();\n});",
         "  if(state.review) state.review.lang=state.lang;\n  render();openDefaultForm();\n});"),
        ("render();\n  }\n} catch {form.hidden=true;",
         "render();\n  }\n  openDefaultForm();\n} catch {form.hidden=true;"),
    ),
    STYLE: (
        ('.ua-order .secondary { background:transparent; color:#f4f5f7; border-color:#728292; }\n',
         '.ua-order .secondary { background:transparent; color:#f4f5f7; border-color:#728292; }\n'
         '.ua-order #other-model { display:block; margin:0 auto 18px; }\n'),
    ),
    STRINGS: (
        ('"other_choose": "Обрати інший автомобіль",', '"other_choose": "Обрати інше авто",'),
    ),
}
# Public proof that each file is live.
CHECK_PAGE = 'order/order.js?v=20261025.2'
CHECK_SCRIPT = 'function openDefaultForm()'
CHECK_STYLE = '.ua-order #other-model { display:block; margin:0 auto 18px; }'
CHECK_STRINGS = '"other_choose": "Обрати інше авто"'


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
