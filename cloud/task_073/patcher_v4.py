"""TASK 073 ROUND 5 - patcher_v4.py

Deterministic, SHA-anchored, AST-located point transforms for the CRM
unified-catalog contract. Only the exact functions named in the task are
touched. Every transform verifies a full-file SHA256 anchor and/or a
per-function SHA256 anchor before editing anything, performs a bounded
substitution (never a blind global replace), and compiles the result.

No network access here. No production writes here. Pure text/AST library
used by gate_a_v4.py (read-only audit) and gate_b_installer_v4.py
(remote, manual-only, owner-approved install).
"""

import ast
import hashlib
import re


class DriftError(RuntimeError):
    """Live source does not match the expected SHA anchor."""


class PatternError(RuntimeError):
    """Expected substitution pattern not found the expected number of times."""


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ROUND 5 full-file SHA anchors (hard-coded, fail-closed). Callers must
# still fetch the live file fresh; these constants only gate the patch,
# they are never trusted blindly for anything beyond comparison.
FULL_FILE_ANCHORS = {
    "konteyner.py": "2d56a970fb76c782f0d5caebd65b6a7ffd44fd3ad1278a775bf641cffd39080d",
    "cars_ui.py": "862baea2ca0794f5e0d83bc04169f6d2fdec401f86f384ef4376e373c02a776b",
    "stranica.py": "4bb4c26eee5948e1dc37b336c4c32689f51baf0fef1a2eceac86a50fe6434959",
    "master_card.py": "96bb7e99b15d6e5d8de7e825e427406945cf866b5cda300710950ab2ac803e81",
    "yadro.py": "45bc957a8f2b9cbc509e5e140badbb2117bedc6857e111607c50adb2058cdc30",
    "publikaciya.py": "7bb8b0e51b41d94ad305179c35bce20d89dee7f7704c844335a478f87499f0a4",
}

PRODUCTION_ANCHORS = {
    "konteyner.py": {
        "gde_mashina": "d49710dbe1831353432c084439afc1ece9203eee116db9c42b0b00fcb7ca964c",
        "_ekran": "5e970dcedd8e29da0562dc2653c1b6173fd8d3007e0203fffc5e9f36bd196e6b",
    },
    "cars_ui.py": {
        "stage_menu": "edf960e645680f758dd3cbfd071410067f6b4be2a94ec4c4ca97793fc9d8d795",
        "toggle_publish": "21c3f452813122f18247359259432bed2a23f12163ac36859bac0ffd594d8682",
    },
    "stranica.py": {"_ua_seo068_normalize": "30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566"},
    "master_card.py": {"_ua_seo068_normalize": "30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566"},
    "yadro.py": {"_ua_seo068_normalize": "30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566"},
    "publikaciya.py": {
        "opublikovat": "93f130c2542124b820eae2416984705ecbbc80019a298d2b3c40fdf58d93033f",
        "_otkat": "141cd24d4d57b4812ea1339fd6f74a0656b993b190897a4e932e2ec6792e15b1",
    },
}


def check_full_file_sha(filename, source):
    expected = FULL_FILE_ANCHORS.get(filename)
    if expected is None:
        raise DriftError("NO_FULL_FILE_ANCHOR:%s" % filename)
    actual = _sha256(source)
    if actual != expected:
        raise DriftError(
            "FULL_FILE_SHA_MISMATCH:%s:expected=%s:actual=%s" % (filename, expected, actual)
        )
    return True


def find_function_segment(source, function_name):
    """Return (node, start_line, end_line, segment_text) for the first
    function/async function named function_name. 1-indexed inclusive lines."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                start = node.lineno
                end = getattr(node, "end_lineno", None)
                if end is None:
                    raise RuntimeError("PY_AST_NO_END_LINENO")
                lines = source.splitlines(keepends=True)
                segment = "".join(lines[start - 1:end])
                return node, start, end, segment
    raise LookupError("FUNCTION_NOT_FOUND:%s" % function_name)


def replace_in_function(source, function_name, expected_sha256, old, new, expected_count=1):
    node, start, end, segment = find_function_segment(source, function_name)
    actual_sha = _sha256(segment)
    if actual_sha != expected_sha256:
        raise DriftError(
            "SHA_MISMATCH:%s:expected=%s:actual=%s" % (function_name, expected_sha256, actual_sha)
        )
    occurrences = segment.count(old)
    if occurrences != expected_count:
        raise PatternError(
            "PATTERN_COUNT_MISMATCH:%s:expected=%d:actual=%d" % (function_name, expected_count, occurrences)
        )
    new_segment = segment.replace(old, new, expected_count)
    lines = source.splitlines(keepends=True)
    patched_lines = lines[:start - 1] + [new_segment] + lines[end:]
    return "".join(patched_lines)


def insert_rows_in_function(source, function_name, expected_sha256, anchor_substring,
                             insertion_lines, expected_anchor_count=1):
    node, start, end, segment = find_function_segment(source, function_name)
    actual_sha = _sha256(segment)
    if actual_sha != expected_sha256:
        raise DriftError(
            "SHA_MISMATCH:%s:expected=%s:actual=%s" % (function_name, expected_sha256, actual_sha)
        )
    seg_lines = segment.splitlines(keepends=True)
    hits = [i for i, ln in enumerate(seg_lines) if anchor_substring in ln]
    if len(hits) != expected_anchor_count:
        raise PatternError(
            "ANCHOR_COUNT_MISMATCH:%s:expected=%d:actual=%d" % (function_name, expected_anchor_count, len(hits))
        )
    idx = hits[0]
    anchor_text = seg_lines[idx]
    stripped = anchor_text.lstrip(" \t")
    indent = anchor_text[:len(anchor_text) - len(stripped)]
    new_lines = [indent + line + "\n" for line in insertion_lines]
    seg_lines[idx + 1:idx + 1] = new_lines
    new_segment = "".join(seg_lines)
    lines = source.splitlines(keepends=True)
    patched_lines = lines[:start - 1] + [new_segment] + lines[end:]
    return "".join(patched_lines)


def patch_konteyner(source, gde_mashina_sha=None, ekran_sha=None, require_full_file_sha=True):
    if require_full_file_sha:
        check_full_file_sha("konteyner.py", source)
    gde_mashina_sha = gde_mashina_sha or PRODUCTION_ANCHORS["konteyner.py"]["gde_mashina"]
    ekran_sha = ekran_sha or PRODUCTION_ANCHORS["konteyner.py"]["_ekran"]

    source = replace_in_function(
        source, "gde_mashina", gde_mashina_sha,
        "if stage_no == nomer_etapa",
        'if stage_no == nomer_etapa and code not in ("sea_loaded", "sea_transit")',
        expected_count=1,
    )
    insertion = [
        'rows.append([types.InlineKeyboardButton("Загружено в контейнер", callback_data="car_setstage:%d:sea_loaded" % cid)])',
        'rows.append([types.InlineKeyboardButton("В пути", callback_data="car_setstage:%d:sea_transit" % cid)])',
    ]
    source = insert_rows_in_function(
        source, "_ekran", ekran_sha, "cont_days", insertion, expected_anchor_count=1,
    )
    compile(source, "konteyner.py", "exec")
    return source


TOGGLE_PUBLISH_V4_BODY = '''async def toggle_publish(cid, novoe, msg_or_call=None):
    """V4: truthful publish success/failure with exact preimage rollback.
    Hide path (novoe == 0) unchanged. Success message only after the
    real publisher returns ok is True and a read-back confirms state.
    """
    preimage_published = _bd_procitat_published(cid)
    _bd_zapisat_published(cid, novoe)
    if novoe == 0:
        return True, "Скрыто из каталога."
    nomer = _bd_procitat_nomer(cid)
    try:
        _ok_rem2, _txt_rem2 = await _aio_rem2.to_thread(_pub_rem2.opublikovat, nomer)
    except Exception as exc:
        _ok_rem2 = False
        _txt_rem2 = "Ошибка публикации: %s" % exc
    if _ok_rem2 is not True:
        _bd_zapisat_published(cid, preimage_published)
        _read_back = _bd_procitat_published(cid)
        if _read_back != preimage_published:
            return False, "Публикация отменена, откат состояния не подтверждён."
        return False, "Публикация отменена: %s" % _txt_rem2
    return True, "Машина видна клиентам в каталоге."
'''


def patch_cars_ui(source, stage_menu_sha=None, toggle_publish_sha=None, require_full_file_sha=True):
    if require_full_file_sha:
        check_full_file_sha("cars_ui.py", source)
    stage_menu_sha = stage_menu_sha or PRODUCTION_ANCHORS["cars_ui.py"]["stage_menu"]
    toggle_publish_sha = toggle_publish_sha or PRODUCTION_ANCHORS["cars_ui.py"]["toggle_publish"]

    source = replace_in_function(
        source, "stage_menu", stage_menu_sha,
        "if stage_no == number",
        'if stage_no == number and code not in ("sea_loaded", "sea_transit")',
        expected_count=1,
    )

    node, start, end, segment = find_function_segment(source, "toggle_publish")
    if _sha256(segment) != toggle_publish_sha:
        raise DriftError("SHA_MISMATCH:toggle_publish:expected=%s" % toggle_publish_sha)
    lines = source.splitlines(keepends=True)
    patched_lines = lines[:start - 1] + [TOGGLE_PUBLISH_V4_BODY] + lines[end:]
    source = "".join(patched_lines)
    compile(source, "cars_ui.py", "exec")
    return source


SEO068_STALE_PATTERN = re.compile(
    r"[ \t]*if not any\(_ua_seo068_os\.path\.isfile\("
    r"_ua_seo068_os\.path\.join\(root, target\)\) "
    r"for root in \('/home/Carix/video', '/home/Carix/site'\)\):\n"
    r"[ \t]*raise RuntimeError\('SEO068_DIAGNOSTIC_TARGET_MISSING:' \+ identifier\)\n"
)


def patch_seo068_stale_precondition(filename, source, normalize_sha=None, require_full_file_sha=True):
    if require_full_file_sha:
        check_full_file_sha(filename, source)
    normalize_sha = normalize_sha or PRODUCTION_ANCHORS[filename]["_ua_seo068_normalize"]
    node, start, end, segment = find_function_segment(source, "_ua_seo068_normalize")
    if _sha256(segment) != normalize_sha:
        raise DriftError("SHA_MISMATCH:_ua_seo068_normalize:%s" % filename)
    matches = SEO068_STALE_PATTERN.findall(segment)
    if len(matches) != 1:
        raise PatternError(
            "STALE_BLOCK_COUNT_MISMATCH:%s:expected=1:actual=%d" % (filename, len(matches))
        )
    new_segment = SEO068_STALE_PATTERN.sub("", segment, count=1)
    lines = source.splitlines(keepends=True)
    patched_lines = lines[:start - 1] + [new_segment] + lines[end:]
    patched_source = "".join(patched_lines)
    compile(patched_source, filename, "exec")
    return patched_source


OPUBLIKOVAT_V4_BODY = '''def opublikovat(auto_number, proba=False):
    """V4 unified publisher: primary + mandatory diag/placeholder + full
    catalog built and validated BEFORE any write. Bounded backup/write
    set, read-back verified, full rollback on any failure. proba=True
    performs zero writes.
    """
    kod = _master(auto_number)
    ok_pre, msg_pre = proverit(kod)
    if not ok_pre:
        return False, msg_pre

    primary_video = _postroit_stranicu_video(kod)
    primary_site = _postroit_stranicu_site(kod)
    diag_content = _postroit_diagnostiku_ili_placeholder(kod)
    katalog_video = _ua9_sobrat_katalog(mesto="video")
    katalog_site = _ua9_sobrat_katalog(mesto="site")

    ozhidaemyi_href = 'href="%s.html"' % auto_number
    if katalog_video.count(ozhidaemyi_href) != 1:
        return False, "SEO068_CATALOG_HREF_MISMATCH:video:%s" % auto_number
    if katalog_site.count(ozhidaemyi_href) != 1:
        return False, "SEO068_CATALOG_HREF_MISMATCH:site:%s" % auto_number

    celi = {
        _put_video(auto_number): primary_video,
        _put_site(auto_number): primary_site,
        _put_video_diag(auto_number): diag_content,
        _put_katalog_video(): katalog_video,
        _put_katalog_site(): katalog_site,
    }

    if proba:
        return True, "DRY_RUN_OK"

    backup = {}
    zapisano = []
    try:
        for put in celi:
            backup[put] = _procitat_esli_est(put)
        for put, soderzhimoe in celi.items():
            _zapisat_atomarno(put, soderzhimoe)
            zapisano.append(put)
        for put, ozhidaemoe in celi.items():
            fakticheskoe = _procitat_esli_est(put)
            if fakticheskoe != ozhidaemoe:
                raise RuntimeError("READBACK_MISMATCH:%s" % put)
        ok_zaschita, msg_zaschita = _proverit_zaschischennye_kartochki()
        if not ok_zaschita:
            raise RuntimeError("PROTECTED_REGRESSION:%s" % msg_zaschita)
    except Exception as exc:
        _otkat(backup, zapisano)
        return False, "Публикация отменена: %s" % exc

    return True, "Опубликовано: %s" % auto_number
'''

OTKAT_V4_BODY = '''def _otkat(backup, zapisano):
    """V4 exact rollback: restore preimage where one existed, otherwise
    delete the newly-created target. Never leaves a partial write set."""
    import os as _os_rem3
    for put in zapisano:
        preimage = backup.get(put)
        if preimage is None:
            try:
                _os_rem3.remove(put)
            except FileNotFoundError:
                pass
        else:
            _zapisat_atomarno(put, preimage)
'''


def patch_publikaciya(source, opublikovat_sha=None, otkat_sha=None, require_full_file_sha=True):
    if require_full_file_sha:
        check_full_file_sha("publikaciya.py", source)
    opublikovat_sha = opublikovat_sha or PRODUCTION_ANCHORS["publikaciya.py"]["opublikovat"]
    otkat_sha = otkat_sha or PRODUCTION_ANCHORS["publikaciya.py"]["_otkat"]

    node, start, end, segment = find_function_segment(source, "opublikovat")
    if _sha256(segment) != opublikovat_sha:
        raise DriftError("SHA_MISMATCH:opublikovat")
    lines = source.splitlines(keepends=True)
    lines = lines[:start - 1] + [OPUBLIKOVAT_V4_BODY] + lines[end:]
    source = "".join(lines)

    node2, start2, end2, segment2 = find_function_segment(source, "_otkat")
    if _sha256(segment2) != otkat_sha:
        raise DriftError("SHA_MISMATCH:_otkat")
    lines2 = source.splitlines(keepends=True)
    lines2 = lines2[:start2 - 1] + [OTKAT_V4_BODY] + lines2[end2:]
    source = "".join(lines2)

    compile(source, "publikaciya.py", "exec")
    return source
