import test from "node:test";
import assert from "node:assert/strict";
import previewWorker from "./preview_worker.js";

test("preview rejects write methods without an upstream fetch", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new Error("must not fetch"); };
  try {
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      const response = await previewWorker.fetch(new Request("https://preview.example/video/UA-0001.html", { method }));
      assert.equal(response.status, 405);
    }
    assert.equal(calls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("preview health proves isolation and no bindings", async () => {
  const response = await previewWorker.fetch(new Request("https://preview.example/health"));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-robots-tag"), "noindex, nofollow, nosnippet");
  const body = await response.json();
  assert.deepEqual(body, {
    ok: true,
    mode: "sandbox-github-preview",
    productionWrite: false,
    formSubmit: false,
    bindings: 0,
    crons: 0,
    spec: "SEO-REHAB-GUARD-068",
  });
});
