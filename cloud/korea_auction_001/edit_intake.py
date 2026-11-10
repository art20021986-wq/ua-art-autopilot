"""Order package: contract.normalize and crm.detail_view hand the auction access request to auction.py.

Same pattern as quick.v1 (cloud/quick_lead_001/edit_intake.py). Each original fragment must occur
exactly once and an applied fragment is refused.
"""

CONTRACT = 'ua_order/contract.py'
CRM = 'ua_order/crm.py'
_SCHEMA = "'ua_order_request.auction.v1'"

EDITS = {
    CONTRACT: (
        ("        return normalize_quick(data, catalog, consent_version)\n",
         "        return normalize_quick(data, catalog, consent_version)\n"
         "    if isinstance(data, dict) and data.get('schema_version') == " + _SCHEMA + ":\n"
         "        from .auction import normalize as normalize_auction\n"
         "        return normalize_auction(data, catalog, consent_version)\n"),
    ),
    CRM: (
        # the list label: after the card enquiry's own label (installed by CARD-CONTACT-INSTALL-20261106)
        ("            country = card_label(data)\n        else:\n",
         "            country = card_label(data)\n"
         "        elif data.get('schema_version') == " + _SCHEMA + ":\n"
         "            from .auction import label as auction_label\n"
         "            country = auction_label(data)\n"
         "        else:\n"),
        ("        return quick_detail(row, catalog)\n",
         "        return quick_detail(row, catalog)\n"
         "    if data.get('schema_version') == " + _SCHEMA + ":\n"
         "        from .auction import detail as auction_detail\n"
         "        return auction_detail(row, catalog)\n"),
    ),
}


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('INTAKE_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
