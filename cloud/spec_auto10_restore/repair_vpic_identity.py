"""Pure, hash-pinned vPIC response-to-request VIN binding for candidate v2.

No production imports, file writes, API calls or source-pool changes.
The frozen source remains intact; the joint builder applies this patch to its
next complete candidate and records the resulting module hash.
"""
import ast
import hashlib

SOURCE_SHA256 = "e9590c1630a8c81bcacf05d620e273a341aaf407f39c3a1bd184258c17ce3f0d"
MARKER = "# UA_SPEC_VPIC_IDENTITY_BINDING_V2: exact response VIN required."


def patch_vpic_identity(source: str) -> str:
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise ValueError("VPIC_SOURCE_SHA_MISMATCH")
    changes = (
        ('    identity["ErrorCode"] = _clean(data.get("ErrorCode"))\n',
         '    identity["ErrorCode"] = _clean(data.get("ErrorCode"))\n'
         '    identity["VIN"] = _clean(data.get("VIN"))\n'),
        ('def vpic_identity_matches(car: dict[str, Any], identity: dict[str, Any]) -> bool:\n'
         '    error_code = _clean(identity.get("ErrorCode"))\n',
         'def vpic_identity_matches(car: dict[str, Any], identity: dict[str, Any]) -> bool:\n'
         '    # Matching model/year alone cannot bind this response to this vehicle.\n'
         '    try:\n'
         '        if normalize_vin(identity.get("VIN")) != normalize_vin(car.get("vin")):\n'
         '            return False\n'
         '    except SourcePolicyError:\n'
         '        return False\n'
         '    error_code = _clean(identity.get("ErrorCode"))\n'),
        ('        {"brand": "Mercedes-Benz", "model": "B-Class", "year": "2013"},\n',
         '        {"vin": "WDDMH0BBXDV171918", "brand": "Mercedes-Benz", "model": "B-Class", "year": "2013"},\n'),
        ('        {"Make": "MERCEDES-BENZ", "Model": "B-Class", "ModelYear": "2013", "ErrorCode": "0"},\n',
         '        {"VIN": "WDDMH0BBXDV171918", "Make": "MERCEDES-BENZ", "Model": "B-Class", "ModelYear": "2013", "ErrorCode": "0"},\n'),
    )
    result = source
    for old, new in changes:
        if result.count(old) != 1:
            raise ValueError("VPIC_PATCH_ANCHOR_MISMATCH")
        result = result.replace(old, new, 1)
    result += "\n" + MARKER + "\n"
    ast.parse(result)
    compile(result, "source_policy.py", "exec")
    return result
