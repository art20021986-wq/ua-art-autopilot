#!/usr/bin/env python3
"""Stage exact public candidate bytes, optionally switch ONLY dedicated Preview.

No business source/DB/HTML write, network, subprocess, service reload or app import.
Every operation uses a new private work directory and immutable journal events.
Stage and switch are separate invocations. A repeated switch intent never writes
again: inspect actual WSGI outcome first. This helper never issues Preview PASS.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import ast
from datetime import datetime, timezone
import fcntl
import hashlib
from html.parser import HTMLParser
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
from urllib.parse import urljoin, urlsplit, unquote
import zipfile

PARENT = Path('/home/Carix/autopilot_inbox/cloud')
TARGET = Path('/var/www/carix_pythonanywhere_com_wsgi.py')
PRODUCTION = Path('/var/www/www_uaart_com_ua_wsgi.py')
PUBLIC = Path('/home/Carix/video')
ORIGIN = 'https://carix.pythonanywhere.com'
PRODUCTION_ORIGIN = 'https://www.uaart.com.ua'
CONTRACT = 'UA-ART-V5-PROTECTED-PREVIEW-1'
RUNTIME = {
 'common.py':'cb30a2b61d28438a9844e79b1bc8550f92885dab8b6dc0d76c2789827c9893fa',
 'routing_proof.py':'fd483b95d5b0a2bc92146d1c137decb9e368706248b7469c9c1243a3fd622c5d',
 'viewport_harness.py':'3b6830eff2d35ed94688707018e606b0d404a00bcb4dce80fa0dadab89b0bae1',
 'wsgi_entry.py':'7b7b9056b55c41a5031e430cf470b10ae66fd812f792a3cd65cb931c1ced02e7',
 'wsgi_preview.py':'191989bd07d0eea55782671778b8bb2dd1b531eda88a561bbc4b229afcd7d289'}
SOURCE_ROUTING = {
 'observed_wsgi_config.py':'3067d39ec9c2eb976114afc6744e2c34b088a8414e98eb3e33e0a47c1849e308',
 'analitika_wsgi.py':'a73be46099596322dcd607ecadd56140d45483a5ad38f1c1a0a0e395cfc8bc94',
 'uaart_bridge_wsgi.py':'b0c93d88d67e8c285c1bffb40bd6f2e40c2779af7a01cebd6beab4beda685150'}
LIMIT = 32*1024*1024


def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path, expected=None, limit=LIMIT):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path, 'NO_SYMLINK_INPUT')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_size <= limit, 'BOUNDED_REGULAR_INPUT')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit+1)
        last = os.fstat(fd)
        stamp = lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        require(stamp(first) == stamp(last) == stamp(path.lstat()) and len(raw) <= limit, 'INPUT_CHANGED_DURING_READ')
        require(expected is None or sha(raw) == expected, 'INPUT_SHA256_MISMATCH:' + path.name)
        return raw
    finally:
        os.close(fd)


def syncdir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, raw):
    require(path.parent.resolve(strict=True) == path.parent, 'NO_SYMLINK_OUTPUT_PARENT')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    syncdir(path.parent)


def event(work, name, obj):
    write(work / name, encoded(obj))


def makeparent(path, work):
    require(path.is_relative_to(work), 'OUTPUT_OUTSIDE_PRIVATE_WORK')
    if not path.exists():
        makeparent(path.parent, work)
        path.mkdir(mode=0o700)
    require(path.resolve(strict=True) == path and stat.S_IMODE(path.stat().st_mode) == 0o700,
            'PRIVATE_NONSYMLINK_DIRECTORY_REQUIRED')


def relative(value):
    require(type(value) is str and not value.startswith('/') and not any(p in ('','.','..') for p in value.split('/'))
            and not any(c in value for c in ('\\','%','\x00')), 'CANONICAL_PUBLIC_RELATIVE_PATH_REQUIRED')
    return value


class References(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.assets, self.links = set(), set()
        self.style = self.script = False
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.add(attrs['href'])
        self.style = self.style or tag == 'style'
        if tag == 'script':
            self.script = not attrs.get('src') and attrs.get('type','').lower() in ('','text/javascript','application/javascript','module')
        if attrs.get('style'):
            self.assets.update(cssrefs(attrs['style']))
        if tag in ('script','img','source','video','audio'):
            self.assets.update(attrs[k] for k in ('src','poster') if attrs.get(k))
            self.assets.update(v.strip().split()[0] for v in attrs.get('srcset','').split(',') if v.strip())
        if tag == 'link' and set(attrs.get('rel','').split()) & {'stylesheet','icon','preload'} and attrs.get('href'):
            self.assets.add(attrs['href'])
    def handle_endtag(self, tag):
        if tag == 'style': self.style = False
        if tag == 'script': self.script = False
    def handle_data(self, data):
        if self.style:
            self.assets.update(cssrefs(data))
        if self.script and re.search(r'\b(?:var|let|const)\s+kadry\b',data):
            prefix = re.match(r'\s*(?:var|let|const)\s+kadry\s*=\s*',data)
            require(prefix is not None and len(re.findall(r'\b(?:var|let|const)\s+kadry\b',data)) == 1,
                    'EXPLICIT_LITERAL_GALLERY_REQUIRED')
            paths, end = json.JSONDecoder().raw_decode(data[prefix.end():])
            require(type(paths) is list and data[prefix.end()+end:].lstrip().startswith(';') and all(
                type(p) is str and re.fullmatch(r'(?:foto/UA-[0-9]{4,}/[0-9]{3}|diag/UA-[0-9]{4,}/m/[0-9]{2})\.jpg',p)
                for p in paths), 'EXPLICIT_LITERAL_GALLERY_PATHS_REQUIRED')
            self.assets.update(paths)


def cssrefs(source):
    return [m[1] for m in re.findall(r'url\(\s*([\"\']?)(.*?)\1\s*\)',source)] + re.findall(r'@import\s+[\"\']([^\"\']+)[\"\']',source)


def publicroute(base, ref):
    if ref.startswith(('data:','blob:','#')):
        return None
    url = urlsplit(urljoin(PRODUCTION_ORIGIN+'/'+base,ref))
    if (url.scheme,url.netloc) != ('https','www.uaart.com.ua'):
        return None
    name = unquote(url.path).lstrip('/')
    relative(name)
    return name


def retained_analytics_asset(config, manifest, args, observer_sha256):
    # The existing reviewed Preview serves this one captured public script.
    # Retain its pinned bytes; never import Production analytics or widen roots.
    item = manifest.get('files',{}).get('/ua/a.js')
    require(type(item) is dict and set(item) == {'storage','path','sha256','bytes','content_type'} and
            item.get('storage') == 'bundle' and item.get('path') == 'public/ua/a.js' and
            item.get('content_type') == 'application/javascript; charset=utf-8' and
            type(item.get('sha256')) is str and re.fullmatch(r'[0-9a-f]{64}',item['sha256']) and
            type(item.get('bytes')) is int and 0 <= item['bytes'] <= LIMIT,
            'EXACT_EXISTING_ANALYTICS_CAPTURE_REQUIRED')
    raw = read(Path(config['bundle_root'])/item['path'],item['sha256'])
    require(len(raw) == item['bytes'], 'EXISTING_ANALYTICS_CAPTURE_LENGTH_MISMATCH')
    # The routing wrapper delegates to analitika_yadro.SKRIPT: its own source
    # pin cannot prove the historical capture still equals the current response.
    observed_raw = read(args.analytics_observation,args.analytics_observation_sha256)
    observed = json.loads(observed_raw)
    require(observed.get('contract') == 'PR114-CURRENT-PUBLIC-ANALYTICS-OBSERVATION-1' and
            observed.get('core_observer_sha256') == observer_sha256 and
            observed.get('url') == observed.get('final_url') == PRODUCTION_ORIGIN+'/ua/a.js' and
            observed.get('http_status') == 200 and
            observed.get('content_type') in ('application/javascript','application/javascript; charset=utf-8') and
            observed.get('sha256') == item['sha256'] and observed.get('bytes') == len(raw),
            'CURRENT_PUBLIC_ANALYTICS_RESPONSE_BINDING_REQUIRED')
    observed_at = datetime.fromisoformat(observed['observed_at_utc'])
    require(observed_at.tzinfo is not None and
            0 <= (datetime.now(timezone.utc)-observed_at).total_seconds() <= 900,
            'FRESH_PUBLIC_ANALYTICS_OBSERVATION_REQUIRED')
    return dict(item), raw, sha(observed_raw)


def oldstate(config_path, wsgi_pin, config_pin):
    wsgi = read(TARGET, wsgi_pin)
    config_path = Path(config_path).absolute()
    require(config_path.is_relative_to(PARENT), 'EXISTING_PRIVATE_CONFIG_REQUIRED')
    raw = read(config_path, config_pin)
    require(not stat.S_IMODE(config_path.stat().st_mode) & 0o077, 'PRIVATE_EXISTING_CONFIG_REQUIRED')
    config = json.loads(raw)
    require(config.get('contract') == CONTRACT and config.get('preview_origin') == ORIGIN,
            'EXACT_DEDICATED_PREVIEW_CONFIG_REQUIRED')
    values = [n.value.value for n in ast.walk(ast.parse(wsgi)) if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Constant) and isinstance(n.value.value,str) and any(
            isinstance(t,ast.Subscript) and isinstance(t.slice,ast.Constant) and t.slice.value == 'UA_ART_PREVIEW_CONFIG'
            for t in n.targets)]
    require(values == [str(config_path)], 'CURRENT_WSGI_CONFIG_BINDING_REQUIRED')
    access = {'access_policy'} if config.get('access_policy') == 'PUBLIC_READ_ONLY_PREVIEW_OWNER_AUTHORIZED' else {'basic_auth'}
    require(set(config) == {'contract','preview_origin','bundle_root','manifest_sha256'} | access,
            'EXACT_CURRENT_ACCESS_POLICY_REQUIRED')
    oldbundle = Path(config['bundle_root'])
    require(oldbundle.is_absolute() and oldbundle.is_relative_to(PARENT), 'PRIVATE_EXISTING_BUNDLE_REQUIRED')
    oldmanifest = json.loads(read(oldbundle/'manifest.json', config['manifest_sha256']))
    return wsgi, config, oldmanifest


def load_runtime(work):
    for name, pin in RUNTIME.items():
        read(work/'runtime'/name, pin)
    sys.path.insert(0,str(work/'runtime'))
    for name in ('common','routing_proof','viewport_harness','wsgi_preview'):
        existing = sys.modules.get(name)
        require(existing is None, 'RUNTIME_MODULE_ALREADY_IMPORTED')
    import common, viewport_harness, wsgi_preview
    return common, viewport_harness, wsgi_preview


def verify_bundle(work, deadline):
    common, harness, runtime = load_runtime(work)
    app = runtime.Preview(work/'config.json')
    config = json.loads(read(work/'config.json'))
    checked = {}
    # Direct file pins are validated independently of access policy. Basic
    # authentication is retained; no credential is read or synthesized here.
    for route, item in sorted(app.files.items()):
        require(time.monotonic() < deadline, 'BOUNDED_STAGE_TIME_EXCEEDED')
        root = app.root if item['storage'] == 'bundle' else app.asset_roots[item['root']]
        raw = read(root/item['path'],item['sha256'])
        require(len(raw) == item['bytes'], 'RESOURCE_LENGTH_MISMATCH')
        checked[route] = item['sha256']
    denied = []
    for route in ('/config.json','/manifest.json','/provenance.json','/cars.db','/db.py','/uaart-bridge','/ua/a/e','/video/../config.json','/site/UA-0001.html'):
        status = []
        body = b''.join(app({'REQUEST_METHOD':'GET','PATH_INFO':route,'QUERY_STRING':'','HTTP_HOST':urlsplit(ORIGIN).netloc,
                            'wsgi.url_scheme':'https'},lambda code,headers:status.append(code)))
        require(status and status[0].split()[0] in ('400','401','404'), 'PRIVATE_ROUTE_NOT_DENIED')
        denied.append(route)
    return {'status':'PASS_IN_PROCESS_EXACT_PUBLIC_BYTES_ONLY','pinned_resources':len(checked),
            'resources_sha256':sha(encoded(checked)),'private_routes_denied':len(denied),
            'browser_run':False,'runtime_worker_binding':'NOT_OBSERVED',
            'access_policy_preserved':'access_policy' if 'access_policy' in config else 'basic_auth'}


def stage(args):
    require(sys.flags.isolated and sys.dont_write_bytecode, 'RUN_PYTHON_WITH_I_B')
    require(re.fullmatch(r'[a-z0-9][a-z0-9_-]{7,70}', args.operation_id), 'UNIQUE_OPERATION_ID_REQUIRED')
    require(PARENT.resolve(strict=True) == PARENT, 'EXACT_EXISTING_PRIVATE_PARENT_REQUIRED')
    work = PARENT / ('pr114-preview-'+args.operation_id)
    require(not work.exists(), 'EXISTING_OPERATION_INSPECT_FIRST_NO_REPEAT')
    package_raw = read(args.package, args.package_sha256, 16*1024*1024)
    obs_raw = read(args.observer,args.observer_sha256)
    obs = json.loads(obs_raw)
    expected_stability = {'database_and_published_rows','source_hashes_and_stamps','routing_hashes_and_stamps',
        'core_html_hashes_and_stamps','diagnostic_hashes_and_stamps','supporting_html_hashes_and_stamps',
        'runtime_modules_hashes_and_stamps','known_runtime_source_overlap','referenced_media_metadata_only','home_routing_equal_core'}
    require(obs.get('contract') == 'PR114-POINT4-CORE-READONLY-OBSERVATION-1' and
            obs.get('status') == 'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION' and obs.get('export_completed') is True and
            not obs.get('blockers') and set(obs.get('stability',{})) == expected_stability and
            all(value is True for value in obs['stability'].values()) and obs.get('database') == obs.get('second_database') and
            obs.get('schema_sha256') == obs.get('second_schema_sha256'), 'CURRENT_TERMINAL_CORE_STABLE_OBSERVATION_REQUIRED')
    oldwsgi, oldconfig, oldmanifest = oldstate(args.existing_config,args.expected_wsgi_sha256,args.expected_config_sha256)
    prod = sha(read(PRODUCTION))
    require(prod == SOURCE_ROUTING['observed_wsgi_config.py'], 'PRODUCTION_ROUTE_SOURCE_DRIFT')
    for name,pin in SOURCE_ROUTING.items():
        require(obs['routing_sources'][name]['sha256'] == pin, 'OBSERVED_ROUTING_SOURCE_DRIFT')
    deadline = time.monotonic()+args.max_seconds
    with zipfile.ZipFile(io.BytesIO(package_raw)) as packed:
        names = packed.namelist()
        require(len(names) == len(set(names)) and len(names) < 200, 'BOUNDED_UNIQUE_ZIP_MEMBERS_REQUIRED')
        for info in packed.infolist():
            relative(info.filename)
            require(info.file_size <= LIMIT and not info.is_dir() and not stat.S_ISLNK(info.external_attr >> 16), 'BOUNDED_REGULAR_ZIP_MEMBER_REQUIRED')
        require(sum(info.file_size for info in packed.infolist()) <= 16*1024*1024, 'BOUNDED_TOTAL_ZIP_EXPANSION_REQUIRED')
        package = json.loads(packed.read('package_manifest.json'))
        require(package.get('contract') == 'PR114-EXACT-PUBLIC-PREVIEW-PACKAGE-1' and package.get('observer_sha256') == sha(obs_raw),
                'PACKAGE_CURRENT_OBSERVER_BINDING_REQUIRED')
        codes = obs['database']['published_codes']
        require(package.get('published_codes') == codes and len(codes) == len(set(codes)) and
                all(re.fullmatch(r'UA-[0-9]{4,}',c) for c in codes), 'EXACT_CURRENT_PUBLISHED_SET_REQUIRED')
        expected_html = {f'{folder}/{code}.html' for folder in ('site','video') for code in ['index','katalog',*codes]}
        require(set(package['candidate_html_sha256']) == expected_html and package['runtime_sha256'] == RUNTIME,
                'EXACT_PACKAGE_HTML_RUNTIME_CLOSURE_REQUIRED')
        require(set(names) == {'package_manifest.json',*('candidate/'+n for n in expected_html),*('runtime/'+n for n in RUNTIME)},
                'ONLY_PUBLIC_HTML_AND_REVIEWED_RUNTIME_ALLOWED')
        blobs = {name:packed.read(name) for name in names}
    require(sha(read(args.package)) == sha(package_raw), 'PACKAGE_CHANGED_DURING_READ')
    for name,pin in package['candidate_html_sha256'].items():
        require(sha(blobs['candidate/'+name]) == pin, 'CANDIDATE_PAGE_PIN_MISMATCH')
    for name,pin in RUNTIME.items():
        require(sha(blobs['runtime/'+name]) == pin, 'UNCHANGED_REVIEWED_RUNTIME_REQUIRED')
    work.mkdir(mode=0o700)
    syncdir(PARENT)
    event(work,'00-stage-intent.json',{'operation_id':args.operation_id,'started_at':now(),'self_sha256':sha(read(__file__)),
          'package_sha256':sha(package_raw),'observer_sha256':sha(obs_raw),'old_wsgi_sha256':sha(oldwsgi),
          'old_config_sha256':args.expected_config_sha256,'old_config_path':args.existing_config,
          'production_wsgi_sha256':prod,'scope':'DEDICATED_PREVIEW_ONLY','business_writes':False})
    write(work/'prior-preview-wsgi.backup.py',oldwsgi)
    for name in RUNTIME:
        makeparent(work/'runtime',work)
        write(work/'runtime'/name,blobs['runtime/'+name])
    # Safe isolated import: unchanged public runtime only, no production imports.
    spec = importlib.util.spec_from_file_location('preview_common_metadata',work/'runtime/common.py')
    metadata = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metadata)
    files, html, linked, dependencies, external = {}, {}, [], {}, set()
    retained_assets = {}
    def add_html(name, raw, protection=None):
        target = work/'candidate'/'public'/name
        makeparent(target.parent,work)
        write(target,raw)
        item = {'storage':'bundle','path':'public/'+name,'sha256':sha(raw),'bytes':len(raw),'content_type':'text/html; charset=utf-8'}
        if protection:
            item.update(protection='UNCHANGED_LINKED_PUBLIC_HTML',source_binding={'type':'CAPTURE','path':name,'sha256':sha(raw)})
        files['/'+name] = item
        html[name] = raw
    for name in sorted(expected_html):
        raw = blobs['candidate/'+name]
        if name.startswith('video/'):
            add_html(name,raw)
        else:
            target = work/'candidate'/'offline'/name
            makeparent(target.parent,work)
            write(target,raw)
    allowed = {'video/info.html','video/podbor.html',*('video/'+c+'-diag.html' for c in codes)}
    pending, seen = list(html), set()
    while pending:
        name = pending.pop()
        for ref in References(html[name].decode()).links:
            target = publicroute(name,ref)
            if target is None or not target.endswith('.html') or target in html or target == 'site/index.html':
                continue
            require(target in allowed, 'UNREVIEWED_LINKED_PUBLIC_HTML:'+target)
            raw = read(PUBLIC/target.split('/',1)[1])
            observed = obs.get('diagnostic_html',{}).get(target) or obs.get('supporting_html',{}).get(target)
            require(observed is not None and observed['sha256'] == sha(raw), 'LINKED_HTML_CURRENT_CAPTURE_REQUIRED:'+target)
            dependencies[target] = sha(raw)
            add_html(target,raw,True)
            linked.append(target)
            pending.append(target)
    pending = [(name,ref) for name,raw in html.items() for ref in References(raw.decode()).assets]
    while pending:
        require(time.monotonic() < deadline, 'BOUNDED_STAGE_TIME_EXCEEDED')
        name,ref = pending.pop()
        target = publicroute(name,ref)
        if target is None:
            if not ref.startswith(('data:','blob:','#')): external.add(ref)
            continue
        if target in seen: continue
        seen.add(target)
        if target == 'ua/a.js':
            item, raw, observation_pin = retained_analytics_asset(oldconfig,oldmanifest,args,sha(obs_raw))
            output = work/'candidate'/item['path']
            makeparent(output.parent,work)
            write(output,raw)
            files['/'+target] = item
            retained_assets[target] = {'sha256':sha(raw),'source_manifest_sha256':oldconfig['manifest_sha256'],
                'capture_type':'HISTORICAL_CAPTURE_MATCHED_TO_CURRENT_RESPONSE',
                'current_response_observation_sha256':observation_pin}
            continue
        require(target.startswith('video/'), 'UNSERVED_PUBLIC_ASSET_ROUTE:'+target)
        ext = Path(target).suffix.lower()
        require(ext in metadata.ASSET_TYPES, 'UNSUPPORTED_ASSET_TYPE:'+target)
        raw = read(PUBLIC/target.split('/',1)[1])
        files['/'+target] = {'storage':'asset','root':'video','path':target.split('/',1)[1],
                             'sha256':sha(raw),'bytes':len(raw),'content_type':metadata.ASSET_TYPES[ext]}
        dependencies[target] = sha(raw)
        if ext == '.css': pending += [(target,r) for r in cssrefs(raw.decode())]
    # The prior redirect proof is retained only under unchanged reviewed routing
    # source pins. Current hosting-map readback is a separate root-owned input.
    require(oldmanifest.get('redirects',{}).get('/site/index.html') is not None, 'REVIEWED_LEGACY_REDIRECT_REQUIRED')
    sys.path.insert(0,str(work/'runtime'))
    import viewport_harness
    harness = viewport_harness.render(files)
    route = viewport_harness.HARNESS_ROUTE
    add_html(route[1:],harness)
    files[route]['protection'] = 'AUTHENTICATED_VIEWPORT_HARNESS'
    harness_spec = viewport_harness.specification(files)
    provenance = {'contract':CONTRACT,'source_capture_sha256':sha(obs_raw),'candidate_package_sha256':sha(package_raw),
        'canonical_candidate_manifest_sha256':package['canonical_candidate_manifest_sha256'],
        'published_count':len(codes),'exact_candidate_html_sha256':package['candidate_html_sha256'],
        'linked_public_html':linked,'external_references':sorted(external),'missing_assets':[], 'missing_linked_html':[],
        'retained_public_asset_captures':retained_assets,
        'preview_gate':'NOT_PASSED','browser_run':False,'production_written':False,'activated':False,
        'routing_scope':'Unchanged retained source proof; fresh hosting map observations remain separately required.'}
    manifest = {'contract':CONTRACT,'source_origin':PRODUCTION_ORIGIN,'asset_roots':{'video':str(PUBLIC)},
        'files':files,'home_route':'/video/index.html','viewport_harness':harness_spec,
        'redirects':oldmanifest['redirects'],'provenance_sha256':sha(encoded(provenance)), 'preview_gate':'NOT_PASSED'}
    if 'unserved_site_prefix_proof' in oldmanifest:
        manifest['unserved_site_prefix_proof'] = oldmanifest['unserved_site_prefix_proof']
    write(work/'candidate'/'provenance.json',encoded(provenance))
    write(work/'candidate'/'manifest.json',encoded(manifest))
    config = dict(oldconfig,bundle_root=str(work/'candidate'),manifest_sha256=sha(encoded(manifest)))
    write(work/'config.json',encoded(config))
    code = ('import os, sys\nsys.dont_write_bytecode = True\nsys.path.insert(0, '+repr(str(work/'runtime'))+')\n'
            'os.environ["UA_ART_PREVIEW_CONFIG"] = '+repr(str(work/'config.json'))+'\nfrom wsgi_entry import application\n').encode()
    compile(code,'dedicated-preview-wsgi','exec')
    write(work/'candidate-preview-wsgi.py',code)
    # Permit runtime verifier to import the already pinned harness once.
    del sys.modules['viewport_harness']
    validation = verify_bundle(work,deadline)
    for name,pin in dependencies.items():
        # Asset-root bytes were hashed when admitted and again by verifier.
        # Auxiliary HTML verifier reads its private copy, so re-read that
        # original explicitly here without a redundant third media pass.
        if not name.endswith('.html'):
            continue
        require(time.monotonic() < deadline, 'BOUNDED_STAGE_TIME_EXCEEDED')
        read(PUBLIC/name.split('/',1)[1],pin)
    oldstate(args.existing_config,args.expected_wsgi_sha256,args.expected_config_sha256)
    read(PRODUCTION,prod)
    receipt = {'contract':'PR114-EXACT-DEDICATED-PREVIEW-STAGE-1','operation_id':args.operation_id,'finished_at':now(),
        'status':'STAGED_NOT_SWITCHED_NOT_RELOADED_NOT_BROWSER_ACCEPTED','work':str(work),
        'package_sha256':sha(package_raw),'observer_sha256':sha(obs_raw),'manifest_sha256':sha(encoded(manifest)),
        'config_sha256':sha(encoded(config)),'candidate_wsgi_sha256':sha(code),'old_wsgi_sha256':sha(oldwsgi),
        'old_config_sha256':args.expected_config_sha256,'old_config_path':args.existing_config,
        'production_wsgi_sha256':prod,'resources':len(files),'linked_pages':len(linked),'served_pages':len(codes)+2,
        'validation':validation,'access_policy_preserved':True,'public_root_directory_serving':False,
        'business_writes':False,'preview_gate':'NOT_PASSED','reload_requested':False}
    event(work,'01-stage-receipt.json',receipt)
    print(encoded(receipt).decode())


def inspect(work):
    intent = json.loads(read(work/'00-stage-intent.json'))
    actual = sha(read(TARGET))
    candidate_path = work/'candidate-preview-wsgi.py'
    candidate = sha(read(candidate_path)) if candidate_path.exists() else None
    return {'observed_at':now(),'work':str(work),'actual_wsgi_sha256':actual,'candidate_wsgi_sha256':candidate,
            'old_wsgi_sha256':intent['old_wsgi_sha256'],
            'actual_outcome':'CANDIDATE_PRESENT' if actual == candidate else 'OLD_PRESENT' if actual == intent['old_wsgi_sha256'] else 'UNKNOWN_FOREIGN_BYTES',
            'switch_intent_exists':(work/'02-switch-intent.json').exists(),
            'switch_receipt_exists':(work/'03-switch-receipt.json').exists(),'reload_observed':False,'writes_performed':False}


def switch(args):
    require(sys.flags.isolated and sys.dont_write_bytecode, 'RUN_PYTHON_WITH_I_B')
    work = Path(args.work).absolute()
    require(work.parent == PARENT and work.name.startswith('pr114-preview-') and work.resolve(strict=True) == work,
            'EXACT_PRIVATE_OPERATION_WORK_REQUIRED')
    require(stat.S_IMODE(work.stat().st_mode) == 0o700, 'PRIVATE_OPERATION_WORK_REQUIRED')
    with open(work/'00-stage-intent.json','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        outcome = inspect(work)
        if args.action == 'inspect':
            print(encoded(outcome).decode()); return
        require(not outcome['switch_intent_exists'], 'EXISTING_SWITCH_INTENT_INSPECT_ACTUAL_NO_REPEAT:'+outcome['actual_outcome'])
        receipt = json.loads(read(work/'01-stage-receipt.json',args.stage_receipt_sha256))
        require(receipt['status'] == 'STAGED_NOT_SWITCHED_NOT_RELOADED_NOT_BROWSER_ACCEPTED', 'COMPLETED_STAGE_REQUIRED')
        oldstate(receipt['old_config_path'],receipt['old_wsgi_sha256'],receipt['old_config_sha256'])
        read(PRODUCTION,receipt['production_wsgi_sha256'])
        read(work/'config.json',receipt['config_sha256'])
        read(work/'candidate'/'manifest.json',receipt['manifest_sha256'])
        code = read(work/'candidate-preview-wsgi.py',receipt['candidate_wsgi_sha256'])
        validation = verify_bundle(work,time.monotonic()+args.max_seconds)
        event(work,'02-switch-intent.json',{'started_at':now(),'stage_receipt_sha256':args.stage_receipt_sha256,
            'expected_old_wsgi_sha256':receipt['old_wsgi_sha256'],'candidate_wsgi_sha256':sha(code),
            'target':str(TARGET),'reload_requested':False})
        temporary = TARGET.parent / (TARGET.name+'.'+work.name+'.tmp')
        write(temporary,code)
        # Cooperative single-author switch: final comparison immediately before
        # atomic replacement. No claim of a filesystem compare-and-swap syscall.
        oldstate(receipt['old_config_path'],receipt['old_wsgi_sha256'],receipt['old_config_sha256'])
        os.replace(temporary,TARGET)
        syncdir(TARGET.parent)
        read(TARGET,receipt['candidate_wsgi_sha256'])
        read(PRODUCTION,receipt['production_wsgi_sha256'])
        result = {'contract':'PR114-EXACT-DEDICATED-PREVIEW-SWITCH-1','finished_at':now(),
            'status':'DEDICATED_WSGI_SWITCHED_PENDING_RELOAD_AND_BROWSER','work':str(work),
            'stage_receipt_sha256':args.stage_receipt_sha256,'actual_wsgi_sha256':sha(read(TARGET)),
            'manifest_sha256':receipt['manifest_sha256'],'validation':validation,
            'business_writes':False,'reload_requested':False,'preview_gate':'NOT_PASSED'}
        event(work,'03-switch-receipt.json',result)
        print(encoded(result).decode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-sha256',required=True)
    sub = parser.add_subparsers(dest='action',required=True)
    stageparser = sub.add_parser('stage')
    for name in ('operation-id','package','package-sha256','observer','observer-sha256','existing-config','expected-wsgi-sha256','expected-config-sha256',
                 'analytics-observation','analytics-observation-sha256'):
        stageparser.add_argument('--'+name,required=True)
    stageparser.add_argument('--max-seconds',type=int,default=180)
    for action in ('switch','inspect'):
        p = sub.add_parser(action)
        p.add_argument('--work',required=True)
        p.add_argument('--max-seconds',type=int,default=180)
        p.add_argument('--stage-receipt-sha256',required=action == 'switch')
    args = parser.parse_args()
    require(re.fullmatch(r'[0-9a-f]{64}',args.self_sha256) is not None and sha(read(__file__)) == args.self_sha256,
            'PINNED_STAGING_HELPER_REQUIRED')
    require(1 <= args.max_seconds <= 300,'BOUNDED_TIME_REQUIRED')
    def bounded(signum, frame):
        raise TimeoutError('TOTAL_PREVIEW_OPERATION_TIME_BOUND_INSPECT_ACTUAL_NO_REPEAT')
    signal.signal(signal.SIGALRM,bounded)
    signal.setitimer(signal.ITIMER_REAL,args.max_seconds)
    try:
        if args.action == 'stage': stage(args)
        else: switch(args)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)


if __name__ == '__main__':
    main()
