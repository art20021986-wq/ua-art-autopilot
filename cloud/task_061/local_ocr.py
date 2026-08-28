#!/usr/bin/env python3
"""Bounded, token-free OCR and deterministic UA ART CRM field extraction."""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


DEFAULT_PHOTO_SECONDS = 13.5

BRANDS = {
    "kia": "Kia",
    "киа": "Kia",
    "hyundai": "Hyundai",
    "хендай": "Hyundai",
    "хёндай": "Hyundai",
    "genesis": "Genesis",
    "генезис": "Genesis",
    "toyota": "Toyota",
    "тойота": "Toyota",
    "lexus": "Lexus",
    "лексус": "Lexus",
    "nissan": "Nissan",
    "ниссан": "Nissan",
    "honda": "Honda",
    "хонда": "Honda",
    "mazda": "Mazda",
    "мазда": "Mazda",
    "subaru": "Subaru",
    "субару": "Subaru",
    "mitsubishi": "Mitsubishi",
    "мицубиси": "Mitsubishi",
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "мерседес": "Mercedes-Benz",
    "bmw": "BMW",
    "бмв": "BMW",
    "audi": "Audi",
    "ауди": "Audi",
    "volkswagen": "Volkswagen",
    "фольксваген": "Volkswagen",
    "skoda": "Skoda",
    "шкода": "Skoda",
    "ford": "Ford",
    "форд": "Ford",
    "chevrolet": "Chevrolet",
    "шевроле": "Chevrolet",
    "renault": "Renault",
    "рено": "Renault",
    "peugeot": "Peugeot",
    "пежо": "Peugeot",
    "citroen": "Citroen",
    "ситроен": "Citroen",
    "volvo": "Volvo",
    "вольво": "Volvo",
}

VIN_RE = re.compile(r"(?<![A-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])", re.I)
CAR_LINE_RE = re.compile(
    r"\b(" + "|".join(re.escape(x) for x in sorted(BRANDS, key=len, reverse=True))
    + r")\s+([A-ZА-ЯЁІЇЄ0-9][A-ZА-ЯЁІЇЄ0-9._-]{0,15})"
      r"(?:\s+((?:19|20)\d{2}))?\b",
    re.I,
)


def _languages(binary: str) -> str:
    try:
        result = subprocess.run(
            [binary, "--list-langs"], capture_output=True, text=True,
            timeout=1.0, check=False,
        )
        available = set(result.stdout.split())
    except Exception:
        available = set()
    chosen = [name for name in ("eng", "ukr", "rus") if name in available]
    return "+".join(chosen) or "eng"


def _prepare(image, scale: int):
    from PIL import ImageEnhance, ImageFilter, ImageOps

    if scale > 1:
        image = image.resize(
            (image.width * scale, image.height * scale),
            resample=getattr(__import__("PIL.Image", fromlist=["Resampling"]), "Resampling").LANCZOS,
        )
    image = ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(1.25)
    return image.filter(ImageFilter.SHARPEN)


def _ocr_one(image, binary: str, languages: str, deadline: float, psm: int) -> str:
    remaining = deadline - time.monotonic()
    if remaining <= 0.3:
        return ""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        path = Path(handle.name)
    try:
        image.save(path, format="PNG", optimize=False)
        result = subprocess.run(
            [binary, str(path), "stdout", "-l", languages, "--psm", str(psm)],
            capture_output=True,
            text=True,
            timeout=max(0.25, min(1.45, remaining)),
            check=False,
        )
        return result.stdout if result.returncode == 0 else ""
    except subprocess.TimeoutExpired:
        return ""
    finally:
        path.unlink(missing_ok=True)


def image_text(image_bytes: bytes, hard_seconds: float = DEFAULT_PHOTO_SECONDS) -> str:
    """Run local OCR within the caller's deadline; never use a network model."""
    binary = shutil.which("tesseract")
    if not binary or not image_bytes:
        return ""
    try:
        from PIL import Image
    except Exception:
        return ""

    deadline = time.monotonic() + max(0.5, float(hard_seconds))
    try:
        original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return ""
    width, height = original.size
    if width < 32 or height < 32:
        return ""

    languages = _languages(binary)
    chunks = []

    # A sparse full-page pass finds large labels before the detailed crop passes.
    full_scale = 2 if max(width, height) < 2200 else 1
    full = _prepare(original.copy(), full_scale)
    first = _ocr_one(full, binary, languages, deadline, 11)
    if first:
        chunks.append(first)

    # Right-first overlapping tiles prioritize nested marketplace screenshots
    # commonly forwarded inside Telegram while still covering the whole image.
    tile_w = max(32, int(width * 0.56))
    tile_h = max(32, int(height * 0.34))
    x_positions = [max(0, width - tile_w), 0]
    y_positions = [
        0,
        max(0, int((height - tile_h) * 0.34)),
        max(0, int((height - tile_h) * 0.67)),
        max(0, height - tile_h),
    ]
    for y in y_positions:
        for x in x_positions:
            if time.monotonic() >= deadline:
                break
            tile = original.crop((x, y, min(width, x + tile_w), min(height, y + tile_h)))
            scale = 3 if max(tile.size) < 1800 else 2
            text = _ocr_one(_prepare(tile, scale), binary, languages, deadline, 3)
            if text and text not in chunks:
                chunks.append(text)
    return "\n".join(chunks)


def _put(data: dict, allowed: set[str], key: str, value) -> None:
    if key in allowed and value not in (None, ""):
        data.setdefault(key, value)


def fields_from_text(text: str, allowed_keys) -> dict:
    """Extract only keys that exist in the live CRM schema."""
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
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})?|\d{1,7})\s*"
        r"(tuc|тыс|тис|тысяч|тисяч)?\.?\s*(km|км)\b",
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
    elif re.search(r"\b(electric|электро|ev)\w*\b", folded):
        _put(data, allowed, "fuel", "electric")
    elif re.search(r"\b(gasoline|petrol|бензин)\w*\b", folded):
        _put(data, allowed, "fuel", "gasoline")

    if re.search(r"\b(automatic|automat|astomat|asromat|автомат)\w*\b", folded):
        _put(data, allowed, "gearbox", "automatic")
    elif re.search(r"\b(manual|механик)\w*\b", folded):
        _put(data, allowed, "gearbox", "manual")

    if re.search(r"\b(awd|4wd|полный|повний)\b", folded):
        _put(data, allowed, "drive", "4wd")
    elif re.search(r"\b(fwd|передний|передній)\b", folded):
        _put(data, allowed, "drive", "fwd")
    elif re.search(r"\b(rwd|задний|задній)\b", folded):
        _put(data, allowed, "drive", "rwd")

    fuel_engine = re.search(
        r"(?:lpg|gas|gaz|fas|газ)[^\n]{0,10}?[,;:\s]\s*"
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


def fields_from_image(
    image_bytes: bytes,
    allowed_keys,
    hard_seconds: float = DEFAULT_PHOTO_SECONDS,
) -> dict:
    return fields_from_text(image_text(image_bytes, hard_seconds=hard_seconds), allowed_keys)
