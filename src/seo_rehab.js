export const PRODUCTION_ORIGIN = "https://www.uaart.com.ua";
export const REQUIRED_CTA = "Задаток 500 $";
export const CORE_PATHS = [
  "/video/index.html",
  "/video/katalog.html",
  "/video/info.html",
  "/video/podbor.html",
];

const CARD_PATH = /^\/video\/(UA-\d{4})\.html$/i;
const CANONICAL_TAG = /<link\b(?=[^>]*\brel\s*=\s*["'][^"']*\bcanonical\b[^"']*["'])[^>]*>\s*/gi;
const ROBOT_META_TAG = /<meta\b(?=[^>]*\bname\s*=\s*["'](?:robots|googlebot)["'])[^>]*>\s*/gi;
const ACTION_ELEMENT = /(<(?:a|button)\b[^>]*>)([\s\S]*?)(<\/(?:a|button)>)/gi;
const DIAGNOSTIC_ELEMENT = /<a\b(?=[^>]*\bclass\s*=\s*["'][^"']*\bmcf-diag-cta\b[^"']*["'])[^>]*>[\s\S]*?<\/a>\s*/gi;
const CTA_VARIANT_SOURCE = "(?:Купить авто|Купити авто|Задаток\\s*\\$?\\s*500\\s*\\$?|Депозит\\s*\\$?\\s*500\\s*\\$?|Забронировать авто за\\s*\\$?\\s*500\\s*\\$?)";

function ctaPattern(flags = "giu") {
  return new RegExp(CTA_VARIANT_SOURCE, flags);
}

function attribute(tag, name) {
  const match = String(tag).match(new RegExp(`\\b${name}\\s*=\\s*(["'])([\\s\\S]*?)\\1`, "i"));
  return match ? match[2] : "";
}

function classTokens(tag) {
  return attribute(tag, "class").split(/\s+/).filter(Boolean);
}

export function escapeAttribute(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

export function cardIdFromPath(pathname) {
  return pathname.match(CARD_PATH)?.[1]?.toUpperCase() || "";
}

export function extractVehicleIds(html) {
  const ids = [];
  for (const match of String(html).matchAll(/<a\b[^>]*\bhref\s*=\s*(["'])([^"']+)\1[^>]*>/gi)) {
    const id = match[2].match(/(?:^|\/)(UA-\d{4})\.html(?:[?#]|$)/i)?.[1];
    if (id) ids.push(id.toUpperCase());
  }
  return [...new Set(ids)].sort();
}

export function indexablePaths(vehicleIds = []) {
  return [...CORE_PATHS, ...vehicleIds.map((id) => `/video/${id}.html`)];
}

function insertIntoHead(source, addition) {
  if (/<\/head\s*>/i.test(source)) {
    return source.replace(/<\/head\s*>/i, `${addition}\n</head>`);
  }
  if (/<html\b[^>]*>/i.test(source)) {
    return source.replace(/<html\b[^>]*>/i, (tag) => `${tag}\n<head>${addition}\n</head>`);
  }
  return `<head>${addition}\n</head>\n${source}`;
}

function normalizeCtaElements(source) {
  return source.replace(ACTION_ELEMENT, (whole, open, inner, close) => {
    const text = stripTags(inner);
    const recognized = classTokens(open).includes("kn_kupit") || ctaPattern("iu").test(text);
    if (!recognized) return whole;
    const safeOpen = open.replace(/\b(aria-label|title)\s*=\s*(["'])([\s\S]*?)\2/gi, (attr, name, quote, value) => {
      return `${name}=${quote}${value.replace(ctaPattern(), REQUIRED_CTA)}${quote}`;
    });
    return `${safeOpen}${inner.replace(ctaPattern(), REQUIRED_CTA)}${close}`;
  });
}

function diagnosticAnchorTags(source) {
  return [...String(source).matchAll(/<a\b[^>]*>/gi)]
    .map((match) => match[0])
    .filter((tag) => classTokens(tag).includes("mcf-diag-cta") || /UA-\d{4}-diag\.html(?:[?#]|$)/i.test(attribute(tag, "href")));
}

function diagnosticCta(id) {
  return `<a class="mcf-diag-cta" href="${id}-diag.html" style="display:flex;align-items:center;gap:12px;margin:14px 0;padding:15px 16px;border-radius:14px;text-decoration:none;background:linear-gradient(180deg,rgba(212,175,55,.20),rgba(212,175,55,.08));border:1px solid rgba(212,175,55,.55);color:#f4e3ae"><span style="font-size:22px;line-height:1">🔧</span><span style="flex:1"><span style="display:block;font-weight:800;font-size:16px">Открыть комплексную диагностику →</span><span style="display:block;font-size:13px;opacity:.85;margin-top:3px">ЛКП · OBD · ходовая · фото · видео</span></span><span style="font-size:20px;opacity:.8">›</span></a>`;
}

function ensureDiagnosticCta(source, id) {
  // Any existing diagnostic anchor is left untouched so mismatches and
  // duplicates remain visible to the fail-closed validator.
  if (diagnosticAnchorTags(source).length) return source;
  const addition = `${diagnosticCta(id)}\n`;
  const primaryCta = /<a\b(?=[^>]*\bclass\s*=\s*["'][^"']*\bkn_kupit\b[^"']*["'])/i;
  if (primaryCta.test(source)) return source.replace(primaryCta, `${addition}<a`);
  if (/<\/body\s*>/i.test(source)) return source.replace(/<\/body\s*>/i, `${addition}</body>`);
  return `${source}\n${addition}`;
}

export function transformCandidateHtml(pathname, html) {
  const normalizedPath = pathname === "/" ? "/video/index.html" : pathname;
  const isCandidate = CORE_PATHS.includes(normalizedPath) || Boolean(cardIdFromPath(normalizedPath));
  if (!isCandidate) return String(html);

  const canonical = `${PRODUCTION_ORIGIN}${normalizedPath}`;
  let result = String(html).replace(CANONICAL_TAG, "").replace(ROBOT_META_TAG, "");
  result = insertIntoHead(result, `<link rel="canonical" href="${escapeAttribute(canonical)}">`);
  const vehicleId = cardIdFromPath(normalizedPath);
  if (vehicleId) {
    result = ensureDiagnosticCta(result, vehicleId);
    result = normalizeCtaElements(result);
  }
  return result;
}

export function stripTags(value) {
  return String(value)
    .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function previewSafeHtml(html) {
  const source = String(html);
  if (source.includes("UA_ART_GITHUB_PREVIEW_GUARD")) return source;
  const head = `<style id="UA_ART_GITHUB_PREVIEW_GUARD">
    #ua-art-preview-bar{position:fixed;z-index:2147483647;top:0;left:0;right:0;padding:8px 12px;
    background:#6d28d9;color:#fff;text-align:center;font:700 12px/1.2 system-ui;box-shadow:0 2px 12px #0005}
    body{padding-top:30px!important}
  </style>`;
  const body = `<div id="ua-art-preview-bar">GITHUB PREVIEW · PRODUCTION WRITE: NO · FORMS DISABLED</div>
  <script>(function(){
    addEventListener("submit",function(e){e.preventDefault();e.stopImmediatePropagation();alert("Preview: отправка отключена");},true);
    addEventListener("click",function(e){var n=e.target.closest("button,[onclick],a[href^='tel:'],a[href^='mailto:'],a[href*='t.me'],a[href*='wa.me']");if(n){e.preventDefault();e.stopImmediatePropagation();alert("Preview: действие отключено");}},true);
  }());</script>`;
  let result = insertIntoHead(source, head);
  if (/<body\b[^>]*>/i.test(result)) result = result.replace(/<body\b[^>]*>/i, (tag) => `${tag}\n${body}`);
  else result += body;
  return result;
}

function tagsInHead(html, tagName) {
  const head = String(html).match(/<head\b[^>]*>([\s\S]*?)<\/head\s*>/i)?.[1] || "";
  return head.match(new RegExp(`<${tagName}\\b[^>]*>`, "gi")) || [];
}

export function htmlFacts(html) {
  const source = String(html);
  const canonicals = tagsInHead(source, "link")
    .filter((tag) => attribute(tag, "rel").toLowerCase().split(/\s+/).includes("canonical"))
    .map((tag) => attribute(tag, "href"));
  const robotMeta = tagsInHead(source, "meta")
    .filter((tag) => ["robots", "googlebot"].includes(attribute(tag, "name").toLowerCase()))
    .map((tag) => attribute(tag, "content"));
  const primaryCtas = [];
  const diagnostics = diagnosticAnchorTags(source).map((open) => ({ text: "", href: attribute(open, "href") }));
  for (const match of source.matchAll(ACTION_ELEMENT)) {
    const open = match[1];
    const text = stripTags(match[2]);
    const href = attribute(open, "href");
    if (classTokens(open).includes("kn_kupit") || ctaPattern("iu").test(text)) {
      primaryCtas.push({ text, href, ariaLabel: attribute(open, "aria-label"), title: attribute(open, "title") });
    }
  }
  return { canonicals, robotMeta, primaryCtas, diagnostics };
}

export function validateCandidateHtml(pathname, html) {
  const normalizedPath = pathname === "/" ? "/video/index.html" : pathname;
  const facts = htmlFacts(html);
  const expectedCanonical = `${PRODUCTION_ORIGIN}${normalizedPath}`;
  const errors = [];
  if (facts.canonicals.length !== 1 || facts.canonicals[0] !== expectedCanonical) errors.push(`canonical:${JSON.stringify(facts.canonicals)}`);
  if (facts.canonicals.some((value) => /\/video\/preview\/|workers\.dev/i.test(value))) errors.push("preview-canonical");
  if (facts.robotMeta.some((value) => /(?:^|[,\s])(noindex|nofollow)(?:$|[,\s])/i.test(value))) errors.push(`robots:${JSON.stringify(facts.robotMeta)}`);

  const vehicleId = cardIdFromPath(normalizedPath);
  if (vehicleId) {
    if (facts.primaryCtas.length !== 1 || facts.primaryCtas[0]?.text !== REQUIRED_CTA) errors.push(`cta:${JSON.stringify(facts.primaryCtas)}`);
    if (facts.primaryCtas.some((item) => /Купить авто|Купити авто/i.test(`${item.text} ${item.ariaLabel} ${item.title}`))) errors.push("legacy-cta");
    const expectedDiag = `${vehicleId}-diag.html`;
    if (facts.diagnostics.length !== 1 || !facts.diagnostics[0].href.split(/[?#]/)[0].endsWith(expectedDiag)) {
      errors.push(`diagnostics:${JSON.stringify(facts.diagnostics)}`);
    }
  }
  return { pass: errors.length === 0, errors, facts };
}

export function productionRobots() {
  return "User-agent: *\nAllow: /\nDisallow: /video/preview/\nSitemap: https://www.uaart.com.ua/sitemap.xml\n";
}

export function previewRobots() {
  return "User-agent: *\nAllow: /\n# Preview HTML is excluded by X-Robots-Tag\n";
}

export function sitemapXml(paths) {
  const body = paths.map((path) => `  <url><loc>${PRODUCTION_ORIGIN}${path}</loc></url>`).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${body}\n</urlset>\n`;
}

export function validateRobots({ status, contentType, redirected, body }) {
  const errors = [];
  if (status !== 200) errors.push(`status:${status}`);
  if (redirected) errors.push("redirected");
  if (!/^text\/plain\b/i.test(contentType)) errors.push(`content-type:${contentType}`);
  if (/^\s*</.test(body)) errors.push("html-body");
  if (body !== productionRobots()) errors.push("body");
  return { pass: errors.length === 0, errors };
}

export function validateSitemap({ status, contentType, redirected, body }, paths) {
  const errors = [];
  if (status !== 200) errors.push(`status:${status}`);
  if (redirected) errors.push("redirected");
  if (!/(?:application|text)\/xml\b/i.test(contentType)) errors.push(`content-type:${contentType}`);
  if (body !== sitemapXml(paths)) errors.push("body");
  const urls = [...String(body).matchAll(/<loc>(https:\/\/www\.uaart\.com\.ua[^<]+)<\/loc>/g)].map((m) => m[1]);
  const expected = paths.map((path) => `${PRODUCTION_ORIGIN}${path}`);
  if (urls.length !== new Set(urls).size || JSON.stringify(urls) !== JSON.stringify(expected)) errors.push("url-set");
  if (urls.some((url) => /\/video\/preview\/|workers\.dev/i.test(url))) errors.push("preview-url");
  return { pass: errors.length === 0, errors };
}

export function normalizeAllowedDiff(html) {
  return String(html)
    .replace(CANONICAL_TAG, "")
    .replace(ROBOT_META_TAG, "")
    .replace(DIAGNOSTIC_ELEMENT, "")
    .replace(ctaPattern(), "__UA_ART_APPROVED_CTA__")
    .replace(/\s+/g, " ")
    .trim();
}
