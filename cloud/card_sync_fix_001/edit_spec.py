"""ua_additional_spec.py (CARD-SYNC-FIX-001): the card builder's external-host guard knows the Google tag host.

Since GA4-TAG-001 (owner «Да» 2026-10-25) every card carries the site's Google tag
(https://www.googletagmanager.com/gtag/js); the UA115 guard, which refuses a card page with a link to an
unapproved external site, did not list that host, so every card publication fails with
UA115_UNAPPROVED_EXTERNAL_HOST:...:www.googletagmanager.com and CRM edits stop reaching the site. One host is
added to the approved set; the guard itself and every other host stay as they are.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
import ast

NAME = 'ua_additional_spec.py'
HOST = 'www.googletagmanager.com'
OLD = '    "maps.app.goo.gl", "ecomm.one-line.com", "www.searates.com", "schema.org", "www.w3.org",\n}\n'
NEW = ('    "maps.app.goo.gl", "ecomm.one-line.com", "www.searates.com", "schema.org", "www.w3.org",\n'
       '    "%s",  # CARD-SYNC-FIX-001: the site\'s Google tag (GA4-TAG-001)\n}\n' % HOST)


def approved_hosts(text):
    """The _UA115_APPROVED_HOSTS literal of the module text."""
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == '_UA115_APPROVED_HOSTS' for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise ValueError('APPROVED_HOSTS_MISSING')


def build(name, source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or HOST in approved_hosts(text):
        raise ValueError('SPEC_FRAGMENT:' + name)
    before = approved_hosts(text)
    text = text.replace(OLD, NEW)
    if approved_hosts(text) != before | {HOST}:
        raise ValueError('SPEC_HOSTS:' + name)
    return text.encode('utf-8')
