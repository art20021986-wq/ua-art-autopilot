"""Build exact price-only Preview candidates without any production writes.

The output must be a NEW private directory outside the source/asset trees.
Existing public media can be hash-bound in place using explicit --asset-root;
the builder never recursively exposes that directory or copies private sources.
"""
import sys
sys.dont_write_bytecode = True
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, unquote

from common import ASSET_TYPES, CONTRACT, encoded, read, relative, sha, write_new
from routing_proof import prove_legacy_home_redirect

RENDERER = Path(__file__).resolve().parents[1] / 'task088_stage3_renderer'
sys.path.insert(0, str(RENDERER))
from initial_html_prices import migrate_card, migrate_catalog, migrate_home
from patch_yadro import patch_yadro
from patch_stranica import patch_stranica
from patch_catalog_design_guard import patch_catalog_design_guard


class References(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.references = set()
        self.links = set()
        self.in_style = False
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'): self.links.add(attrs['href'])
        if tag == 'style': self.in_style = True
        if attrs.get('style'): self.references.update(css_references(attrs['style']))
        if tag in ('script','img','source','video','audio'):
            for key in ('src','poster'):
                if attrs.get(key): self.references.add(attrs[key])
            if attrs.get('srcset'):
                self.references.update(item.strip().split()[0] for item in attrs['srcset'].split(',') if item.strip())
        if tag == 'link' and set(attrs.get('rel','').split()) & {'stylesheet','icon','preload'} and attrs.get('href'):
            self.references.add(attrs['href'])
    def handle_endtag(self, tag):
        if tag == 'style': self.in_style = False
    def handle_data(self, data):
        if self.in_style: self.references.update(css_references(data))


def css_references(source):
    urls = [match[1] for match in re.findall(r'url\(\s*([\"\']?)(.*?)\1\s*\)',source)]
    urls.extend(re.findall(r'@import\s+[\"\']([^\"\']+)[\"\']',source))
    return urls


def build(snapshot, output, source_origin, routing_evidence, asset_root=None, site_asset_root=None):
    snapshot = Path(snapshot).resolve(strict=True)
    # Resolve existing ancestor symlinks before comparing with live input roots.
    output = Path(output).resolve(strict=False)
    asset_root = Path(asset_root).resolve(strict=True) if asset_root else None
    site_asset_root = Path(site_asset_root).resolve(strict=True) if site_asset_root else None
    asset_roots = {prefix: root for prefix,root in (('video',asset_root),('site',site_asset_root)) if root}
    origin = urlsplit(source_origin)
    if origin.scheme != 'https' or not origin.netloc or origin.path not in ('','/') or origin.query or origin.fragment or origin.username:
        raise ValueError('EXPLICIT_HTTPS_SOURCE_ORIGIN_REQUIRED')
    source_origin = source_origin.rstrip('/')
    for source in (snapshot, *asset_roots.values()):
        if source and (output == source or source in output.parents or output in source.parents):
            raise ValueError('OUTPUT_MUST_BE_SEPARATE_FROM_INPUTS')
    if output.exists():
        raise ValueError('NEW_PRIVATE_OUTPUT_DIRECTORY_REQUIRED')
    captured_raw = read(snapshot, 'capture_manifest.json')
    captured = json.loads(captured_raw)
    def captured_file(name):
        raw = read(snapshot, name)
        if sha(raw) != captured['sha256'].get(name):
            raise ValueError('CAPTURE_HASH_MISMATCH:' + name)
        return raw
    rows = json.loads(captured_file('published_price_rows.json'))
    if not rows or len(rows) != captured['published_count'] or len({row['auto_number'] for row in rows}) != len(rows):
        raise ValueError('CAPTURED_PUBLISHED_SET_INVALID')
    route_raw = Path(routing_evidence).read_bytes()
    routes = json.loads(route_raw)
    if routes.get('conclusion') != {'served_home':'video/index.html',
            'site/index.html':'UNSERVED_LEGACY_PRESERVE_EXACT_BYTES','new_preview_route_present':False}:
        raise ValueError('EXPLICIT_OBSERVED_HOME_ROUTE_REQUIRED')
    for name in ('video/index.html','site/index.html','observed_wsgi_config.py','analitika_wsgi.py','uaart_bridge_wsgi.py'):
        if sha(captured_file(name)) != routes['source_sha256'].get(name):
            raise ValueError('ROUTING_EVIDENCE_CAPTURE_MISMATCH:' + name)
    legacy_redirect = prove_legacy_home_redirect(captured_file,routes,sha(route_raw))
    source_checks = []
    for name, patcher in (('yadro.py',patch_yadro),('stranica.py',patch_stranica),('catalog_design_guard.py',patch_catalog_design_guard)):
        patched, evidence = patcher(captured_file(name))
        compile(patched, name, 'exec')
        source_checks.append(evidence)
    payload = {}
    pages = []
    for folder in ('video','site'):
        for row in rows:
            name = folder + '/' + row['auto_number'] + '.html'
            before = captured_file(name)
            candidate, evidence = migrate_card(before.decode(), row)
            payload[name] = candidate.encode()
            pages.append(dict(path='/' + name, kind='CARD', **evidence))
        name = folder + '/katalog.html'
        candidate, evidence = migrate_catalog(captured_file(name).decode(), rows)
        payload[name] = candidate.encode()
        pages.append(dict(path='/' + name, kind='CATALOG', **evidence))
    candidate, evidence = migrate_home(captured_file('video/index.html').decode(), rows)
    payload['video/index.html'] = candidate.encode()
    pages.append(dict(path='/video/index.html', kind='HOME', **evidence))
    files = {'/' + name: {'storage':'bundle','path':'public/' + name,'sha256':sha(raw),
                         'bytes':len(raw),'content_type':'text/html; charset=utf-8'} for name, raw in payload.items()}
    # Only these observed public navigation and per-published-car diagnostic
    # paths may be added unchanged. Never crawl or expose arbitrary HTML.
    auxiliary_allowed = {folder + '/' + name for folder in ('video','site')
        for name in ('info.html','podbor.html',*(row['auto_number']+'-diag.html' for row in rows))}
    linked_pages, missing_pages, pending_pages, seen_pages = [], [], list(payload), set()
    bound_auxiliary_sources = []
    while pending_pages:
        referring = pending_pages.pop()
        for ref in sorted(References(payload[referring].decode()).links):
            parsed = urlsplit(urljoin(source_origin + '/' + referring,ref))
            if (parsed.scheme,parsed.netloc) != (origin.scheme,origin.netloc) or not parsed.path.endswith('.html'):
                continue
            name = unquote(parsed.path).lstrip('/')
            if name in payload or name == 'site/index.html' or name in seen_pages: continue
            seen_pages.add(name)
            if name not in auxiliary_allowed:
                missing_pages.append({'path':'/'+name,'referring_path':'/'+referring,
                                      'reason':'UNREVIEWED_LINKED_HTML_ROUTE'})
                continue
            try:
                if name in captured['sha256']:
                    raw = captured_file(name)
                    binding = {'type':'CAPTURE','path':name,'sha256':sha(raw)}
                    bound_auxiliary_sources.append((snapshot,name,sha(raw)))
                else:
                    prefix,asset_path = name.split('/',1)
                    if prefix not in asset_roots: raise FileNotFoundError(name)
                    raw = read(asset_roots[prefix],asset_path)
                    binding = {'type':'EXPLICIT_PUBLIC_ROOT','root':prefix,'path':asset_path,'sha256':sha(raw)}
                    bound_auxiliary_sources.append((asset_roots[prefix],asset_path,sha(raw)))
                raw.decode('utf-8')
                payload[name] = raw
                files['/'+name] = {'storage':'bundle','path':'public/'+name,'sha256':sha(raw),'bytes':len(raw),
                    'content_type':'text/html; charset=utf-8','protection':'UNCHANGED_LINKED_PUBLIC_HTML',
                    'source_binding':binding}
                linked_pages.append({'path':'/'+name,'referring_path':'/'+referring,'source_binding':binding,
                    'before_sha256':sha(raw),'after_sha256':sha(raw),'all_bytes_unchanged':True,
                    'browser_link_check':'NOT_RUN'})
                pending_pages.append(name)
            except (OSError,ValueError,UnicodeError):
                missing_pages.append({'path':'/'+name,'referring_path':'/'+referring,
                    'reason':'UNCHANGED_PUBLIC_HTML_NOT_CAPTURED_OR_UNREADABLE'})
    pending = [(name, ref) for name, raw in payload.items() for ref in References(raw.decode()).references]
    missing, external, seen = [], [], set()
    while pending:
        referring, ref = pending.pop()
        if ref.startswith(('data:','blob:','#')): continue
        absolute = urljoin(source_origin + '/' + referring, ref)
        parsed = urlsplit(absolute)
        key = (parsed.scheme, parsed.netloc, parsed.path)
        if key in seen: continue
        seen.add(key)
        if (parsed.scheme,parsed.netloc) != (origin.scheme,origin.netloc):
            external.append({'url':absolute,'status':'NOT_CAPTURED','kind':'THIRD_PARTY_REFERENCE'})
            continue
        name = unquote(parsed.path).lstrip('/')
        try: relative(name)
        except ValueError:
            missing.append({'path':parsed.path,'reason':'NON_CANONICAL_ASSET_REFERENCE'});continue
        extension = Path(name).suffix.lower()
        if extension not in ASSET_TYPES:
            missing.append({'path':'/' + name,'reason':'PUBLIC_ASSET_TYPE_NOT_ALLOWED'});continue
        item = None
        try:
            if name in captured['sha256']:
                raw = captured_file(name)
                payload[name] = raw
                item = {'storage':'bundle','path':'public/' + name}
            elif name.split('/',1)[0] in asset_roots and '/' in name:
                prefix,asset_path = name.split('/',1)
                raw = read(asset_roots[prefix], asset_path)
                item = {'storage':'asset','root':prefix,'path':asset_path}
            else:
                raise FileNotFoundError(name)
            item.update(sha256=sha(raw),bytes=len(raw),content_type=ASSET_TYPES[extension])
            files['/' + name] = item
            if extension == '.css':
                pending.extend((name, ref) for ref in css_references(raw.decode('utf-8')))
        except (OSError,ValueError,UnicodeError):
            missing.append({'path':'/' + name,'reason':'ASSET_MISSING_UNREADABLE_OR_UNBOUNDED'})
    matrix = [{'path':page['path'],'kind':page['kind'],'source_diff':'PASS_PRICE_ONLY_OR_UNCHANGED_HOME',
               'browser':[{ 'language':lang,'viewport':size,'status':'NOT_RUN'}
                          for lang in ('RU','UA','GE') for size in ('desktop','mobile')]} for page in pages]
    for root,name,expected in bound_auxiliary_sources:
        if sha(read(root,name)) != expected:
            raise ValueError('UNCHANGED_PUBLIC_HTML_SOURCE_CHANGED_DURING_BUILD:' + name)
    provenance = {'contract':CONTRACT,'source_capture_sha256':sha(captured_raw),
        'routing_evidence_sha256':sha(route_raw),'published_count':len(rows),
        'sources':source_checks,'pages':pages,'matrix':matrix,
        'excluded_protected_legacy':[{'path':'site/index.html','sha256':sha(captured_file('site/index.html')),
                                    'reason':'OBSERVED_UNSERVED_LEGACY_PRESERVED'}],
        'missing_assets':sorted(missing,key=lambda x:x['path']),'external_references':sorted(external,key=lambda x:x['url']),
        'linked_public_html':sorted(linked_pages,key=lambda x:x['path']),
        'missing_linked_html':sorted(missing_pages,key=lambda x:x['path']),
        'legacy_home_redirect_proof':legacy_redirect,
        'preview_gate':'NOT_PASSED','browser_run':False,'production_written':False,'activated':False}
    manifest = {'contract':CONTRACT,'source_origin':source_origin,
                'asset_roots':{prefix:str(root) for prefix,root in asset_roots.items()},
                'redirects':{'/site/index.html':{'status':'302 Found','location':'/video/index.html','proof':legacy_redirect}},
                'home_route':'/video/index.html','files':files,'provenance_sha256':sha(encoded(provenance)),
                'preview_gate':'NOT_PASSED'}
    output.mkdir(mode=0o700)
    for name, raw in payload.items(): write_new(output, 'public/' + name, raw)
    write_new(output,'provenance.json',encoded(provenance))
    write_new(output,'manifest.json',encoded(manifest))
    return {'output':str(output),'manifest_sha256':sha(encoded(manifest)),'pages':len(pages),
            'pinned_assets':len(files)-len(pages)-len(linked_pages),'missing_assets':len(missing),
            'unchanged_linked_pages':len(linked_pages),'missing_linked_pages':len(missing_pages),
            'external_references':len(external),'preview_gate':'NOT_PASSED','activated':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-origin',required=True)
    parser.add_argument('--routing-evidence',type=Path,required=True)
    parser.add_argument('--asset-root',type=Path)
    parser.add_argument('--site-asset-root',type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.snapshot,args.output,args.source_origin,args.routing_evidence,args.asset_root,args.site_asset_root),ensure_ascii=False))


if __name__=='__main__': main()
