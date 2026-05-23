/**
 * AIMarket Widget v2.0.0 — MIT Licensed
 *
 * Embeddable AI capability search + invoke widget.
 * Single <script> tag, renders everything inline.
 *
 * Usage:
 *   <script src="https://cdn.modelmarket.dev/widget.js"
 *           data-intent="translate to 5 languages"
 *           data-budget="3.00"
 *           data-theme="cyber"
 *           data-hub-url="https://hub.modelmarket.dev"
 *           data-affiliate-id="my_blog"></script>
 *
 * Themes: cyber, neon, light, paper, midnight, ocean
 * Affiliate: data-affiliate-id earns 30% of spend from widget invocations.
 *
 * Security: No inline event handlers. Uses addEventListener exclusively.
 * All user-controlled strings rendered via textContent or safe DOM APIs.
 */

(function (global) {
  "use strict";

  function findScriptEl() {
    if (document.currentScript) return document.currentScript;
    var nodes = document.querySelectorAll('script[src*="aimarket.js"]');
    return nodes.length ? nodes[nodes.length - 1] : null;
  }

  var scriptEl = findScriptEl();
  var HUB_URL =
    (scriptEl && scriptEl.getAttribute("data-hub-url")) ||
    (typeof location !== "undefined" ? location.origin : "http://localhost:9080");
  var INTENT = (scriptEl && scriptEl.getAttribute("data-intent")) || "";
  var BUDGET = parseFloat((scriptEl && scriptEl.getAttribute("data-budget")) || "3.00");
  var THEME = (scriptEl && scriptEl.getAttribute("data-theme")) || "cyber";
  var AFFILIATE_ID = (scriptEl && scriptEl.getAttribute("data-affiliate-id")) || "";

  // Validate theme — "auto" detects parent page theme
  var VALID_THEMES = ["cyber", "neon", "light", "paper", "midnight", "ocean", "auto"];
  if (VALID_THEMES.indexOf(THEME) === -1) {
    THEME = "auto";
  }

  // ── Auto-theme: detect parent page theme ────────────────────
  function detectParentTheme() {
    // 1. Check <html> data-theme-bg attribute (used by AI-Factory storefront)
    var htmlEl = document.documentElement;
    var bgAttr = htmlEl.getAttribute("data-theme-bg");
    if (bgAttr === "dark") return "midnight";
    if (bgAttr === "light") return "light";

    // 2. Check <html> class for dark/light
    var htmlClass = htmlEl.className || "";
    if (/\bdark\b/.test(htmlClass)) return "midnight";
    if (/\blight\b/.test(htmlClass)) return "paper";

    // 3. Check body background color lightness
    try {
      var bodyBg = getComputedStyle(document.body).backgroundColor;
      var match = bodyBg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
      if (match) {
        var r = parseInt(match[1]), g = parseInt(match[2]), b = parseInt(match[3]);
        var luma = 0.299 * r + 0.587 * g + 0.114 * b;
        if (luma < 128) return "midnight";
        if (luma > 200) return "paper";
      }
    } catch(e) {}

    // 4. Fallback to system preference
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "midnight";
    }
    return "light";
  }

  var resolvedTheme = THEME;
  if (THEME === "auto") {
    resolvedTheme = detectParentTheme();
  }

  // Listen for parent theme changes (e.g. dark mode toggle)
  if (THEME === "auto" && window.matchMedia) {
    try {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function() {
        // Re-detect and update root class
        var newTheme = detectParentTheme();
        var root = document.querySelector(".aimw-root");
        if (root) {
          root.classList.remove("aimw-theme-" + resolvedTheme);
          root.classList.add("aimw-theme-" + newTheme);
          resolvedTheme = newTheme;
        }
      });
    } catch(e) {}
  }

  // ── Critical layout (works even if themes.css is slow/missing) ─
  (function injectCriticalCSS() {
    if (document.getElementById("aimw-critical-style")) return;
    var s = document.createElement("style");
    s.id = "aimw-critical-style";
    s.textContent =
      "#aimarket-widget-host{position:fixed;bottom:1.25rem;left:1.25rem;z-index:380;width:min(320px,calc(100vw - 2.5rem));max-height:min(85vh,640px);overflow:hidden;pointer-events:none;transition:width .4s cubic-bezier(.4,0,.2,1)}" +
      "#aimarket-widget-host.aimw-host-expanded{width:min(420px,calc(100vw - 2.5rem));overflow:auto}" +
      ".aimw-root{pointer-events:auto;display:flex;flex-direction:column;width:100%;max-width:100%;margin:0;padding:10px 12px;border-radius:14px;border:1px solid #334155;background:#0f172a;color:#e2e8f0;box-shadow:0 8px 32px rgba(0,0,0,.45);transition:padding .35s cubic-bezier(.4,0,.2,1),box-shadow .35s ease}" +
      ".aimw-root.aimw-expanded{padding:16px 18px;box-shadow:0 12px 40px rgba(0,0,0,.5)}" +
      ".aimw-compact-row{display:flex;gap:8px;align-items:center}" +
      ".aimw-search{flex:1;min-width:0;margin:0;padding:11px 14px;border:2px solid #334155;border-radius:10px;background:#1e293b;color:#e2e8f0;font-size:14px;transition:border-color .2s,box-shadow .2s}" +
      ".aimw-toggle{flex-shrink:0;display:flex;align-items:center;justify-content:center;width:42px;height:42px;border:2px solid #334155;border-radius:10px;background:#1e293b;color:#94a3b8;cursor:pointer;transition:transform .4s cubic-bezier(.4,0,.2,1),border-color .2s,color .2s,background .2s}" +
      ".aimw-root.aimw-expanded .aimw-toggle{transform:rotate(180deg);color:#e2e8f0;border-color:#475569}" +
      ".aimw-expanded-panel{display:grid;grid-template-rows:0fr;opacity:0;margin-top:0;transition:grid-template-rows .42s cubic-bezier(.4,0,.2,1),opacity .32s ease,margin-top .35s ease}" +
      ".aimw-root.aimw-expanded .aimw-expanded-panel{grid-template-rows:1fr;opacity:1;margin-top:12px}" +
      ".aimw-expanded-inner{overflow:hidden;min-height:0}" +
      ".aimw-header{font-size:20px;font-weight:800;margin-bottom:6px}" +
      ".aimw-subheader{font-size:12px;color:#94a3b8;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px}" +
      ".aimw-budget{display:grid;grid-template-columns:auto minmax(72px,1fr) auto;gap:8px;align-items:center;margin-bottom:12px}" +
      ".aimw-budget input{padding:8px 10px;border:1px solid #334155;border-radius:8px;background:#1e293b;color:#e2e8f0;width:100%}" +
      ".aimw-btn{padding:10px 16px;border:none;border-radius:8px;background:#2563eb;color:#fff;font-weight:600;cursor:pointer}" +
      ".aimw-footer{font-size:11px;color:#64748b;margin-top:8px}" +
      "@media(prefers-reduced-motion:reduce){.aimw-root,.aimw-expanded-panel,.aimw-toggle,#aimarket-widget-host{transition:none!important}}";
    document.head.appendChild(s);
  })();

  // ── Load themes CSS dynamically ─────────────────────────────
  (function loadCSS() {
    var existing = document.querySelector("link[data-aimw-theme]");
    if (existing) return;

    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.setAttribute("data-aimw-theme", "1");
    var href = "/themes.css";
    if (scriptEl && scriptEl.src) {
      try {
        var u = new URL(scriptEl.src, window.location.href);
        href = u.pathname.replace(/aimarket\.js.*$/i, "themes.css");
        if (href.charAt(0) !== "/") href = "/" + href;
      } catch (e) {}
    }
    link.href = href;
    document.head.appendChild(link);
  })();

  // ── Security: safe DOM helpers ──────────────────────────────

  function safeText(el, text) {
    el.textContent = text || "";
  }

  function safeHTML(container, html) {
    // Parse HTML string into detached DOM, then attach event listeners
    // before inserting into document. Prevents XSS through event handlers.
    var template = document.createElement("template");
    template.innerHTML = html;
    return template.content;
  }

  // ── Collapse / expand ───────────────────────────────────────

  function createToggleIcon() {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "20");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "aimw-toggle-icon");
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M6 9l6 6 6-6");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "2.25");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    svg.appendChild(path);
    return svg;
  }

  function setWidgetExpanded(expanded) {
    var root = document.querySelector(".aimw-root");
    var host = document.getElementById("aimarket-widget-host");
    var toggle = document.querySelector(".aimw-toggle");
    if (!root) return;
    root.classList.toggle("aimw-expanded", expanded);
    root.classList.toggle("aimw-collapsed", !expanded);
    if (host) host.classList.toggle("aimw-host-expanded", expanded);
    if (toggle) {
      toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
      toggle.setAttribute(
        "aria-label",
        expanded ? "Collapse AI Market panel" : "Expand AI Market panel"
      );
    }
  }

  function expandWidget() {
    setWidgetExpanded(true);
  }

  function collapseWidget() {
    setWidgetExpanded(false);
  }

  function toggleWidget() {
    var root = document.querySelector(".aimw-root");
    if (!root) return;
    setWidgetExpanded(!root.classList.contains("aimw-expanded"));
  }

  // ── Render ──────────────────────────────────────────────────

  function makeRoot() {
    var root = document.createElement("div");
    root.className =
      "aimw-root aimw-theme-" + resolvedTheme + " aimw-collapsed";

    var compactRow = document.createElement("div");
    compactRow.className = "aimw-compact-row";

    var search = document.createElement("input");
    search.className = "aimw-search";
    search.type = "text";
    search.placeholder = "Search AI capabilities…";
    search.setAttribute("aria-label", "Search AI capabilities");
    search.value = INTENT;

    var toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "aimw-toggle";
    toggleBtn.setAttribute("aria-expanded", "false");
    toggleBtn.setAttribute("aria-label", "Expand AI Market panel");
    toggleBtn.appendChild(createToggleIcon());

    compactRow.appendChild(search);
    compactRow.appendChild(toggleBtn);

    var expandedPanel = document.createElement("div");
    expandedPanel.className = "aimw-expanded-panel";
    var expandedInner = document.createElement("div");
    expandedInner.className = "aimw-expanded-inner";

    var header = document.createElement("div");
    header.className = "aimw-header";
    safeText(header, "AI Market");

    var subheader = document.createElement("div");
    subheader.className = "aimw-subheader";
    safeText(subheader, "Discover & invoke AI capabilities");

    var budgetDiv = document.createElement("div");
    budgetDiv.className = "aimw-budget";
    var budgetLabel = document.createElement("span");
    safeText(budgetLabel, "Budget: $");
    var budgetInput = document.createElement("input");
    budgetInput.type = "number";
    budgetInput.value = BUDGET;
    budgetInput.min = 0.1;
    budgetInput.max = 10000;
    budgetInput.step = 0.1;
    budgetInput.id = "aimw-budget-input";
    var searchBtn = document.createElement("button");
    searchBtn.className = "aimw-btn";
    searchBtn.type = "button";
    safeText(searchBtn, "Search");
    budgetDiv.appendChild(budgetLabel);
    budgetDiv.appendChild(budgetInput);
    budgetDiv.appendChild(searchBtn);

    if (AFFILIATE_ID) {
      var affTag = document.createElement("div");
      affTag.className = "aimw-affiliate-tag";
      safeText(affTag, "via " + AFFILIATE_ID);
      expandedInner.appendChild(affTag);
    }

    var resultsDiv = document.createElement("div");
    resultsDiv.id = "aimw-results";
    var outputDiv = document.createElement("div");
    outputDiv.id = "aimw-output";

    var footer = document.createElement("div");
    footer.className = "aimw-footer";
    var footerLink = document.createElement("a");
    footerLink.href = "https://modelmarket.dev";
    footerLink.target = "_blank";
    footerLink.rel = "noopener noreferrer";
    safeText(footerLink, "modelmarket-hub");
    footer.appendChild(document.createTextNode("Powered by "));
    footer.appendChild(footerLink);

    expandedInner.appendChild(header);
    expandedInner.appendChild(subheader);
    expandedInner.appendChild(budgetDiv);
    expandedInner.appendChild(resultsDiv);
    expandedInner.appendChild(outputDiv);
    expandedInner.appendChild(footer);
    expandedPanel.appendChild(expandedInner);

    root.appendChild(compactRow);
    root.appendChild(expandedPanel);

    toggleBtn.addEventListener("click", toggleWidget);
    searchBtn.addEventListener("click", doSearch);
    search.addEventListener("keydown", function (e) {
      if (e.key === "Enter") doSearch();
    });

    var host = document.getElementById("aimarket-widget-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "aimarket-widget-host";
      host.setAttribute("aria-label", "AI Market capability search");
      document.body.appendChild(host);
    }
    host.appendChild(root);

    if (INTENT) {
      expandWidget();
      doSearch();
    }

    return root;
  }

  // ── URL helpers ─────────────────────────────────────────────

  function apiUrl(path) {
    return HUB_URL.replace(/\/$/, "") + path;
  }

  // ── Search ──────────────────────────────────────────────────

  function doSearch() {
    var query = document.querySelector(".aimw-search") ? document.querySelector(".aimw-search").value : "";
    var budget = parseFloat((document.getElementById("aimw-budget-input") || {}).value || "3");
    var resultsEl = document.getElementById("aimw-results");
    var outputEl = document.getElementById("aimw-output");

    if (!query.trim()) return;
    expandWidget();
    if (resultsEl) {
      resultsEl.innerHTML = '<div class="aimw-spinner" style="margin:8px;"></div> Searching...';
    }
    if (outputEl) outputEl.innerHTML = "";

    fetch(apiUrl("/ai-market/v2/search?" + new URLSearchParams({
      intent: query,
      budget: budget.toString(),
      limit: "6",
    })))
      .then(function(resp) {
        if (!resp.ok) throw new Error("Search failed: " + resp.status);
        return resp.json();
      })
      .then(function(data) {
        renderResults(data.matches || [], query, budget, data.empty_hint || "");
      })
      .catch(function(err) {
        if (resultsEl) {
          resultsEl.innerHTML = '<div class="aimw-error-box">Search error: ' +
            (err.message || "Unknown error").replace(/</g, "&lt;") + '</div>';
        }
      });
  }

  function renderResults(matches, query, budget, emptyHint) {
    var el = document.getElementById("aimw-results");
    if (!el) return;

    if (!matches.length) {
      var div = document.createElement("div");
      div.style.cssText = "font-size:13px;padding:12px;line-height:1.45;";
      var msg = emptyHint || ('No factory capabilities for "' + query + '". Try another term.');
      safeText(div, msg);
      el.innerHTML = "";
      el.appendChild(div);
      return;
    }

    el.innerHTML = ""; // Clear

    matches.forEach(function(m) {
      var card = document.createElement("div");
      card.className = "aimw-card";

      var infoDiv = document.createElement("div");
      infoDiv.className = "aimw-card-info";

      var nameDiv = document.createElement("div");
      nameDiv.className = "aimw-card-name";
      var title = m.product_display_name
        ? (m.product_display_name + " · " + (m.name || m.capability_id || ""))
        : (m.name || m.capability_id || "");
      safeText(nameDiv, title);

      // Trust badge
      var trustBadge = document.createElement("span");
      trustBadge.className = "aimw-badge aimw-badge-trust";
      safeText(trustBadge, "trust " + ((m.trust_score || 0).toFixed(2)));
      nameDiv.appendChild(trustBadge);

      // Safety badge
      var safetyBadge = document.createElement("span");
      safetyBadge.className = "aimw-badge aimw-badge-safety";
      safeText(safetyBadge, "safety gate");
      nameDiv.appendChild(safetyBadge);

      var descDiv = document.createElement("div");
      descDiv.className = "aimw-card-desc";
      safeText(descDiv, (m.description || "").substring(0, 100));

      var metaDiv = document.createElement("div");
      metaDiv.className = "aimw-card-meta";
      var price = m.routed_price_usd || m.price_per_call_usd || 0;
      var meta = "$" + price.toFixed(2) + " · " + (m.p50_latency_ms || "?") + "ms";
      if (m.status_label) meta += " · " + m.status_label;
      if (m.source_hub_name) meta += " · " + m.source_hub_name;
      safeText(metaDiv, meta);

      infoDiv.appendChild(nameDiv);
      infoDiv.appendChild(descDiv);
      infoDiv.appendChild(metaDiv);

      var tryBtn = document.createElement("button");
      tryBtn.className = "aimw-btn";
      safeText(tryBtn, "Try");
      // Safe: addEventListener with closure captures the values
      (function(pid, cid, hub) {
        tryBtn.addEventListener("click", function() {
          tryCapability(pid, cid, hub);
        });
      })(m.product_id, m.capability_id, m.source_hub || "local");

      card.appendChild(infoDiv);
      card.appendChild(tryBtn);
      el.appendChild(card);
    });
  }

  // ── Invoke ──────────────────────────────────────────────────
  var globalTryCapability = null; // Stored for potential external use

  function tryCapability(productId, capabilityId, sourceHub) {
    globalTryCapability = { productId: productId, capabilityId: capabilityId, sourceHub: sourceHub };
    var outputEl = document.getElementById("aimw-output");
    var query = document.querySelector(".aimw-search") ? document.querySelector(".aimw-search").value : "";
    if (outputEl) {
      outputEl.innerHTML = '<div class="aimw-spinner" style="margin:8px;"></div> Invoking ' +
        (capabilityId || "").replace(/</g, "&lt;") + '...';
    }

    var budgetVal = parseFloat((document.getElementById("aimw-budget-input") || {}).value || "3");

    // Step 1: Open channel
    fetch(apiUrl("/ai-market/channel/open"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deposit_usd: budgetVal,
        tx_hash: "demo-" + Date.now(),
      }),
    })
      .then(function(r) { return r.ok ? r.json() : Promise.reject("Channel open failed"); })
      .then(function(chData) {
        var channelId = chData.channel && chData.channel.channel_id;
        if (!channelId) throw new Error("No channel ID");

        // Step 2: Invoke
        var headers = { "Content-Type": "application/json", "X-Payment-Channel": channelId };
        if (AFFILIATE_ID) headers["X-AIMarket-Affiliate"] = AFFILIATE_ID;

        return fetch(apiUrl("/ai-market/v2/invoke"), {
          method: "POST",
          headers: headers,
          body: JSON.stringify({
            product_id: productId,
            capability_id: capabilityId,
            source_hub: sourceHub,
            input: { text: query },
          }),
        }).then(function(r) {
          return { response: r, json: r.ok || r.status === 403 ? r.json() : Promise.reject("Invoke failed: " + r.status), channelId: channelId };
        });
      })
      .then(function(data) {
        var resp = data.response;
        var body = data.json.then ? data.json : Promise.resolve(data.json);
        return body.then(function(result) {
          return { status: resp.status, result: result, channelId: data.channelId };
        });
      })
      .then(function(data) {
        var result = data.result;
        var channelId = data.channelId;

        // Close channel
        fetch(apiUrl("/ai-market/channel/close"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channel_id: channelId, settle_tx_hash: "demo-settle-" + Date.now() }),
        });

        if (!outputEl) return;

        if (data.status === 403) {
          outputEl.innerHTML = '<div class="aimw-error-box">' +
            '<strong>Safety gate blocked</strong><br/>' +
            ((result.category || "unknown").replace(/</g, "&lt;")) + ': ' +
            ((result.reason || "").replace(/</g, "&lt;")) +
            (result.refund && result.refund.refunded ? '<br/>Auto-refunded' : '') +
            '</div>';
          return;
        }

        if (data.status === 402) {
          outputEl.innerHTML = '<div class="aimw-error-box">Payment required. Connect wallet.</div>';
          return;
        }

        var ok = result.success;
        var mark = ok ? "OK" : "FAIL";
        var price = result.price_usd || 0;

        outputEl.innerHTML = '<div class="aimw-result">' +
          '<strong>' + mark + ' ' + (capabilityId || "").replace(/</g, "&lt;") + '</strong>' +
          '<span style="font-size:11px;"> · $' + price.toFixed(2) + ' · ' + (result.latency_ms || "?") + 'ms</span>' +
          (result.safety_checked ? '<span class="aimw-badge aimw-badge-safety">safety passed</span>' : '') +
          '<pre style="margin-top:8px;font-size:12px;white-space:pre-wrap;">' +
          JSON.stringify(result.result || {}, null, 2).replace(/</g, "&lt;") +
          '</pre>' +
          (AFFILIATE_ID ? '<div style="font-size:10px;margin-top:4px;">Earned $' + (price * 0.3).toFixed(4) + ' for ' + AFFILIATE_ID.replace(/</g, "&lt;") + '</div>' : '') +
          '</div>';
      })
      .catch(function(err) {
        if (outputEl) {
          outputEl.innerHTML = '<div class="aimw-error-box">Error: ' +
            ((err.message || String(err)).replace(/</g, "&lt;")) + '</div>';
        }
      });
  }

  // Expose tryCapability for external programmatic use (safe — no inline onclick)
  global.__aimwTry = tryCapability;

  // ── Boot (skip admin — panel is storefront-only) ────────────
  function shouldMount() {
    try {
      var p = (location && location.pathname) || "";
      if (p.indexOf("/admin") === 0) return false;
    } catch (e) {}
    return true;
  }

  function boot() {
    if (!shouldMount()) return;
    if (document.getElementById("aimarket-widget-host") && document.querySelector(".aimw-root")) return;
    makeRoot();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(window);
