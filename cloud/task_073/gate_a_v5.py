"""Real secret-backed GET-only Gate A for TASK 073 V5."""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import patcher_v5 as patcher


CONTRACT = "CRM-UNIFIED-CATALOG-001-V1.0"
USERNAME = "Carix"
ROOT = "/home/Carix"
API_BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
EVIDENCE = pathlib.Path(__file__).resolve().parent / "evidence" / "gate_a_v5.json"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


class ReadOnlyAPI:
    """The only HTTP operation implemented here is GET."""

    def __init__(self, token: str):
        if not token:
            raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
        self.token = token

    def read_text(self, path: str) -> str:
        if not path.startswith(ROOT + "/"):
            raise RuntimeError("REMOTE_PATH_OUT_OF_SCOPE:%s" % path)
        url = API_BASE + "files/path" + urllib.parse.quote(path, safe="/")
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": "Token " + self.token,
                "User-Agent": "ua-art-task073-gate-a-v5/1",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = response.read(8_000_001)
                status = response.status
        except urllib.error.HTTPError as exc:
            raise RuntimeError("GET_HTTP_%d:%s" % (exc.code, pathlib.PurePosixPath(path).name))
        if status != 200 or len(data) > 8_000_000:
            raise RuntimeError("GET_INVALID:%s:%s:%d" % (path, status, len(data)))
        return data.decode("utf-8")


def semantic_checks(candidates):
    checks = {}
    konteyner = candidates["konteyner.py"]
    cars_ui = candidates["cars_ui.py"]
    publikaciya = candidates["publikaciya.py"]

    checks["outer_actual_filter"] = (
        'if stage_no == nomer_etapa and code not in ("sea_loaded", "sea_transit")]'
        in konteyner
    )
    checks["outer_fallback_filter"] = (
        'if stage_no == number and code not in ("sea_loaded", "sea_transit")]'
        in cars_ui
    )
    ekran = [s for s in patcher._function_spans(konteyner, "_ekran")]
    checks["inner_actions_exact_once"] = len(ekran) == 1 and all(
        ekran[0].source.count(value) == 1
        for value in ("car_setstage:%d:sea_loaded", "car_setstage:%d:sea_transit")
    )
    checks["inner_uses_existing_button_class"] = (
        len(ekran) == 1
        and "InlineKeyboardButton" in ekran[0].source
        and "types.InlineKeyboardButton" not in ekran[0].source
    )
    toggle = [s for s in patcher._function_spans(cars_ui, "toggle_publish")]
    checks["toggle_signature_preserved"] = len(toggle) == 1 and toggle[0].source.startswith(
        "async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):"
    )
    checks["toggle_false_success_blocked"] = len(toggle) == 1 and all(
        value in toggle[0].source
        for value in ("if _ok_rem2 is not True:", "preimage_published", "_rollback_ok")
    )
    checks["seo_stale_guard_removed"] = all(
        "SEO068_DIAGNOSTIC_TARGET_MISSING" not in candidates[name]
        for name in ("stranica.py", "master_card.py", "yadro.py")
    )
    opub = [s for s in patcher._function_spans(publikaciya, "opublikovat")]
    checks["real_master_publisher_only"] = len(opub) == 1 and all(
        value in opub[0].source
        for value in (
            "html, diag, m = _master(kod)",
            "prichiny = proverit(html, kod)",
            "katalog, spisok = _ua9_sobrat_katalog()",
            'os.path.join(papka, "katalog.html")',
        )
    )
    checks["no_synthetic_renderer"] = not any(
        value in publikaciya
        for value in ("render_primary_html", "_postroit_stranicu", "ua-catalog-cards")
    )
    rollback = [s for s in patcher._function_spans(publikaciya, "_otkat")]
    checks["rollback_restores_or_deletes"] = len(rollback) == 1 and all(
        value in rollback[0].source
        for value in ("shutil.copy2(kopiya, put)", "os.remove(put)")
    )
    for name, value in candidates.items():
        try:
            compile(value, name, "exec")
            checks["compile:" + name] = True
        except Exception:
            checks["compile:" + name] = False
    return checks


def run() -> dict:
    result = {
        "contract_id": CONTRACT,
        "mode": "LIVE_GET_ONLY",
        "status": "BLOCKED",
        "production_write": False,
        "crm_db_write": False,
        "http_methods": ["GET"],
        "runtime_llm_tokens": 0,
        "generated_at_utc": utc_now(),
        "source_before_sha256": {},
        "candidate_sha256": {},
        "checks": {},
        "errors": [],
    }
    username = os.environ.get("PYTHONANYWHERE_USERNAME", "")
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
    try:
        if username != USERNAME:
            raise RuntimeError("PYTHONANYWHERE_USERNAME_MISMATCH")
        api = ReadOnlyAPI(token)
        sources = {}
        for name in patcher.FULL_FILE_SHA256:
            value = api.read_text(ROOT + "/" + name)
            patcher.require_full_sha(name, value)
            sources[name] = value
            result["source_before_sha256"][name] = patcher.sha256_text(value)
        candidates = patcher.build_candidates(sources, check_full_sha=True)
        result["candidate_sha256"] = patcher.candidate_hashes(candidates)
        result["checks"] = semantic_checks(candidates)
        if not result["checks"] or not all(result["checks"].values()):
            failed = sorted(name for name, ok in result["checks"].items() if not ok)
            raise RuntimeError("SEMANTIC_CHECKS:" + ",".join(failed))
        result["status"] = "PASS_READY_FOR_APPROVED_GATE_B"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    return result


def atomic_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    value = run()
    atomic_json(EVIDENCE, value)
    print(json.dumps({"status": value["status"], "errors": value["errors"]}, ensure_ascii=False))
    return 0 if value["status"] == "PASS_READY_FOR_APPROVED_GATE_B" else 1


if __name__ == "__main__":
    raise SystemExit(main())
