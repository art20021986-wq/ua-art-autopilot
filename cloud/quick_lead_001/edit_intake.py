"""Order package: contract.normalize and crm.detail_view hand the short model-page enquiry to quick.py.

The same pattern the package already uses for v2 (preferences.py / preference_summary.py).
Each original fragment must occur exactly once and an applied fragment is refused.
"""

CONTRACT = 'ua_order/contract.py'
CRM = 'ua_order/crm.py'

EDITS = {
    CONTRACT: (
        ("        return normalize_preferences(data, catalog, consent_version)\n",
         "        return normalize_preferences(data, catalog, consent_version)\n"
         "    if isinstance(data, dict) and data.get('schema_version') == 'ua_order_request.quick.v1':\n"
         "        from .quick import normalize as normalize_quick\n"
         "        return normalize_quick(data, catalog, consent_version)\n"),
    ),
    CRM: (
        ("        return preference_summary.detail(row, catalog)\n",
         "        return preference_summary.detail(row, catalog)\n"
         "    if data.get('schema_version') == 'ua_order_request.quick.v1':\n"
         "        from .quick import detail as quick_detail\n"
         "        return quick_detail(row, catalog)\n"),
    ),
}


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('INTAKE_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
