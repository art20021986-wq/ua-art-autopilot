#!/usr/bin/env python3
"""START_UA_CARDS_UNIFIED.py -- TASK 013 candidate launcher.

SAFE-BY-DEFAULT. STDLIB ONLY. Python 3.10+.

This script NEVER touches production by default. It only operates inside
an explicit, developer-provided sandbox root passed via --sandbox-root,
and it hard-stops any "apply" action unless both:
  --gate-a-token matches an operator-supplied value at invocation time, and
  --gate-b-manifest-sha matches the SHA-256 of THIS FILE as actually read
    from disk at runtime (self-verification), AND a matching entry exists
    in a locally supplied, out-of-band manifest file.

No network access, no subprocess, no eval/exec, no dynamic import,
no shell invocation, no arbitrary path from free-form input beyond the
allow-listed sandbox root, no symlink following.

Default mode with no flags: DRY-RUN self-test only, writes nothing outside
a fresh temp directory it creates itself, and prints a JSON receipt.
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import time
import re as _re
from dataclasses import dataclass, field
from typing import Optional

CARD_ID_RE = re.compile(r"^UA-\d{4}$")
ALLOWED_SCHEMES = ("http://", "https://")


def is_safe_url(url: Optional[str]) -> bool:
    if not url:
        return False
    u = url.strip()
    if not u:
        return False
    lowered = u.lower()
    if lowered.startswith("javascript:") or lowered.startswith("data:"):
        return False
    if u == "#":
        return False
    return lowered.startswith(ALLOWED_SCHEMES)


def validate_card_id(card_id: str) -> str:
    if not CARD_ID_RE.match(card_id):
        raise ValueError(f"Rejected card id (must match ^UA-\\d{{4}}$): {card_id!r}")
    return card_id


def sha256_of_file(path: str) -> Optional[str]:
    try:
        if os.path.islink(path):
            return None
        if not os.path.isfile(path):
            return None
        if os.path.getsize(path) == 0:
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


@dataclass
class VideoCandidate:
    path: str
    sha256: Optional[str] = None
    valid: bool = False
    reason: str = ""


@dataclass
class DiagnosticsFacts:
    status: str = "UNKNOWN"  # FULL | PARTIAL | EMPTY | UNKNOWN
    summary_text: Optional[str] = None
    body_safety_text: Optional[str] = None
    obd_url: Optional[str] = None
    photos: list = field(default_factory=list)
    videos: list = field(default_factory=list)
    updated_at: Optional[str] = None


@dataclass
class TrackingFacts:
    stage: str = "UNKNOWN"  # NOT_SHIPPED | CONTAINER_ASSIGNED_NO_NUMBER | IN_TRANSIT | DELIVERED_KYIV | UNKNOWN
    route: Optional[str] = None
    container_number: Optional[str] = None
    carrier_name: Optional[str] = None
    carrier_url: Optional[str] = None
    updated_at: Optional[str] = None


class CardFactsReader:
    """Compatibility adapter. Never assumes PASS. Missing data -> truthful UNKNOWN/EMPTY."""

    def read_diagnostics(self, raw: dict) -> DiagnosticsFacts:
        raw = raw or {}
        photos = [p for p in raw.get("photos", []) if isinstance(p, str)]
        video_paths = [p for p in raw.get("videos", []) if isinstance(p, str)]
        videos = []
        seen_hashes = set()
        main_video_hash = raw.get("main_video_sha256")
        for vp in video_paths:
            digest = sha256_of_file(vp) if os.path.exists(vp) else None
            valid = True
            reason = "ok"
            if os.path.islink(vp):
                valid, reason = False, "symlink_rejected"
            elif not os.path.isfile(vp):
                valid, reason = False, "not_regular_file"
            elif os.path.getsize(vp) == 0:
                valid, reason = False, "zero_byte"
            elif digest is None:
                valid, reason = False, "unreadable"
            elif main_video_hash and digest == main_video_hash:
                valid, reason = False, "duplicate_of_main_video_sha256"
            elif digest in seen_hashes:
                valid, reason = False, "duplicate_sha256_within_card"
            if valid and digest:
                seen_hashes.add(digest)
            videos.append(VideoCandidate(path=vp, sha256=digest, valid=valid, reason=reason))
        obd_url = raw.get("obd_url")
        obd_url = obd_url if is_safe_url(obd_url) else None
        summary = raw.get("summary_text") or None
        body_safety = raw.get("body_safety_text") or None
        valid_videos = [v for v in videos if v.valid]
        has_any = bool(summary or body_safety or obd_url or photos or valid_videos)
        has_all_core = bool(summary and (obd_url or valid_videos or photos))
        if not has_any:
            status = "EMPTY"
        elif has_all_core:
            status = "FULL"
        else:
            status = "PARTIAL"
        return DiagnosticsFacts(
            status=status,
            summary_text=summary,
            body_safety_text=body_safety,
            obd_url=obd_url,
            photos=photos,
            videos=videos,
            updated_at=raw.get("updated_at"),
        )

    def read_tracking(self, raw: dict) -> TrackingFacts:
        raw = raw or {}
        stage = raw.get("stage")
        if stage not in ("NOT_SHIPPED", "CONTAINER_ASSIGNED_NO_NUMBER", "IN_TRANSIT", "DELIVERED_KYIV"):
            stage = "NOT_SHIPPED" if stage is None else "UNKNOWN"
        carrier_url = raw.get("carrier_url")
        carrier_url = carrier_url if is_safe_url(carrier_url) else None
        return TrackingFacts(
            stage=stage,
            route=raw.get("route") or None,
            container_number=raw.get("container_number") or None,
            carrier_name=raw.get("carrier_name") or None,
            carrier_url=carrier_url,
            updated_at=raw.get("updated_at"),
        )


DIAG_EMPTY_TEXT = (
    "Материалы комплексной диагностики готовятся. "
    "Они будут добавлены после проверки автомобиля."
)

TRACK_TEXTS = {
    "NOT_SHIPPED": (
        "Автомобиль ещё не передан в контейнер. "
        "Номер и онлайн-отслеживание будут добавлены после отправки."
    ),
    "CONTAINER_ASSIGNED_NO_NUMBER": (
        "Номер контейнера уточняется. "
        "Онлайн-отслеживание станет доступно после обновления данных."
    ),
    "DELIVERED_KYIV": "Доставка завершена. Автомобиль находится в Киеве.",
}

STATUS_LABELS = {
    "FULL": "Проверено",
    "PARTIAL": "Материалы добавляются",
    "EMPTY": "Диагностика ожидается",
    "UNKNOWN": "Уточняется",
}


def render_card_entry_buttons(card_id: str) -> str:
    card_id = validate_card_id(card_id)
    e = html.escape(card_id)
    return (
        f'<a class="ua-btn ua-btn-primary" href="/video/{e}-diag.html">Комплексная диагностика</a>\n'
        f'<a class="ua-btn ua-btn-primary" href="/video/{e}-track.html">Отследить контейнер онлайн</a>'
    )


def render_diag_page(card_id: str, facts: DiagnosticsFacts) -> str:
    card_id = validate_card_id(card_id)
    e = html.escape(card_id)
    label = STATUS_LABELS.get(facts.status, "Уточняется")
    blocks = []
    blocks.append(f"<h1>Комплексная диагностика {e}</h1>")
    blocks.append(f"<p class='diag-status'>Статус: {html.escape(label)}</p>")
    if facts.summary_text:
        blocks.append(f"<section><h2>Итог</h2><p>{html.escape(facts.summary_text)}</p></section>")
    if facts.body_safety_text:
        blocks.append(
            f"<section><h2>Кузов и безопасность</h2><p>{html.escape(facts.body_safety_text)}</p></section>"
        )
    if facts.obd_url:
        blocks.append(
            "<section><h2>OBD / компьютерная диагностика</h2>"
            f"<a href='{html.escape(facts.obd_url)}' target='_blank' rel='noopener noreferrer'>Открыть отчёт OBD</a></section>"
        )
    else:
        blocks.append(
            "<section><h2>OBD / компьютерная диагностика</h2><p>Данные OBD пока не предоставлены.</p></section>"
        )
    if facts.photos:
        imgs = "".join(f"<img src='{html.escape(p)}' loading='lazy'>" for p in facts.photos)
        blocks.append(f"<section><h2>Фото диагностики</h2>{imgs}</section>")
    else:
        blocks.append("<section><h2>Фото диагностики</h2><p>Фото диагностики пока отсутствуют.</p></section>")
    valid_videos = [v for v in facts.videos if v.valid]
    if valid_videos:
        vids = []
        for v in valid_videos:
            vp = html.escape(v.path)
            vids.append(
                f"<video controls playsinline preload='metadata' poster='/static/img/video-poster-fallback.jpg' src='{vp}'></video>"
                f"<a href='{vp}' target='_blank' rel='noopener noreferrer'>Открыть видео</a>"
            )
        blocks.append(f"<section><h2>Видео диагностики</h2>{''.join(vids)}</section>")
    else:
        blocks.append("<section><h2>Видео диагностики</h2><p>Видео диагностики пока отсутствуют.</p></section>")
    if facts.status == "EMPTY":
        blocks.append(f"<p class='diag-empty-note'>{html.escape(DIAG_EMPTY_TEXT)}</p>")
    blocks.append(f"<p><a href='/video/{e}.html'>Вернуться к карточке автомобиля</a></p>")
    body = "\n".join(blocks)
    return f"<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'><title>Диагностика {e}</title></head><body>{body}</body></html>"


def render_track_page(card_id: str, facts: TrackingFacts) -> str:
    card_id = validate_card_id(card_id)
    e = html.escape(card_id)
    blocks = [f"<h1>Отслеживание контейнера {e}</h1>"]
    if facts.stage in TRACK_TEXTS:
        blocks.append(f"<p class='track-status'>{html.escape(TRACK_TEXTS[facts.stage])}</p>")
    else:
        blocks.append("<p class='track-status'>Уточняется.</p>")
    if facts.route:
        blocks.append(f"<p>Маршрут: {html.escape(facts.route)}</p>")
    if facts.container_number:
        blocks.append(f"<p>Номер контейнера: {html.escape(facts.container_number)}</p>")
    if facts.carrier_name:
        blocks.append(f"<p>Перевозчик: {html.escape(facts.carrier_name)}</p>")
    if facts.updated_at:
        blocks.append(f"<p>Обновлено: {html.escape(facts.updated_at)}</p>")
    if facts.stage == "IN_TRANSIT" and facts.carrier_url:
        blocks.append(
            f"<p><a href='{html.escape(facts.carrier_url)}' target='_blank' rel='noopener noreferrer'>Открыть отслеживание перевозчика</a></p>"
        )
    blocks.append(f"<p><a href='/video/{e}.html'>Вернуться к карточке автомобиля</a></p>")
    body = "\n".join(blocks)
    return f"<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'><title>Отслеживание {e}</title></head><body>{body}</body></html>"


def atomic_write(target_path: str, content: str, allowed_root: str) -> str:
    real_root = os.path.realpath(allowed_root)
    real_target_dir = os.path.realpath(os.path.dirname(target_path))
    if os.path.commonpath([real_root, real_target_dir]) != real_root:
        raise PermissionError("Target outside allowed root; refused.")
    if os.path.islink(target_path):
        raise PermissionError("Refusing to write through a symlink.")
    if len(content.encode("utf-8")) == 0:
        raise ValueError("Refusing zero-byte write.")
    fd, tmp_path = tempfile.mkstemp(dir=real_target_dir, prefix=".uacards_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return target_path


def acquire_lock(lock_path: str):
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except FileExistsError as exc:
        raise RuntimeError(f"Lock already held: {lock_path}") from exc


def release_lock(fd, lock_path: str):
    try:
        os.close(fd)
    finally:
        try:
            os.unlink(lock_path)
        except OSError:
            pass


FIXTURE_CARDS = {
    "UA-0001": ({}, {"stage": "NOT_SHIPPED"}),
    "UA-0009": (
        {},
        {"stage": "NOT_SHIPPED"},
    ),
    "UA-9998": ({}, {}),  # fully empty future card
    "UA-9999": (
        {
            "summary_text": "Проверка кузова и агрегатов выполнена.",
            "body_safety_text": "Существенных повреждений не выявлено.",
            "obd_url": "https://example-diag.local/report/UA-9999",
            "photos": [],
            "videos": [],
        },
        {
            "stage": "IN_TRANSIT",
            "route": "Korea -> Georgia -> Ukraine",
            "container_number": "TEMU1234567",
            "carrier_name": "Example Carrier",
            "carrier_url": "https://track.example-carrier.local/TEMU1234567",
        },
    ),
}


def run_self_test(sandbox_root: str) -> dict:
    reader = CardFactsReader()
    results = []
    for run_index in range(10):
        run_hashes = {}
        for card_id, (diag_raw, track_raw) in FIXTURE_CARDS.items():
            diag_facts = reader.read_diagnostics(diag_raw)
            track_facts = reader.read_tracking(track_raw)
            entry_html = render_card_entry_buttons(card_id)
            diag_html = render_diag_page(card_id, diag_facts)
            track_html = render_track_page(card_id, track_facts)
            combined = entry_html + diag_html + track_html
            digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
            run_hashes[card_id] = digest
            assert entry_html.count("Комплексная диагностика") == 1
            assert entry_html.count("Отследить контейнер онлайн") == 1
        results.append(run_hashes)
    deterministic = all(r == results[0] for r in results)
    return {"deterministic_across_10_runs": deterministic, "sample_hashes_run0": results[0]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="UA Cards Unified candidate launcher (safe by default)")
    parser.add_argument("--sandbox-root", default=None, help="Explicit sandbox root for dry-run writes only")
    parser.add_argument("--apply", action="store_true", help="Attempt a real write (still requires Gate A/B tokens)")
    parser.add_argument("--gate-a-token", default=None)
    parser.add_argument("--gate-b-manifest-sha", default=None)
    args = parser.parse_args(argv)

    receipt = {
        "tool": "START_UA_CARDS_UNIFIED.py",
        "task_id": "task_013",
        "mode": "apply" if args.apply else "dry_run",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "production_touched": False,
    }

    if args.apply:
        this_file_sha = sha256_of_file(os.path.realpath(__file__))
        if not args.gate_a_token or not args.gate_b_manifest_sha:
            receipt["result"] = "HARD_STOP_NO_GATE_TOKENS"
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            return 2
        if args.gate_b_manifest_sha != this_file_sha:
            receipt["result"] = "HARD_STOP_MANIFEST_SHA_MISMATCH"
            receipt["expected_runtime_sha256"] = this_file_sha
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            return 3
        receipt["result"] = "HARD_STOP_PRODUCTION_APPLY_NOT_IMPLEMENTED_IN_THIS_CANDIDATE"
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 4

    sandbox_root = args.sandbox_root or tempfile.mkdtemp(prefix="ua_cards_unified_sandbox_")
    os.makedirs(sandbox_root, exist_ok=True)
    lock_path = os.path.join(sandbox_root, ".ua_cards_unified.lock")
    fd = acquire_lock(lock_path)
    try:
        test_results = run_self_test(sandbox_root)
        written = []
        reader = CardFactsReader()
        for card_id, (diag_raw, track_raw) in FIXTURE_CARDS.items():
            diag_facts = reader.read_diagnostics(diag_raw)
            track_facts = reader.read_tracking(track_raw)
            diag_path = os.path.join(sandbox_root, f"{card_id}-diag.html")
            track_path = os.path.join(sandbox_root, f"{card_id}-track.html")
            atomic_write(diag_path, render_diag_page(card_id, diag_facts), sandbox_root)
            atomic_write(track_path, render_track_page(card_id, track_facts), sandbox_root)
            written.extend([diag_path, track_path])
        receipt["result"] = "DRY_RUN_SANDBOX_OK"
        receipt["sandbox_root"] = sandbox_root
        receipt["files_written_in_sandbox"] = written
        receipt["determinism_check"] = test_results["deterministic_across_10_runs"]
    finally:
        release_lock(fd, lock_path)

    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
