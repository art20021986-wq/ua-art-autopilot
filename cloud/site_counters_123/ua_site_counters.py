import html
import re

CARD_RE = re.compile(
    r'<a\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bstage-card\b[^"\']*["\'])'
    r'(?=[^>]*\bdata-stage\s*=\s*["\'](?:kiev|georgia|sea|korea)["\'])'
    r'[^>]*>.*?</a\s*>',
    re.I | re.S,
)

CTA_RE = re.compile(
    r'<i\b(?=[^>]*\bdata-ru\s*=\s*["\'][^"\']*Открыть все автомобили)'
    r'[^>]*>.*?</i\s*>',
    re.I | re.S,
)

class HomeCounterError(RuntimeError):
    pass

def _ru(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        word = "автомобиль"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        word = "автомобиля"
    else:
        word = "автомобилей"
    return "%d %s" % (count, word)

def _uk(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        word = "автомобіль"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        word = "автомобілі"
    else:
        word = "автомобілів"
    return "%d %s" % (count, word)

def _set_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(
        r"\s+" + re.escape(name) + r'\s*=\s*(["\']).*?\1',
        re.I | re.S,
    )
    tag = pattern.sub("", tag)
    if not tag.endswith(">"):
        raise HomeCounterError("INVALID_TAG:" + name)
    return tag[:-1] + ' %s="%s">' % (name, html.escape(value, quote=True))

def _stage_of(block: str) -> str:
    opening = re.match(r"<a\b[^>]*>", block, re.I | re.S)
    if not opening:
        raise HomeCounterError("STAGE_OPENING_MISSING")
    match = re.search(
        r'\bdata-stage\s*=\s*["\'](kiev|georgia|sea|korea)["\']',
        opening.group(0),
        re.I,
    )
    if not match:
        raise HomeCounterError("STAGE_ATTRIBUTE_MISSING")
    return match.group(1).casefold()

def _patch_stage(block: str, stage: str, count: int) -> str:
    opening = re.match(r"<a\b[^>]*>", block, re.I | re.S)
    if not opening:
        raise HomeCounterError("STAGE_OPENING_MISSING:" + stage)
    tag = _set_attr(opening.group(0), "data-count", str(count))
    value = tag + block[opening.end():]
    em_matches = list(re.finditer(r"<em\b[^>]*>.*?</em\s*>", value, re.I | re.S))
    if len(em_matches) != 1:
        raise HomeCounterError("STAGE_COUNT_LABELS:%s:%d" % (stage, len(em_matches)))
    match = em_matches[0]
    old = match.group(0)
    em_open = re.match(r"<em\b[^>]*>", old, re.I | re.S)
    if not em_open:
        raise HomeCounterError("STAGE_EM_OPENING:" + stage)
    em_tag = _set_attr(_set_attr(em_open.group(0), "data-ru", _ru(count)), "data-uk", _uk(count))
    replacement = em_tag + html.escape(_ru(count)) + "</em>"
    return value[:match.start()] + replacement + value[match.end():]

def _patch_cta(source: str, total: int) -> str:
    matches = list(CTA_RE.finditer(source))
    if len(matches) != 1:
        raise HomeCounterError("TOTAL_CTA_COUNT:%d" % len(matches))
    match = matches[0]
    block = match.group(0)
    opening = re.match(r"<i\b[^>]*>", block, re.I | re.S)
    if not opening:
        raise HomeCounterError("TOTAL_CTA_OPENING")
    ru = "Открыть все автомобили · %d" % total
    uk = "Відкрити всі автомобілі · %d" % total
    tag = _set_attr(_set_attr(opening.group(0), "data-ru", ru), "data-uk", uk)
    replacement = tag + html.escape(ru) + "</i>"
    return source[:match.start()] + replacement + source[match.end():]

CLIENT_SCRIPT = '/* UA-SITE-COUNTERS-123: one published-catalog snapshot for vehicle counts. */\n(function () {\n  \'use strict\';\n  const aliases = {kiev:\'kiev\',kyiv:\'kiev\',georgia:\'georgia\',gruzia:\'georgia\',\n    sea:\'sea\',more:\'sea\',ferry:\'sea\',korea:\'korea\'};\n  function snapshot(doc) {\n    if (!doc.querySelector(\'.catalog-grid\')) throw Error(\'Missing catalog grid\');\n    const records = new Map();\n    const cards = Array.from(doc.querySelectorAll(\'article.catalog-card\'));\n    doc.querySelectorAll(\'a[data-ua-card]\').forEach(node => {\n      if (!node.closest(\'article.catalog-card\')) cards.push(node);\n    });\n    cards.forEach(card => {\n      const ids = new Set(), stages = new Set();\n      const nodes = [card, ...card.querySelectorAll(\'[data-ua-card],[data-category],[data-stage],[data-etap],[data-ua-card-stage]\')];\n      nodes.forEach(node => {\n        [\'data-ua-card\',\'data-ua\'].forEach(key => {\n          const id = (node.getAttribute(key) || \'\').trim().toUpperCase();\n          if (id) { if (!/^UA-[0-9]{4,}$/.test(id)) throw Error(\'Invalid ID\'); ids.add(id); }\n        });\n        [\'data-category\',\'data-stage\',\'data-etap\',\'data-ua-card-stage\'].forEach(key => {\n          const stage = aliases[(node.getAttribute(key) || \'\').trim().toLowerCase()];\n          if (stage) stages.add(stage);\n        });\n      });\n      if (!ids.size) {\n        card.querySelectorAll(\'a[href]\').forEach(link => {\n          const href = link.getAttribute(\'href\') || \'\';\n          if (/^(?:https?:)?\\/\\//i.test(href)) return;\n          const match = href.match(/(?:^|\\/)(UA-[0-9]{4,})\\.html(?:[?#].*)?$/i);\n          if (match) ids.add(match[1].toUpperCase());\n        });\n      }\n      if (ids.size !== 1 || stages.size > 1) throw Error(\'Ambiguous card\');\n      const id = [...ids][0], stage = [...stages][0] || null;\n      if (records.has(id) && records.get(id) !== stage) throw Error(\'Conflicting duplicate\');\n      records.set(id, stage);\n    });\n    const counts = {all:records.size,kiev:0,georgia:0,sea:0,korea:0};\n    records.forEach(stage => { if (stage) counts[stage]++; });\n    return counts;\n  }\n  function words(n, uk) {\n    const forms = uk ? [\'автомобіль\',\'автомобілі\',\'автомобілів\'] : [\'автомобиль\',\'автомобиля\',\'автомобилей\'];\n    const d = n % 10, h = n % 100;\n    return n + \' \' + forms[d === 1 && h !== 11 ? 0 : d >= 2 && d <= 4 && !(h >= 12 && h <= 14) ? 1 : 2];\n  }\n  function start() {\n    if (window.__uaSiteCounters123) return;\n    window.__uaSiteCounters123 = true;\n    let last = null, sequence = 0;\n    const catalog = !!document.querySelector(\'.catalog-grid\');\n    function put(node, ru, uk) {\n      node.setAttribute(\'data-ru\', ru); node.setAttribute(\'data-uk\', uk);\n      node.textContent = /^(uk|ua)(-|$)/i.test(document.documentElement.lang || \'\') ? uk : ru;\n    }\n    function render() {\n      if (!last) return;\n      document.querySelectorAll(\'.stage-card[data-stage]\').forEach(card => {\n        const key = aliases[card.getAttribute(\'data-stage\')];\n        if (!key) return;\n        const label = card.querySelector(\'.stage-copy em\') || card.querySelector(\'em\');\n        card.setAttribute(\'data-count\', String(last[key]));\n        if (label) put(label, words(last[key],false), words(last[key],true));\n      });\n      document.querySelectorAll(\'.outline-cta i[data-ru*="Открыть все автомобили"]\').forEach(node =>\n        put(node, \'Открыть все автомобили · \' + last.all, \'Відкрити всі автомобілі · \' + last.all));\n      const labels = {all:[\'Все\',\'Усі\'],kiev:[\'В Киеве\',\'У Києві\'],georgia:[\'В Грузии\',\'У Грузії\'],sea:[\'На пароме\',\'На поромі\'],korea:[\'В Корее\',\'У Кореї\']};\n      document.querySelectorAll(\'button[data-f]\').forEach(node => {\n        const key = node.getAttribute(\'data-f\');\n        if (labels[key]) put(node, labels[key][0] + \' · \' + last[key], labels[key][1] + \' · \' + last[key]);\n      });\n    }\n    async function sync() {\n      const current = ++sequence;\n      try {\n        let next;\n        if (catalog) next = snapshot(document);\n        else {\n          const anchor = document.querySelector(\'.outline-cta[href]\');\n          if (!anchor) return;\n          const url = new URL(anchor.getAttribute(\'href\'), document.baseURI);\n          if (url.origin !== location.origin) throw Error(\'External catalog\');\n          [\'f\',\'stage\',\'etap\'].forEach(key => url.searchParams.delete(key));\n          url.hash = \'\';\n          const response = await fetch(url.href, {cache:\'no-store\',credentials:\'same-origin\'});\n          if (!response.ok || !/^text\\/html\\b/i.test(response.headers.get(\'content-type\') || \'\')) throw Error(\'Catalog response\');\n          if (response.url && new URL(response.url).origin !== location.origin) throw Error(\'External redirect\');\n          const source = await response.text();\n          if (!/<\\/html\\s*>\\s*$/i.test(source)) throw Error(\'Incomplete catalog\');\n          next = snapshot(new DOMParser().parseFromString(source,\'text/html\'));\n        }\n        if (current === sequence) { last = next; render(); }\n      } catch (error) { console.warn(\'[UA counters] Keeping last valid counts:\', error.message); }\n    }\n    new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:[\'lang\']});\n    window.addEventListener(\'pageshow\', event => {\n      if (event.persisted) { if (catalog) location.reload(); else sync(); }\n    });\n    if (!catalog) document.addEventListener(\'visibilitychange\', () => { if (!document.hidden) sync(); });\n    sync();\n  }\n  if (typeof module !== \'undefined\' && module.exports) module.exports = {snapshot,words};\n  else if (document.readyState === \'loading\') document.addEventListener(\'DOMContentLoaded\',start,{once:true});\n  else start();\n}());\n'
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
