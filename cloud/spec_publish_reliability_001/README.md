# Automatic specifications after CRM publication

Fixes the deployed collector's full-VIN-only lookup, the four manufacturer
sources omitted from the subprocess protocol, and completed queues that never
reconsider corrected model inputs. Scope is specification collection and its
existing narrow HTML projection. No CRM schema, price, advertising, media,
Telegram receipt, or full-catalog publisher changes. No new dependencies.

## Behavior

- Successful published CRM rows are recovered by the existing 15-second scan.
- One collection cycle has attempts at 0, 10, 20 and 30 minutes. Durable leases
  survive restarts. Price/stage changes and repeated publication do not reset it.
- Model input/policy signatures create a new generation exactly once. This
  release backfills all existing published cards. Same-VIN refreshes retain
  accepted, manually edited and hidden facts. Different VINs retain the old
  facts only in the existing history archive.
- Ten sources are registered and independently attempted where applicable:
  Kia Korea, Hyundai Korea, Mercedes archive, Audi MediaCenter, Danawa,
  Carisyou, Auto-Data, Cars-Data, UltimateSpecs and NHTSA vPIC.
- Catalogue search discovers URLs only. No snippet is treated as a fact. HTTPS,
  approved domains, same-domain redirects, body size, concurrency and deadlines
  are bounded. A subprocess imposes the existing 18-second outer limit.
- Model snapshots are explicitly dated CURATED fallback. Fresh verification,
  unknown variants, irrelevant manufacturers and failures are separate outcomes.
  A registry entry or an HTTP success is not represented as verified facts.
- Supported model families no longer require enumerating every full VIN. New
  audited families cover K5 DL3 2.0 LPi, Sonata DN8 2.0 LPi and common Audi C7
  3.0 TDI engine facts. Other catalogue discoveries require a sufficiently
  specified, matching variant or a strict successful VIN decode. Unconfirmed
  specifications stay absent; this does not guarantee data for every vehicle.
- Purchase fields cannot enter through arbitrary keys, labels or values. Only
  known technical field keys and approved provenance can be merged. Existing
  manual/hidden protections, transactional merge, and two-page sync are kept.

## Modules

`spec_model_profiles.py`: model matching and dated evidence.
`spec_catalog_pages.py`: URL discovery and conservative page extraction.
`spec84_collector.py`: bounded orchestration and additive persistence guards.
`spec_retry84.py`: durable scheduling and collection-input signatures.
`ua_spec84_runtime.py`: existing CRM integration, stale-result checks and HTML sync.

## Verified source evidence (2026-09-27)

- [Kia K5 pre-facelift specifications](https://www.kia.com/kr/vehicles/k5_bak_20231031/specification), specifically the 2.0 LPI section. No tyre-dependent fuel economy or equipment is inferred.
- [Hyundai Sonata DN8 English catalogue](https://www.hyundai.com/content/dam/hyundai/kr/ko/html/pdf/en-cn-catalog/en-catalog/sonata-catalog-eng.pdf), specification table p. 17; distinguish gasoline from LPi columns.
- Audi C7 3.0 TDI fundamentals cross-checked across [218 PS](https://www.auto-data.net/en/audi-a6-limousine-4g-c7-facelift-2014-3.0-tdi-v6-clean-diesel-218hp-s-tronic-20590), [272 PS](https://www.auto-data.net/en/audi-a6-limousine-4g-c7-facelift-2014-3.0-tdi-v6-clean-diesel-272hp-quattro-s-tronic-20591), and [320 PS](https://www.auto-data.net/en/audi-a6-limousine-4g-c7-facelift-2014-3.0-tdi-v6-clean-diesel-320hp-quattro-tiptronic-20592). No specific power, gearbox or body dimensions assigned from a generic Audi VIN prefix.
- Technical approach checked against [Python sqlite3 backup/transactions](https://docs.python.org/3/library/sqlite3.html), [urllib request](https://docs.python.org/3/library/urllib.request.html), [NHTSA vPIC](https://vpic.nhtsa.dot.gov/api/), and [PythonAnywhere always-on tasks](https://help.pythonanywhere.com/pages/AlwaysOnTasks/).

## Validation and deployment

Run the unittest suite with the installed legacy dependencies on PYTHONPATH and
`UA_ART_SPEC_TEST_RENDERER` pointing to the actual renderer. Tests cover future
VINs, wrong generations/fuels, ambiguous variants, purchase-field rejection,
four durable attempts, crash recovery, input changes, repeat events, manual and
hidden facts, transactional rollback and both HTML projections.

`install.py` first checks audited live source hashes and compiles every module.
`--apply` uses the existing coordinated writer guard, backs up the source and
both specification databases, installs only five modules atomically per file,
verifies readback and conditionally rolls back on failure. A drifted live source
aborts installation. Restart only the existing CRM always-on task afterward.
`verify_live.py` reads the running queue, model matches, published sections and
purchase-field scan; it does not change CRM or publish listings.
