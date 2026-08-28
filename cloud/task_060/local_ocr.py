#!/usr/bin/env python3
"""Token-free OCR and deterministic UA ART CRM field extraction."""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


BRANDS = {
    "kia": "Kia",
    "hyundai": "Hyundai",
    "genesis": "Genesis",
    "toyota": "Toyota",
    "lexus": "Lexus",
    "nissan": "Nissan",
    "honda": "Honda",
    "mazda": "Mazda",
    "subaru": "Subaru",
    "mitsubishi": "Mitsubishi",
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "bmw": "BMW",
    "audi": "Audi",
    "volkswagen": "Volkswagen",
    "skoda": "Skoda",
    "ford": "Ford",
    "chevrolet": "Chevrolet",
    "renault": "Renault",
    "peugeot": "Peugeot",
    "citroen": "Citroen",
    "volvo": "Volvo",
}

VIN_RE = re.compile(r"(?<![A-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])", re.I)
CAR_LINE_RE = re.compile(
    r"\b(" + "|".join(re.escape(x) for x in sorted(BRANDS, key=len, reverse=True))
    + r")\s+([A-Z0-9][A-Z0-9._-]{0,15})(?:\s+((?:19|20)\d{2}))?\b",
    re.I,
)


def _languages(binary: str) -> str:
    try:
        result = subprocess.run(
            [binary, "--list-langs"], capture_output=True, text=True, timeout=1.0,
            check=False,
        )
        available = set(result.stdout.split())
    except Exception:
        available = set()
    chosen = [name for name in ("eng", "ukr", "rus") if name in available]
    return "+".join(chosen) or "eng"


def _ocr_one(image, binary: str, languages: str, deadline: float) -> str:
    remaining = deadline - time.monotonic()
    if remaining <= 0.25:
        return ""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        path = Path(handle.name)
    try:
        image.save(path, format="PNG", optimize=False)
        result = subprocess.run(
            [binary, str(path), "stdout", "-l", languages, "--psm", "3"],
            capture_output=True,
            text=True,
            timeout=max(0.2, min(1.2, remaining)),
            check=False,
        )
        return result.stdout if result.returncode == 0 else ""
    except subprocess.TimeoutExpired:
        return ""
    finally:
        path.unlink(missing_ok=True)


def image_text(image_bytes: bytes, hard_seconds: float = 5.5) -> str:
    """Run bounded local OCR; no network and no model-token use."""
    binary = shutil.which("tesseract")
    if not binary or not image_bytes:
        return ""
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    except Exception:
        return ""
    deadline = time.monotonic() + max(0.5, hard_seconds)
    try:
        original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return ""
    languages = _languages(binary)
    width, height = original.size
    if width < 32 or height < 32:
        return ""

    # Overlapping tiles make small nested advertisement screenshots readable.
    cols, rows = 2, 4
    tile_w = max(32, int(width * 0.56))
    tile_h = max(32, int(height * 0.34))
    x_positions = [0, max(0, width - tile_w)]
    y_positions = [
        0,
        max(0, int((height - tile_h) * 0.34)),
        max(0, int((height - tile_h) * 0.67)),
        max(0, height - tile_h),
    ]
    chunks = []
    for y in y_positions:
        for x in x_positions:
            if time.monotonic() >= deadline:
                break
            tile = original.crop((x, y, min(width, x + tile_w), min(height, y + tile_h)))
            scale = 3 if max(tile.size) < 1800 else 2
            tile = tile.resize((tile.width * scale, tile.height * scale), Image.Resampling.LANCZOS)
            tile = ImageOps.autocontrast(ImageOps.grayscale(tile), cutoff=1)
            tile = ImageEnhance.Contrast(tile).enhance(1.25)
            tile = tile.filter(ImageFilter.SHARPEN)
            text = _ocr_one(tile, binary, languages, deadline)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _put(data: dict, allowed: set[str], key: str, value) -> None:
    if key in allowed and value not in (None, ""):
        data.setdefault(key, value)


def fields_from_text(text: str, allowed_keys) -> dict:
    """Extract only runtime-allowed CRM fields from OCR or owner text."""
    allowed = set(allowed_keys or ())
    data = {}
    raw = str(text or "")
    folded = raw.casefold()

    match = CAR_LINE_RE.search(raw)
    if match:
        _put(data, allowed, "brand", BRANDS[match.group(1).casefold()])
        _put(data, allowed, "model", match.group(2).upper())
        _put(data, allowed, "year", match.group(3))

    vins = VIN_RE.findall(raw.upper())
    vins = [v for v in vins if any(c.isalpha() for c in v) and any(c.isdigit() for c in v)]
    if vins:
        _put(data, allowed, "vin", vins[0].upper())

    if "year" not in data:
        years = re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", raw)
        if years:
            _put(data, allowed, "year", years[0])

    mileage = re.search(
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})?|\d{1,4})\s*"
        r"(tuc|тыс|тис)?\.?\s*(km|км)\b",
        folded,
    )
    if mileage:
        value = int(re.sub(r"\D", "", mileage.group(1)))
        if mileage.group(2) and value < 10000:
            value *= 1000
        if 0 < value <= 2_000_000:
            _put(data, allowed, "mileage_km", value)

    if re.search(r"\b(lpg|газ|gaz|gas|fas)\b", folded):
        _put(data, allowed, "fuel", "LPG")
    elif re.search(r"\b(diesel|дизел)\w*\b", folded):
        _put(data, allowed, "fuel", "diesel")
    elif re.search(r"\b(hybrid|гибрид)\w*\b", folded):
        _put(data, allowed, "fuel", "hybrid")
    elif re.search(r"\b(electric|электро)\w*\b", folded):
        _put(data, allowed, "fuel", "electric")

    if re.search(r"\b(automatic|automat|astomat|asromat|автомат)\w*\b", folded):
        _put(data, allowed, "gearbox", "automatic")
    elif re.search(r"\b(manual|механик)\w*\b", folded):
        _put(data, allowed, "gearbox", "manual")

    fuel_engine = re.search(
        r"(?:lpg|gas|gaz|fas|\[a3|газ)[^\n]{0,8}?[,;:\s]\s*"
        r"([1-8])(?:\s*[.,]\s*([0-9]))?\s*(?:l|л|n)\b",
        folded,
    )
    engine = fuel_engine or re.search(
        r"(?<!\d)([1-8])\s*[.,]\s*([0-9])\s*(?:l|л|n)?\b", folded
    )
    if engine:
        fraction = int(engine.group(2) or 0)
        _put(data, allowed, "engine_cc", int(engine.group(1)) * 1000 + fraction * 100)
    else:
        engine = re.search(r"(?<!\d)([1-8])\s*(?:l|л|n)\b", folded)
        if engine:
            _put(data, allowed, "engine_cc", int(engine.group(1)) * 1000)
    return data


def fields_from_image(image_bytes: bytes, allowed_keys, hard_seconds: float = 5.5) -> dict:
    return fields_from_text(image_text(image_bytes, hard_seconds=hard_seconds), allowed_keys)
