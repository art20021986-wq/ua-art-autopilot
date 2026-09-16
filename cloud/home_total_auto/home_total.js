(function () {
  "use strict";
  function start() {
    var cta = document.querySelector('.outline-cta i[data-ru*="Открыть все автомобили"]');
    if (!cta || window.__uaHomeTotalAutoV1) return;
    window.__uaHomeTotalAutoV1 = true;
    var total = null, request = 0;
    function render() {
      if (total === null) return;
      var ru = "Открыть все автомобили · " + total;
      var uk = "Відкрити всі автомобілі · " + total;
      var lang = (document.documentElement.getAttribute("lang") || "").toLowerCase();
      cta.setAttribute("data-ru", ru);
      cta.setAttribute("data-uk", uk);
      cta.textContent = /^(uk|ua)(-|$)/.test(lang) ? uk : ru;
    }
    function normalize(value) {
      value = (value || "").trim().toUpperCase();
      return /^UA-\d{4,}$/.test(value) ? value : null;
    }
    function cardId(card, base) {
      var ids = new Set();
      function add(value) { var id = normalize(value); if (id) ids.add(id); }
      add(card.getAttribute("data-ua"));
      add(card.getAttribute("data-ua-card"));
      card.querySelectorAll("[data-ua-card]").forEach(function (node) {
        add(node.getAttribute("data-ua-card"));
      });
      var links = Array.from(card.querySelectorAll("a[href]"));
      if (card.matches("a[href]")) links.push(card);
      links.forEach(function (link) {
        try {
          var url = new URL(link.getAttribute("href"), base);
          var match = url.pathname.match(/\/(UA-\d{4,})\.html$/i);
          if (url.origin === location.origin && match) add(match[1]);
        } catch (_error) { /* An invalid link cannot identify a vehicle. */ }
      });
      if (ids.size !== 1) throw new Error("Missing or conflicting catalogue vehicle ID");
      return Array.from(ids)[0];
    }
    function count(html, base) {
      if (!/<\/html\s*>/i.test(html)) throw new Error("Catalogue response is incomplete");
      var doc = new DOMParser().parseFromString(html, "text/html");
      var cards = Array.from(doc.querySelectorAll("article.catalog-card"));
      doc.querySelectorAll("a[data-ua-card]").forEach(function (node) {
        if (!node.closest("article.catalog-card")) cards.push(node);
      });
      if (!cards.length && !doc.querySelector(".catalog-grid")) {
        throw new Error("Catalogue markup is missing");
      }
      var ids = new Set();
      cards.forEach(function (card) { ids.add(cardId(card, base)); });
      return ids.size;
    }
    async function sync() {
      var current = ++request;
      try {
        var anchor = cta.closest("a[href]");
        if (!anchor) throw new Error("Catalogue link is missing");
        var url = new URL(anchor.getAttribute("href"), document.baseURI);
        if (url.origin !== location.origin) throw new Error("Catalogue link is not same-origin");
        ["f", "etap", "stage"].forEach(function (key) { url.searchParams.delete(key); });
        url.hash = "";
        var response = await fetch(url.href, {cache: "no-store", credentials: "same-origin"});
        if (!response.ok) throw new Error("Catalogue HTTP " + response.status);
        if (!/^text\/html\b/i.test(response.headers.get("content-type") || "")) {
          throw new Error("Catalogue response is not HTML");
        }
        var base = response.url || url.href;
        if (new URL(base).origin !== location.origin) throw new Error("Catalogue redirected off-site");
        var next = count(await response.text(), base);
        if (current !== request) return;
        total = next;
        render();
      } catch (error) {
        if (current === request) console.warn("[UA home total] Keeping previous total:", error.message);
      }
    }
    new MutationObserver(render).observe(document.documentElement, {
      attributes: true, attributeFilter: ["lang"]
    });
    window.addEventListener("pageshow", function (event) { if (event.persisted) sync(); });
    sync();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once: true});
  } else start();
}());
