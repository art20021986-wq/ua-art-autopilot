# SEO and routing audit — read-only

Evidence discipline: VERIFIED / INFERRED / PENDING, as defined in `current_architecture_audit.md`.

## 1. What was actually probed

The attached machine evidence contains five read-only GET requests against the live public site, performed once, at a single point in time:

| Requested URL | HTTP | Final URL | Title | Canonical |
|---|---:|---|---|---|
| `https://www.uaart.com.ua/` | 200 | `https://www.uaart.com.ua/video/index.html` | "UA ART COMPANY — автомобили под ключ в Киеве" | `https://www.uaart.com.ua/video/index.html` |
| `https://uaart.com.ua/` | 200 | `https://www.uaart.com.ua/video/index.html` | (same) | (same) |
| `https://www.uaart.com.ua/robots.txt` | 200 | itself | — | — |
| `https://www.uaart.com.ua/sitemap.xml` | 200 | itself | — | — |
| `https://www.uaart.com.ua/video/podbor.html` | 200 | itself | "Подбор авто под заказ — UA ART COMPANY" | itself |

This is a **point-in-time technical read**, not a full crawl, not a content audit, and not permission to publish anything.

## 2. VERIFIED findings

1. **Homepage lives under `/video/`.** Both the bare apex domain and the `www` domain redirect/resolve to `https://www.uaart.com.ua/video/index.html`, and that URL is also the page's own self-canonical. This means the site's logical "home" is architecturally a page inside a `/video/` directory tree, not a dedicated root document.
2. **`robots.txt` exists and returns 200.** Its body/rules were not captured in this evidence — only reachability was confirmed.
3. **`sitemap.xml` exists and returns 200.** Its entries were not enumerated in this evidence — only reachability was confirmed.
4. **A second content page (`/video/podbor.html`) exists, is reachable, and self-canonicalizes to itself** — consistent with more than one page living inside the `/video/` tree beyond just the homepage.

## 3. INFERRED findings (plausible, not proven)

- The `/video/` path segment in the homepage's canonical/final URL is unusual for a primary corporate homepage and suggests either (a) a historical site restructuring where `/video/` became the de-facto root, or (b) a deliberate but non-obvious information architecture. Either way, it is a **structural fact worth flagging** before any new top-level language tree (`/ua/`, `/ru/`) is designed, so the new tree does not accidentally nest under or collide with `/video/`.
- Because both the apex and `www` hosts converge on the same canonical, the site likely already has a working host-canonicalization rule (`www` vs non-`www`), which the future news canonical/hreflang design can reuse rather than reinvent.

## 4. PENDING — must be confirmed before any SEO decision, not assumed

- The literal `robots.txt` disallow/allow rules (e.g., whether `/video/` or any preview path is disallowed).
- The literal `sitemap.xml` entry list (whether it lists only production pages, or also draft/preview/staging paths).
- Whether any page currently emits `<meta name="robots" content="noindex">`, `X-Robots-Tag`, or `hreflang` link tags — none of this was captured by the probe (the "Robots meta" column was blank in the evidence, which is treated as **not captured**, not as **confirmed absent**).
- Whether any currently-live preview/staging route (referenced by name only in the workflow inventory, e.g. multiple `task*_gate_a`/`stage_*` scripts) is reachable from the public internet or is strictly internal-only.
- The current HTTP response headers relevant to caching/CDN (Cloudflare) behavior for any future `/ua/` or `/ru/` tree.

## 5. Recommended future routing scheme (recommendation only — not yet implemented, not yet approved)

Subject to confirming the PENDING items above:

- `https://www.uaart.com.ua/ua/avto-novyny/` — Ukrainian news hub, fully outside `/video/`.
- `https://www.uaart.com.ua/ru/avto-novosti/` — Russian news hub, fully outside `/video/`.
- Country/topic sub-paths inside each language tree (e.g. `/ua/avto-novyny/koreya/`).
- A dedicated `news-sitemap.xml`, separate from the existing `sitemap.xml`, added only after the existing sitemap's current content is confirmed not to already need cleanup.
- `NewsArticle` structured data, `BreadcrumbList`, Open Graph tags, `datePublished`/`dateModified`, `author`/`publisher`/`mainEntityOfPage`.
- Self-canonical per language URL, plus reciprocal `hreflang="uk"` / `hreflang="ru"` link tags between the two URLs of the same STORY ID.
- Draft/pending stories: `noindex`, excluded from the news sitemap, excluded from any public navigation and internal linking, until the owner presses "ОПУБЛИКОВАТЬ".
- Internal links from the news hub into the existing catalog only where topically justified (e.g. a story about a specific import corridor may link to the general catalog section), never as an artificial SEO-only cross-link scheme.

## 6. Explicit non-decision

This routing scheme is a **recommendation for a future, separately-approved SANDBOX/production step**. Nothing here authorizes creating `/ua/avto-novyny/`, `/ru/avto-novosti/`, a news sitemap, or any public route today. No such route was created in this task.
