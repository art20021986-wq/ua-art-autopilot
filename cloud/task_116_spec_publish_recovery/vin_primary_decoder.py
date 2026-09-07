#!/usr/bin/env python3
"""Strict official-vPIC adapter for deterministic primary-field candidates."""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from typing import Any, Callable

from recovery_core import BaseCandidate, normalize_vin, vin_sha256


ENDPOINT = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
MAP = {
    "Make": "brand",
    "Model": "model",
    "ModelYear": "year",
    "BodyClass": "body",
    "FuelTypePrimary": "fuel",
    "DisplacementCC": "engine_cc",
    "TransmissionStyle": "gearbox",
    "DriveType": "drive",
}
EMPTY = {"", "0", "null", "not applicable", "n/a"}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def decode_primary_candidates(
    vin: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = 15.0,
) -> list[BaseCandidate]:
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise RuntimeError("VPIC_TIMEOUT_INVALID")
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 30:
        raise RuntimeError("VPIC_TIMEOUT_INVALID")
    normalized = normalize_vin(vin)
    url = ENDPOINT.format(vin=urllib.parse.quote(normalized, safe=""))
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "UAART-TASK116/1.0", "Accept": "application/json"},
        method="GET",
    )
    with opener(request, timeout=timeout) as response:
        final = urllib.parse.urlsplit(str(response.geturl()))
        if final.scheme != "https" or final.hostname != "vpic.nhtsa.dot.gov":
            raise RuntimeError("VPIC_REDIRECT_FORBIDDEN")
        if int(getattr(response, "status", 200)) != 200:
            raise RuntimeError("VPIC_HTTP_STATUS")
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise RuntimeError("VPIC_RESPONSE_TOO_LARGE")
    value = json.loads(payload.decode("utf-8"))
    rows = value.get("Results") if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise RuntimeError("VPIC_RESULT_INVALID")
    row = rows[0]
    returned_vin = _clean(row.get("VIN"))
    if not returned_vin or normalize_vin(returned_vin) != normalized:
        raise RuntimeError("VPIC_VIN_MISMATCH")
    raw_error_code = row.get("ErrorCode")
    if not isinstance(raw_error_code, (str, int)):
        raise RuntimeError("VPIC_ERROR_CODE_MISSING")
    error_code = _clean(raw_error_code)
    if not error_code:
        raise RuntimeError("VPIC_ERROR_CODE_MISSING")
    if not re.fullmatch(r"0(?:\s*,\s*0)*", error_code):
        raise RuntimeError("VPIC_IDENTITY_NOT_DECODED")
    additional_error = _clean(row.get("AdditionalErrorText"))
    if additional_error and additional_error.casefold() not in EMPTY:
        raise RuntimeError("VPIC_ADDITIONAL_ERROR")
    result: list[BaseCandidate] = []
    for source_field, target_field in MAP.items():
        item = _clean(row.get(source_field))
        if item.casefold() in EMPTY:
            continue
        result.append(
            BaseCandidate(
                field=target_field,
                value=item,
                source_kind="vin_decoder",
                source="vpic.nhtsa.dot.gov",
                confidence=0.96,
                vin_sha256=vin_sha256(normalized),
            )
        )
    return result
