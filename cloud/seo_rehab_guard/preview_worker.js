import {
  PRODUCTION_ORIGIN,
  cardIdFromPath,
  extractVehicleIds,
  indexablePaths,
  previewRobots,
  previewSafeHtml,
  productionRobots,
  sitemapXml,
  transformCandidateHtml,
} from "../../src/seo_rehab.js";

const FALLBACK_IDS = Array.from({ length: 10 }, (_, index) => `UA-${String(index + 1).padStart(4, "0")}`);
const ALLOWED_PATH = /^(?:\/video\/[A-Za-z0-9._~!$&'()+,;=@%\/-]+|\/favicon\.ico)$/;
const PREVIEW_HEADERS = {
  "cache-control": "no-store",
  "x-robots-tag": "noindex, nofollow, nosnippet",
  "x-ua-art-scope": "sandbox-github-preview",
};

function previewResponse(body, init = {}) {
  const headers = new Headers(init.headers || {});
  for (const [key, value] of Object.entries(PREVIEW_HEADERS)) headers.set(key, value);
  return new Response(body, { ...init, headers });
}

function upstreamUrl(url) {
  if (!ALLOWED_PATH.test(url.pathname) || url.pathname.includes("..")) return null;
  const result = new URL(`${url.pathname}${url.search}`, PRODUCTION_ORIGIN);
  return result.origin === PRODUCTION_ORIGIN ? result : null;
}

async function currentPaths() {
  const upstream = await fetch(`${PRODUCTION_ORIGIN}/video/katalog.html`, {
    method: "GET",
    redirect: "manual",
    headers: { "user-agent": "UA-ART-SEO-Rehab-Preview/1.0 (read-only)" },
  });
  if (upstream.status !== 200 || !(upstream.headers.get("content-type") || "").includes("text/html")) {
    return indexablePaths(FALLBACK_IDS);
  }
  const ids = extractVehicleIds(await upstream.text());
  return indexablePaths(ids.length ? ids : FALLBACK_IDS);
}

async function diagnosticReady(id) {
  const response = await fetch(`${PRODUCTION_ORIGIN}/video/${id}-diag.html`, {
    method: "GET",
    redirect: "manual",
    headers: { "user-agent": "UA-ART-SEO-Rehab-Preview/1.0 (read-only)" },
  });
  if (response.status !== 200 || !(response.headers.get("content-type") || "").includes("text/html")) return false;
  return /диагност|Материалы пока не добавлены/iu.test(await response.text());
}

async function proxyGet(url, method) {
  const target = upstreamUrl(url);
  if (!target) return previewResponse("Not found\n", { status: 404, headers: { "content-type": "text/plain;charset=UTF-8" } });
  const upstream = await fetch(target, {
    method: "GET",
    redirect: "manual",
    headers: { "user-agent": "UA-ART-SEO-Rehab-Preview/1.0 (read-only)" },
  });
  if (upstream.status >= 300 && upstream.status < 400) {
    return previewResponse("Upstream redirect blocked in preview\n", { status: 502, headers: { "content-type": "text/plain;charset=UTF-8" } });
  }
  const contentType = upstream.headers.get("content-type") || "application/octet-stream";
  if (contentType.includes("text/html")) {
    const source = await upstream.text();
    const vehicleId = cardIdFromPath(url.pathname);
    if (vehicleId && !(await diagnosticReady(vehicleId))) {
      return previewResponse("Diagnostic source is not ready; preview blocked\n", {
        status: 502,
        headers: { "content-type": "text/plain;charset=UTF-8" },
      });
    }
    const candidate = transformCandidateHtml(url.pathname, source);
    const guarded = previewSafeHtml(candidate);
    return previewResponse(method === "HEAD" ? null : guarded, {
      status: upstream.status,
      headers: { "content-type": "text/html;charset=UTF-8" },
    });
  }
  const headers = new Headers(upstream.headers);
  for (const name of ["set-cookie", "content-security-policy", "location"]) headers.delete(name);
  return previewResponse(method === "HEAD" ? null : upstream.body, { status: upstream.status, headers });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const method = request.method.toUpperCase();
    if (!new Set(["GET", "HEAD"]).has(method)) {
      return previewResponse("Preview is read-only\n", { status: 405, headers: { allow: "GET, HEAD", "content-type": "text/plain;charset=UTF-8" } });
    }
    if (url.pathname === "/health") {
      return previewResponse(method === "HEAD" ? null : JSON.stringify({
        ok: true,
        mode: "sandbox-github-preview",
        productionWrite: false,
        formSubmit: false,
        bindings: 0,
        crons: 0,
        spec: "SEO-REHAB-GUARD-068",
      }), { headers: { "content-type": "application/json;charset=UTF-8" } });
    }
    if (url.pathname === "/") return previewResponse(null, { status: 302, headers: { location: "/video/index.html" } });
    if (url.pathname === "/robots.txt") {
      return previewResponse(method === "HEAD" ? null : previewRobots(), { headers: { "content-type": "text/plain;charset=UTF-8" } });
    }
    if (url.pathname === "/__candidate/robots.txt") {
      return previewResponse(method === "HEAD" ? null : productionRobots(), { headers: { "content-type": "text/plain;charset=UTF-8" } });
    }
    if (url.pathname === "/__candidate/sitemap.xml") {
      const paths = await currentPaths();
      return previewResponse(method === "HEAD" ? null : sitemapXml(paths), { headers: { "content-type": "application/xml;charset=UTF-8" } });
    }
    if (url.pathname === "/__candidate/report.json") {
      const paths = await currentPaths();
      return previewResponse(method === "HEAD" ? null : JSON.stringify({
        spec: "SEO-REHAB-GUARD-068",
        scope: "sandbox-github-preview",
        productionWrite: false,
        indexableCandidatePaths: paths,
        candidateRobots: "/__candidate/robots.txt",
        candidateSitemap: "/__candidate/sitemap.xml",
      }, null, 2), { headers: { "content-type": "application/json;charset=UTF-8" } });
    }
    if (url.pathname === "/sitemap.xml") {
      return previewResponse("Preview sitemap is disabled. Inspect /__candidate/sitemap.xml\n", { status: 404, headers: { "content-type": "text/plain;charset=UTF-8" } });
    }
    return proxyGet(url, method);
  },
};
