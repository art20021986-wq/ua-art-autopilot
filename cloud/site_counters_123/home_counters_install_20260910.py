#!/usr/bin/env python3
"""UA-SITE-COUNTERS-123: default read-only preflight, --apply after validation."""
import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

ROOT = Path('/home/Carix')
EXPECTED_PUBLISHER = 'ce6bd00338fbdc38b91f9554ea7baab3b8e921ffe6c1035aa4aba0186e2b549d'
EXPECTED_HOME = '3a8869b4da2fe58898a1237c0fea1b09d45dea80f7c61ab855c0d3a1cf739f8d'
CORE_TEXT = 'import html\nimport re\n\nCARD_RE = re.compile(\n    r\'<a\\b(?=[^>]*\\bclass\\s*=\\s*["\\\'][^"\\\']*\\bstage-card\\b[^"\\\']*["\\\'])\'\n    r\'(?=[^>]*\\bdata-stage\\s*=\\s*["\\\'](?:kiev|georgia|sea|korea)["\\\'])\'\n    r\'[^>]*>.*?</a\\s*>\',\n    re.I | re.S,\n)\n\nCTA_RE = re.compile(\n    r\'<i\\b(?=[^>]*\\bdata-ru\\s*=\\s*["\\\'][^"\\\']*Открыть все автомобили)\'\n    r\'[^>]*>.*?</i\\s*>\',\n    re.I | re.S,\n)\n\nclass HomeCounterError(RuntimeError):\n    pass\n\ndef _ru(count: int) -> str:\n    if count % 10 == 1 and count % 100 != 11:\n        word = "автомобиль"\n    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):\n        word = "автомобиля"\n    else:\n        word = "автомобилей"\n    return "%d %s" % (count, word)\n\ndef _uk(count: int) -> str:\n    if count % 10 == 1 and count % 100 != 11:\n        word = "автомобіль"\n    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):\n        word = "автомобілі"\n    else:\n        word = "автомобілів"\n    return "%d %s" % (count, word)\n\ndef _set_attr(tag: str, name: str, value: str) -> str:\n    pattern = re.compile(\n        r"\\s+" + re.escape(name) + r\'\\s*=\\s*(["\\\']).*?\\1\',\n        re.I | re.S,\n    )\n    tag = pattern.sub("", tag)\n    if not tag.endswith(">"):\n        raise HomeCounterError("INVALID_TAG:" + name)\n    return tag[:-1] + \' %s="%s">\' % (name, html.escape(value, quote=True))\n\ndef _stage_of(block: str) -> str:\n    opening = re.match(r"<a\\b[^>]*>", block, re.I | re.S)\n    if not opening:\n        raise HomeCounterError("STAGE_OPENING_MISSING")\n    match = re.search(\n        r\'\\bdata-stage\\s*=\\s*["\\\'](kiev|georgia|sea|korea)["\\\']\',\n        opening.group(0),\n        re.I,\n    )\n    if not match:\n        raise HomeCounterError("STAGE_ATTRIBUTE_MISSING")\n    return match.group(1).casefold()\n\ndef _patch_stage(block: str, stage: str, count: int) -> str:\n    opening = re.match(r"<a\\b[^>]*>", block, re.I | re.S)\n    if not opening:\n        raise HomeCounterError("STAGE_OPENING_MISSING:" + stage)\n    tag = _set_attr(opening.group(0), "data-count", str(count))\n    value = tag + block[opening.end():]\n    em_matches = list(re.finditer(r"<em\\b[^>]*>.*?</em\\s*>", value, re.I | re.S))\n    if len(em_matches) != 1:\n        raise HomeCounterError("STAGE_COUNT_LABELS:%s:%d" % (stage, len(em_matches)))\n    match = em_matches[0]\n    old = match.group(0)\n    em_open = re.match(r"<em\\b[^>]*>", old, re.I | re.S)\n    if not em_open:\n        raise HomeCounterError("STAGE_EM_OPENING:" + stage)\n    em_tag = _set_attr(_set_attr(em_open.group(0), "data-ru", _ru(count)), "data-uk", _uk(count))\n    replacement = em_tag + html.escape(_ru(count)) + "</em>"\n    return value[:match.start()] + replacement + value[match.end():]\n\ndef _patch_cta(source: str, total: int) -> str:\n    matches = list(CTA_RE.finditer(source))\n    if len(matches) != 1:\n        raise HomeCounterError("TOTAL_CTA_COUNT:%d" % len(matches))\n    match = matches[0]\n    block = match.group(0)\n    opening = re.match(r"<i\\b[^>]*>", block, re.I | re.S)\n    if not opening:\n        raise HomeCounterError("TOTAL_CTA_OPENING")\n    ru = "Открыть все автомобили · %d" % total\n    uk = "Відкрити всі автомобілі · %d" % total\n    tag = _set_attr(_set_attr(opening.group(0), "data-ru", ru), "data-uk", uk)\n    replacement = tag + html.escape(ru) + "</i>"\n    return source[:match.start()] + replacement + source[match.end():]\n\nCLIENT_SCRIPT = \'/* UA-SITE-COUNTERS-123: one published-catalog snapshot for vehicle counts. */\\n(function () {\\n  \\\'use strict\\\';\\n  const aliases = {kiev:\\\'kiev\\\',kyiv:\\\'kiev\\\',georgia:\\\'georgia\\\',gruzia:\\\'georgia\\\',\\n    sea:\\\'sea\\\',more:\\\'sea\\\',ferry:\\\'sea\\\',korea:\\\'korea\\\'};\\n  function snapshot(doc) {\\n    if (!doc.querySelector(\\\'.catalog-grid\\\')) throw Error(\\\'Missing catalog grid\\\');\\n    const records = new Map();\\n    const cards = Array.from(doc.querySelectorAll(\\\'article.catalog-card\\\'));\\n    doc.querySelectorAll(\\\'a[data-ua-card]\\\').forEach(node => {\\n      if (!node.closest(\\\'article.catalog-card\\\')) cards.push(node);\\n    });\\n    cards.forEach(card => {\\n      const ids = new Set(), stages = new Set();\\n      const nodes = [card, ...card.querySelectorAll(\\\'[data-ua-card],[data-category],[data-stage],[data-etap],[data-ua-card-stage]\\\')];\\n      nodes.forEach(node => {\\n        [\\\'data-ua-card\\\',\\\'data-ua\\\'].forEach(key => {\\n          const id = (node.getAttribute(key) || \\\'\\\').trim().toUpperCase();\\n          if (id) { if (!/^UA-[0-9]{4,}$/.test(id)) throw Error(\\\'Invalid ID\\\'); ids.add(id); }\\n        });\\n        [\\\'data-category\\\',\\\'data-stage\\\',\\\'data-etap\\\',\\\'data-ua-card-stage\\\'].forEach(key => {\\n          const stage = aliases[(node.getAttribute(key) || \\\'\\\').trim().toLowerCase()];\\n          if (stage) stages.add(stage);\\n        });\\n      });\\n      if (!ids.size) {\\n        card.querySelectorAll(\\\'a[href]\\\').forEach(link => {\\n          const href = link.getAttribute(\\\'href\\\') || \\\'\\\';\\n          if (/^(?:https?:)?\\\\/\\\\//i.test(href)) return;\\n          const match = href.match(/(?:^|\\\\/)(UA-[0-9]{4,})\\\\.html(?:[?#].*)?$/i);\\n          if (match) ids.add(match[1].toUpperCase());\\n        });\\n      }\\n      if (ids.size !== 1 || stages.size > 1) throw Error(\\\'Ambiguous card\\\');\\n      const id = [...ids][0], stage = [...stages][0] || null;\\n      if (records.has(id) && records.get(id) !== stage) throw Error(\\\'Conflicting duplicate\\\');\\n      records.set(id, stage);\\n    });\\n    const counts = {all:records.size,kiev:0,georgia:0,sea:0,korea:0};\\n    records.forEach(stage => { if (stage) counts[stage]++; });\\n    return counts;\\n  }\\n  function words(n, uk) {\\n    const forms = uk ? [\\\'автомобіль\\\',\\\'автомобілі\\\',\\\'автомобілів\\\'] : [\\\'автомобиль\\\',\\\'автомобиля\\\',\\\'автомобилей\\\'];\\n    const d = n % 10, h = n % 100;\\n    return n + \\\' \\\' + forms[d === 1 && h !== 11 ? 0 : d >= 2 && d <= 4 && !(h >= 12 && h <= 14) ? 1 : 2];\\n  }\\n  function start() {\\n    if (window.__uaSiteCounters123) return;\\n    window.__uaSiteCounters123 = true;\\n    let last = null, sequence = 0;\\n    const catalog = !!document.querySelector(\\\'.catalog-grid\\\');\\n    function put(node, ru, uk) {\\n      node.setAttribute(\\\'data-ru\\\', ru); node.setAttribute(\\\'data-uk\\\', uk);\\n      node.textContent = /^(uk|ua)(-|$)/i.test(document.documentElement.lang || \\\'\\\') ? uk : ru;\\n    }\\n    function render() {\\n      if (!last) return;\\n      document.querySelectorAll(\\\'.stage-card[data-stage]\\\').forEach(card => {\\n        const key = aliases[card.getAttribute(\\\'data-stage\\\')];\\n        if (!key) return;\\n        const label = card.querySelector(\\\'.stage-copy em\\\') || card.querySelector(\\\'em\\\');\\n        card.setAttribute(\\\'data-count\\\', String(last[key]));\\n        if (label) put(label, words(last[key],false), words(last[key],true));\\n      });\\n      document.querySelectorAll(\\\'.outline-cta i[data-ru*="Открыть все автомобили"]\\\').forEach(node =>\\n        put(node, \\\'Открыть все автомобили · \\\' + last.all, \\\'Відкрити всі автомобілі · \\\' + last.all));\\n      const labels = {all:[\\\'Все\\\',\\\'Усі\\\'],kiev:[\\\'В Киеве\\\',\\\'У Києві\\\'],georgia:[\\\'В Грузии\\\',\\\'У Грузії\\\'],sea:[\\\'На пароме\\\',\\\'На поромі\\\'],korea:[\\\'В Корее\\\',\\\'У Кореї\\\']};\\n      document.querySelectorAll(\\\'button[data-f]\\\').forEach(node => {\\n        const key = node.getAttribute(\\\'data-f\\\');\\n        if (labels[key]) put(node, labels[key][0] + \\\' · \\\' + last[key], labels[key][1] + \\\' · \\\' + last[key]);\\n      });\\n    }\\n    async function sync() {\\n      const current = ++sequence;\\n      try {\\n        let next;\\n        if (catalog) next = snapshot(document);\\n        else {\\n          const anchor = document.querySelector(\\\'.outline-cta[href]\\\');\\n          if (!anchor) return;\\n          const url = new URL(anchor.getAttribute(\\\'href\\\'), document.baseURI);\\n          if (url.origin !== location.origin) throw Error(\\\'External catalog\\\');\\n          [\\\'f\\\',\\\'stage\\\',\\\'etap\\\'].forEach(key => url.searchParams.delete(key));\\n          url.hash = \\\'\\\';\\n          const response = await fetch(url.href, {cache:\\\'no-store\\\',credentials:\\\'same-origin\\\'});\\n          if (!response.ok || !/^text\\\\/html\\\\b/i.test(response.headers.get(\\\'content-type\\\') || \\\'\\\')) throw Error(\\\'Catalog response\\\');\\n          if (response.url && new URL(response.url).origin !== location.origin) throw Error(\\\'External redirect\\\');\\n          const source = await response.text();\\n          if (!/<\\\\/html\\\\s*>\\\\s*$/i.test(source)) throw Error(\\\'Incomplete catalog\\\');\\n          next = snapshot(new DOMParser().parseFromString(source,\\\'text/html\\\'));\\n        }\\n        if (current === sequence) { last = next; render(); }\\n      } catch (error) { console.warn(\\\'[UA counters] Keeping last valid counts:\\\', error.message); }\\n    }\\n    new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:[\\\'lang\\\']});\\n    window.addEventListener(\\\'pageshow\\\', event => {\\n      if (event.persisted) { if (catalog) location.reload(); else sync(); }\\n    });\\n    if (!catalog) document.addEventListener(\\\'visibilitychange\\\', () => { if (!document.hidden) sync(); });\\n    sync();\\n  }\\n  if (typeof module !== \\\'undefined\\\' && module.exports) module.exports = {snapshot,words};\\n  else if (document.readyState === \\\'loading\\\') document.addEventListener(\\\'DOMContentLoaded\\\',start,{once:true});\\n  else start();\\n}());\\n\'\n# Appended to markup_helpers.py with CLIENT_SCRIPT by build_installer.py.\nfrom html.parser import HTMLParser\nfrom pathlib import Path\n\nALIASES = {\'kiev\':\'kiev\',\'kyiv\':\'kiev\',\'georgia\':\'georgia\',\'gruzia\':\'georgia\',\n           \'sea\':\'sea\',\'more\':\'sea\',\'ferry\':\'sea\',\'korea\':\'korea\'}\nSTAGES = (\'kiev\',\'georgia\',\'sea\',\'korea\')\nSTART = \'<!-- UA-SITE-COUNTERS-123:START -->\'\nEND = \'<!-- UA-SITE-COUNTERS-123:END -->\'\n\n\nclass CatalogParser(HTMLParser):\n    VOID = {\'area\',\'base\',\'br\',\'col\',\'embed\',\'hr\',\'img\',\'input\',\'link\',\'meta\',\'param\',\'source\',\'track\',\'wbr\'}\n    def __init__(self):\n        super().__init__(convert_charrefs=True)\n        self.stack, self.current, self.records, self.grid = [], None, {}, False\n\n    def handle_starttag(self, tag, pairs):\n        attrs = dict(pairs)\n        classes = (attrs.get(\'class\') or \'\').split()\n        self.grid |= \'catalog-grid\' in classes\n        if self.current is None and (tag == \'article\' and \'catalog-card\' in classes\n                                     or tag == \'a\' and \'data-ua-card\' in attrs):\n            self.current = {\'depth\':len(self.stack),\'ids\':set(),\'href_ids\':set(),\'stages\':set()}\n        if self.current is not None:\n            for key in (\'data-ua-card\',\'data-ua\'):\n                value = (attrs.get(key) or \'\').strip().upper()\n                if value:\n                    if not re.fullmatch(r\'UA-[0-9]{4,}\', value):\n                        raise HomeCounterError(\'INVALID_ID\')\n                    self.current[\'ids\'].add(value)\n            for key in (\'data-category\',\'data-stage\',\'data-etap\',\'data-ua-card-stage\'):\n                stage = ALIASES.get((attrs.get(key) or \'\').strip().lower())\n                if stage:\n                    self.current[\'stages\'].add(stage)\n            href = attrs.get(\'href\') or \'\'\n            if tag == \'a\' and not re.match(r\'^(?:https?:)?//\', href, re.I):\n                match = re.search(r\'(?:^|/)(UA-[0-9]{4,})\\.html(?:[?#].*)?$\', href, re.I)\n                if match:\n                    self.current[\'href_ids\'].add(match[1].upper())\n        if tag not in self.VOID:\n            self.stack.append(tag)\n\n    def handle_endtag(self, tag):\n        if tag not in self.stack:\n            return\n        index = len(self.stack) - 1 - self.stack[::-1].index(tag)\n        del self.stack[index:]\n        if self.current is not None and len(self.stack) <= self.current[\'depth\']:\n            ids = self.current[\'ids\'] or self.current[\'href_ids\']\n            stages = self.current[\'stages\']\n            if len(ids) != 1 or len(stages) > 1:\n                raise HomeCounterError(\'AMBIGUOUS_CARD\')\n            identifier = next(iter(ids))\n            stage = next(iter(stages), None)\n            if identifier in self.records and self.records[identifier] != stage:\n                raise HomeCounterError(\'CONFLICTING_DUPLICATE\')\n            self.records[identifier] = stage\n            self.current = None\n\n    def handle_startendtag(self, tag, attrs):\n        self.handle_starttag(tag, attrs)\n        if tag not in self.VOID:\n            self.handle_endtag(tag)\n\n\ndef catalog_snapshot(source):\n    if not re.search(r\'<html\\b\', source, re.I) or not re.search(r\'</html\\s*>\\s*$\', source, re.I):\n        raise HomeCounterError(\'INCOMPLETE_CATALOG\')\n    parser = CatalogParser()\n    parser.feed(source)\n    parser.close()\n    if not parser.grid or parser.current is not None:\n        raise HomeCounterError(\'INVALID_CATALOG\')\n    counts = {\'all\':len(parser.records), **{stage:0 for stage in STAGES}}\n    for stage in parser.records.values():\n        if stage:\n            counts[stage] += 1\n    return parser.records, counts\n\n\ndef inject_script(source):\n    # Replace only identified counter scripts; keep language, filters, analytics.\n    patterns = [re.escape(START)+r\'.*?\'+re.escape(END),\n                r\'<!-- UA-HOME-STAGE-COUNTER-SYNC-093:START -->.*?<!-- UA-HOME-STAGE-COUNTER-SYNC-093:END -->\',\n                r\'<script\\b[^>]*>\\s*/\\* UA-CIFRY-V1 \\*/.*?</script\\s*>\']\n    for pattern in patterns:\n        source, n = re.subn(pattern+r\'(?:\\r?\\n)?\', \'\', source, flags=re.S)\n        if n > 1:\n            raise HomeCounterError(\'DUPLICATE_COUNTER_SCRIPT\')\n    if len(re.findall(r\'</body\\s*>\',source,re.I)) != 1:\n        raise HomeCounterError(\'BODY_END\')\n    block = START+\'\\n<script id="ua-site-counters-123">\\n\'+CLIENT_SCRIPT+\'\\n</script>\\n\'+END\n    return re.sub(r\'</body\\s*>\', lambda m: block+\'\\n\'+m.group(), source, count=1, flags=re.I)\n\n\ndef ukrainian(source):\n    return bool(re.search(r\'<html\\b[^>]*\\blang=["\\\'](?:uk|ua)(?:-[^"\\\']*)?["\\\']\',source,re.I))\n\n\ndef patch_home(source, counts):\n    found = {}\n    uk = ukrainian(source)\n    def stage_replace(match):\n        block = match.group()\n        stage = _stage_of(block)\n        found[stage] = found.get(stage,0)+1\n        block = _patch_stage(block,stage,counts[stage])\n        if uk:\n            block = re.sub(r\'(<em\\b[^>]*>).*?(</em\\s*>)\',lambda m:m[1]+_uk(counts[stage])+m[2],block,flags=re.S)\n        return block\n    result = CARD_RE.sub(stage_replace,source)\n    if found != {stage:1 for stage in STAGES}:\n        raise HomeCounterError(\'HOME_STAGE_SET:\'+repr(found))\n    result = _patch_cta(result,counts[\'all\'])\n    if uk:\n        result = CTA_RE.sub(lambda m:re.sub(r\'(?<=>)[^<]*(?=</i)\', \'Відкрити всі автомобілі · \'+str(counts[\'all\']),m.group()), result)\n    return inject_script(result)\n\n\ndef patch_catalog(source, counts):\n    labels = {\'all\':(\'Все\',\'Усі\'),\'kiev\':(\'В Киеве\',\'У Києві\'),\n              \'georgia\':(\'В Грузии\',\'У Грузії\'),\'sea\':(\'На пароме\',\'На поромі\'),\n              \'korea\':(\'В Корее\',\'У Кореї\')}\n    found = {}\n    def replace(match):\n        block = match.group()\n        opening = re.match(r\'<button\\b[^>]*>\',block,re.I).group()\n        key = re.search(r\'\\bdata-f=["\\\']([^"\\\']+)["\\\']\',opening,re.I)[1]\n        if key not in labels:\n            return block\n        found[key] = found.get(key,0)+1\n        ru,uk = (label+\' · \'+str(counts[key]) for label in labels[key])\n        tag = _set_attr(_set_attr(opening,\'data-ru\',ru),\'data-uk\',uk)\n        return tag+html.escape(uk if ukrainian(source) else ru)+\'</button>\'\n    result = re.sub(r\'<button\\b(?=[^>]*\\bdata-f=["\\\'])[^>]*>.*?</button\\s*>\',replace,source,flags=re.S|re.I)\n    if found != {key:1 for key in labels}:\n        raise HomeCounterError(\'CATALOG_FILTER_SET:\'+repr(found))\n    # The existing catalog renderer/filter is correct and protected by its\n    # shell fingerprint. Change only its numeric labels, not its scripts.\n    return result\n\n\ndef prepare_updates(roots):\n    updates, reference, counts = [], None, None\n    for root in roots:\n        root = Path(root)\n        path = root/\'katalog.html\'\n        before = path.read_bytes()\n        source = before.decode(\'utf-8\')\n        records, current = catalog_snapshot(source)\n        if reference is not None and records != reference:\n            raise HomeCounterError(\'CATALOG_COPIES_DIFFER\')\n        reference, counts = records, current\n        updates.append((path,before,patch_catalog(source,current).encode(\'utf-8\')))\n        home = root/\'index.html\'\n        if home.is_file():\n            before_home = home.read_bytes()\n            source_home = before_home.decode(\'utf-8\')\n            if \'outline-cta\' in source_home or \'stage-card\' in source_home:\n                updates.append((home,before_home,patch_home(source_home,current).encode(\'utf-8\')))\n    if counts is None:\n        raise HomeCounterError(\'NO_CATALOG_ROOTS\')\n    return updates, counts\n'
FRAGMENT = '# UA-SITE-COUNTERS-123:START\nfrom ua_site_counters import prepare_updates as _ua123_prepare_updates\n\n_UA123_BASE_SNAPSHOT = Snapshot\n_UA123_BASE_INSTALL = _install_catalog\n\n\nclass Snapshot(_UA123_BASE_SNAPSHOT):\n    """Include homepage counters in the existing publication rollback."""\n    def __init__(self, codes):\n        super().__init__(codes)\n        manifest_path = self.root / \'manifest.json\'\n        manifest = json.loads(manifest_path.read_text(encoding=\'utf-8\'))\n        for folder in ROOTS:\n            path = folder / \'index.html\'\n            if not path.is_file() or str(path) in manifest:\n                continue\n            data = _read(path)\n            relative = pathlib.Path(\'files\') / (str(path.relative_to(ROOT)) + \'.gz\')\n            _atomic(self.root / relative, _ua099_gzip.compress(data, compresslevel=9, mtime=0), 0o600)\n            manifest[str(path)] = {\n                \'exists\': True, \'path\': str(path), \'sha256\': _sha(data),\n                \'mode\': path.stat().st_mode & 0o777, \'storage\': \'gzip-v1\',\n                \'stored_relative\': str(relative),\n            }\n            self.before_paths.add(path)\n            self.present.add(path)\n        _atomic(manifest_path, (json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+\'\\n\').encode(), 0o600)\n\n\ndef _install_catalog(source, target):\n    # Both callers already hold the publisher lock and own Snapshot rollback.\n    result = _UA123_BASE_INSTALL(source, target)\n    updates, counts = _ua123_prepare_updates(ROOTS)\n    for path, before, after in updates:\n        if _read(path) != before:\n            raise PublishError(\'COUNTER_SOURCE_CHANGED:\' + str(path))\n        if after != before:\n            _atomic(path, after, path.stat().st_mode & 0o777)\n        if _read(path) != after:\n            raise PublishError(\'COUNTER_READBACK:\' + str(path))\n    result[\'site_counters\'] = counts\n    rows, _ = _row_map()\n    for path_string, evidence in result.get(\'installed\', {}).items():\n        path = pathlib.Path(path_string)\n        evidence[\'sha256\'] = _sha(_read(path))\n        evidence[\'audit\'] = _validate_catalog(_read(path).decode(\'utf-8\'), rows)\n    return result\n# UA-SITE-COUNTERS-123:END\n'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def atomic(path,data,mode=0o600,create_only=False):
    fd,name = tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name,mode)
        if create_only:
            try:
                os.link(name,path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise RuntimeError('Concurrent core change')
        else:
            os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def preflight(validate_live=True):
    publisher = ROOT/'publish_transaction_guard.py'
    before = publisher.read_bytes()
    if sha(before) != EXPECTED_PUBLISHER:
        raise RuntimeError('Publisher SHA changed; refusing overwrite')
    if sha((ROOT/'video/index.html').read_bytes()) != EXPECTED_HOME:
        raise RuntimeError('Homepage SHA changed; refusing overwrite')
    core = CORE_TEXT.encode('utf-8')
    core_path = ROOT/'ua_site_counters.py'
    if core_path.exists() and core_path.read_bytes() != core:
        raise RuntimeError('Different counter core exists')
    candidate = before+b'\n\n'+FRAGMENT.encode('utf-8')
    compile(candidate,str(publisher),'exec')
    namespace = {'__name__':'ua123_preflight'}
    exec(compile(core,str(core_path),'exec'),namespace)
    updates,counts = namespace['prepare_updates']((ROOT/'video',ROOT/'site'))
    # Cross-check catalog identities against existing CRM, without database writes.
    con = sqlite3.connect('file:'+str(ROOT/'crm.db')+'?mode=ro',uri=True)
    try:
        con.row_factory = sqlite3.Row
        rows = [dict(row) for row in con.execute('SELECT * FROM cars')]
    finally:
        con.close()
    row_map = {row['auto_number']:row for row in rows}
    records,_ = namespace['catalog_snapshot']((ROOT/'video/katalog.html').read_text())
    if not set(records) <= set(row_map):
        raise RuntimeError('Catalog identity missing from CRM')
    if validate_live:
        # This is the existing, hash-verified publisher; no publication is invoked.
        spec = importlib.util.spec_from_file_location('ua123_existing_publisher',publisher)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for path,old,new in updates:
            if path.name == 'katalog.html':
                module._validate_catalog(new.decode('utf-8'),{key:row_map[key] for key in records})
    updates.append((publisher,before,candidate))
    report = {'counts':counts,'catalog_ids':sorted(records),
        'core_sha256':sha(core),'publisher_before_sha256':sha(before),
        'publisher_after_sha256':sha(candidate),
        'files':[{'path':str(path),'before_sha256':sha(old),'after_sha256':sha(new)} for path,old,new in updates]}
    return updates,core,report

def apply(updates,core,report):
    backup = ROOT/'backups/site_counters_123'/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    backup.mkdir(parents=True,exist_ok=False)
    manifest = {}
    for index,(path,old,new) in enumerate(updates):
        if path.read_bytes() != old: raise RuntimeError('Source changed before backup')
        saved = str(index)+'.gz'
        atomic(backup/saved,gzip.compress(old,mtime=0))
        manifest[str(path)] = {'stored':saved,'mode':path.stat().st_mode & 0o777,
                              'before_sha256':sha(old),'after_sha256':sha(new)}
    atomic(backup/'manifest.json',json.dumps(manifest,indent=2).encode())
    written = []
    try:
        atomic(ROOT/'ua_site_counters.py',core,0o644,create_only=True)
        for path,old,new in updates:
            if path.read_bytes() != old: raise RuntimeError('Concurrent source change:'+str(path))
            if new != old:
                atomic(path,new,manifest[str(path)]['mode'])
                written.append((path,old,new))
            if path.read_bytes() != new: raise RuntimeError('Readback mismatch:'+str(path))
    except Exception:
        for path,old,new in reversed(written):
            if path.read_bytes() == new:
                atomic(path,old,manifest[str(path)]['mode'])
        raise
    return dict(report,status='INSTALLED',backup=str(backup))

def rollback(directory):
    backup = Path(directory).resolve()
    if backup.parent != (ROOT/'backups/site_counters_123').resolve():
        raise RuntimeError('Unexpected backup path')
    manifest = json.loads((backup/'manifest.json').read_text())
    originals = []
    for name,item in manifest.items():
        path = Path(name)
        if path.resolve().parent not in (ROOT.resolve(),(ROOT/'video').resolve(),(ROOT/'site').resolve()):
            raise RuntimeError('Unexpected restore target')
        old = gzip.decompress((backup/item['stored']).read_bytes())
        if sha(old) != item['before_sha256'] or sha(path.read_bytes()) != item['after_sha256']:
            raise RuntimeError('Rollback hash mismatch')
        originals.append((path,old,item['mode']))
    for path,old,mode in reversed(originals): atomic(path,old,mode)
    return {'status':'ROLLED_BACK','backup':str(backup)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--rollback')
    args = parser.parse_args()
    if args.apply and args.rollback: raise RuntimeError('Choose apply or rollback')
    # Use the exact lock already used by publication/rebuild; never create another writer.
    with (ROOT/'.ua_art_publish_transaction.lock').open('rb') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.rollback: result = rollback(args.rollback)
        else:
            updates,core,report = preflight()
            result = apply(updates,core,report) if args.apply else dict(report,status='PREFLIGHT_OK')
        print(json.dumps(result,ensure_ascii=False))

if __name__ == '__main__': main()
