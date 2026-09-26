"""Build exact-source gallery fixes; never install or mutate production here."""
import ast
import hashlib

SOURCES = {
 'publikaciya.py': ('296c389b477472032bad714e41f12bfa4b7e47ad784ac6900ba55f136d939c72', None, "\n# Validate completed public card before existing transaction writes any HTML.\n_CRM_CONSISTENCY_MASTER = _master\ndef _master(kod):\n    html, diag, card = _CRM_CONSISTENCY_MASTER(kod)\n    if html is None or card is None:\n        raise RuntimeError('CRM public card missing')\n    from public_fields import verify_core_fields\n    from public_media import verify_photo_structure\n    from crm_gallery import gallery_paths\n    verify_core_fields(html, card)\n    verify_photo_structure(html, card, gallery_paths(card))\n    return html, diag, card\n"),
 'stranica.py': ('cdb532f36e6e8fd17c7f933ad347a8bb0bcd8c00644d9c8ea7d9e3ddbb6ae687', 'kadry_mashiny', '''def kadry_mashiny(m):
    from crm_gallery import gallery_paths
    return gallery_paths(m)
'''),
 'master_card.py': ('27e32420bbec9f1e0a25621e1c20dda20944537daa40c1ccac574689cd6c3f6e', 'vybrat_glavnoe', '''def vybrat_glavnoe(kod, m=None):
    from crm_gallery import gallery_paths
    paths = gallery_paths(m if m is not None else dannye(kod))
    if not paths:
        raise RuntimeError('No public CRM photo available for cover')
    return os.path.basename(paths[0]), 'CRM public gallery'
'''),
 'ua_crm_public_sync.py': ('31e47106dc65ac1a2e013708bd58112fc1fffae06445351ea5f08246cf984e5c', 'snapshot', "def snapshot():\n    from crm_revision import snapshot as revision_snapshot\n    return revision_snapshot(ROOT)\n"),
}


def replace_function(source, name, replacement):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise ValueError('Ambiguous function replacement')
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    out = ''.join(lines[:node.lineno-1]) + replacement + ''.join(lines[node.end_lineno:])
    compile(out, '<candidate>', 'exec')
    return out


def build(name, raw):
    expected, function, replacement = SOURCES[name]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Runtime source changed; re-read before applying')
    source = (raw.decode('utf-8') + replacement) if function is None else replace_function(raw.decode('utf-8'), function, replacement)
    if name == 'master_card.py':
        nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'sdelat_vitrinnoe']
        if len(nodes) != 1:
            raise ValueError('Ambiguous cover renderer')
        original = ast.get_source_segment(source, nodes[0])
        changes = {
            'put_jpg = os.path.join(STAGE, "%s.jpg" % kod)': 'from crm_assets import save_immutable\n            put_jpg = ""',
            'put_webp = os.path.join(STAGE, "%s.webp" % kod)': 'put_webp = ""',
            'kadr.save(put_jpg, quality=86, optimize=True, progressive=True)': 'put_jpg = save_immutable(kadr, STAGE, kod, "jpg", quality=86, optimize=True, progressive=True)',
            'kadr.save(put_webp, quality=84, method=5)': 'put_webp = save_immutable(kadr, STAGE, kod, "webp", quality=84, method=5)',
        }
        modified = original
        for old, new in changes.items():
            if modified.count(old) != 1:
                raise ValueError('Cover renderer anchor changed')
            modified = modified.replace(old, new)
        source = replace_function(source, 'sdelat_vitrinnoe', modified + '\n')
    return source.encode('utf-8')
