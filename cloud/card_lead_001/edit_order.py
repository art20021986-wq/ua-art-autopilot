"""Order package: contract.normalize and crm hand the car card enquiry (ua_order_request.card.v1) to card_lead.py.

The same pattern the package uses for quick.v1 and v2. Each original fragment must occur exactly once and an
applied fragment is refused.
"""
CONTRACT = 'ua_order/contract.py'
CRM = 'ua_order/crm.py'

EDITS = {
    CONTRACT: (
        ("        return normalize_quick(data, catalog, consent_version)\n",
         "        return normalize_quick(data, catalog, consent_version)\n"
         "    if isinstance(data, dict) and data.get('schema_version') == 'ua_order_request.card.v1':\n"
         "        from .card_lead import normalize as normalize_card\n"
         "        return normalize_card(data, catalog, consent_version)\n"),
    ),
    CRM: (
        ("        country = preference_summary.country_label(data, catalog)\n"
         "        # Telegram inline labels are plain text, never HTML.\n",
         "        if data.get('schema_version') == 'ua_order_request.card.v1':\n"
         "            from .card_lead import label as card_label\n"
         "            country = card_label(data)\n"
         "        else:\n"
         "            country = preference_summary.country_label(data, catalog)\n"
         "        # Telegram inline labels are plain text, never HTML.\n"),
        ("        return quick_detail(row, catalog)\n",
         "        return quick_detail(row, catalog)\n"
         "    if data.get('schema_version') == 'ua_order_request.card.v1':\n"
         "        from .card_lead import detail as card_detail\n"
         "        return card_detail(row)\n"),
    ),
}


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
