# Canonical source continuity remains open

The original Stage 2 receipt pins `cars_ui.py` to SHA-256 `4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde`.

The root audit supplied a subsequent UA0022 task003 installed-after-image pin of `d9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837`. Exact retained bytes were recovered and their local copies verified. This subtask has not independently proven that these bytes are the current live server files.

`cloud/task088_price_sync/build_preflight_bundle.py` deliberately still requires the Stage 2 installed source digest to equal the observed current source digest. A current observation containing the UA0022 digest cannot pass that original check. No receipt, source pin, gate, timestamp, or authority was substituted to bypass it.

Before a future canonical preflight package can accept this successor, its reviewed validator needs an authentic and complete successor chain:

1. Preserve the original valid Stage 1/Stage 2 receipt and its original source digest.
2. Bind the actual UA0022 request, approved manifest, gate, canonical transaction outcome, and final receipt by their immutable hashes and matching identities.
3. Verify that the successor before-image matches the accepted predecessor and that the successor installed-after-image matches the new source digest.
4. Reconcile the recorded final public-check HALT and the actual rollback outcome. A reported installer PASS alone does not establish a canonical control PASS. The root reported rollback was never executed; this statement requires current evidence in the canonical chain.
5. Obtain a fresh authenticated read-only observation proving that the live source equals the accepted successor and that no intervening source mutation invalidates the chain.
6. Independently review and test the successor validator against missing receipts, mismatched identities/hashes, wrong before-images, failed/unknown outcomes, and current source drift before admitting it.

This is a requirement for future canonical packaging and installation authority. The isolated pure entry point `install_package.build_candidates` can compose exact supplied source bytes, runtime modules, rows, and HTML without issuing installation authority or calling that packaging gate. Point 4 may evaluate that isolated candidate separately, retaining explicit historical HTML/data scope until current inputs exist.

## Visibility module and future delegation

The changed product behavior requires an explicit new V5 delegation scope: operation `UPDATE_CAR_DATA_AND_VISIBLE_PRICE_PROJECTIONS` and identity policy `AUTHENTICATED_CRM_ALL_CARS_PUBLIC_VISIBILITY_ONLY`. The runtime validator must reject the former scope rather than silently extend previously granted authority.

The verified source snapshot contains no `prepare_manifest.py` delegation producer. `prepare_install_plan.py` consumes genuine external evidence. The historical `resume_20260914/canonical/derive_candidate_parts.py` validates an old V2 delegation and is retained unchanged. A future authority producer must generate the new explicit scope through the approved canonical process and bind the complete code set, including the new `visibility_lifecycle.py` module and the existing `ua_site_counters.py` dependency.

The V5 delegation must also contain this exact `visibility_delegation` object, validated by the runtime:

```json
{
  "operation": "EXISTING_CRM_PUBLISH_UNPUBLISH_SOLD",
  "permission": "EXISTING_CRM_EDIT_CAR_ACL",
  "fields": ["published", "publish_pending", "status"],
  "public_files": "CURRENT_CAR_VIEWS_AND_SHARED_INVENTORY",
  "source_data_media": "PRESERVE",
  "actual_outcome_before_replay": true
}
```

The local closure now requires 9 patched sources, 11 runtime modules, and 9 existing dependencies. `ua_site_counters.py` was promoted from a dependency to a patched source after review identified an actual server/client identifier collision on dual-price catalog markup. `publikaciya.py` was also promoted to a patched source to enforce the visibility authority boundary around actual public-file switches and explicitly owned recovery. Current server observation must include their exact digests; retained historical digests are suitable only for separately labelled offline reconstruction until a fresh observation confirms them.

The bounded counter client correction also updates an exact existing script in candidate HTML. It preserves all other markup and does not inject a script where one was absent. The protected unserved `site/index.html` remains unchanged. Preflight records the separate price and counter-client proofs; when the client changes, `outside_price_unchanged` is explicitly false and `outside_price_and_counter_client_unchanged` records the combined approved boundary. Historical HTML byte identity cannot be claimed for such changed pages.
