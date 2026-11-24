"""cars_schema.py (the CRM car card): the money lines the owner sees are shown to everyone with full rights
(owner + managing admin, ua_full_access); the manager still does not see them. The docstring says the same."""
NAME = 'cars_schema.py'
EDITS = (
    ('    role: "owner" видит деньги, "admin"/"manager" — нет.\n',
     '    role: "owner" и "admin" (полные права, ua_full_access) видят деньги, "manager" — нет.\n'),
    ('    if role == "owner":\n',
     '    import ua_full_access  # STAFF-FULL-ACCESS-001: the owner and the managing admin have the same rights\n'
     '    if role in ua_full_access.roles():\n'),
)
