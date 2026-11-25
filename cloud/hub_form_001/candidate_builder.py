"""Build the ADS-LP-001 candidate (owner «да» 2026-11-25: on the Kyiv «Авто з Кореї під ключ» pages, uk and ru, the
short enquiry form right under the first paragraph, and «пригон» in that paragraph).

- ua_seo_quick_form.py: hub_block(lang) — the same short form as on the model pages, sent as the general Korea enquiry
  (data-auction="korea": quick-lead.js already sends it as ua_order_request.auction.v1); appended at the end.
- ua_order/auction.py: that enquiry is also accepted from the two «під ключ» pages; in the CRM it reads
  «Корея под ключ» / «Авто из Кореи под ключ» instead of the auctions access request.
- ua_seo_landings.py: the hub's first paragraph says «пригон» and the form follows it; the install refreshes the
  landing pages.
Each file is pinned to its live hash; each original fragment must occur exactly once and an applied one is refused.
"""
import hashlib

SOURCE_SHA256 = {
    'ua_seo_landings.py': '4ffe374ae0eb4f368c1a6a8d278153264ce27de0e29aae6f0e0ea5b4a5e81cbe',
    'ua_seo_quick_form.py': 'ff6090c0109556ac2cc02c6ca131390293cf577cee1346cbd4072e5087728363',
    'ua_order/auction.py': '4259e81c8a93929bb623cbc0618fb33faef9f2a6e221582060b89bc0107d9c48',
}
# The form's sender, served unchanged: it must still send data-auction forms as the auction schema.
DEPENDENCY_SHA256 = {'video/order/quick-lead.js': 'dc958a813dca83d6f8329d59a1c080918add57eb47255208ebfcdef42dd3f3dc'}
TAG = 'ADS-LP-001'
HUB_PATHS = ('/video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html', '/video/seo/ru/avto-iz-korei-v-kiev-pod-kluch.html')
EDITS = {
    'ua_seo_landings.py': (
        ('перевіряє їх, доставляє через Грузію та передає в Києві.', 'перевіряє їх і робить пригон через Грузію до Києва.'),
        ('проверяет их, доставляет через Грузию и передаёт в Киеве.', 'проверяет их и делает пригон через Грузию в Киев.'),
        ("        escape(t['hub_intro'].format(**fill)), hub_texts.hub(lang, lambda key: '/video/' + path(lang, key)),\n",
         "        escape(t['hub_intro'].format(**fill)),\n"
         "        quick_form.hub_block(lang) + hub_texts.hub(lang, lambda key: '/video/' + path(lang, key)),  # ADS-LP-001\n"),
    ),
    'ua_order/auction.py': (
        ("SOURCE_PATHS = frozenset(('/video/korea.html',))\n",
         "# ADS-LP-001: the short form on the Kyiv «під ключ» pages sends this enquiry too (no model, no lot).\n"
         "HUB_PATHS = frozenset((%r, %r))\n"
         "SOURCE_PATHS = frozenset(('/video/korea.html',)) | HUB_PATHS\n" % HUB_PATHS),
        ("    return 'Аукционы онлайн: ' + {'korea': 'Корея'}.get(data.get('purchase_country_code'), '—')\n",
         "    if data.get('source_path') in HUB_PATHS:\n"
         "        return 'Корея под ключ'\n"
         "    return 'Аукционы онлайн: ' + {'korea': 'Корея'}.get(data.get('purchase_country_code'), '—')\n"),
        ("    fields = [('Заявка', row['number']), ('Тип', 'Доступ к аукционам онлайн'),\n"
         "              ('Аукционы', AUCTIONS.get(data['purchase_country_code'], data['purchase_country_code'])),\n",
         "    hub = data.get('source_path') in HUB_PATHS  # ADS-LP-001\n"
         "    fields = [('Заявка', row['number']),\n"
         "              ('Тип', 'Авто из Кореи под ключ' if hub else 'Доступ к аукционам онлайн'),\n"
         "              *([] if hub else [('Аукционы', AUCTIONS.get(data['purchase_country_code'],\n"
         "                                                          data['purchase_country_code']))]),\n"),
    ),
}
QUICK_TAIL = '''

# ADS-LP-001: the same short form on the Kyiv «під ключ» pages — the general Korea enquiry (no model):
# quick-lead.js sends a form with data-auction as ua_order_request.auction.v1.
HUB_TITLE = {'uk': 'Отримати пропозицію на авто з Кореї', 'ru': 'Получить предложение на авто из Кореи'}


def hub_block(lang):
    """The short form for the «під ключ» page, or '' for another language."""
    if lang not in HUB_TITLE:
        return ''
    html = block(lang, ('Kia', 'K5'))
    model = ' data-model="%s"' % MODELS[('Kia', 'K5')]
    title = '<h2>%s</h2>' % escape(T[lang]['title'].format(model='Kia K5'))
    if html.count(model) != 1 or html.count(title) != 1:
        raise ValueError('HUB_FORM_TEMPLATE')
    return html.replace(model, ' data-auction="korea"').replace(title, '<h2>%s</h2>' % escape(HUB_TITLE[lang]))
'''
QUICK_ANCHOR = 'def block(lang, key):'


def targets(root):
    return tuple(SOURCE_SHA256)


def is_page(name):
    return False


def page_names(root):
    return ()


def edit(name, text):
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('HUB_FRAGMENT:' + name + ':' + old[:40])
        text = text.replace(old, new)
    return text


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: edit(name, source[name].decode('utf-8')).encode('utf-8') for name in EDITS}
    quick = source['ua_seo_quick_form.py'].decode('utf-8')
    if TAG in quick or quick.count(QUICK_ANCHOR) != 1:
        raise ValueError('HUB_QUICK_FORM_ANCHOR')
    result['ua_seo_quick_form.py'] = (quick.rstrip('\n') + QUICK_TAIL).encode('utf-8')
    return result
