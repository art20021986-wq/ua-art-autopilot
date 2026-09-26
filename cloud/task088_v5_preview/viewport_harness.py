"""Deterministic, authenticated Preview UI for observing CSS viewport layout.

This does not emulate a device or issue acceptance receipts. It only loads exact
manifest-listed documents in one fixed-size same-origin browsing context. The
candidate response bytes remain untouched; the Preview server adds restrictive
framing headers only for the exact, explicit observation query below.
"""
import json
import re

HARNESS_ROUTE = '/__uaart_preview__/viewport.html'
HARNESS_CONTRACT = 'UA-ART-PREVIEW-CSS-VIEWPORT-1'
FRAME_QUERY = '__uaart_viewport=1'
VIEWPORTS = {'mobile': {'width': 390, 'height': 844},
             'desktop': {'width': 1280, 'height': 900}}
HTML_MIME = 'text/html; charset=utf-8'
_DOCUMENT = re.compile(r'/video/(?:index|UA-[0-9]{4,}(?:-diag)?|katalog|info|podbor)\.html')
_UNSERVED_DOCUMENT = re.compile(r'/site/(?:UA-[0-9]{4,}(?:-diag)?|katalog|info|podbor)\.html')


def document_routes(files):
    routes = []
    for route, item in files.items():
        if route == HARNESS_ROUTE or item.get('content_type') != HTML_MIME:
            continue
        # Routing evidence binds Production to /video/. Preserved /site/
        # artifacts are never presented as an actual served viewport surface.
        if type(route) is str and _UNSERVED_DOCUMENT.fullmatch(route):
            continue
        if (type(route) is not str or not _DOCUMENT.fullmatch(route)
                or item.get('storage') != 'bundle'
                or not re.fullmatch(r'[0-9a-f]{64}', item.get('sha256', ''))):
            raise ValueError('VIEWPORT_REQUIRES_EXACT_PINNED_PUBLIC_DOCUMENTS')
        routes.append(route)
    if not routes or '/video/index.html' not in routes:
        raise ValueError('VIEWPORT_REQUIRES_PINNED_HOME')
    return sorted(routes)


def specification(files):
    return {'contract': HARNESS_CONTRACT, 'route': HARNESS_ROUTE,
            'frame_query': FRAME_QUERY, 'viewports': VIEWPORTS,
            'document_routes': document_routes(files),
            'acceptance': 'NOT_RUN'}


def render(files):
    spec = specification(files)
    documents = [{'path': path, 'sha256': files[path]['sha256']}
                 for path in spec['document_routes']]
    # All strings are validated route/hash constants. Escape HTML delimiters as
    # defense in depth; never interpolate a request URL, hostname or secret.
    data = json.dumps({'documents': documents, 'viewports': VIEWPORTS,
                       'frame_query': FRAME_QUERY}, sort_keys=True,
                      separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return (_HEAD + data + _TAIL).encode('utf-8')


_HEAD = '''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="uaart-preview-harness" content="UA-ART-PREVIEW-CSS-VIEWPORT-1">
<title>UA ART — проверка размера Preview</title>
<style>
body{margin:16px;font:16px/1.45 system-ui,sans-serif;background:#eef1f5;color:#142033}
label,button,a{font:inherit}select,button{font:inherit;padding:8px;margin:4px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;max-width:1250px}
.note{max-width:1000px}.surface{overflow:auto;padding:8px 0;max-width:100%}
iframe{display:block;border:0;padding:0;margin:0;box-sizing:content-box;background:white;max-width:none;max-height:none}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-width:1250px;background:white;padding:12px}
</style></head><body>
<h1>Защищённый Preview: CSS-размер экрана</h1>
<p class="note">Наблюдение макета в текущем браузере. Это не эмуляция iPhone или Safari и не автоматический PASS.
Язык переключайте штатными RU | UA | GE внутри страницы. Ссылки, внешние приложения и системные кнопки
проверяются отдельно: изоляция встроенного просмотра ограничивает переходы.</p>
<div class="controls"><label>Страница <select id="document"></select></label>
<label>Размер <select id="viewport"><option value="mobile">390 × 844 CSS px</option>
<option value="desktop">1280 × 900 CSS px</option></select></label>
<button id="observe" type="button">Прочитать текущие размеры и цены</button>
<a id="direct" target="_blank" rel="noopener noreferrer">Открыть страницу отдельно</a></div>
<p id="state" role="status">Ожидание загрузки.</p>
<div class="surface"><iframe id="candidate" title="Кандидат с точным CSS-размером"
sandbox="allow-scripts allow-same-origin" referrerpolicy="no-referrer"></iframe></div>
<pre id="observation">Наблюдение ещё не выполнено.</pre>
<script id="viewport-data" type="application/json">'''

_TAIL = '''</script><script>
"use strict";
(() => {
  const config = JSON.parse(document.getElementById("viewport-data").textContent);
  const selector = document.getElementById("document");
  const sizes = document.getElementById("viewport");
  const frame = document.getElementById("candidate");
  const state = document.getElementById("state");
  const output = document.getElementById("observation");
  const direct = document.getElementById("direct");
  for (const doc of config.documents) {
    const option = document.createElement("option");
    option.value = doc.path;
    option.textContent = doc.path;
    selector.appendChild(option);
  }
  selector.value = "/video/index.html";
  function selected() { return config.documents.find(doc => doc.path === selector.value); }
  function resize() {
    const size = config.viewports[sizes.value];
    if (!size) throw new Error("Unknown fixed viewport");
    frame.style.width = size.width + "px";
    frame.style.height = size.height + "px";
    state.textContent = "Размер задан. Для результата прочитайте фактические размеры после загрузки.";
    output.textContent = "Новый размер: наблюдение ещё не выполнено.";
  }
  function load() {
    const doc = selected();
    if (!doc) throw new Error("Document is outside the pinned list");
    const target = new URL(doc.path, location.origin);
    if (target.origin !== location.origin || target.pathname !== doc.path) throw new Error("Exact same-origin path required");
    target.search = config.frame_query;
    frame.src = target.href;
    direct.href = doc.path;
    output.textContent = "Новая страница: наблюдение ещё не выполнено.";
    state.textContent = "Загрузка выбранного кандидата.";
  }
  function observe() {
    try {
      const doc = selected();
      const win = frame.contentWindow;
      const child = frame.contentDocument;
      const expected = new URL(doc.path, location.origin);
      expected.search = config.frame_query;
      if (!child || win.location.href !== expected.href) throw new Error("Selected candidate is not loaded");
      const size = config.viewports[sizes.value];
      const root = child.documentElement;
      const box = element => {
        const rect = element.getBoundingClientRect();
        return {x:rect.x,y:rect.y,width:rect.width,height:rect.height};
      };
      const prices = Array.from(child.querySelectorAll(".ua-market-prices-v1")).map(block => ({
        car:block.getAttribute("data-ua-car"), box:box(block),
        rows:Array.from(block.querySelectorAll("[data-ua-market]")).map(row => ({
          market:row.getAttribute("data-ua-market"), value:row.getAttribute("data-ua-value"),
          text:row.innerText, box:box(row),
          text_sizes:Array.from(row.querySelectorAll(".ua-market-amount-v1,.ua-market-caption-v1,.ua-market-amount-v1 span"))
            .map(element => ({text:element.innerText,font_size:win.getComputedStyle(element).fontSize,box:box(element)}))
        }))
      }));
      const result = {
        status:"OBSERVED_ONLY", acceptance:"NOT_EVALUATED", observed_at:new Date().toISOString(),
        path:doc.path, candidate_sha256:doc.sha256, language:root.lang,
        requested_css_viewport:size, actual_css_viewport:{width:win.innerWidth,height:win.innerHeight},
        exact_dimensions:win.innerWidth===size.width && win.innerHeight===size.height,
        viewport_media_match:win.matchMedia("(width: "+size.width+"px) and (height: "+size.height+"px)").matches,
        document_width:root.clientWidth, document_scroll_width:root.scrollWidth,
        ready_state:child.readyState, device_pixel_ratio:win.devicePixelRatio,
        images_total:child.images.length, images_decoded:Array.from(child.images).filter(image=>image.complete&&image.naturalWidth>0).length,
        fonts_status:child.fonts ? child.fonts.status : "unavailable",
        prices:prices,
        limitations:["Current browser CSS layout only; no mobile OS, Safari or touch emulation",
          "Scoped HTTP sandbox restricts navigation, popups, forms and native actions",
          "No acceptance verdict; use separate screenshots, comparisons and top-level link checks"]
      };
      output.textContent = JSON.stringify(result,null,2);
      state.textContent = result.exact_dimensions && result.viewport_media_match
        ? "Размер подтверждён измерением. Прочие проверки и решение Gate выполняются отдельно."
        : "Фактический размер не совпал: этот просмотр не подтверждает требуемый макет.";
    } catch (error) {
      state.textContent = "Наблюдение недоступно. PASS не выдан.";
      output.textContent = JSON.stringify({status:"OBSERVATION_ERROR",acceptance:"NOT_EVALUATED",reason:String(error)},null,2);
    }
  }
  selector.addEventListener("change",load);
  sizes.addEventListener("change",resize);
  document.getElementById("observe").addEventListener("click",observe);
  frame.addEventListener("load",()=>{state.textContent="Загрузка завершилась. Прочитайте фактические размеры и проверьте страницу.";});
  resize();
  load();
})();
</script></body></html>'''
