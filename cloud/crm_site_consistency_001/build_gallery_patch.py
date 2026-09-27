"""Build exact-source gallery fixes; never install or mutate production here."""
import ast
import hashlib

SOURCES = {
 'publikaciya.py': ('296c389b477472032bad714e41f12bfa4b7e47ad784ac6900ba55f136d939c72', None, "\n# Validate completed public card before existing transaction writes any HTML.\n_CRM_CONSISTENCY_MASTER = _master\ndef _master(kod):\n    html, diag, card = _CRM_CONSISTENCY_MASTER(kod)\n    if html is None or card is None:\n        raise RuntimeError('CRM public card missing')\n    from public_fields import verify_core_fields\n    from public_media import verify_photo_structure\n    from crm_gallery import gallery_paths\n    verify_core_fields(html, card)\n    verify_photo_structure(html, card, gallery_paths(card))\n    return html, diag, card\n"),
 'stranica.py': ('4d710266abb2a92754ff3e3fc7de86c628760bee3c455dfbb177dedec113b1a1', 'kadry_mashiny', '''def kadry_mashiny(m):
    from crm_gallery import gallery_paths
    return gallery_paths(m)
'''),
 'master_card.py': ('c99b6c0271586d4f8c56e4184528ab6f20541173be9a287d9d64661b4b7184b2', 'vybrat_glavnoe', '''def vybrat_glavnoe(kod, m=None):
    from crm_gallery import gallery_paths
    paths = gallery_paths(m if m is not None else dannye(kod))
    if not paths:
        return '', 'CRM gallery is empty'
    return os.path.basename(paths[0]), 'CRM public gallery'
'''),
 'ua_crm_public_sync.py': ('2b5f6a2473b263fddd6ab3266a3ba76cc9738da15178f865862098821cabcc41', 'snapshot', "def snapshot():\n    from crm_revision import snapshot as revision_snapshot\n    return revision_snapshot(ROOT)\n"),
 'video_sinhron.py': ('7a49a09546267751b4a8a4bc70d6970e599c702968542c72ba7205537ad09a4e', 'peresobrat', '''def peresobrat():
    from ua_crm_public_sync import notify
    notify()
    return True, 'CRM publication queued; public verification is pending'
'''),
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
    expected = SOURCES[name][0]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Runtime source changed; re-read before applying')
    return apply_reviewed_changes(name, raw)


def apply_reviewed_changes(name, raw):
    """Internal transform; callers must verify the exact original/intermediate SHA."""
    _, function, replacement = SOURCES[name]
    source = (raw.decode('utf-8') + replacement) if function is None else replace_function(raw.decode('utf-8'), function, replacement)
    from build_media_patch import finish_media_patch
    source = finish_media_patch(name, source)
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
