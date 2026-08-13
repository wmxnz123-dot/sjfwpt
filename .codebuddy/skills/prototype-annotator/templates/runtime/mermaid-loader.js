(function () {
  "use strict";

  var loadPromise = null;
  var DEFAULT_SOURCES = [
    "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js",
    "https://unpkg.com/mermaid@10/dist/mermaid.min.js"
  ];

  function escapeHtml(value) {
    if (window.PrototypeAnnotatorMarkdown) {
      return window.PrototypeAnnotatorMarkdown.escapeHtml(value);
    }
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function mermaidSources() {
    var config = window.PROTOTYPE_ANNOTATOR_CONFIG || {};
    if (Array.isArray(config.mermaidSources)) return config.mermaidSources;
    if (typeof config.mermaidSrc === "string") return [config.mermaidSrc];
    return DEFAULT_SOURCES;
  }

  function setFallback(node, title, code) {
    node.innerHTML = '<div class="pa-card-kicker">' + escapeHtml(title) + '</div><pre class="pa-mermaid-fallback"><code>' +
      escapeHtml(code) +
      "</code></pre>";
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.onload = resolve;
      script.onerror = function () {
        reject(new Error("Failed to load " + src));
      };
      document.head.appendChild(script);
    });
  }

  function ensureMermaid() {
    if (window.mermaid && window.mermaid.render) return Promise.resolve(window.mermaid);
    if (loadPromise) return loadPromise;

    var sources = mermaidSources().filter(Boolean);
    loadPromise = sources.reduce(function (promise, src) {
      return promise.catch(function () {
        return loadScript(src).then(function () {
          if (!window.mermaid || !window.mermaid.render) {
            throw new Error("Mermaid did not initialize from " + src);
          }
          return window.mermaid;
        });
      });
    }, Promise.reject(new Error("Mermaid is not loaded")));

    return loadPromise;
  }

  function renderMermaid(root) {
    var container = root || document;
    var nodes = Array.prototype.slice.call(container.querySelectorAll("[data-pa-mermaid]"));
    if (!nodes.length) return;

    if (!window.mermaid || !window.mermaid.render) {
      nodes.forEach(function (node) {
        if (node.getAttribute("data-pa-mermaid-rendered")) return;
        node.setAttribute("data-pa-mermaid-code", node.textContent || "");
        node.innerHTML = '<div class="pa-card-kicker">Loading Mermaid...</div>';
        node.setAttribute("data-pa-mermaid-rendered", "loading");
      });
      ensureMermaid().then(function () {
        nodes.forEach(function (node) {
          node.textContent = node.getAttribute("data-pa-mermaid-code") || node.textContent || "";
          node.removeAttribute("data-pa-mermaid-rendered");
        });
        renderMermaid(container);
      }).catch(function (err) {
        nodes.forEach(function (node) {
          var code = node.getAttribute("data-pa-mermaid-code") || node.textContent || "";
          setFallback(node, "Mermaid unavailable", code + "\n\n" + err.message);
          node.setAttribute("data-pa-mermaid-rendered", "fallback");
        });
      });
      return;
    }

    try {
      window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
    } catch (err) {
      // Mermaid may already be initialized.
    }

    nodes.forEach(function (node, index) {
      if (node.getAttribute("data-pa-mermaid-rendered") === "svg") return;
      var code = node.getAttribute("data-pa-mermaid-code") || node.textContent || "";
      var id = "pa-mermaid-" + Date.now() + "-" + index;
      Promise.resolve(window.mermaid.render(id, code)).then(function (result) {
        node.innerHTML = result.svg || result;
        node.setAttribute("data-pa-mermaid-rendered", "svg");
      }).catch(function (err) {
        setFallback(node, "Mermaid render failed", code + "\n\n" + err.message);
        node.setAttribute("data-pa-mermaid-rendered", "error");
      });
    });
  }

  window.PrototypeAnnotatorMermaid = {
    render: renderMermaid
  };
})();
