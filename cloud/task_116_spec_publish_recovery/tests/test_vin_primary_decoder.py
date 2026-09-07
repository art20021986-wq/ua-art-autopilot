import io
import json

import pytest

from vin_primary_decoder import decode_primary_candidates


VIN = "1HGBH41JXMN109186"  # Synthetic fixture; not the VIN of UA-0017.


class Response:
    status = 200

    def __init__(self, value, url=None):
        self.value = value
        self.url = url or (
            "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
            + VIN
            + "?format=json"
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self, _limit):
        return json.dumps(self.value).encode()


def opener(value, url=None):
    def call(_request, timeout):
        assert timeout > 0
        return Response(value, url)

    return call


def test_exact_returned_vin_is_required():
    payload = {"Results": [{"VIN": VIN, "ErrorCode": "0", "Make": "Mercedes-Benz"}]}
    rows = decode_primary_candidates(VIN, opener=opener(payload))
    assert [(row.field, row.value) for row in rows] == [("brand", "Mercedes-Benz")]

    payload["Results"][0]["VIN"] = "WDDMH0BBXDV171918"
    with pytest.raises(RuntimeError, match="VPIC_VIN_MISMATCH"):
        decode_primary_candidates(VIN, opener=opener(payload))


def test_redirect_and_decoder_error_fail_closed():
    payload = {"Results": [{"VIN": VIN, "ErrorCode": "0", "Model": "B-Class"}]}
    with pytest.raises(RuntimeError, match="VPIC_REDIRECT_FORBIDDEN"):
        decode_primary_candidates(
            VIN, opener=opener(payload, "https://example.test/result")
        )
    payload["Results"][0]["ErrorCode"] = "1"
    with pytest.raises(RuntimeError, match="VPIC_IDENTITY_NOT_DECODED"):
        decode_primary_candidates(VIN, opener=opener(payload))


@pytest.mark.parametrize("error_code", [None, "", "0,,0", "0,garbage"])
def test_missing_or_malformed_decoder_success_code_fails_closed(error_code):
    payload = {"Results": [{"VIN": VIN, "Make": "Example"}]}
    if error_code is not None:
        payload["Results"][0]["ErrorCode"] = error_code
    with pytest.raises(RuntimeError, match="VPIC_(ERROR_CODE_MISSING|IDENTITY_NOT_DECODED)"):
        decode_primary_candidates(VIN, opener=opener(payload))


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 31])
def test_decoder_timeout_is_positive_finite_and_bounded(timeout):
    with pytest.raises(RuntimeError, match="VPIC_TIMEOUT_INVALID"):
        decode_primary_candidates(VIN, opener=opener({}), timeout=timeout)
