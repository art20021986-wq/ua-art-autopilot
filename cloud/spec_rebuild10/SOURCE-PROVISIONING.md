# Historical source inputs — 9 September 2026

`source_provisioning.py` adds a working, finite local-document collector to the
existing `SpecWorker`. Each run verifies the saved source capture and normalized
payload against separately reviewed SHA-256 values. An altered file fails;
an exact different model returns `NO_MATCH`; missing target identity or ambiguous
documents fail. It never changes CRM data, publishes a page, opens a network
connection, grants supplier rights or reports live source acceptance.

## Concrete Kia input found and prepared

The [official archived 2023 K5 page](https://www.kia.com/kr/vehicles/k5_bak_20231031/specification)
has a distinct Korean 2.0 LPI specification table. A reviewed numerical excerpt
and an eight-fact candidate are included in `evidence/source-candidates/`:
length, width, height, wheelbase, displacement, metric horsepower, torque and
automatic transmission gear count. These are model facts, not fitted equipment.
The parser preserves PS and kgf·m units rather than mislabelling them as bhp/Nm.
Wheel-dependent economy, mass, track and optional equipment are not selected.

The captured text SHA identifies that reviewed excerpt, **not** the supplier's
original HTML. The normalizer deliberately accepts a strict text-capture format;
it is not described as a tested live HTML scraper. The candidate carries no
supplier grant or production import authorization. Its obvious applicability
candidate is UA-0018 (CRM: Kia K5, 2023, 1999 cm³, gas, automatic, front drive),
but the vehicle's actual sales market, LPG fuel classification and correct
2023 version still need documented identity mapping. The page's Korean market
does not by itself prove a particular car was sold in that market.

## Audi UA-0017: the exact remaining distinction

Read-only CRM input is Audi A6, 2015, 2967 cm³ diesel, automatic, all-wheel drive;
trim, sales market and source documents are empty. Audi's own [2015 annual
report, specification appendix, printed page 294](https://emea-dam.audi.com/adobe/assets/urn:aaid:aem:d9374e0a-e9b1-451d-b306-ce3c4328afee/original/as/2015_audi_annual_report_financial.pdf)
lists several 3.0 TDI quattro outputs and both seven-speed S tronic and
eight-speed tiptronic. The appendix explicitly concerns the German market.
Therefore those CRM fields cannot select one power/transmission version.
The report is useful manufacturer evidence of this ambiguity; no particular
power, economy or fitted equipment has been assigned to UA-0017.

The Audi document lives at `emea-dam.audi.com`, which is not in the current
registry routes. The discovered URL is recorded for review. This change does
not silently expand that allowlist or fetch through another route.

## Old sixteen: new mismatch found, without overwriting history

The historical [Danawa K5 source, lineup 42280](https://auto.danawa.com/auto/?Lineup=42280&Model=3260%2C3151&Tab=spec&Work=model&pcUse=y)
currently selects a **2018 model-year** LPG rental variant, listed from April
2017. The saved records use this same source for UA-0003/0004/0006 (CRM 2019),
UA-0009/0010/0012 (CRM 2018) and UA-0016 (owner-confirmed 2017). This is a
documented mismatch of year labels for four records; it does not prove that
every numerical value is wrong. Build year and model year must be distinguished
using vehicle documents before admitting new verified facts.

The [Danawa Sonata source, lineup 42773](https://auto.danawa.com/auto/modelPopup.php?Lineup=42773&Type=spec)
does select the 2018 New Rise LPG range, which matches the stated year for
UA-0011/0015. Exact variant and vehicle-market evidence remain necessary.
UA-0015 also carries old Hyundai 2020MY taxi provenance; that is retained as
history, not taken as new proof for a 2018 car.

CRM displacement is 2000 for UA-0003/0004/0006/0009/0010/0011/0012. Exact source
matching must not silently change this to 1999. UA-0014 stores 1645 while its
old source identifies a 1.7 CRDi; that inconsistency needs a vehicle document.
All eighteen CRM records lack a declared sales market. Shipment country,
manufacturer nationality and an old source domain are not substitutes.
Mercedes records also require exact variant/market confirmation; historical
Auto-Data URLs are retained, not transformed into contracted API receipts.

## Integration

Provide `ReviewedSourceInput(capture_path, payload_path, capture_sha256,
payload_sha256, ImportAuthorization(...))` for each reviewed local document,
and an existing confirmed `AccessGrant`. Then bind:

```python
binding = reviewed_file_collector("kia_kr", reviewed_inputs, access=confirmed_access)
worker = SpecWorker(store, {"kia_kr": binding})
report = worker.run_once()
```

The same collector supports all nine normalized-import suppliers once their
reviewed documents and access rights exist. It is suitable for reusing an
accepted model document for subsequent matching cards. It does not discover
new variants or replace live provider connectors. No access grant is bundled.

Fourteen local tests cover the real queue/store/parser flow, input tampering,
model ambiguity, missing market, rounded displacement, a wrong petrol column,
unit preservation and no publication. Test grants are explicitly synthetic.
Run `python -m unittest discover -s cloud/spec_rebuild10/tests -p test_source_provisioning.py`.

Next executable step for actual enrichment: verify a vehicle identity document,
authorize an exact source capture with an existing usable supplier grant, and
run the bound worker against an isolated copy. Publish only after the separate
installation and page-readback gates. The preserved sixteen-card restoration
and new collection readiness remain separately reported.
