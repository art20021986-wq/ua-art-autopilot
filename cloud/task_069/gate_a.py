#!/usr/bin/env python3
"""Build and verify a bounded TASK 069 candidate without production writes."""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import pathlib
import urllib.parse
import urllib.request


API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE_PATH = "/home/Carix/konteyner.py"
EXPECTED_SOURCE_SHA256 = "2d56a970fb76c782f0d5caebd65b6a7ffd44fd3ad1278a775bf641cffd39080d"
OUT = pathlib.Path("cloud/task_069/evidence/gate_a.json")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_remote() -> bytes:
    request = urllib.request.Request(
        API + "files/path" + urllib.parse.quote(REMOTE_PATH, safe="/"),
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task069-container-gate-a/1",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read(3_000_001)
    if len(data) > 3_000_000:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE")
    return data


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError("%s_MATCH_COUNT_%d" % (label, count))
    return source.replace(old, new, 1)


def function_hashes(source: str) -> dict[str, list[str]]:
    tree = ast.parse(source)
    lines = source.splitlines()
    result: dict[str, list[str]] = {}
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = "\n".join(lines[node.lineno - 1:node.end_lineno])
        result.setdefault(node.name, []).append(sha(body.encode()))
    return result


def main() -> None:
    original_data = read_remote()
    original_sha = sha(original_data)
    if original_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("LIVE_SOURCE_CHANGED:" + original_sha)
    original = original_data.decode("utf-8")
    candidate = original

    candidate = replace_once(
        candidate,
        '        [InlineKeyboardButton("Дни до прибытия",\n'
        '                              callback_data="cont_days:%d" % cid)],',
        '        [InlineKeyboardButton("⏱ Количество дней до Киева",\n'
        '                              callback_data="car_setf:%d:eta_days" % cid)],',
        "CENTRAL_DAYS_BUTTON",
    )
    candidate = replace_once(
        candidate,
        '                [InlineKeyboardButton("Ввести дату отправления",\n'
        '                                      callback_data="cont_date:%d" % cid)],\n'
        '                [InlineKeyboardButton("Пропустить",',
        '                [InlineKeyboardButton("Ввести дату отправления",\n'
        '                                      callback_data="cont_date:%d" % cid)],\n'
        '                [InlineKeyboardButton("⏱ Количество дней до Киева",\n'
        '                                      callback_data="car_setf:%d:eta_days" % cid)],\n'
        '                [InlineKeyboardButton("Пропустить",',
        "STATUS_PROMPT_DAYS_BUTTON",
    )
    candidate = replace_once(
        candidate,
        '    context.user_data.pop("cont_wait", None)\n'
        '    do = _karta(cid) or {}\n'
        '    try:\n'
        '        _pisat(cid, pole, znachenie, kto)',
        '    do = _karta(cid) or {}\n'
        '    try:\n'
        '        _pisat(cid, pole, znachenie, kto)',
        "WAIT_CLEAR_BEFORE_WRITE",
    )
    candidate = replace_once(
        candidate,
        '    posle = _karta(cid) or {}          # повторное чтение из базы\n'
        '    stalo = (posle.get(pole) or "").strip()\n'
        '    if pole == "sea_container":\n'
        '        podpis = "Номер контейнера сохранён: %s" % (stalo or "—")',
        '    posle = _karta(cid) or {}          # повторное чтение из базы\n'
        '    stalo = str(posle.get(pole) or "").strip()\n'
        '    ozhidaemoe = str(znachenie).strip()\n'
        '    if stalo != ozhidaemoe:\n'
        '        log.warning("konteyner: read-back mismatch %s expected=%r actual=%r",\n'
        '                    pole, ozhidaemoe, stalo)\n'
        '        await msg.reply_text(\n'
        '            "Не удалось подтвердить сохранение. Повторите ввод.",\n'
        '            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(\n'
        '                "Отмена", callback_data="cont_menu:%d" % cid)]]))\n'
        '        raise ApplicationHandlerStop\n'
        '    context.user_data.pop("cont_wait", None)\n'
        '    if pole == "sea_container":\n'
        '        podpis = "✅ Контейнер сохранён: %s" % stalo',
        "READ_BACK_GATE",
    )

    compile(candidate, REMOTE_PATH, "exec")
    before = function_hashes(original)
    after = function_hashes(candidate)
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    if changed != ["_ekran", "posle_statusa", "prinyat"]:
        raise RuntimeError("UNEXPECTED_CHANGED_FUNCTIONS:" + ",".join(changed))

    tree = ast.parse(candidate)
    lines = candidate.splitlines()
    functions = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in changed:
            functions[node.name] = "\n".join(lines[node.lineno - 1:node.end_lineno])
    checks = {
        "compile": True,
        "source_hash_guard": original_sha == EXPECTED_SOURCE_SHA256,
        "only_expected_functions_changed": changed == ["_ekran", "posle_statusa", "prinyat"],
        "central_button_once": functions["_ekran"].count("⏱ Количество дней до Киева") == 1,
        "status_prompt_button_once": functions["posle_statusa"].count("⏱ Количество дней до Киева") == 1,
        "days_routes_existing_handler": (
            functions["_ekran"].count("car_setf:%d:eta_days") == 1
            and functions["posle_statusa"].count("car_setf:%d:eta_days") == 1
        ),
        "wait_clear_after_readback": (
            functions["prinyat"].index('context.user_data.pop("cont_wait", None)')
            > functions["prinyat"].index("if stalo != ozhidaemoe")
        ),
        "readback_equality_required": "if stalo != ozhidaemoe" in functions["prinyat"],
        "exact_container_success": "✅ Контейнер сохранён: %s" in functions["prinyat"],
        "runtime_llm_tokens": 0,
    }
    if not all(value is True or key == "runtime_llm_tokens" for key, value in checks.items()):
        raise RuntimeError("GATE_A_CHECK_FAILED")

    diff = "".join(difflib.unified_diff(
        original.splitlines(True), candidate.splitlines(True),
        fromfile="/home/Carix/konteyner.py", tofile="candidate/konteyner.py",
    ))
    evidence = {
        "task_id": "CRM-CONTAINER-KYIV-DAYS-001-V1.0",
        "mode": "ISOLATED_GATE_A",
        "status": "PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL",
        "production_touched": False,
        "crm_db_write": False,
        "service_reload": False,
        "source": {"path": REMOTE_PATH, "sha256": original_sha, "size": len(original_data)},
        "candidate": {"sha256": sha(candidate.encode()), "size": len(candidate)},
        "changed_functions": changed,
        "checks": checks,
        "diff": diff,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("TASK069_GATE_A_PASS changed=" + ",".join(changed))


if __name__ == "__main__":
    main()
