"""Build the ADS-AWTAG-SITE candidate (ADS-AWTAG-001 step 2): the site Google tag block V1 -> V2.

ua_google_tag.py (GA4-TAG-001, installed f5f0a304) is replaced: the GA4 config stays as it is, the tag is also
configured for Google Ads AW-18537441937, and every generate_lead sends one Google Ads conversion (gtag wrapped, so
quick-lead.js is counted too). apply() of V2 replaces an earlier block, so every page writer (ua_seo_metadata,
ua_seo_index, site_ge_inject, the catalogue hook) writes V2 from now on. targets() finds, on the server, every
public page that carries the V1 block; build() swaps exactly that block for V2 there. Nothing else changes.
"""
import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = 'ua_google_tag.py'
# The installed copy (GA4-TAG-INSTALL-20261025; still this hash in the USA-LOTS-FIX3-INSTALL-20261127 plan).
MODULE_SHA256 = 'f5f0a30489d20d7f7d973c27bd31e583e9827fb5a6d1e24a97fb35d1e6a3b6d4'
OLD_COPY = 'ua_google_tag_old.py'
# Where a page with the tag may live (the public site and its mirror).
GLOBS = ('video/**/*.html', 'site/**/*.html')
DEPENDENCY_SHA256 = {}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def modules():
    """(V1, V2): the installed module (its copy here, pinned by hash) and the new one."""
    if sha((HERE/OLD_COPY).read_bytes()) != MODULE_SHA256:
        raise ValueError('AWTAG_OLD_COPY_HASH')
    return _load(HERE/OLD_COPY, 'ua_google_tag_v1_copy'), _load(HERE/MODULE, 'ua_google_tag_v2_candidate')


OLD, NEW = modules()


def carries(text):
    return OLD.MARK in text


def swap(text):
    """V1 block -> V2 block; the page must carry exactly one V1 block and nothing else of the tag."""
    if text.count(OLD.MARK) != 1 or text.count(OLD.END) != 1 or text.count(OLD.SNIPPET) != 1 or NEW.SNIPPET in text:
        raise ValueError('AWTAG_PAGE_UNEXPECTED')
    return text.replace(OLD.SNIPPET, NEW.SNIPPET)


def undo(text):
    """V2 block -> V1 block (rollback of a page a writer rewrote after the install)."""
    return text.replace(NEW.SNIPPET, OLD.SNIPPET)


def is_new(text):
    """The V2 block once and no V1 block."""
    return text.count(NEW.MARK) == 1 and text.count(NEW.SNIPPET) == 1 and OLD.SNIPPET not in text


def is_old(text):
    return text.count(OLD.MARK) == 1 and text.count(OLD.SNIPPET) == 1


def is_page(name):
    return name.endswith('.html')


def pages(root):
    """Relative names of the public pages that carry the tag block."""
    root = Path(root)
    found = set()
    for pattern in GLOBS:
        for path in root.glob(pattern):
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 << 20:
                continue
            if carries(path.read_bytes().decode('utf-8', 'replace')):
                found.add(path.relative_to(root).as_posix())
    return tuple(sorted(found))


def targets(root):
    """Existing files the candidate replaces: the module and every page with the tag."""
    return (MODULE,) + pages(root)


def build(source, dependencies):
    """{name: new bytes}; the live module must be V1 and each page must carry exactly one V1 or one V2 block."""
    if MODULE not in source or sha(source[MODULE]) != MODULE_SHA256:
        raise ValueError('AWTAG_LIVE_MODULE_UNEXPECTED')
    result = {MODULE: (HERE/MODULE).read_bytes()}
    for name, value in source.items():
        if name != MODULE:
            if not is_page(name):
                raise ValueError('AWTAG_SOURCE_UNEXPECTED:' + name)
            try:
                text = value.decode('utf-8')
                # Already V2 (the landings the stale bot rewrote on 28.11 during the R1 rollback): kept as they are.
                result[name] = value if is_new(text) else swap(text).encode('utf-8')
            except ValueError:
                raise ValueError('AWTAG_PAGE_UNEXPECTED:' + name) from None
    if len(result) < 2:
        raise ValueError('AWTAG_NO_PAGES')
    return result
