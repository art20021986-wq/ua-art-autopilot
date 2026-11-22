"""Reading and writing one HTML start tag's attributes by regular expressions, keeping the raw (escaped) values."""
import re

ATTRIBUTE = re.compile(r'([\w:-]+)\s*=\s*(["\'])(.*?)\2', re.S)


def find(source, pattern):
    """The only start tag matching pattern (a regular expression for the whole tag)."""
    found = re.findall(pattern, source, flags=re.I | re.S)
    if len(found) != 1:
        raise ValueError('TAG_COUNT:%s:%d' % (pattern[:40], len(found)))
    return found[0]


def attributes(tag):
    return {name.lower(): value for name, _, value in ATTRIBUTE.findall(tag)}


def with_attribute(tag, name, value):
    """The tag with name="value" (raw value); the attribute must already be there once."""
    result, count = re.subn(r'(\s%s\s*=\s*)(["\']).*?\2' % re.escape(name), lambda m: '%s"%s"' % (m[1], value), tag,
                            count=1, flags=re.I | re.S)
    if count != 1:
        raise ValueError('ATTRIBUTE_MISSING:' + name)
    return result


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('TAG_NOT_UNIQUE')
    return source.replace(old, new)
