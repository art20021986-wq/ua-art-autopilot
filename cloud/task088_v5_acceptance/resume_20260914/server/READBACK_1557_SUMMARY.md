# Readback 15:57 UTC — no observed drift

The exact remote JSON is preserved as `readback_1557.json` (141,690 bytes), SHA256 `1ef3d1e3f346268da4a4cb110f1382d7768f9ea19226d9fc9b3bf67f636fe95f`. The neighboring terminal evidence independently records this server hash.

All 15 comparisons match: before/after plus both retained preview baselines, each covering DB schema, all DB tables, live HTML, source files and production static mappings. The current inventory contains 17 database tables / 2,816 rows, 880 HTML files and 18 source/WSGI files. Embedded inventory hashes were independently recomputed and match.

The captured six-field published-row snapshot matches all 18 current cars before and after observation. All 18 captured source/WSGI pins match. All 679 current manifest resources, five runtime modules, config and dedicated Preview WSGI match their exact pins. Stage 2 cars_ui pin and the existing routing source/mapping pins match fresh state.

This is readback evidence only. It is not browser acceptance, backup proof, writer exclusion, installation, activation, or an end-to-end CRM test. Both historical baseline files were read in place and their hashes recorded now; independently preserved historical baseline hashes were not available. The receipt includes after inventory and a before inventory hash, not the full before inventory.

`full_preview: NOT_PASSED`; no Gate was created.
