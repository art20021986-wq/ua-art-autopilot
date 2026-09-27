"""Exact anchors reviewed against the six privately retrieved runtime sources.

The caller enforces the complete input SHA before any replacement. No install,
state reset, protected-runtime pin change, or production operation occurs here.
"""
import ast
import textwrap


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Media source anchor changed')
    return source.replace(old, new, 1)


def function(source, name, replacement):
    from build_gallery_patch import replace_function
    return replace_function(source, name, replacement)


def finish_media_patch(name, source):
    if name == 'publikaciya.py':
        source = once(source, '    verify_photo_structure(html, card, gallery_paths(card))\n',
                      '    verify_photo_structure(html, card, gallery_paths(card))\n'
                      '    from crm_videos import video_paths, verify_video_structure\n'
                      '    verify_video_structure(html, card, video_paths(card))\n')
    if name == 'stranica.py':
        candidates = [n for n in ast.parse(source).body
                      if isinstance(n, ast.FunctionDef) and n.name == 'sobrat_kartochku'
                      and 'video_est = os.path.exists' in ast.get_source_segment(source, n)]
        if len(candidates) != 1:
            raise ValueError('Ambiguous base card renderer')
        original = ast.get_source_segment(source, candidates[0])
        renderer = once(original,
                      '    video_est = os.path.exists(os.path.join(PAPKA_VID, nom + ".mp4"))',
                      '    from crm_videos import video_paths\n'
                      '    from crm_media_identity import poster_attribute\n'
                      '    _vse = video_paths(m)\n    video_est = bool(_vse)')
        start = '        _vse = ["%s.mp4" % nom]\n'
        end = '        c.append("<div class=\'zagolovok\'>Видео</div>")'
        a, b = renderer.index(start), renderer.index(end)
        if b <= a or renderer.count(start) != 1 or renderer.count(end) != 1:
            raise ValueError('Ambiguous video block')
        renderer = renderer[:a] + renderer[b:]
        renderer = once(renderer, 'zastavka(_f) or poster', 'poster_attribute(_f) or poster')
        renderer = once(renderer, '    if not kadry:\n',
                        '    if not kadry:\n'
                        '        from crm_assets import empty_cover\n'
                        '        empty = empty_cover(os.path.dirname(PAPKA_VID), nom)\n'
                        '        c.append("<div class=\'lenta\' data-crm-media-empty=\'1\'><img src=\'%s\' alt=\'Фото відсутні\'></div>" % empty)\n')
        source = once(source, original, renderer)
        source = once(source, '        video_est = os.path.exists(os.path.join(PAPKA_VID, nom + ".mp4"))',
                      '        from crm_videos import visible_video_ids\n'
                      '        video_est = bool(visible_video_ids(m))')
    if name in ('stranica.py', 'master_card.py'):
        resolver = ('dannye(kod)' if name == 'master_card.py' else
                    'next((m for m in mashiny() if nomer(m) == kod), {})')
        source = function(source, '_ua068_video_count', '''def _ua068_video_count(kod, row=None, source=None):
    from crm_videos import visible_video_ids
    return len(visible_video_ids(row if row is not None else RESOLVER))
'''.replace('RESOLVER', resolver))
    if name == 'master_card.py':
        source = once(source, '    imya, istochnik = vybrat_glavnoe(kod, m)\n',
                      '    imya, istochnik = vybrat_glavnoe(kod, m)\n'
                      '    if not imya:\n'
                      '        from crm_assets import empty_cover\n'
                      '        return empty_cover(DOM, kod), {"ok": True, "empty": True, "foto": "", "istochnik": istochnik}\n')
        source = function(source, 'video_fajly_mashiny', '''def video_fajly_mashiny(kod):
    from crm_videos import video_paths
    return [os.path.join(VIDEO, p) for p in video_paths(dannye(kod))]
''')
        source = once(source, 'def zastavka_rolika(src):\n',
                      'def zastavka_rolika(src):\n'
                      '    if re.fullmatch(r"UA-\\d{4,}.*-[0-9a-f]{64}\\.mp4", src or ""):\n'
                      '        from crm_media_identity import poster_path\n'
                      '        return poster_path(src)\n')
        source = function(source, 'ubrat_dubli_video', '''def ubrat_dubli_video(html, kod=''):
    # Distinct CRM entries are authoritative, even when their bytes match.
    # The final publisher gate rejects repeated player URLs and wrong order.
    return html, 0
''')
        source = function(source, 'svesti_k_unikalnym', '''def svesti_k_unikalnym(kod):
    count = len(video_fajly_mashiny(kod))
    return {'fajlov': count, 'unikalnyh': count, 'ubrano': []}
''')
        source = function(source, 'nayti_poteryannoe_video', '''def nayti_poteryannoe_video(kod, imeyushiesya):
    # Archived files cannot be evidence of current CRM membership.
    return []
''')
        source = once(source, '''    if len(srcy) > 1 and len(postery) > 1 and len(set(postery)) == 1:
        bedy.append("VIDEO DUPLICATE DETECTED — одинаковая заставка у разных роликов")
''', '')
    if name == 'video_sinhron.py':
        source = once(source, '                shutil.copyfileobj(r, f)\n',
                      '                shutil.copyfileobj(r, f)\n'
                      '                f.flush()\n                os.fsync(f.fileno())\n'
                      '                expected = r.headers.get("Content-Length")\n'
                      '                if expected is not None and os.fstat(f.fileno()).st_size != int(expected):\n'
                      '                    raise RuntimeError("Incomplete media response")\n')
        source = function(source, '_spisok_fid', '''def _spisok_fid(znachenie, predel):
    from public_media import _list
    values = _list(znachenie)
    ids = [v.get('file_id') if isinstance(v, dict) else v for v in values]
    if any(not isinstance(fid, str) or not fid for fid in ids) or len(ids) != len(set(ids)):
        raise RuntimeError('Invalid CRM media identities')
    return ids
''')
        source = function(source, 'mashiny', '''def mashiny():
    out = {}
    con = sqlite3.connect('file:%s?mode=ro' % BD, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute('SELECT auto_number,photos,videos FROM cars ORDER BY id').fetchall()
    finally:
        con.close()
    for row in rows:
        code = row['auto_number']
        try:
            if not isinstance(code, str) or not re.fullmatch(r'UA-\\d{4,}', code) or code in out:
                raise RuntimeError('Invalid car identity')
            out[code] = {'video': _spisok_fid(row['videos'], None),
                         'foto': _spisok_fid(row['photos'], None)}
        except Exception as error:
            log('media_list_pending=%s' % type(error).__name__)
    return out
''')
        source = once(source, '    pamyat = pamyat_chitat()\n',
                      '    from crm_media_identity import stable_names, source_unchanged\n'
                      '    pamyat = pamyat_chitat()\n'
                      '    previous = json.loads(json.dumps(pamyat))\n')
        source = once(source, '    skachano = udaleno = 0',
                      '    pending = 0\n    skachano = udaleno = 0')
        source = once(source, '    for nom in sorted(vse):\n',
                      '    ordered = sorted(vse)\n'
                      '    cursor = pamyat.get("_crm_media_cursor")\n'
                      '    if cursor in ordered:\n'
                      '        offset = ordered.index(cursor) + 1\n'
                      '        ordered = ordered[offset:] + ordered[:offset]\n'
                      '    pamyat["_crm_media_cursor"] = ordered[0]\n'
                      '    for nom in ordered:\n')
        source = once(source, '            na_meste = os.path.exists(cel) and znal.get(imya) == fid',
                      '            na_meste = (os.path.exists(cel) and znal.get(imya) == fid\n'
                      '                        and vnutri_mp4(cel) and source_unchanged(cel, DOM))')
        source = once(source, '            if os.path.exists(cel) and znal_f.get(imya) == fid:',
                      '            if (os.path.exists(cel) and znal_f.get(imya) == fid\n'
                      '                    and vnutri_jpeg(cel) and source_unchanged(cel, DOM)):')
        source = once(source,
                      '        nuzhno = {}\n        for i, fid in enumerate(fid_spisok, 1):\n'
                      '            nuzhno[imya_rolika(nom, i)] = fid',
                      '        nuzhno = stable_names(nom, "video", fid_spisok, pamyat.get(nom) or {})')
        source = once(source,
                      '        nuzhno_f = {}\n        for i, fid in enumerate(fid_foto, 1):\n'
                      '            nuzhno_f[imya_foto(i)] = fid',
                      '        nuzhno_f = stable_names(nom, "photo", fid_foto, pamyat.get("foto:" + nom) or {})')
        source = once(source, '''        for imya in bylo:
            if imya not in nuzhno:
                udaleno += ubrat(os.path.join(PUB, imya))
                izmenilos.append(nom)
''', '        # Retain old files for rollback; CRM controls public membership.\n')
        source = once(source, '''        for imya in bylo_f:
            if imya not in nuzhno_f:
                if ubrat(os.path.join(foto_papka(nom), imya)):
                    udaleno_foto += 1
                    menyalis_foto = True
''', '        # No physical deletion during a CRM synchronization pass.\n')
        source = once(source, '        if menyalis_foto:\n            chistit_kesh(nom)\n',
                      '        if menyalis_foto:\n')
        source = once(source, '    if izmenilos:\n        pamyat_pisat(pamyat)\n',
                      '    media_changed = ({k: v for k, v in pamyat.items() if k != "_crm_media_cursor"}\n'
                      '                     != {k: v for k, v in previous.items() if k != "_crm_media_cursor"})\n'
                      '    if pamyat != previous:\n'
                      '        if not pamyat_pisat(pamyat):\n'
                      '            raise RuntimeError("Media ledger not committed")\n'
                      '    if media_changed:\n')
        source = once(source, '    if mertvye:\n        pamyat_pisat(pamyat)\n', '')
        source = once(source, 'return itog + " · страницы пересобраны"',
                      'return itog + " · обновление сайта поставлено в очередь"')
        source = once(source, '    return "всё совпадает, менять нечего"',
                      '    if pending:\n'
                      '        return "Медиа ожидают загрузки: %d; публикация проверяется отдельно" % pending\n'
                      '    return "Медиа сверены с журналом, менять нечего; публикация проверяется отдельно"')
        source = once(source, '        for s in sboi_mashiny:\n',
                      '        pending += sum(znal.get(n) != f for n, f in nuzhno.items())\n'
                      '        pending += sum(znal_f.get(n) != f for n, f in nuzhno_f.items())\n'
                      '        for s in sboi_mashiny:\n')
        source = once(source, '        time.sleep(SHAG)', '        time.sleep(min(SHAG, 15))')
        source = source.replace('time.time() - kogda < POVTOR_MERTVYH',
                                'time.time() - kogda < min(POVTOR_MERTVYH, 300)')
        source = source.replace('пробую снова через 6 часов', 'повтор не позднее чем через 5 минут')
        # Isolate a bad card without swallowing the persistent-ledger write.
        tree = ast.parse(source)
        run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'prohod')
        loop = [n for n in run.body if isinstance(n, ast.For)]
        if len(loop) != 1:
            raise ValueError('Ambiguous media processing loop')
        node = loop[0]
        lines = source.splitlines(keepends=True)
        body = ''.join(lines[node.body[0].lineno-1:node.end_lineno])
        wrapped = '        try:\n' + textwrap.indent(body, '    ')
        wrapped += ('        except Exception as error:\n'
                    '            pending += 1\n'
                    '            log("car_id=%s media_pending=%s" % (nom, type(error).__name__))\n')
        source = ''.join(lines[:node.body[0].lineno-1]) + wrapped + ''.join(lines[node.end_lineno:])
    compile(source, '<media-candidate>', 'exec')
    return source
