import patcher_v4 as pv4

KONTEYNER_FIXTURE = (
    "import types\n\n\n"
    "def gde_mashina(cid, nomer_etapa):\n"
    "    rows = []\n"
    "    for code, info in S.STATUSES.items():\n"
    "        stage_no = info['stage']\n"
    "        if stage_no == nomer_etapa:\n"
    "            rows.append(code)\n"
    "    return rows\n\n\n"
    "def _ekran(cid):\n"
    "    rows = []\n"
    "    rows.append(['nomer_kontejnera'])\n"
    "    rows.append(['data_pribytiya'])\n"
    "    rows.append(['cont_days'])\n"
    "    rows.append(['ochistit'])\n"
    "    return rows\n"
)

CARS_UI_FIXTURE = (
    "def stage_menu(cid, number):\n"
    "    out = []\n"
    "    for code, info in S.STATUSES.items():\n"
    "        stage_no = info['stage']\n"
    "        if stage_no == number:\n"
    "            out.append(code)\n"
    "    return out\n\n\n"
    "async def toggle_publish(cid, novoe, msg_or_call=None):\n"
    "    preimage_published = _bd_procitat_published(cid)\n"
    "    _bd_zapisat_published(cid, novoe)\n"
    "    if novoe == 0:\n"
    "        return True, 'hidden'\n"
    "    nomer = _bd_procitat_nomer(cid)\n"
    "    _ok_rem2, _txt_rem2 = await _aio_rem2.to_thread(_pub_rem2.opublikovat, nomer)\n"
    "    return True, 'Машина видна клиентам в каталоге.'\n"
)

SEO068_FIXTURE = (
    "def _ua_seo068_normalize(identifier, target):\n"
    "    if True:\n"
    "        if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) for root in ('/home/Carix/video', '/home/Carix/site')):\n"
    "            raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)\n"
    "    return target\n"
)

PUBLIKACIYA_FIXTURE = (
    "def opublikovat(auto_number, proba=False):\n"
    "    kod = _master(auto_number)\n"
    "    return True, 'old'\n\n\n"
    "def _otkat(backup, zapisano):\n"
    "    return None\n"
)


def test_patch_konteyner_outer_removed_inner_added():
    _, _, _, seg_gde = pv4.find_function_segment(KONTEYNER_FIXTURE, "gde_mashina")
    _, _, _, seg_ekran = pv4.find_function_segment(KONTEYNER_FIXTURE, "_ekran")
    patched = pv4.patch_konteyner(
        KONTEYNER_FIXTURE,
        gde_mashina_sha=pv4._sha256(seg_gde),
        ekran_sha=pv4._sha256(seg_ekran),
        require_full_file_sha=False,
    )
    compile(patched, "konteyner.py", "exec")
    assert 'code not in ("sea_loaded", "sea_transit")' in patched
    assert patched.count("car_setstage:%d:sea_loaded") == 1
    assert patched.count("car_setstage:%d:sea_transit") == 1


def test_patch_konteyner_sha_drift_blocks():
    try:
        pv4.patch_konteyner(
            KONTEYNER_FIXTURE,
            gde_mashina_sha="0" * 64,
            ekran_sha="0" * 64,
            require_full_file_sha=False,
        )
        raised = False
    except pv4.DriftError:
        raised = True
    assert raised


def test_patch_cars_ui_outer_and_toggle_publish():
    _, _, _, seg_stage = pv4.find_function_segment(CARS_UI_FIXTURE, "stage_menu")
    _, _, _, seg_toggle = pv4.find_function_segment(CARS_UI_FIXTURE, "toggle_publish")
    patched = pv4.patch_cars_ui(
        CARS_UI_FIXTURE,
        stage_menu_sha=pv4._sha256(seg_stage),
        toggle_publish_sha=pv4._sha256(seg_toggle),
        require_full_file_sha=False,
    )
    compile(patched, "cars_ui.py", "exec")
    assert 'code not in ("sea_loaded", "sea_transit")' in patched
    assert "_ok_rem2 is not True" in patched
    assert patched.count("Машина видна клиентам в каталоге.") == 1


def test_patch_seo068_removes_only_stale_block():
    _, _, _, seg = pv4.find_function_segment(SEO068_FIXTURE, "_ua_seo068_normalize")
    patched = pv4.patch_seo068_stale_precondition(
        "stranica.py", SEO068_FIXTURE, normalize_sha=pv4._sha256(seg), require_full_file_sha=False,
    )
    compile(patched, "stranica.py", "exec")
    assert "SEO068_DIAGNOSTIC_TARGET_MISSING" not in patched
    assert "def _ua_seo068_normalize" in patched


def test_patch_publikaciya_replaces_functions():
    _, _, _, seg_op = pv4.find_function_segment(PUBLIKACIYA_FIXTURE, "opublikovat")
    _, _, _, seg_otkat = pv4.find_function_segment(PUBLIKACIYA_FIXTURE, "_otkat")
    patched = pv4.patch_publikaciya(
        PUBLIKACIYA_FIXTURE,
        opublikovat_sha=pv4._sha256(seg_op),
        otkat_sha=pv4._sha256(seg_otkat),
        require_full_file_sha=False,
    )
    compile(patched, "publikaciya.py", "exec")
    assert "_ua9_sobrat_katalog" in patched
    assert "def _otkat(backup, zapisano):" in patched


def test_full_file_sha_check_fails_closed_on_unknown_content():
    try:
        pv4.check_full_file_sha("konteyner.py", "random content that is not live source")
        raised = False
    except pv4.DriftError:
        raised = True
    assert raised
