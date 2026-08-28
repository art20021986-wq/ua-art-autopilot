import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import {
  CORE_PATHS,
  PRODUCTION_ORIGIN,
  extractVehicleIds,
  indexablePaths,
  normalizeAllowedDiff,
  productionRobots,
  sitemapXml,
  transformCandidateHtml,
  validateCandidateHtml,
  validateRobots,
  validateSitemap,
} from "../../src/seo_rehab.js";

const outputArg = process.argv.indexOf("--output");
const output = resolve(outputArg >= 0 ? process.argv[outputArg + 1] : "cloud/seo_rehab_guard/evidence/GATE-REPORT.json");

async function get(path) {
  const response = await fetch(`${PRODUCTION_ORIGIN}${path}`, {
    method: "GET",
    redirect: "manual",
    headers: { "user-agent": "UA-ART-SEO-Rehab-Gate/1.0 (read-only)" },
  });
  const body = await response.text();
  return {
    path,
    status: response.status,
    redirected: response.status >= 300 && response.status < 400,
    location: response.headers.get("location") || "",
    contentType: response.headers.get("content-type") || "",
    body,
  };
}

function treeHash(pages, paths) {
  const digest = createHash("sha256");
  for (const path of paths) digest.update(path).update("\0").update(transformCandidateHtml(path, pages.get(path).body)).update("\0");
  digest.update(productionRobots()).update(sitemapXml(paths));
  return digest.digest("hex");
}

const catalog = await get("/video/katalog.html");
const vehicleIds = extractVehicleIds(catalog.body);
const paths = indexablePaths(vehicleIds);
const fetched = await Promise.all(paths.map(get));
const pages = new Map(fetched.map((item) => [item.path, item]));
const diagnosticPages = await Promise.all(vehicleIds.map((id) => get(`/video/${id}-diag.html`)));
const liveRobots = await get("/robots.txt");
const liveSitemap = await get("/sitemap.xml");

const candidatePages = paths.map((path) => {
  const live = pages.get(path);
  const candidate = transformCandidateHtml(path, live.body);
  const gate = validateCandidateHtml(path, candidate);
  return {
    path,
    sourceStatus: live.status,
    sourceRedirected: live.redirected,
    sourceContentType: live.contentType,
    gatePass: gate.pass,
    gateErrors: gate.errors,
    protectedDiffPass: normalizeAllowedDiff(live.body) === normalizeAllowedDiff(candidate),
    candidateSha256: createHash("sha256").update(candidate).digest("hex"),
  };
});

const candidateRobots = validateRobots({ status: 200, contentType: "text/plain", redirected: false, body: productionRobots() });
const candidateSitemap = validateSitemap({ status: 200, contentType: "application/xml", redirected: false, body: sitemapXml(paths) }, paths);
const hashes = Array.from({ length: 10 }, () => treeHash(pages, paths));
const diagnostics = diagnosticPages.map((item, index) => ({
  id: vehicleIds[index],
  path: item.path,
  status: item.status,
  redirected: item.redirected,
  contentType: item.contentType,
  marker: /диагност|Материалы пока не добавлены/iu.test(item.body),
}));
const diagnosticsPass = diagnostics.length === vehicleIds.length && diagnostics.every((item) => item.status === 200 && !item.redirected && /text\/html/i.test(item.contentType) && item.marker);
const pagesPass = candidatePages.every((item) => item.sourceStatus === 200 && !item.sourceRedirected && /text\/html/i.test(item.sourceContentType) && item.gatePass && item.protectedDiffPass);
const pass = catalog.status === 200 && !catalog.redirected && vehicleIds.length >= 10 && vehicleIds.includes("UA-0010")
  && pagesPass && diagnosticsPass && candidateRobots.pass && candidateSitemap.pass && new Set(hashes).size === 1;

const report = {
  spec: "SEO-REHAB-GUARD-068",
  generatedAtUtc: new Date().toISOString(),
  mode: "sandbox-github-preview",
  productionWrite: false,
  sourceMethod: "public GET only; redirects manual",
  status: pass ? "PASS_READY_FOR_OWNER_VISUAL_GATE" : "BLOCKED_FOR_PRODUCTION",
  discoveredVehicleIds: vehicleIds,
  catalogCardSetEqualsScannedCardSet: JSON.stringify(paths.slice(CORE_PATHS.length)) === JSON.stringify(vehicleIds.map((id) => `/video/${id}.html`)),
  candidatePages,
  diagnostics: { pass: diagnosticsPass, pages: diagnostics },
  candidateRobots,
  candidateSitemap,
  repeatability: { runs: 10, uniqueTreeHashes: new Set(hashes).size, treeSha256: hashes[0] },
  liveBlockerEvidence: {
    robots: { status: liveRobots.status, redirected: liveRobots.redirected, location: liveRobots.location, contentType: liveRobots.contentType },
    sitemap: { status: liveSitemap.status, redirected: liveSitemap.redirected, location: liveSitemap.location, contentType: liveSitemap.contentType },
  },
};

await mkdir(dirname(output), { recursive: true });
await writeFile(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ status: report.status, vehicles: vehicleIds.length, pages: candidatePages.length, repeatability: report.repeatability }, null, 2));
if (!pass) process.exitCode = 1;
