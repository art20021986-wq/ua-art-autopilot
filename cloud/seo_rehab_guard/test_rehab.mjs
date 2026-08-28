import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  REQUIRED_CTA,
  extractVehicleIds,
  indexablePaths,
  normalizeAllowedDiff,
  previewSafeHtml,
  productionRobots,
  sitemapXml,
  transformCandidateHtml,
  validateCandidateHtml,
  validateRobots,
  validateSitemap,
} from "../../src/seo_rehab.js";

const page = ({ canonical = "https://www.uaart.com.ua/video/preview/v4/index.html", robots = "noindex,nofollow", cta = "Купить авто", diagnostics = true, id = "UA-9999" } = {}) => `<!doctype html><html><head>
  <meta name="robots" content="${robots}"><meta name="googlebot" content="noindex">
  <link rel="canonical" href="${canonical}"><title>Fixture</title></head><body><h1>UA ART</h1>
  ${diagnostics ? `<a class="mcf-diag-cta" href="${id}-diag.html">Комплексная диагностика</a>` : ""}
  <a class="dejstvie kn_kupit" href="https://t.me/bot?start=${id}"><span>${cta}</span></a>
  <div>VIN ABC123 · 24 500 $ · На пароме</div></body></html>`;

test("home and catalog lose noindex and receive self-canonical", () => {
  for (const path of ["/video/index.html", "/video/katalog.html"]) {
    const result = transformCandidateHtml(path, page());
    const gate = validateCandidateHtml(path, result);
    assert.equal(gate.pass, true, JSON.stringify(gate));
    assert.equal(gate.facts.canonicals[0], `https://www.uaart.com.ua${path}`);
    assert.equal(gate.facts.robotMeta.length, 0);
  }
});

test("UA-0009 and UA-0010 receive a self-canonical and exact CTA", () => {
  for (const id of ["UA-0009", "UA-0010"]) {
    const path = `/video/${id}.html`;
    const result = transformCandidateHtml(path, page({ canonical: "", cta: "Забронировать авто за 500$", id }));
    const gate = validateCandidateHtml(path, result);
    assert.equal(gate.pass, true, JSON.stringify(gate));
    assert.equal(gate.facts.primaryCtas[0].text, REQUIRED_CTA);
  }
});

test("legacy CTA is normalized on every current and future UA-XXXX card", () => {
  for (const id of ["UA-0002", "UA-0007", "UA-0008", "UA-9999"]) {
    const path = `/video/${id}.html`;
    const result = transformCandidateHtml(path, page({ id }));
    assert.equal(validateCandidateHtml(path, result).pass, true);
    assert.match(result, /Задаток 500 \$/);
    assert.doesNotMatch(result, /Купить авто|Купити авто/);
  }
});

test("catalog IDs are discovered from card links, including future cards", () => {
  const catalog = '<a href="UA-0002.html">A</a><a href="/video/UA-0010.html?x=1">B</a><p>UA-7777</p><a href="UA-9999.html">C</a>';
  assert.deepEqual(extractVehicleIds(catalog), ["UA-0002", "UA-0010", "UA-9999"]);
  assert.ok(indexablePaths(extractVehicleIds(catalog)).includes("/video/UA-9999.html"));
});

test("future cards fail closed when diagnostics are absent or duplicated", () => {
  const path = "/video/UA-9999.html";
  let result = transformCandidateHtml(path, page({ diagnostics: false }));
  assert.ok(validateCandidateHtml(path, result).errors.some((value) => value.startsWith("diagnostics:")));
  result = transformCandidateHtml(path, page() + '<a href="UA-9999-diag.html">Комплексная диагностика</a>');
  assert.equal(validateCandidateHtml(path, result).pass, false);
});

test("duplicate primary CTA fails closed", () => {
  const path = "/video/UA-9999.html";
  const result = transformCandidateHtml(path, page() + '<a class="kn_kupit">Купить авто</a>');
  assert.equal(validateCandidateHtml(path, result).pass, false);
});

test("protected business fields and CTA destination stay unchanged", () => {
  const original = page();
  const candidate = transformCandidateHtml("/video/UA-9999.html", original);
  assert.equal(normalizeAllowedDiff(original), normalizeAllowedDiff(candidate));
  for (const value of ["VIN ABC123", "24 500 $", "На пароме", "https://t.me/bot?start=UA-9999"]) assert.ok(candidate.includes(value));
});

test("robots and sitemap require 200, no redirect and correct content type", () => {
  const paths = indexablePaths(["UA-0001", "UA-0010", "UA-9999"]);
  assert.equal(validateRobots({ status: 200, contentType: "text/plain", redirected: false, body: productionRobots() }).pass, true);
  assert.equal(validateRobots({ status: 302, contentType: "text/html", redirected: true, body: "<html>" }).pass, false);
  assert.equal(validateSitemap({ status: 200, contentType: "application/xml", redirected: false, body: sitemapXml(paths) }, paths).pass, true);
  assert.equal(validateSitemap({ status: 301, contentType: "text/html", redirected: true, body: "<html>" }, paths).pass, false);
});

test("transform is idempotent and ten builds are byte-identical", () => {
  const path = "/video/UA-9999.html";
  const once = transformCandidateHtml(path, page());
  assert.equal(transformCandidateHtml(path, once), once);
  const hashes = Array.from({ length: 10 }, () => createHash("sha256").update(transformCandidateHtml(path, page())).digest("hex"));
  assert.equal(new Set(hashes).size, 1);
});

test("preview guard is idempotent and disables production actions", () => {
  const guarded = previewSafeHtml(page());
  assert.equal(previewSafeHtml(guarded), guarded);
  assert.match(guarded, /PRODUCTION WRITE: NO/);
  assert.match(guarded, /отправка отключена/);
});
