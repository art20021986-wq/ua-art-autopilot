#!/usr/bin/env python3
"""
UA-ORDER-GE-8COUNTRY-GUARD-016 sandbox executor.

Stdlib-only, fail-closed sandbox builder/validator for the 8-country
"Auto under order" expansion and the UA/RU/KA language rollout.

This tool NEVER writes to production. It only ever writes files when an
explicit --sandbox-root is supplied via --build-sandbox, and only after
confirming that path is not equal to, and not nested inside, any known
production root, and does not itself resemble a production path.

Modes:
  --self-test       Run internal assertions against the bundled config
                     JSON files. No filesystem writes. Default mode.
  --discover        Validate an externally supplied car manifest
                     (--car-manifest) against the required 16-card /
                     3+1+8+4 baseline. Read-only.
  --build-sandbox   Copy vetted config JSON into an isolated
                     --sandbox-root. Refuses unsafe roots.
  --validate        Validate bundled config plus (optionally) an
                     external car manifest. Read-only.
  --report          Print a small JSON summary of whitelists and
                     expected counters. Read-only.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

LANG_WHITELIST = ("uk", "ru", "ka")
DEFAULT_LANG = "uk"

COUNTRY_WHITELIST = (
    "korea", "japan", "usa", "europe",
    "china", "canada", "uae", "georgia",
)
DEFAULT_COUNTRY = "korea"

EXPECTED_TOTAL_CARDS = 16
EXPECTED_STAGE_COUNTS = {
    "kyiv": 3,
    "georgia": 1,
    "on_ferry": 8,
    "korea": 4,
}

# Defensive denylist only. This does not claim knowledge of real
# production infrastructure secrets or exact PythonAnywhere paths.
PRODUCTION_PATH_MARKERS = (
    "/home/", "pythonanywhere", "production", "prod_live", "/var/www",
)

HERE = Path(__file__).resolve().parent


def load_json(name):
    path = HERE / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_lang(code):
    if not code:
        return DEFAULT_LANG
    code = str(code).strip().lower()
    if code == "ge":
        # 'ge' as a language code is explicitly forbidden by spec.
        return DEFAULT_LANG
    if code in LANG_WHITELIST:
        return code
    return DEFAULT_LANG


def normalize_country(code):
    if not code:
        return DEFAULT_COUNTRY
    code = str(code).strip().lower()
    if code in COUNTRY_WHITELIST:
        return code
    return DEFAULT_COUNTRY


def build_route(country, lang):
    country = normalize_country(country)
    lang = normalize_lang(lang)
    return f"podbor.html?strana={country}&lang={lang}"


def is_production_path(path):
    """Fail-closed check: True if the path looks like a production path."""
    p = str(Path(path).resolve()).lower()
    return any(marker in p for marker in PRODUCTION_PATH_MARKERS)


def assert_safe_sandbox_root(sandbox_root, production_root=None):
    """
    Raise ValueError if sandbox_root is unsafe:
    - resembles a production path via denylist markers
    - equals a declared production root
    - is nested inside a declared production root
    """
    sandbox_resolved = Path(sandbox_root).resolve()

    if is_production_path(sandbox_resolved):
        raise ValueError(
            f"REFUSING: sandbox root looks like a production path: {sandbox_resolved}"
        )

    if production_root:
        prod_resolved = Path(production_root).resolve()
        if sandbox_resolved == prod_resolved:
            raise ValueError("REFUSING: sandbox root equals production root")
        is_nested = False
        try:
            sandbox_resolved.relative_to(prod_resolved)
            is_nested = True
        except ValueError:
            is_nested = False
        if is_nested:
            raise ValueError("REFUSING: sandbox root is nested inside production root")

    return True


def load_country_models():
    return load_json("country_models.json")


def load_i18n():
    return load_json("i18n_dictionary_uk_ru_ka.json")


def validate_country_models(data):
    errors = []
    countries = data.get("countries", {})
    if set(countries.keys()) != set(COUNTRY_WHITELIST):
        errors.append(
            f"country key mismatch: expected {sorted(COUNTRY_WHITELIST)}, "
            f"got {sorted(countries.keys())}"
        )

    total_models = 0
    for code in COUNTRY_WHITELIST:
        entry = countries.get(code)
        if not entry:
            errors.append(f"missing country entry: {code}")
            continue
        models = entry.get("models", [])
        if len(models) != 5:
            errors.append(f"{code}: expected 5 models, got {len(models)}")
        total_models += len(models)

    if total_models != 40:
        errors.append(f"expected 40 total models, got {total_models}")

    usa_models = countries.get("usa", {}).get("models")
    uae_models = countries.get("uae", {}).get("models")
    if usa_models is uae_models:
        errors.append("uae models must not be the same object reference as usa")

    return errors


def validate_i18n(data):
    errors = []
    for lang in LANG_WHITELIST:
        if lang not in data:
            errors.append(f"missing language block: {lang}")

    control_strings_ka = {
        "order_title": "ავტომობილი შეკვეთით",
        "order_subtitle": "შეგირჩევთ ავტომობილს თქვენი ბიუჯეტისა და სურვილების შესაბამისად",
        "price_fixed_notice": "ფასი ფიქსირდება ხელშეკრულებაში და არ იცვლება",
        "select_car_cta": "ავტომობილის შერჩევა",
    }
    ka_block = data.get("ka", {})
    for key, expected in control_strings_ka.items():
        actual = ka_block.get(key)
        if actual != expected:
            errors.append(f"ka control string mismatch for {key}: {actual!r} != {expected!r}")
        else:
            try:
                actual.encode("utf-8")
            except UnicodeEncodeError:
                errors.append(f"ka control string {key} not valid UTF-8")
    return errors


def compute_stage_counters(car_manifest):
    counters = {"kyiv": 0, "georgia": 0, "on_ferry": 0, "korea": 0}
    for car in car_manifest:
        stage = car.get("stage")
        if stage in counters:
            counters[stage] += 1
    return counters


def validate_card_baseline(car_manifest):
    errors = []
    ids = [c.get("id") for c in car_manifest]
    if len(ids) != EXPECTED_TOTAL_CARDS:
        errors.append(f"expected {EXPECTED_TOTAL_CARDS} cards, got {len(ids)}")
    if len(set(ids)) != len(ids):
        errors.append("duplicate card ids detected")

    counters = compute_stage_counters(car_manifest)
    for stage, expected in EXPECTED_STAGE_COUNTS.items():
        if counters.get(stage) != expected:
            errors.append(
                f"stage {stage}: expected {expected}, got {counters.get(stage)}"
            )
    if sum(EXPECTED_STAGE_COUNTS.values()) != EXPECTED_TOTAL_CARDS:
        errors.append("expected stage sum mismatch with total cards constant")

    return errors, counters


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest_entry(car):
    """Deterministic manifest fields for a single card (no side effects)."""
    return {
        "id": car.get("id"),
        "vin": car.get("vin"),
        "stage": car.get("stage"),
        "price": car.get("price"),
        "photo_count": car.get("photo_count"),
        "video_count": car.get("video_count"),
        "diagnostics_count": car.get("diagnostics_count"),
        "container": car.get("container"),
        "media_sha256": car.get("media_sha256"),
    }


def compare_manifests(before, after):
    """Return a list of unexpected diffs. Empty list means identical (PASS)."""
    diffs = []
    before_by_id = {c["id"]: c for c in before}
    after_by_id = {c["id"]: c for c in after}
    if set(before_by_id) != set(after_by_id):
        diffs.append("card id set changed")
        return diffs
    for cid, b in before_by_id.items():
        a = after_by_id[cid]
        for key in b:
            if b.get(key) != a.get(key):
                diffs.append(f"{cid}.{key} changed: {b.get(key)!r} -> {a.get(key)!r}")
    return diffs


def cmd_self_test():
    print("Running internal self-test (no filesystem writes)...")
    assert normalize_lang(None) == "uk"
    assert normalize_lang("ge") == "uk"
    assert normalize_lang("KA") == "ka"
    assert normalize_country(None) == "korea"
    assert normalize_country("mars") == "korea"

    data = load_country_models()
    errs = validate_country_models(data)
    if errs:
        print("SELF-TEST FAIL:", errs)
        return 1

    i18n = load_i18n()
    errs = validate_i18n(i18n)
    if errs:
        print("SELF-TEST FAIL:", errs)
        return 1

    print("SELF-TEST PASS")
    return 0


def cmd_discover(args):
    """
    Discovery mode: only reads a car manifest JSON supplied by the caller
    via --car-manifest. This tool does not know or assume any real
    production file paths and will not scan the filesystem for them.
    """
    if not args.car_manifest:
        print("DISCOVER: no --car-manifest supplied. NOT_RUN (no source of truth available).")
        return 2
    manifest_path = Path(args.car_manifest)
    if is_production_path(manifest_path):
        print("REFUSING: --car-manifest path looks like production. Aborting.")
        return 3
    with open(manifest_path, "r", encoding="utf-8") as f:
        cars = json.load(f)
    errors, counters = validate_card_baseline(cars)
    result = {
        "total": len(cars),
        "counters": counters,
        "errors": errors,
        "baseline_ok": not errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 4


def cmd_build_sandbox(args):
    if not args.sandbox_root:
        print("REFUSING: --sandbox-root is required for --build-sandbox")
        return 2
    try:
        assert_safe_sandbox_root(args.sandbox_root, args.production_root)
    except ValueError as e:
        print(str(e))
        return 3

    sandbox_root = Path(args.sandbox_root)
    sandbox_root.mkdir(parents=True, exist_ok=True)
    (sandbox_root / "config").mkdir(exist_ok=True)
    for name in ("country_models.json", "i18n_dictionary_uk_ru_ka.json"):
        src = HERE / name
        dst = sandbox_root / "config" / name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Sandbox build written to isolated path: {sandbox_root}")
    return 0


def cmd_validate(args):
    rc = 0
    data = load_country_models()
    errs = validate_country_models(data)
    if errs:
        print("VALIDATE country_models FAIL:", errs)
        rc = 1
    else:
        print("VALIDATE country_models PASS")

    i18n = load_i18n()
    errs = validate_i18n(i18n)
    if errs:
        print("VALIDATE i18n FAIL:", errs)
        rc = 1
    else:
        print("VALIDATE i18n PASS")

    if args.car_manifest:
        manifest_path = Path(args.car_manifest)
        if is_production_path(manifest_path):
            print("REFUSING: --car-manifest path looks like production.")
            return 3
        with open(manifest_path, "r", encoding="utf-8") as f:
            cars = json.load(f)
        errs, counters = validate_card_baseline(cars)
        if errs:
            print("VALIDATE cards FAIL:", errs)
            rc = 1
        else:
            print("VALIDATE cards PASS", counters)
    else:
        print("VALIDATE cards NOT_RUN (no --car-manifest supplied)")

    return rc


def cmd_report(args):
    report = {
        "languages": list(LANG_WHITELIST),
        "default_language": DEFAULT_LANG,
        "countries": list(COUNTRY_WHITELIST),
        "expected_total_cards": EXPECTED_TOTAL_CARDS,
        "expected_stage_counts": EXPECTED_STAGE_COUNTS,
        "production_write": "NO",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def build_arg_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--discover", action="store_true")
    p.add_argument("--build-sandbox", action="store_true")
    p.add_argument("--validate", action="store_true")
    p.add_argument("--report", action="store_true")
    p.add_argument("--sandbox-root", default=None)
    p.add_argument("--production-root", default=None)
    p.add_argument("--car-manifest", default=None)
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    if args.self_test:
        return cmd_self_test()
    if args.discover:
        return cmd_discover(args)
    if args.build_sandbox:
        return cmd_build_sandbox(args)
    if args.validate:
        return cmd_validate(args)
    if args.report:
        return cmd_report(args)

    print("No mode selected. Defaulting to --self-test (no writes performed).")
    return cmd_self_test()


if __name__ == "__main__":
    sys.exit(main())
