# UA-0011 Before/After matrix — TASK 084

Live Gate A status: **PASS**

| CRM field | Before (fresh GET-only) | After (sandbox target) |
|---|---|---|
| `status` | `kr_bought` | `kr_bought` |
| `sea_container` | `ONEYSELGF1046602` | `NULL` |
| `sea_date_out` | `NULL` | `NULL` |
| `eta_manual` | `2026-12-12` | `NULL` |
| `days_to_kyiv` | `NULL` | `NULL` |

- Changed non-empty fields: `sea_container`, `eta_manual`
- All other CRM fields: unchanged, field-by-field SHA-256 **PASS**
- Ordered media manifest: 35 photos, preserved **PASS**
- Own facade cover first: **PASS**
- Repeated sandbox transform: 10/10 identical after first application
- Production touched: **NO**
