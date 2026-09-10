# Appended to markup_helpers.py with CLIENT_SCRIPT by build_installer.py.
from html.parser import HTMLParser
from pathlib import Path

ALIASES = {'kiev':'kiev','kyiv':'kiev','georgia':'georgia','gruzia':'georgia',
           'sea':'sea','more':'sea','ferry':'sea','korea':'korea'}
STAGES = ('kiev','georgia','sea','korea')
START = '<!-- UA-SITE-COUNTERS-123:START -->'
END = '<!-- UA-SITE-COUNTERS-123:END -->'


class CatalogParser(HTMLParser):
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.current, self.records, self.grid = [], None, {}, False

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        classes = (attrs.get('class') or '').split()
        self.grid |= 'catalog-grid' in classes
        if self.current is None and (tag == 'article' and 'catalog-card' in classes
                                     or tag == 'a' and 'data-ua-card' in attrs):
            self.current = {'depth':len(self.stack),'ids':set(),'href_ids':set(),'stages':set()}
        if self.current is not None:
            for key in ('data-ua-card','data-ua'):
                value = (attrs.get(key) or '').strip().upper()
                if value:
                    if not re.fullmatch(r'UA-[0-9]{4,}', value):
                        raise HomeCounterError('INVALID_ID')
                    self.current['ids'].add(value)
            for key in ('data-category','data-stage','data-etap','data-ua-card-stage'):
                stage = ALIASES.get((attrs.get(key) or '').strip().lower())
                if stage:
                    self.current['stages'].add(stage)
            href = attrs.get('href') or ''
            if tag == 'a' and not re.match(r'^(?:https?:)?//', href, re.I):
                match = re.search(r'(?:^|/)(UA-[0-9]{4,})\.html(?:[?#].*)?$', href, re.I)
                if match:
                    self.current['href_ids'].add(match[1].upper())
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag not in self.stack:
            return
        index = len(self.stack) - 1 - self.stack[::-1].index(tag)
        del self.stack[index:]
        if self.current is not None and len(self.stack) <= self.current['depth']:
            ids = self.current['ids'] or self.current['href_ids']
            stages = self.current['stages']
            if len(ids) != 1 or len(stages) > 1:
                raise HomeCounterError('AMBIGUOUS_CARD')
            identifier = next(iter(ids))
            stage = next(iter(stages), None)
            if identifier in self.records and self.records[identifier] != stage:
                raise HomeCounterError('CONFLICTING_DUPLICATE')
            self.records[identifier] = stage
            self.current = None

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)


def catalog_snapshot(source):
    if not re.search(r'<html\b', source, re.I) or not re.search(r'</html\s*>\s*$', source, re.I):
        raise HomeCounterError('INCOMPLETE_CATALOG')
    parser = CatalogParser()
    parser.feed(source)
    parser.close()
    if not parser.grid or parser.current is not None:
        raise HomeCounterError('INVALID_CATALOG')
    counts = {'all':len(parser.records), **{stage:0 for stage in STAGES}}
    for stage in parser.records.values():
        if stage:
            counts[stage] += 1
    return parser.records, counts


def inject_script(source):
    # Replace only identified counter scripts; keep language, filters, analytics.
    patterns = [re.escape(START)+r'.*?'+re.escape(END),
                r'<!-- UA-HOME-STAGE-COUNTER-SYNC-093:START -->.*?<!-- UA-HOME-STAGE-COUNTER-SYNC-093:END -->',
                r'<script\b[^>]*>\s*/\* UA-CIFRY-V1 \*/.*?</script\s*>']
    for pattern in patterns:
        source, n = re.subn(pattern+r'(?:\r?\n)?', '', source, flags=re.S)
        if n > 1:
            raise HomeCounterError('DUPLICATE_COUNTER_SCRIPT')
    if len(re.findall(r'</body\s*>',source,re.I)) != 1:
        raise HomeCounterError('BODY_END')
    block = START+'\n<script id="ua-site-counters-123">\n'+CLIENT_SCRIPT+'\n</script>\n'+END
    return re.sub(r'</body\s*>', lambda m: block+'\n'+m.group(), source, count=1, flags=re.I)


def ukrainian(source):
    return bool(re.search(r'<html\b[^>]*\blang=["\'](?:uk|ua)(?:-[^"\']*)?["\']',source,re.I))


def patch_home(source, counts):
    found = {}
    uk = ukrainian(source)
    def stage_replace(match):
        block = match.group()
        stage = _stage_of(block)
        found[stage] = found.get(stage,0)+1
        block = _patch_stage(block,stage,counts[stage])
        if uk:
            block = re.sub(r'(<em\b[^>]*>).*?(</em\s*>)',lambda m:m[1]+_uk(counts[stage])+m[2],block,flags=re.S)
        return block
    result = CARD_RE.sub(stage_replace,source)
    if found != {stage:1 for stage in STAGES}:
        raise HomeCounterError('HOME_STAGE_SET:'+repr(found))
    result = _patch_cta(result,counts['all'])
    if uk:
        result = CTA_RE.sub(lambda m:re.sub(r'(?<=>)[^<]*(?=</i)', 'Відкрити всі автомобілі · '+str(counts['all']),m.group()), result)
    return inject_script(result)


def patch_catalog(source, counts):
    labels = {'all':('Все','Усі'),'kiev':('В Киеве','У Києві'),
              'georgia':('В Грузии','У Грузії'),'sea':('На пароме','На поромі'),
              'korea':('В Корее','У Кореї')}
    found = {}
    def replace(match):
        block = match.group()
        opening = re.match(r'<button\b[^>]*>',block,re.I).group()
        key = re.search(r'\bdata-f=["\']([^"\']+)["\']',opening,re.I)[1]
        if key not in labels:
            return block
        found[key] = found.get(key,0)+1
        ru,uk = (label+' · '+str(counts[key]) for label in labels[key])
        tag = _set_attr(_set_attr(opening,'data-ru',ru),'data-uk',uk)
        return tag+html.escape(uk if ukrainian(source) else ru)+'</button>'
    result = re.sub(r'<button\b(?=[^>]*\bdata-f=["\'])[^>]*>.*?</button\s*>',replace,source,flags=re.S|re.I)
    if found != {key:1 for key in labels}:
        raise HomeCounterError('CATALOG_FILTER_SET:'+repr(found))
    # The existing catalog renderer/filter is correct and protected by its
    # shell fingerprint. Change only its numeric labels, not its scripts.
    return result


def prepare_updates(roots):
    updates, reference, counts = [], None, None
    for root in roots:
        root = Path(root)
        path = root/'katalog.html'
        before = path.read_bytes()
        source = before.decode('utf-8')
        records, current = catalog_snapshot(source)
        if reference is not None and records != reference:
            raise HomeCounterError('CATALOG_COPIES_DIFFER')
        reference, counts = records, current
        updates.append((path,before,patch_catalog(source,current).encode('utf-8')))
        home = root/'index.html'
        if home.is_file():
            before_home = home.read_bytes()
            source_home = before_home.decode('utf-8')
            if 'outline-cta' in source_home or 'stage-card' in source_home:
                updates.append((home,before_home,patch_home(source_home,current).encode('utf-8')))
    if counts is None:
        raise HomeCounterError('NO_CATALOG_ROOTS')
    return updates, counts
