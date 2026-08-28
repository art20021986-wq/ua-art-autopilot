const PREVIEW_HEADERS = {
  "x-robots-tag": "noindex, nofollow",
  "cache-control": "no-store",
  "x-ua-art-scope": "sandbox-github-preview",
};

function withPreviewHeaders(response) {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(PREVIEW_HEADERS)) headers.set(name, value);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!['GET', 'HEAD'].includes(request.method)) {
      return new Response('Sandbox preview is read-only', {
        status: 405,
        headers: { ...PREVIEW_HEADERS, allow: 'GET, HEAD' },
      });
    }

    if (url.pathname === '/health') {
      return Response.json({
        ok: true,
        mode: 'read-only',
        d1: false,
        urls: 17,
        scope: 'sandbox-github-preview',
        productionWrite: false,
        formSubmit: false,
        candidatePages: 14,
      }, { headers: PREVIEW_HEADERS });
    }

    if (url.pathname === '/' || url.pathname === '/index.html') {
      const target = new URL('/video/index.html', request.url);
      return new Response(null, {
        status: 301,
        headers: { ...PREVIEW_HEADERS, location: target.toString() },
      });
    }

    return withPreviewHeaders(await env.ASSETS.fetch(request));
  },
};

