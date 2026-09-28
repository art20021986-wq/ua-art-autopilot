"""Small edits to existing SEO and write functions, guarded by live hashes."""
import ast
import hashlib

SOURCE_SHA256 = {
    'publikaciya.py': '3fbddc9f7a87619fd851839d1f76c60ba3ca1e266a84653898a4427fe5f53121',
    'stranica.py': '4d710266abb2a92754ff3e3fc7de86c628760bee3c455dfbb177dedec113b1a1',
    'master_card.py': 'c99b6c0271586d4f8c56e4184528ab6f20541173be9a287d9d64661b4b7184b2',
    'yadro.py': '1c6bddccec30198179f9a179aa67ac8f2e40da1a794c87f2342150eb5d2ec793',
    'www_uaart_com_ua_wsgi.py': 'cb1e8b15223c429f2caa21c02be2bd8d23d2367560626ed5fba5e6a3e3417bcd',
}

ROOT_APPLICATION = '''def application(environ, start_response):
    method = str(environ.get('REQUEST_METHOD', 'GET')).upper()
    if environ.get('PATH_INFO', '/') == '/' and method in ('GET', 'HEAD'):
        query = str(environ.get('QUERY_STRING', ''))
        location = CEL + ('?' + query if query and not any(c in query for c in '\\r\\n') else '')
        start_response('301 Moved Permanently', [
            ('Location', location), ('Content-Length', '0'),
            ('Cache-Control', 'public, max-age=300'),
        ])
        return []
    body = ('<!doctype html><html lang="uk"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Сторінку не знайдено — UA ART COMPANY</title>'
            '<body><main><h1>Сторінку не знайдено</h1>'
            '<p>Перевірте адресу або перейдіть до каталогу автомобілів.</p>'
            '<a href="/video/katalog.html">Відкрити каталог</a></main></body></html>').encode('utf-8')
    start_response('404 Not Found', [
        ('Content-Type', 'text/html; charset=utf-8'),
        ('Content-Length', str(len(body))), ('Cache-Control', 'no-cache'),
    ])
    return [] if method == 'HEAD' else [body]
'''


def replace_function(source, name, transform, first=False):
    functions = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name]
    if not functions or not first and len(functions) != 1:
        raise ValueError('FUNCTION_COUNT:' + name)
    node = functions[0]
    lines = source.splitlines(keepends=True)
    old = ''.join(lines[node.lineno-1:node.end_lineno]).rstrip('\n')
    new = transform(old)
    lines[node.lineno-1:node.end_lineno] = [new.rstrip('\n')+'\n']
    return ''.join(lines)


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('ANCHOR_COUNT:' + old[:70])
    return source.replace(old, new, 1)


def seo_generator(source):
    def normalizer(old):
        end = '    return source'
        if not old.endswith(end):
            raise ValueError('NORMALIZER_RETURN')
        return old[:-len(end)] + ('    from ua_seo_metadata import normalize\n'
                                 '    return normalize(source, file_name)')
    source = replace_function(source, '_ua_seo068_normalize', normalizer)
    return replace_function(source, '_ua_seo068_core_path', lambda old:
        'def _ua_seo068_core_path(source):\n'
        '    from ua_seo_metadata import page_name\n'
        '    return page_name(source)')


def atomic_writer(old, argument, temporary):
    old = replace_once(old, '    %s = put +' % temporary,
        '    from ua_seo_metadata import normalize\n'
        '    from ua_seo_sitemap import sync_after_write\n'
        '    %s = normalize(%s, put)\n' % (argument, argument) +
        '    %s = put +' % temporary)
    return replace_once(old, '    os.replace(%s, put)' % temporary,
        '    os.replace(%s, put)\n    sync_after_write(put, %s)' % (temporary, argument))


def routing(source):
    source = replace_function(source, 'application', lambda old: ROOT_APPLICATION, first=True)
    def payload(old):
        node = ast.parse(old).body[0]
        matches = [n for n in node.body if isinstance(n, ast.If) and "'/sitemap.xml'" in ast.get_source_segment(old, n.test)]
        if len(matches) != 1:
            raise ValueError('SITEMAP_ROUTE_COUNT')
        item = matches[0]
        lines = old.splitlines(keepends=True)
        lines[item.lineno-1:item.end_lineno] = [
            "    if path == '/sitemap.xml':\n"
            "        from ua_seo_sitemap import sitemap\n"
            "        return sitemap('/home/Carix/video'), 'application/xml; charset=utf-8'\n"]
        return ''.join(lines)
    return replace_function(source, '_ua_seo068_wsgi_payload', payload)


def build(sources):
    if set(sources) != set(SOURCE_SHA256):
        raise ValueError('SOURCE_SET')
    output = {}
    for name, value in sources.items():
        if hashlib.sha256(value).hexdigest() != SOURCE_SHA256[name]:
            raise ValueError('SOURCE_CHANGED:' + name)
        source = value.decode('utf-8')
        if name in ('stranica.py', 'master_card.py', 'yadro.py'):
            source = seo_generator(source)
        if name == 'publikaciya.py':
            source = replace_function(source, '_zapisat_atomarno',
                lambda old: atomic_writer(old, 'tekst', 'vrem'), first=True)
        if name == 'yadro.py':
            source = replace_function(source, 'zapisat_atomarno',
                lambda old: atomic_writer(old, 'soderzhimoe', 'vremenno'), first=True)
        if name == 'www_uaart_com_ua_wsgi.py':
            source = routing(source)
        compile(source, name, 'exec')
        output[name] = source.encode('utf-8')
    return output
