"""Model landing pages (ADS-READY-001): the title and heading name the advertised version.

A model text in ua_seo_order_models.KOREA may carry «name» (for example «Kia K5 на газу (LPi)»):
the page title and h1 show it, so the page matches the ad; the catalogue counts, prices and description
stay as they are. A model without «name» keeps its page exactly. Each original fragment must occur
exactly once and an applied fragment is refused.
"""
NAME = 'ua_seo_landings.py'

EDITS = {
    NAME: (
        ("    texts = order_models.KOREA.get(key, {}).get(lang)\n",
         "    texts = order_models.KOREA.get(key, {}).get(lang)\n"
         "    # A model text may name the advertised version (fuel): the title and heading show it.\n"
         "    head = dict(fill, model=texts['name']) if texts and texts.get('name') else fill\n"),
        ("        title, description = t['model_title'].format(**fill), t['model_desc'].format(**fill)\n",
         "        title, description = t['model_title'].format(**head), t['model_desc'].format(**fill)\n"),
        ("        title, description = t['model_title_empty'].format(**fill), t['model_desc_empty'].format(**fill)\n",
         "        title, description = t['model_title_empty'].format(**head), t['model_desc_empty'].format(**fill)\n"),
        ("    h1 = t['model_h1'].format(**fill)\n",
         "    h1 = t['model_h1'].format(**head)\n"),
    ),
}


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('LANDINGS_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
