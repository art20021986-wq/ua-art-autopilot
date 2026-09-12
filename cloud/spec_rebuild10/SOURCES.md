# Approved sources — UA-ART-SPEC-REBUILD-10-001 v1.0

The owner approved this selection on 2026-09-09. Selection approval is not a
supplier licence, account/key provision, schema acceptance, or live extraction PASS.
This package performs **no network operation on import or by default**.

| ID | Primary source/documentation | Role | Current connection state |
|---|---|---|---|
| `kia_kr` | [Kia Korea specifications](https://www.kia.com/kr/vehicles/k5/specification) | Exact Korean manufacturer model/year document | NOT_PROVISIONED / NOT_TESTED |
| `hyundai_kr` | [Hyundai Korea catalogue](https://www.hyundai.com/contents/repn-car/catalog/sonata-the-edge_catalog.pdf) | Exact Korean manufacturer model/year document | NOT_PROVISIONED / NOT_TESTED |
| `mercedes_archive` | [Mercedes-Benz Public Archive](https://mercedes-benz-publicarchive.com/marsClassic/en/instance/ko/B-180-CDI-2008---2011.xhtml?oid=192213151) | Historical manufacturer specifications | NOT_PROVISIONED / NOT_TESTED |
| `audi_official` | [Audi MediaCenter](https://www.audi-mediacenter.com/en/audi-a6-40) | Historical manufacturer technical sheets; explicit Audi-domain redirect allowed | NOT_PROVISIONED / NOT_TESTED |
| `danawa` | [Danawa Auto](https://auto.danawa.com/auto/?Model=3260&Tab=spec&Work=model) | Korean model/variant catalogue | NOT_PROVISIONED / NOT_TESTED |
| `carisyou` | [Carisyou specifications](https://www.carisyou.com/car/5217/Spec/52976) | Korean model/variant catalogue | NOT_PROVISIONED / NOT_TESTED |
| `auto_data` | [Auto-Data.net API documentation](https://api.auto-data.net/documentation) | Contracted One-call API and permanent-storage rights | NOT_PROVISIONED / NOT_TESTED |
| `cars_data` | [Cars-Data.com API](https://cars-data.com/en/api) | Contracted key API; exact endpoint/schema must be pinned | NOT_PROVISIONED / NOT_TESTED |
| `ultimate_specs` | [UltimateSpecs example technical page](https://www.ultimatespecs.com/car-specs/Kia/73956/Kia-Optima-%28JF%29-GT-20-T-GDI-245HP.html) | Additional catalogue corroboration | NOT_PROVISIONED / NOT_TESTED |
| `vpic` | [NHTSA vPIC API](https://vpic.nhtsa.dot.gov/api/) | VIN identity helper; limited non-US coverage | PUBLIC_API_AVAILABLE / NOT_TESTED |

Linked example pages identify the supplier and document type. They do **not**
prove that the example model, current model year, market or petrol variant matches
any published UA ART car. In particular, an Optima GT petrol page cannot verify
Korean K5 LPI specifications, and a current Audi A6 page cannot verify an A6 2015.
CarWiki, Encycarpedia, Carfolio and Automobile-Catalog are absent from this new
registry. Existing historical provenance is retained separately, not relabelled.

## Ready implementation boundary

`sources.py` is Python 3.10 standard-library code with:

- An exact ten-source registry and fixed per-source HTTPS host/path rules.
- A real parser for vPIC flat `Results` JSON. It requires one successful result,
  the exact VIN and matching known make/model/year; partial decode errors fail.
  Its output is `IDENTITY_ONLY`, never automatic model/equipment verification.
- An explicit `ua-art.normalized-source.v1` import format for the other nine
  sources. No undocumented supplier API response or speculative HTML parser is
  presented as implemented. A trusted normalizer must review the exact document,
  verify its SHA-256 and provide an out-of-band `ImportAuthorization`.
- `AccessGrant`: automated access, permanent storage and public display must all
  be confirmed with a reference before fetching/importing those nine suppliers.
  Keys/contracts and any paid purchase are outside this package. JSON fields
  claiming rights or trust cannot authorize themselves.
- `fetch_source`: one injected bounded GET, maximum 1,000,000 response bytes,
  15 seconds total, at most two explicit allowed redirects, no retries. The
  injected transport must enforce timeout/stream size, public DNS resolution,
  TLS validation and disabled automatic redirects; no network implementation is
  silently installed. Credentials are never forwarded on a redirect. Exceptions
  expose fixed codes, not response text, keys or full diagnostic URLs.

## Integration API

```python
registry = load_registry()                    # dict[str, Source]
safe_url = validate_source_url(source_id, url)
target = VehicleIdentity(vin=..., make=..., model=..., year=...,
                         market=..., fuel=..., gearbox=...)
facts = parse_normalized_import(source_id, normalized_document, target,
    access=AccessGrant(source_id, True, True, True, rights_reference),
    authorization=ImportAuthorization(source_id, trusted_normalizer_id, document_sha256))
resolution = resolve_facts(facts, target)       # accepted / pending / rejected
kept = retain_on_failed_refresh(old_facts, resolved=resolution)
```

Facts contain `key`, `value`, `unit`, `label_uk`, `label_ru`, `category`,
`source_id`, `source_url`, `verification_status` and `provenance`. The provenance
contains exact identity, evidence kind, document hash, normalizer and rights
reference. Consolidated facts retain all corroborating document references.
Public rendering should use native text/links only; never embed source HTML,
scripts, advertising, iframes or widgets. A historical URL outside the approved
registry may remain stored as provenance without becoming a clickable link.

Required normalized document structure:

```json
{
  "schema": "ua-art.normalized-source.v1",
  "source_id": "kia_kr",
  "identity": {
    "make": "Kia", "model": "K5", "year": 2019,
    "market": "KR", "fuel": "LPG", "gearbox": "automatic"
  },
  "document": {
    "url": "https://www.kia.com/kr/vehicles/k5/specification",
    "sha256": "REPLACE_WITH_THE_VERIFIED_DOCUMENT_SHA256",
    "evidence_kind": "manufacturer_document"
  },
  "facts": [
    {
      "key": "length_mm", "value": null, "unit": "mm",
      "label_uk": "Довжина", "label_ru": "Длина", "category": "technical"
    }
  ]
}
```

This is an illustrative schema with no asserted measurement. Its placeholder
hash is deliberately invalid. The caller must supply the reviewed historical
document, exact identity and actual source facts before it can pass admission.

## Acceptance and retention rules

Exact make, model, year, market, fuel and gearbox are required on model facts.
If the target has a generation, engine identifier, displacement or trim, the
source must match it.
Aliases are not guessed: `K5` and `Optima`, or `LPG` and petrol, cannot silently
match. Any alias mapping must be reviewed before reaching this boundary.

One exact manufacturer document or two independently attributed catalogue
origins must agree on a technical value. Multiple rows or URLs from the same
origin count once. Independence remains a reviewed registry assertion: two
sites known to mirror the same upstream data must share one origin group before
they may be used as corroboration. Conflicting values remain pending even when
one comes from a manufacturer. Equipment requires a vehicle-specific document
and matching full VIN; catalogue availability never proves equipment fitted.

Unknown is absent/null, not zero. Valid zero (for example mileage) and explicit
false are preserved. Physically positive fields such as length or displacement
reject zero placeholders. Failed requests, missing evidence and conflicts do
not delete the last verified specification. Existing manual overrides retain
priority. Storage, provenance, publication and collection readiness must remain
separate; empty source results are not an instruction to empty a public page.

## Verification performed

27 local synthetic tests pass, covering URL attacks, host/source impersonation,
supplier rights, credentials, transport limits/redirects, exact identity,
unknown/zero/false, equipment evidence, consensus, conflict retention and vPIC
parsing. This is **offline code verification**, not ten-source live acceptance,
production publication, or a Gate B PASS.

Run: `python -m unittest discover -s cloud/spec_rebuild10/tests -p test_sources.py`

Next concrete integration step: supply reviewed source rights and normalized
control documents, then run each exact provisioned adapter against a known
matching vehicle. Record separate `PASS`, `NO_MATCH`, `UNAVAILABLE` or
`NOT_PROVISIONED` results without fabricated coverage. Existing verified facts
can be rendered while collection remains pending.
