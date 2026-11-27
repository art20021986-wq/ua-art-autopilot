"""Build the BOT-GUARD-001 candidate (owner «Да, вариант А» 2026-11-27, tasks/BOT-PROTECT-001.md).

- ua_bot_guard.py (new): which counter events are not recorded (robots, automation tools, floods from one address).
- analitika_wsgi.py: the event endpoint /ua/a/e records an event only when ua_bot_guard allows it.
- analitika_yadro.py: the page script sends nothing from an automated browser (navigator.webdriver).
Each fragment must occur exactly once and an applied one is refused; the plan pins the live hashes.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAG = 'UA-BOT-GUARD-001'
NEW_MODULES = ('ua_bot_guard.py',)
DEPENDENCY_SHA256 = {}
EDITS = {
    'analitika_wsgi.py': (
        ('                    import analitika_yadro as ya\n                    ya.zapisat(dannye)\n',
         '                    import analitika_yadro as ya\n'
         '                    import ua_bot_guard  # ' + TAG + ': robots and floods are not recorded\n'
         '                    if ua_bot_guard.allow(environ):\n'
         '                        ya.zapisat(dannye)\n'),
    ),
    'analitika_yadro.py': (
        ('if (window.__UA_A) { return; } window.__UA_A = 1;\n',
         'if (window.__UA_A) { return; } window.__UA_A = 1;\n'
         'if (navigator.webdriver) { return; } // ' + TAG + ': automated browsers are not counted\n'),
    ),
}


def targets(root):
    return tuple(EDITS)


def is_page(name):
    return False


def page_names(root):
    return ()


def edit(name, text):
    if TAG in text:
        raise ValueError('BOT_GUARD_ALREADY_APPLIED:' + name)
    for old, new in EDITS[name]:
        if text.count(old) != 1:
            raise ValueError('BOT_GUARD_FRAGMENT:' + name + ':' + old.strip()[:40])
        text = text.replace(old, new)
    return text


def build(source, dependencies):
    result = {name: (HERE / name).read_bytes() for name in NEW_MODULES}
    result.update({name: edit(name, source[name].decode('utf-8')).encode('utf-8') for name in EDITS})
    return result
