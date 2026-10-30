"""Order package: contract.normalize and crm.detail_view hand the request's «attribution» to attribution.py.

normalize keeps its own validation as _normalize; the new normalize takes the attribution off first,
so every schema (v1, v2, quick) accepts it unchanged, and adds the clean values to the stored request.
detail_view (owner inbox and notification) appends the source lines whatever the schema.
Each original fragment must occur exactly once and an applied fragment is refused.
"""

CONTRACT = 'ua_order/contract.py'
CRM = 'ua_order/crm.py'

EDITS = {
    CONTRACT: (
        ("def normalize(data, catalog, consent_version, *, verified_contact=False):\n",
         "def normalize(data, catalog, consent_version, *, verified_contact=False):\n"
         "    from .attribution import split\n"
         "    data, attribution = split(data)\n"
         "    result = _normalize(data, catalog, consent_version, verified_contact=verified_contact)\n"
         "    return {**result, 'attribution': attribution} if attribution else result\n"
         "\n"
         "\n"
         "def _normalize(data, catalog, consent_version, *, verified_contact=False):\n"),
    ),
    CRM: (
        ("def detail_view(row, catalog):\n",
         "def detail_view(row, catalog):\n"
         "    from .attribution import with_source\n"
         "    return with_source(_detail_view(row, catalog), row['data'].get('attribution') or {})\n"
         "\n"
         "\n"
         "def _detail_view(row, catalog):\n"),
    ),
}


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('INTAKE_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
