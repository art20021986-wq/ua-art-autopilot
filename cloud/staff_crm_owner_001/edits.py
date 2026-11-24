"""Apply exact fragment edits to one installed source: each original fragment occurs exactly once, the result is
refused if an edit was already applied, so a drifted or re-run file stops the plan instead of being patched twice."""


def apply(source, edits):
    text = source.decode('utf-8')
    for old, new in edits:
        if text.count(old) != 1 or (new not in old and new in text):
            raise ValueError('FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
