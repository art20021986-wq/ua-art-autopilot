const BASE = "https://www.uaart.com.ua";
const PATHS = [
  "/", "/robots.txt", "/sitemap.xml", "/video/index.html",
  "/video/katalog.html", "/video/info.html", "/video/podbor.html",
  ...Array.from({ length: 10 }, (_, i) => `/video/UA-${String(i + 1).padStart(4, "0")}.html`),
];

const escapeHtml = (value = "") => String(value).replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

function first(html, pattern) {
  const match = html.match(pattern);
  return match ? match[1].replace(/\s+/g, " ").trim() : "";
}

async function inspect(path) {
  const requestedUrl = BASE + path;
  try {
    const response = await fetch(requestedUrl, {
      redirect: "follow",
      headers: { "User-Agent": "UA-ART-SEO-Watch/2.0 (read-only)" },
    });
    const body = await response.text();
    const isHtml = (response.headers.get("content-type") || "").includes("html");
    const title = isHtml ? first(body, /<title[^>]*>([\s\S]*?)<\/title>/i) : "";
    const robots = isHtml ? first(body, /<meta[^>]+name=["']robots["'][^>]+content=["']([^"']*)/i) : "";
    const canonical = isHtml ? first(body, /<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']*)/i) : "";
    const diagnostics = isHtml ? (body.match(/комплексн\w*\s+(?:діагностик|диагностик)/gi) || []).length : 0;
    const booking = isHtml ? (body.match(/(?:задаток|депозит)[^<]{0,30}500|500[^<]{0,30}(?:задаток|депозит)/gi) || []).length : 0;
    const vehicleIds = [...new Set(body.match(/UA-\d{4}/g) || [])].sort();
    return {
      url: requestedUrl,
      status: response.status,
      finalUrl: response.url,
      title, robots, canonical, diagnostics, booking,
      vehicleIds: vehicleIds.join(","),
      error: "",
    };
  } catch (error) {
    return {
      url: requestedUrl, status: 0, finalUrl: "", title: "", robots: "",
      canonical: "", diagnostics: 0, booking: 0, vehicleIds: "",
      error: String(error),
    };
  }
}

async function scan() {
  return Promise.all(PATHS.map(inspect));
}

async function initialize(db) {
  await db.prepare(`CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT NOT NULL,
    site_ok INTEGER NOT NULL,
    changed_pages INTEGER NOT NULL
  )`).run();
  await db.prepare(`CREATE TABLE IF NOT EXISTS pages (
    run_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    status INTEGER NOT NULL,
    final_url TEXT,
    title TEXT,
    robots TEXT,
    canonical TEXT,
    diagnostics INTEGER,
    booking INTEGER,
    vehicle_ids TEXT,
    error TEXT,
    signature TEXT,
    PRIMARY KEY (run_id, url)
  )`).run();
}

function signature(page) {
  return JSON.stringify([
    page.status, page.finalUrl, page.title, page.robots, page.canonical,
    page.diagnostics, page.booking, page.vehicleIds, page.error,
  ]);
}

async function save(db, pages) {
  await initialize(db);
  const previous = await db.prepare(`SELECT p.url, p.signature FROM pages p
    JOIN (SELECT MAX(id) id FROM runs) r ON p.run_id = r.id`).all();
  const old = new Map((previous.results || []).map(row => [row.url, row.signature]));
  const changed = old.size ? pages.filter(page => old.get(page.url) !== signature(page)).length : 0;
  const siteOk = pages.every(page => page.status > 0 && page.status < 500) ? 1 : 0;
  await db.prepare("INSERT INTO runs(checked_at,site_ok,changed_pages) VALUES(?,?,?)")
    .bind(new Date().toISOString(), siteOk, changed).run();
  const run = await db.prepare("SELECT MAX(id) id FROM runs").first();
  await db.batch(pages.map(page => db.prepare(`INSERT INTO pages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)`).bind(
    run.id, page.url, page.status, page.finalUrl, page.title, page.robots,
    page.canonical, page.diagnostics, page.booking, page.vehicleIds,
    page.error, signature(page),
  )));
  return { changed, siteOk };
}

function render(pages, stored, meta = {}) {
  const siteOk = pages.every(page => page.status > 0 && page.status < 500);
  const cards = pages.filter(page => /\/video\/UA-\d{4}\.html$/.test(page.url));
  const missingDiagnostics = cards.filter(page => page.diagnostics === 0).length;
  const missingCanonical = cards.filter(page => !page.canonical).length;
  const rows = pages.map(page => `<tr>
    <td><a href="${escapeHtml(page.url)}">${escapeHtml(page.url.replace(BASE, "") || "/")}</a></td>
    <td class="${page.status === 200 ? "good" : "bad"}">${page.status || "ERR"}</td>
    <td>${escapeHtml(page.robots || "—")}</td>
    <td>${page.canonical ? "✓" : "—"}</td>
    <td>${page.diagnostics}</td><td>${page.booking}</td>
  </tr>`).join("");
  return `<!doctype html><html lang="ru"><meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60">
  <title>UA ART SEO Watch</title><style>
  body{margin:0;background:#08111f;color:#e8eef8;font:15px system-ui}main{max-width:1100px;margin:auto;padding:20px}
  .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}.card{background:#142239;border:1px solid #29405f;border-radius:14px;padding:14px}
  .number{font-size:27px;font-weight:800}.good{color:#4ade80}.bad{color:#fb7185}small{color:#9fb0c7}
  table{width:100%;border-collapse:collapse;background:#101d31}td,th{padding:9px;border-bottom:1px solid #263957;text-align:left}a{color:#60a5fa}
  @media(max-width:700px){.grid{grid-template-columns:1fr 1fr}table{font-size:11px}td,th{padding:6px}}
  </style><main><h1>UA ART SEO Watch</h1>
  <small>READ-ONLY · production write: NO · ${new Date().toISOString()} · D1: ${stored ? "CONNECTED" : "PENDING"}</small>
  <div class="grid"><div class="card"><small>Сайт</small><div class="number ${siteOk ? "good" : "bad"}">${siteOk ? "ONLINE" : "ERROR"}</div></div>
  <div class="card"><small>Проверено URL</small><div class="number">${pages.length}</div></div>
  <div class="card"><small>Без диагностики</small><div class="number ${missingDiagnostics ? "bad" : "good"}">${missingDiagnostics}</div></div>
  <div class="card"><small>Без canonical</small><div class="number ${missingCanonical ? "bad" : "good"}">${missingCanonical}</div></div></div>
  ${meta.changed === undefined ? "" : `<p>Изменено страниц с прошлого прогона: <b>${meta.changed}</b></p>`}
  <table><tr><th>URL</th><th>HTTP</th><th>Robots</th><th>Canonical</th><th>Диагн.</th><th>CTA 500</th></tr>${rows}</table></main></html>`;
}

export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname === "/health") {
      return Response.json({ ok: true, mode: "read-only", d1: Boolean(env.DB), urls: PATHS.length });
    }
    const pages = await scan();
    let meta = {};
    if (env.DB) meta = await save(env.DB, pages);
    return new Response(render(pages, Boolean(env.DB), meta), {
      headers: { "content-type": "text/html;charset=UTF-8", "cache-control": "no-store" },
    });
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil((async () => {
      const pages = await scan();
      if (env.DB) await save(env.DB, pages);
    })());
  },
};
