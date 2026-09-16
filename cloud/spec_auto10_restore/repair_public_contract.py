"""Bridge the exact legacy VIN-panel contract to the approved single-VIN page.

The former contract required a second VIN panel. The canonical validator now
requires the one VIN in the technical table. Preserve all unrelated legacy
conditions, and add canonical fact, VIN, static-shell and stage-order checks.
"""
import hashlib

SOURCE_SHA256 = "5a03cb99d1f4514539956f32a75e09e119e2e9049a91da6326adb32877518e56"
BLOCK = r'''
# >>> UA SPEC AUTO10 SINGLE VIN CONTRACT BRIDGE V1
_UA_AUTO10_LEGACY_PUBLIC_CONTRACT = public_contract_errors


def public_contract_errors(source, value):
    code = canonical_uid(value)
    if not code:
        return ["INVALID_CARD_ID"]
    errors = [error for error in _UA_AUTO10_LEGACY_PUBLIC_CONTRACT(source, value)
              if error not in {"clean VIN blocks != 1", "additional spec/VIN order", "VIN/stage order"}]
    try:
        _ua_auto10_publication.validate_page(
            source, code, _ua_auto10_publication.load_facts(code)
        )
        shell = _ua_auto10_publication.card_shell
        _, shown_vin = shell._main_vin(shell._Page(source), code)
        if shown_vin != str(_car_vin(code) or "").strip().upper():
            errors.append("primary VIN differs from operator CRM")
    except _ua_auto10_publication.SpecError as exc:
        errors.append("canonical spec/VIN: " + str(exc))
    stage = _contract_marker_span(source, "STAGE")
    if stage is None or source.find(END) < 0 or source.find(END) + len(END) > stage[0]:
        errors.append("additional spec/stage order")
    return list(dict.fromkeys(errors))
# <<< UA SPEC AUTO10 SINGLE VIN CONTRACT BRIDGE V1
'''.strip()


def patch_public_contract(source: str) -> str:
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise ValueError("PUBLIC_CONTRACT_SOURCE_SHA_MISMATCH")
    output = source.rstrip() + "\n\n" + BLOCK + "\n"
    compile(output, "ua_additional_spec.py", "exec")
    return output
