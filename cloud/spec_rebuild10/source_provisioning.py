"""Reviewed historical document inputs for the approved source worker.

No network calls, inferred vehicle identity, access grants or live acceptance.
The Kia normalizer operates on a reviewed text excerpt, not untested supplier
HTML. The file collector verifies both original capture and normalized payload.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import hashlib
import json
import re

from . import sources
from .worker import CollectedDocument, CollectorBinding, CollectionRequest

KIA_2023_URL = "https://www.kia.com/kr/vehicles/k5_bak_20231031/specification"


def kia_2023_lpi_candidate(excerpt: bytes) -> dict:
    """Extract eight model facts from a reviewed Korean 2023 LPI excerpt.

    The bytes' digest identifies the reviewed text capture, never the original
    supplier HTML. This creates a proposal only. Authorizing its import still
    requires independently supplied source rights, review and exact target data.
    """
    if not isinstance(excerpt, bytes) or not 1 <= len(excerpt) <= 12_000:
        raise sources.SourceError("REVIEWED_EXCERPT_SIZE_INVALID")
    try:
        text = excerpt.decode("utf-8")
    except UnicodeError:
        raise sources.SourceError("REVIEWED_EXCERPT_ENCODING_INVALID") from None
    if "<" in text or ">" in text or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
        raise sources.SourceError("REVIEWED_EXCERPT_FORMAT_INVALID")
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    if len(lines) != 10 or lines[:2] != ["The 2023 K5", "2.0 LPI"]:
        raise sources.SourceError("KIA_EXCERPT_SCOPE_INVALID")
    patterns = (
        (r"전장 \(mm\)\s*:\s*([\d,]+)", "length_mm", "mm", "Довжина", "Длина"),
        (r"전폭 \(mm\)\s*:\s*([\d,]+)", "width_mm", "mm", "Ширина", "Ширина"),
        (r"전고 \(mm\)\s*:\s*([\d,]+)", "height_mm", "mm", "Висота", "Высота"),
        (r"축거 \(mm\)\s*:\s*([\d,]+)", "wheelbase_mm", "mm", "Колісна база", "Колёсная база"),
        (r"배기량 \(cc\)\s*:\s*([\d,]+)", "engine_cc", "cm³", "Об’єм двигуна", "Объём двигателя"),
        (r"최고 출력 \(ps\)\s*:\s*([\d,]+)", "power_ps", "PS", "Потужність (метричні к. с.)", "Мощность (метрические л. с.)"),
        (r"최대 토크 \(kgf.m\)\s*:\s*(\d+(?:\.\d+)?)", "torque_kgfm", "kgf·m", "Крутний момент", "Крутящий момент"),
        (r"자동\s*:\s*(\d+)단", "transmission_gears", "", "Кількість передач АКПП", "Количество передач АКПП"),
    )
    facts = []
    for line, (pattern, key, unit, uk, ru) in zip(lines[2:], patterns):
        match = re.fullmatch(pattern, line)
        if not match:
            raise sources.SourceError("KIA_EXCERPT_SCHEMA_CHANGED")
        value = float(match[1].replace(",", ""))
        if not 0 < value < 100_000:
            raise sources.SourceError("KIA_EXCERPT_VALUE_INVALID")
        facts.append({"key": key, "value": int(value) if value.is_integer() else value,
                      "unit": unit, "label_uk": uk, "label_ru": ru, "category": "technical"})
    values = {row["key"]: row["value"] for row in facts}
    # Control-document checks detect the wrong engine, shifted columns or a
    # changed historical page. Do not turn this parser into a general K5 alias.
    if (values["engine_cc"] != 1999 or values["power_ps"] != 146
            or values["transmission_gears"] != 6):
        raise sources.SourceError("KIA_CONTROL_VARIANT_MISMATCH")
    return {"schema": "ua-art.normalized-source.v1", "source_id": "kia_kr",
            "identity": {"make": "Kia", "model": "K5", "year": 2023,
                         "market": "KR", "fuel": "LPG", "gearbox": "automatic",
                         "engine_cc": 1999},
            "document": {"url": KIA_2023_URL, "sha256": hashlib.sha256(excerpt).hexdigest(),
                         "evidence_kind": "manufacturer_document",
                         "capture_format": "reviewed-text-excerpt-v1"},
            "facts": facts}


@dataclass(frozen=True)
class ReviewedSourceInput:
    capture_path: Path
    payload_path: Path
    capture_sha256: str
    payload_sha256: str
    authorization: sources.ImportAuthorization


def _read_pinned(path: Path, digest: str, limit: int) -> bytes:
    path = Path(path)
    if not sources.SHA256.fullmatch(str(digest)) or path.is_symlink() or not path.is_file():
        raise sources.SourceError("REVIEWED_FILE_INVALID")
    try:
        with path.open("rb") as stream:
            value = stream.read(limit + 1)
    except OSError:
        raise sources.SourceError("REVIEWED_FILE_UNAVAILABLE") from None
    if len(value) > limit:
        raise sources.SourceError("REVIEWED_FILE_TOO_LARGE")
    if hashlib.sha256(value).hexdigest() != digest:
        raise sources.SourceError("REVIEWED_FILE_CHANGED")
    return value


def reviewed_file_collector(source_id: str, inputs: Sequence[ReviewedSourceInput], *,
                            access: sources.AccessGrant) -> CollectorBinding:
    """Use finite pinned supplier documents in the actual queue worker.

    Capture and payload hashes are reviewed out of band and checked on every
    collection, so replacing an accepted file cannot silently change its facts.
    No matching known variant returns NO_MATCH. Ambiguous matches fail closed.
    This is local document ingestion, not a claim of automated supplier access.
    """
    registry = sources.load_registry()
    if source_id not in registry or registry[source_id].adapter != "normalized_import_v1":
        raise sources.SourceError("SOURCE_ADAPTER_MISMATCH")
    sources._check_access(registry[source_id], access)
    inputs = tuple(inputs)
    if not 1 <= len(inputs) <= 128 or not all(isinstance(x, ReviewedSourceInput) for x in inputs):
        raise sources.SourceError("REVIEWED_INPUTS_INVALID")
    for entry in inputs:
        if (entry.authorization.source_id != source_id
                or entry.authorization.document_sha256 != entry.capture_sha256):
            raise sources.SourceError("REVIEWED_AUTHORIZATION_MISMATCH")

    def collect(request: CollectionRequest) -> CollectedDocument:
        if request.source_id != source_id:
            raise sources.SourceError("SOURCE_IMPERSONATION")
        matches = []
        for entry in inputs:
            _read_pinned(entry.capture_path, entry.capture_sha256, request.max_bytes)
            raw = _read_pinned(entry.payload_path, entry.payload_sha256, request.max_bytes)
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError):
                raise sources.SourceError("REVIEWED_PAYLOAD_INVALID") from None
            # Validate the payload against its own declared model before testing
            # applicability; an invalid or untrusted file is never NO_MATCH.
            if not isinstance(payload, dict):
                raise sources.SourceError("REVIEWED_PAYLOAD_INVALID")
            sources.parse_normalized_import(source_id, payload, payload.get("identity"),
                access=access, authorization=entry.authorization)
            try:
                sources.validate_identity(payload.get("identity"), request.identity)
            except sources.SourceError as error:
                if error.code == "IDENTITY_MISMATCH":
                    continue
                raise
            matches.append(CollectedDocument(source_id, payload,
                source_url=payload["document"]["url"], authorization=entry.authorization))
        if not matches:
            return CollectedDocument(source_id, outcome="NO_MATCH")
        if len(matches) != 1:
            raise sources.SourceError("REVIEWED_DOCUMENT_AMBIGUOUS")
        return matches[0]

    return CollectorBinding(source_id, collect, access)
