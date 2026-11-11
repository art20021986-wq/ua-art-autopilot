"""Build the CONTACT-NOTE candidate: «Менеджер напише вам у Viber або Telegram.» becomes «Менеджер зв’яжеться з вами.»
in uk/ru/ka (owner answer 1в of 2026-11-10: the manager dialog does not name Telegram).

The sentence lives in the page writers (ua_card_contact.py, ua_seo_quick_form.py, ...), in the order page strings and
in the published pages. targets() finds, on the server, every module, page and string file that carries it; build()
replaces exactly these sentences there, so new pages and the pages already published read the same. Nothing else
changes.
"""
from pathlib import Path

REPLACE = (
    ('Менеджер напише вам у Viber або Telegram.', 'Менеджер зв’яжеться з вами.'),
    ('Менеджер напишет вам в Viber или Telegram.', 'Менеджер свяжется с вами.'),
    ('მენეჯერი მოგწერთ Viber-ში ან Telegram-ში.', 'მენეჯერი დაგიკავშირდებათ.'),
)
# Where the sentence may live: page writers, the order package, public pages, the order page strings.
GLOBS = ('*.py', 'ua_order/*.py', 'video/**/*.html', 'site/**/*.html', 'video/order/*.json',
         'catalog_design_golden.html')
SKIP = ('deployment_', 'test_')
DEPENDENCY_SHA256 = {}


def carries(text):
    return any(old in text for old, _ in REPLACE)


def targets(root):
    """Relative names of the files that carry an old sentence."""
    root = Path(root)
    found = set()
    for pattern in GLOBS:
        for path in root.glob(pattern):
            if path.is_symlink() or not path.is_file() or path.name.startswith(SKIP) or path.stat().st_size > 16 << 20:
                continue
            if carries(path.read_bytes().decode('utf-8', 'replace')):
                found.add(path.relative_to(root).as_posix())
    return tuple(sorted(found))


def replace(text):
    for old, new in REPLACE:
        text = text.replace(old, new)
    return text


def undo(text):
    for old, new in REPLACE:
        text = text.replace(new, old)
    return text


def build(source, dependencies):
    """{name: new bytes} for every file that carries an old sentence."""
    result = {}
    for name, value in source.items():
        text = value.decode('utf-8')
        if not carries(text):
            raise ValueError('CONTACT_NOTE_SOURCE_UNEXPECTED:' + name)
        result[name] = replace(text).encode('utf-8')
    if not result:
        raise ValueError('CONTACT_NOTE_NOTHING_TO_CHANGE')
    return result


def is_page(name):
    """Published pages may be rewritten by the CRM sync after the install (with the new writers' text)."""
    return name.endswith('.html') and name != 'catalog_design_golden.html'


def webapp(names):
    """The web app imports the order package: a change there needs its reload."""
    return any(name.startswith('ua_order/') for name in names)
