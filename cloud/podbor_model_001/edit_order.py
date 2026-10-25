"""Order page: a link with ?model=<key> opens the form with that model chosen (PODBOR-MODEL-001).

Owner request 2026-10-25: the «Підібрати» button of a model page chooses that model.
Built on top of PODBOR-FORM-001 (order.js?v=20261025.2), which is installed first.
order-state.js gets the pure modelFromUrl (only a model of the chosen country counts);
order.js chooses it after the first render, exactly as a click on the model would, and
an explicit model link wins over an older unsent draft, as a country link already does.
A country click drops the model from the address. order.js imports order-state.js with
a version and the page raises the order.js version, so browsers never mix old and new
modules. Each original fragment must occur exactly once and an applied fragment is refused.
"""

PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STATE = 'video/order/order-state.js'
VERSION = '20261025.3'

EDITS = {
    PAGE: (
        ('order/order.js?v=20261025.2', 'order/order.js?v=' + VERSION),
    ),
    SCRIPT: (
        ("import {languages, fromUrl} from './order-state.js';",
         "import {languages, fromUrl, modelFromUrl} from './order-state.js?v=" + VERSION + "';"),
        ("  url.searchParams.set('lang',state.lang);\n",
         "  url.searchParams.set('lang',state.lang);\n  url.searchParams.delete('model');\n"),
        ("  render();message('');\n",
         "  render();message('');\n"
         "  const preselected=modelFromUrl(location.href,state.catalog.countries[state.country]?.models);\n"
         "  if(preselected) selectModel(preselected);\n"),
        ("        // drafts yield to an explicit incoming country link.\n"
         "        if(saved.pending || !state.country || state.country===saved.country) {\n",
         "        // drafts yield to an explicit incoming country or model link.\n"
         "        if(saved.pending || (!preselected && (!state.country || state.country===saved.country))) {\n"),
    ),
    STATE: (
        ("export function changeCountry(data, country) {\n",
         "// The model of a ?model= link, only when the chosen country offers it.\n"
         "export function modelFromUrl(href, models) {\n"
         "  const key = new URL(href).searchParams.get('model');\n"
         "  return (models || []).some(model => model.key === key) ? key : '';\n"
         "}\n"
         "export function changeCountry(data, country) {\n"),
    ),
}
# Public proof that each file is live.
CHECK_PAGE = 'order/order.js?v=' + VERSION
CHECK_SCRIPT = 'if(preselected) selectModel(preselected);'
CHECK_STATE = 'export function modelFromUrl(href, models)'


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
