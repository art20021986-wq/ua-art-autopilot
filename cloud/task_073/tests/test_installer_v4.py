import os

import patcher_v4 as pv4
import gate_b_installer_v4 as installer_v4

KONTEYNER_SRC = (
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

CARS_UI_SRC = (
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

SEO068_SRC = (
    "def _ua_seo068_normalize(identifier, target):\n"
    "    if True:\n"
    "        if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) for root in ('/home/Carix/video', '/home/Carix/site')):\n"
    "            raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)\n"
    "    return target\n"
)

PUBLIKACIYA_SRC = (
    "def opublikovat(auto_number, proba=False):\n"
    "    kod = _master(auto_number)\n"
    "    return True, 'old'\n\n\n"
    "def _otkat(backup, zapisano):\n"
    "    return None\n"
)

FIXTURES = {
    "konteyner.py": KONTEYNER_SRC,
    "cars_ui.py": CARS_UI_SRC,
    "stranica.py": SEO068_SRC,
    "master_card.py": SEO068_SRC,
    "yadro.py": SEO068_SRC,
    "publikaciya.py": PUBLIKACIYA_SRC,
}


def _patch_anchors(monkeypatch):
    for filename, content in FIXTURES.items():
        monkeypatch.setitem(pv4.FULL_FILE_ANCHORS, filename, pv4._sha256(content))
    _, _, _, seg = pv4.find_function_segment(KONTEYNER_SRC, "gde_mashina")
    monkeypatch.setitem(pv4.PRODUCTION_ANCHORS["konteyner.py"], "gde_mashina", pv4._sha256(seg))
    _, _, _, seg = pv4.find_function_segment(KONTEYNER_SRC, "_ekran")
    monkeypatch.setitem(pv4.PRODUCTION_ANCHORS["konteyner.py"], "_ekran", pv4._sha256(seg))
    _, _, _, seg = pv4.find_function_segment(CARS_UI_SRC, "stage_menu")
    monkeypatch.setitem(pv4.PRODUCTION_ANCHORS["cars_ui.py"], "stage_menu", pv4._sha256(seg))
    _, _, _, seg = pv4.find_function_segment(CARS_UI_SRC, "toggle_publish")
    monkeypatch.setitem(pv4.PRODUCTION_ANCHORS["cars_ui.py"], "toggle_publish", pv4._sha256(seg))
    _, _, _, seg = pv4.find_function_segment(SEO068_SRC, "_ua_seo068_normalize")
    for filename in ("stranica.py", "master_card.py", "yadro.py"):
        monkeypatch.setitem(pv4.PRODUCTION_ANCHORS[filename], "_ua_seo068_normalize", pv4._sha256(seg))
    _, _, _, seg = pv4.find_function_segment(PUBLIKACIYA_SRC, "opublikovat")
    monkeypatch.setitem(pv4.PRODUCTION_ANCHORS["publikaciya.py"], "opublikovat", pv4._sha256(seg))
    _, _, _, seg = pv4.find_function_segment(PUBLIKACIYA_SRC, "_otkat")
    monkeypatch.setitem(pv4.PRODUCTION_ANCHORS["publikaciya.py"], "_otkat", pv4._sha256(seg))


def _write_fixtures(root):
    for filename, content in FIXTURES.items():
        with open(os.path.join(root, filename), "w", encoding="utf-8") as fh:
            fh.write(content)


def test_run_shadow_pass(tmp_path, monkeypatch):
    _patch_anchors(monkeypatch)
    _write_fixtures(tmp_path)
    result = installer_v4.run_shadow(str(tmp_path))
    assert result["status"] == "SHADOW_PASS"
    assert result["production_writes"] == 0


def test_run_install_rolls_back_on_publish_failure(tmp_path, monkeypatch):
    _patch_anchors(monkeypatch)
    _write_fixtures(tmp_path)
    original_konteyner = FIXTURES["konteyner.py"]
    result = installer_v4.run_install(str(tmp_path))
    assert result["status"] == "INSTALL_FAIL_ROLLED_BACK"
    with open(os.path.join(str(tmp_path), "konteyner.py"), "r", encoding="utf-8") as fh:
        restored = fh.read()
    assert restored == original_konteyner
