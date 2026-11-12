"""Build the DIAG-COUNTERS-001 candidate from the exact installed source and the current diagnostics pages.

- site_ge_inject.inject_html, which every page writer already calls, adds the Google tag and the site's own counter
  (the installed ua_google_tag / ua_own_counter, both idempotent): a page rewritten later keeps both
  (appended at the end of the module, after the existing chain);
- the car diagnostics pages (video, site) get both now; pages that already carry both are left out.
"""
import hashlib
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
TAG = 'DIAG-COUNTERS-001'
INJECT = 'site_ge_inject.py'
INJECT_TAIL = ("\n\n# DIAG-COUNTERS-001: the Google tag and the site's own counter on every page a writer produces.\n"
               "_ua_counters_base_inject = inject_html\n"
               "def inject_html(source):\n"
               "    import ua_google_tag, ua_own_counter\n"
               "    return ua_own_counter.apply(ua_google_tag.apply(_ua_counters_base_inject(source)))\n")
# The installed modules (the same bytes the server runs); the copies here must match them.
DEPENDENCY_SHA256 = {
    'ua_google_tag.py': 'f5f0a30489d20d7f7d973c27bd31e583e9827fb5a6d1e24a97fb35d1e6a3b6d4',
    'ua_own_counter.py': 'e9414d9988d3d3a2b22011cd051a65d6f8d086cde3d7abc1443bb35b45a5fd38',
}
DIAG = re.compile(r'UA-[0-9]{4,}-diag\.html')
DIAG_ROOTS = ('video', 'site')


def page_names(root):
    root = Path(root)
    return tuple(p.relative_to(root).as_posix() for folder in DIAG_ROOTS
                 for p in sorted((root/folder).glob('UA-*-diag.html')) if DIAG.fullmatch(p.name))


def targets(root):
    """Existing files the candidate may replace."""
    return (INJECT,) + page_names(root)


def edit_inject(value):
    text = value.decode('utf-8')
    if TAG in text:
        raise ValueError('DIAG_COUNTERS_ALREADY_APPLIED')
    if 'def inject_html(' not in text:
        raise ValueError('DIAG_COUNTERS_INJECT_MISSING')
    return (text.rstrip('\n') + INJECT_TAIL).encode('utf-8')


def counted(html):
    import ua_google_tag
    import ua_own_counter
    return ua_own_counter.apply(ua_google_tag.apply(html))


def has_both(html):
    import ua_google_tag
    import ua_own_counter
    return html.count(ua_google_tag.MARK) == 1 and html.count(ua_own_counter.MARK) == 1


def build(source, dependencies):
    """{name: new bytes}: the inject chain and the diagnostics pages that miss a counter."""
    for name, digest in DEPENDENCY_SHA256.items():
        if hashlib.sha256(dependencies[name]).hexdigest() != digest or \
                hashlib.sha256((HERE/name).read_bytes()).hexdigest() != digest:
            raise ValueError('DEPENDENCY_HASH:' + name)
    result = {INJECT: edit_inject(source[INJECT])}
    for name, value in source.items():
        if name == INJECT:
            continue
        changed = counted(value.decode('utf-8')).encode('utf-8')
        if changed != value:
            if not has_both(changed.decode('utf-8')):
                raise ValueError('DIAG_COUNTERS_PAGE:' + name)
            result[name] = changed
    return result


def is_page(name):
    return name.endswith('.html')
