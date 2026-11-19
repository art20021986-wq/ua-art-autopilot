"""Exact text replacements: each old text must be in the file exactly once, else the edit is refused."""


def replace_once(text, pairs, name):
    for old, new in pairs:
        if text.count(old) != 1:
            raise ValueError('EDIT_ANCHOR:%s:%d' % (name, text.count(old)))
        text = text.replace(old, new)
    return text
