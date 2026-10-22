// The free checks at /tools/: read what a person pasted, send it to /tools/api/<tool>, draw the
// answer. Answers quote untrusted text (poisoned tool descriptions, attacker addresses), so every
// value reaches the page through textContent — this file never assigns innerHTML.
(function () {
  "use strict";

  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else el.setAttribute(k, v === true ? "" : String(v));
      });
    }
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { add(el, c); }); return; }
    el.appendChild(typeof child === "object" ? child : document.createTextNode(String(child)));
  }

  // Copy buttons on every code block, as on the rest of the site.
  function copyButton(getText, ui) {
    var btn = h("button", { type: "button", class: "copy", text: (ui && ui.copy) || "copy" });
    btn.addEventListener("click", function () {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(getText()).then(function () {
        btn.textContent = (ui && ui.copied) || "copied";
        btn.classList.add("done");
        setTimeout(function () { btn.textContent = (ui && ui.copy) || "copy"; btn.classList.remove("done"); }, 1400);
      }, function () {});
    });
    return btn;
  }
  function wrapPre(pre, ui) {
    if (pre.parentElement && pre.parentElement.classList.contains("pre-wrap")) return;
    var wrap = h("div", { class: "pre-wrap" });
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);
    wrap.appendChild(copyButton(function () { return pre.innerText; }, ui));
  }

  var dataEl = document.getElementById("tool-data");
  var D = dataEl ? JSON.parse(dataEl.textContent) : null;
  document.querySelectorAll("main pre").forEach(function (pre) { wrapPre(pre, D && D.ui); });
  if (!D) return;

  var UI = D.ui, L = D.labels, TOOL = D.tool;
  var form = document.getElementById("check");
  var result = document.getElementById("result");
  var runBtn = document.getElementById("run");
  var note = document.getElementById("example-note");
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function field(name) { return form.elements.namedItem(name); }
  function val(name) { var f = field(name); return f ? f.value : ""; }
  function fail(message) { var e = new Error(message); e.user = true; return e; }

  // ── reading what people paste ────────────────────────────────────────────────────────────
  function stripHeader(text) {
    return String(text).trim().replace(/^(x-payment|payment-signature|payment-required)\s*:\s*/i, "").trim();
  }
  function looksBase64(text) { return /^[A-Za-z0-9+/_-]+={0,2}$/.test(text) && text.length >= 16; }
  function base64Json(text) {
    try {
      var bin = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
      var bytes = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return JSON.parse(new TextDecoder().decode(bytes));
    } catch (e) { return undefined; }
  }
  /** JSON, an event-stream answer (the last data: line that parses), or base64 JSON. */
  function readJson(text) {
    var t = stripHeader(text);
    if (!t) return undefined;
    try { return JSON.parse(t); } catch (e) { /* not plain JSON */ }
    var lines = t.split(/\r?\n/).filter(function (l) { return /^data:/.test(l); });
    for (var i = lines.length - 1; i >= 0; i--) {
      try { return JSON.parse(lines[i].slice(5).trim()); } catch (e) { /* next */ }
    }
    var compact = t.replace(/\s+/g, "");
    return looksBase64(compact) ? base64Json(compact) : undefined;
  }
  function toolsOf(v) {
    if (Array.isArray(v)) return v;
    if (v && Array.isArray(v.tools)) return v.tools;
    if (v && v.result && Array.isArray(v.result.tools)) return v.result.tools;
    return null;
  }
  function toolList(name, label) {
    var text = val(name);
    if (!text.trim()) throw fail(UI.errEmpty);
    var v = readJson(text);
    if (v === undefined) throw fail((label ? label + ": " : "") + UI.errJson);
    var tools = toolsOf(v);
    if (!tools) throw fail((label ? label + ": " : "") + UI.errNoTools);
    return tools;
  }

  var meta = {};
  var BUILD = {
    "x402-check": function () {
      var raw = stripHeader(val("payment"));
      if (!raw) throw fail(UI.errEmpty);
      var body = { now: Math.floor(Date.now() / 1000) };
      var p;
      try { p = JSON.parse(raw); } catch (e) { p = undefined; }
      if (p === undefined) {
        var compact = raw.replace(/\s+/g, "");
        if (!looksBase64(compact)) throw fail(UI.errPayment);
        body.x_payment = compact;
        p = base64Json(compact);
      } else if (p && typeof p === "object" && p.payload && typeof p.payload === "object") {
        body.payment = p;
      } else if (p && typeof p === "object") {
        ["authorization", "signature", "network", "v", "r", "s", "domain", "primary_type"].forEach(function (k) {
          if (p[k] !== undefined) body[k] = p[k];
        });
        if (!body.authorization) throw fail(UI.errPayment);
      } else {
        throw fail(UI.errPayment);
      }
      meta.reqFromPayment = false;
      var termsText = val("requirements");
      if (termsText.trim()) {
        var r = readJson(termsText);
        if (r && Array.isArray(r.accepts)) r = r.accepts[0];
        if (!r || typeof r !== "object" || Array.isArray(r)) throw fail(UI.errTerms);
        body.requirements = r;
      } else if (p && typeof p === "object" && p.accepted && typeof p.accepted === "object") {
        body.requirements = p.accepted;
        meta.reqFromPayment = true;
      }
      return body;
    },
    "mcp-diff": function () {
      return { old: toolList("old", L.before), new: toolList("new", L.after) };
    },
    "warden-scan": function () {
      return { tools: toolList("tools") };
    },
    "tool-list-cost": function () {
      // A pasted list wins; otherwise the server is looked up in HISTOR.
      if (val("tools").trim()) return { tools: toolList("tools") };
      var q = val("server").trim();
      if (!q) throw fail(UI.errEmpty);
      if (/^http:\/\//i.test(q)) q = q.replace(/^http:/i, "https:");
      // A host name without a scheme is an endpoint; registry names read the other way round.
      if (!/^[a-z]+:/i.test(q) && /^[^/@]+\.[a-z]{2,}(\/|$)/i.test(q) && !/^(io|com|dev|ai|net|org|app|co|me|sh|xyz)\./i.test(q)) q = "https://" + q;
      return { server: q };
    },
    "histor-check": function () {
      var q = val("query").trim();
      if (!q) throw fail(UI.errEmpty);
      if (/^https?:\/\//i.test(q)) return { endpoint: q.replace(/^http:/i, "https:") };
      var head = q.split("/")[0];
      // Registry names are reverse-DNS (io.github.owner/server); a host name reads the other way.
      if (/^(io|com|dev|ai|net|org|app|co|me|sh|xyz)\./i.test(head) || head.indexOf(".") < 0) return { name: q };
      return { endpoint: "https://" + q };
    },
  };

  // ── drawing answers ──────────────────────────────────────────────────────────────────────
  var LOCALE = { zh: "zh-Hans" }[D.lang] || D.lang;
  function when(v) {
    var d = typeof v === "number" ? new Date(v * 1000) : new Date(v);
    if (isNaN(d.getTime())) return String(v);
    try { return new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" }).format(d); }
    catch (e) { return d.toISOString(); }
  }
  function sev(s) {
    var key = String(s || "info").toLowerCase();
    return h("span", { class: "sev sev-" + key, text: (UI.severity && UI.severity[key]) || key });
  }
  function verdictHead(kind, label, noteText) {
    return h("div", { class: "verdict verdict-" + kind },
      h("span", { class: "verdict-badge", text: label }),
      noteText ? h("p", { class: "verdict-note", text: noteText }) : null);
  }
  function section(title) {
    var s = h("div", { class: "r-section" }, title ? h("h3", { text: title }) : null);
    for (var i = 1; i < arguments.length; i++) add(s, arguments[i]);
    return s;
  }
  function kv(rows) {
    var dl = h("dl", { class: "kv" });
    rows.forEach(function (r) {
      if (r[1] === null || r[1] === undefined || r[1] === "") return;
      dl.appendChild(h("dt", { text: r[0] }));
      dl.appendChild(h("dd", { class: r[2] ? "mono" : null }, r[1]));
    });
    return dl;
  }
  function code(text) { return h("code", { text: String(text) }); }
  function rawBlock(body) {
    var pre = h("pre", { class: "raw" }, h("code", { text: JSON.stringify(body, null, 2) }));
    var det = h("details", { class: "raw-wrap" }, h("summary", { text: UI.raw }));
    var wrap = h("div", { class: "pre-wrap" }, pre, copyButton(function () { return JSON.stringify(body, null, 2); }, UI));
    det.appendChild(wrap);
    return det;
  }
  function signatureBlock(key, value) {
    if (!key && !value) return null;
    return h("p", { class: "signed" }, h("span", { class: "pill live", text: UI.signed }), " ",
      UI.signedBy, " ", code(key || "—"));
  }

  function drawX402(body) {
    var r = body.result || {};
    var out = [verdictHead(r.verdict === "valid" ? "good" : "bad",
      (L.verdict && L.verdict[r.verdict]) || r.verdict, L.verdictNote && L.verdictNote[r.verdict])];
    if (meta.reqFromPayment) out.push(h("p", { class: "muted small", text: L.reqFromPayment }));
    if (r.diagnosis) {
      var sf = r.diagnosis.signed_for || {};
      out.push(h("div", { class: "callout" },
        h("h3", { text: L.diagnosis }),
        h("p", { text: r.diagnosis.explains }),
        kv([[L.signedFor, [sf.primary_type, "name '" + sf.name + "'", "version '" + sf.version + "'", "chain " + sf.chainId].join(" · "), true],
            ["verifyingContract", sf.verifyingContract, true]])));
    }
    var list = h("ul", { class: "check-list" });
    (r.checks || []).forEach(function (c) {
      var state = c.ok === true ? "pass" : c.ok === false ? "fail" : "unknown";
      list.appendChild(h("li", { class: "check-" + state },
        h("span", { class: "mark", "aria-hidden": "true", text: state === "pass" ? "✓" : state === "fail" ? "✕" : "–" }),
        h("span", { class: "sr-only", text: L.state[state] }),
        h("strong", { text: (L.checks && L.checks[c.check]) || c.check }),
        h("span", { class: "detail", text: c.detail })));
    });
    out.push(section(null, list));
    var a = r.authorization || {}, d = r.domain || {};
    out.push(section(L.facts, kv([
      [L.from, a.from, true], [L.to, a.to, true],
      [L.value, r.value_usdc ? r.value_usdc + " USDC (" + a.value + ")" : a.value, true],
      [L.signer, r.signer, true],
      [L.validAfter, a.validAfter ? when(a.validAfter) + " (" + a.validAfter + ")" : "0", true],
      [L.validBefore, a.validBefore ? when(a.validBefore) + " (" + a.validBefore + ")" : null, true],
      [L.nonce, a.nonce, true],
      [L.token, r.token, false],
      [L.domain, [d.name, d.version, d.chainId].join(" · ") + (d.verifyingContract ? " · " + d.verifyingContract : ""), true],
      [L.digest, r.digest, true],
    ])));
    if (r.not_checked && r.not_checked.length) {
      out.push(section(L.notChecked, h("ul", { class: "plain" }, r.not_checked.map(function (n) { return h("li", { text: n }); }))));
    }
    out.push(signatureBlock(body.provider_pubkey, body.signature));
    return out;
  }

  function diffText(ops) {
    var p = h("p", { class: "diff" });
    (ops || []).forEach(function (op) {
      var text = String(op[1]);
      if (op[0] === "=") {
        if (text.length > 260) text = text.slice(0, 110) + " … " + text.slice(-110);
        p.appendChild(document.createTextNode(text));
      } else {
        p.appendChild(h(op[0] === "+" ? "ins" : "del", { text: text }));
      }
    });
    return p;
  }
  function pathTable(rows) {
    var t = h("table", { class: "paths" });
    var tb = h("tbody");
    rows.forEach(function (r) {
      tb.appendChild(h("tr", null,
        h("td", { class: "mono", text: r.path }),
        h("td", null, r.old !== undefined ? h("del", { text: String(r.old) }) : null),
        h("td", null, r.new !== undefined ? h("ins", { text: String(r.new) }) : (r.note ? r.note : null))));
    });
    t.appendChild(tb);
    return h("div", { class: "table-wrap" }, t);
  }
  var DIFF_KIND = { unchanged: "good", changed: "info", review: "warn", suspicious: "bad" };
  function drawDiff(body) {
    var r = body.result || {};
    var s = r.summary || {};
    var out = [verdictHead(DIFF_KIND[r.verdict] || "info", (L.verdict && L.verdict[r.verdict]) || r.verdict,
      L.verdictNote && L.verdictNote[r.verdict])];
    var stats = h("div", { class: "stat-row" });
    [["added", (s.added || []).length], ["removed", (s.removed || []).length],
     ["modified", (s.modified || []).length], ["unchanged", s.unchanged || 0]].forEach(function (x) {
      stats.appendChild(h("div", { class: "mini-stat" }, h("b", { text: String(x[1]) }), h("span", { text: L.summary[x[0]] })));
    });
    out.push(stats);
    if ((s.added || []).length) out.push(h("p", { class: "names" }, "+ ", s.added.map(function (n, i) { return [i ? ", " : "", code(n)]; })));
    if ((s.removed || []).length) out.push(h("p", { class: "names" }, "− ", s.removed.map(function (n, i) { return [i ? ", " : "", code(n)]; })));
    var sig = r.signals || [];
    out.push(section(L.signals, sig.length ? h("ul", { class: "signal-list" }, sig.map(function (x) {
      return h("li", null, sev(x.severity), " ",
        h("strong", { text: (L.kinds && L.kinds[x.kind]) || x.kind }),
        x.tool ? [" · ", code(x.tool)] : null,
        x.where ? h("span", { class: "muted", text: " · " + x.where }) : null,
        x.evidence ? h("div", { class: "evidence" }, code(x.evidence)) : null);
    })) : h("p", { class: "muted", text: L.noSignals })));
    (r.changes || []).forEach(function (c, i) {
      var block = h("div", { class: "change" }, h("h4", null, code(c.tool)));
      if (c.description) block.appendChild(h("div", null, h("h5", { text: L.description }), diffText(c.description)));
      if (c.title) block.appendChild(h("div", null, h("h5", { text: L.title }),
        h("p", { class: "diff" }, h("del", { text: String(c.title.old || "") }), " ", h("ins", { text: String(c.title.new || "") }))));
      ["inputSchema", "outputSchema"].forEach(function (k) {
        if (c[k] && c[k].length) block.appendChild(h("div", null, h("h5", { text: L[k] }), pathTable(c[k])));
      });
      if (c.annotations) {
        var rows = Object.keys(c.annotations).map(function (k) {
          return { path: k, old: JSON.stringify(c.annotations[k].old), new: JSON.stringify(c.annotations[k].new) };
        });
        block.appendChild(h("div", null, h("h5", { text: L.annotations }), pathTable(rows)));
      }
      if (i === 0) out.push(h("h3", { class: "r-title", text: L.changes }));
      out.push(block);
    });
    if ((r.new_addresses || []).length) {
      out.push(section(L.newAddresses, h("p", { class: "names" }, r.new_addresses.map(function (a, i) {
        return [i ? ", " : "", code(a.address), h("span", { class: "muted", text: " " + a.kind })];
      }))));
    }
    if (r.digests) out.push(section(L.digests, kv([[L.before, r.digests.old, true], [L.after, r.digests.new, true]])));
    out.push(signatureBlock(body.provider_pubkey, body.signature));
    return out;
  }

  function drawWarden(body) {
    var v = body.verdict || {};
    var out = [verdictHead(v.allow ? "good" : "bad", v.allow ? L.verdict.allow : L.verdict.block,
      v.allow ? L.verdictNote.allow : L.verdictNote.block)];
    if (body.engine) {
      out.push(h("p", { class: "muted small" }, L.engine + ": ", code(body.engine.package),
        body.engine.ruleset ? [" · " + L.ruleset + " v", String(body.engine.ruleset.version)] : null));
    }
    var lists = h("div", { class: "split-lists" });
    [["blocked", v.blockedTools, "bad"], ["allowed", v.allowedTools, "good"]].forEach(function (x) {
      if (!x[1] || !x[1].length) return;
      lists.appendChild(h("div", null, h("h3", { text: L[x[0]] }),
        h("p", { class: "names" }, x[1].map(function (n) { return h("span", { class: "tool-chip tool-" + x[2], text: n }); }))));
    });
    out.push(lists);
    var findings = v.findings || [];
    if (!findings.length) {
      out.push(section(L.findings, h("p", { class: "muted", text: L.noFindings })));
    } else {
      var byTool = {};
      var order = [];
      findings.forEach(function (f) {
        var k = f.tool || "";
        if (!byTool[k]) { byTool[k] = []; order.push(k); }
        byTool[k].push(f);
      });
      var wrap = section(L.findings);
      order.forEach(function (k) {
        wrap.appendChild(h("h4", null, k ? code(k) : L.server));
        wrap.appendChild(h("ul", { class: "signal-list" }, byTool[k].map(function (f) {
          return h("li", null, sev(f.severity), f.advisory ? h("span", { class: "tag-adv", text: UI.advisory }) : null, " ",
            h("strong", { class: "mono", text: f.code }), h("div", { class: "evidence", text: f.message }));
        })));
      });
      out.push(wrap);
    }
    if (body.scope) out.push(h("p", { class: "muted small", text: body.scope }));
    return out;
  }

  var HISTOR_KIND = { "no-digest": "info", "not-listed": "warn", "not-observed": "warn" };
  function drawHistor(body) {
    var c = body.check || {};
    var state = c.match || "";
    var out = [verdictHead(HISTOR_KIND[state] || "info", (L.state && L.state[state]) || state,
      (L.stateNote && L.stateNote[state]) || c.note)];
    var tgt = c.target;
    if (tgt) {
      var page = typeof tgt.page === "string" && /^https:\/\/histor\.modelmarket\.dev\//.test(tgt.page) ? tgt.page : null;
      out.push(section(L.server, kv([
        ["name", tgt.name, true], ["endpoint", tgt.endpoint, true], ["status", tgt.lastStatus, true],
        [L.page, page ? h("a", { href: page, rel: "noopener", target: "_blank", text: page }) : null, false],
      ])));
    }
    var o = c.observed;
    if (o) {
      var stats = h("div", { class: "stat-row" });
      [[o.toolCount, L.tools], [o.observations, L.observations], [o.changes, L.changes]].forEach(function (x) {
        if (x[0] === undefined) return;
        stats.appendChild(h("div", { class: "mini-stat" }, h("b", { text: String(x[0]) }), h("span", { text: x[1] })));
      });
      out.push(stats);
      out.push(kv([[L.firstPinned, o.firstPinned ? when(o.firstPinned) : null], [L.unchangedSince, o.unchangedSince ? when(o.unchangedSince) : null],
                   [L.lastObserved, o.lastObserved ? when(o.lastObserved) : null]]));
    }
    var ps = c.patternScan;
    if (ps && ps.status === "scanned") {
      var m = ps.matches || [];
      out.push(section(L.scan + " · " + (ps.block || 0) + " " + L.block + " · " + (ps.advise || 0) + " " + L.advise,
        m.length ? h("ul", { class: "signal-list" }, m.map(function (x) {
          return h("li", null, sev(x.severity), " ", h("strong", { class: "mono", text: x.code }),
            x.tool ? [" · ", code(x.tool)] : null, x.where ? h("span", { class: "muted", text: " · " + x.where }) : null,
            x.span ? h("div", { class: "evidence" }, code(x.span)) : null);
        })) : h("p", { class: "muted", text: L.noMatches })));
    }
    if (c.note && state === "no-digest") out.push(h("p", { class: "muted small", text: c.note }));
    out.push(kv([[L.issuer, c.issuer, true],
                 [L.log, c.log && c.log.treeSize ? c.log.treeSize.toLocaleString(LOCALE) + " " + L.entries : null, false]]));
    if (c.signature) out.push(signatureBlock(c.signature.verificationMethod, c.signature.value));
    return out;
  }

  function num(n) { return Number(n).toLocaleString(LOCALE); }
  function pct(x) { return (Math.round(x * 1000) / 10).toLocaleString(LOCALE) + "%"; }
  function usd(x) { return "$" + Number(x).toLocaleString(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function costKind(share) { return share <= 0.5 ? "good" : share <= 0.9 ? "info" : share <= 0.99 ? "warn" : "bad"; }
  function badgeUrl(server) {
    return "https://img.shields.io/endpoint?url=" + encodeURIComponent(location.origin + "/tools/badge/tool-list-cost?server=" + encodeURIComponent(server));
  }
  function drawCost(body) {
    if (body.found === false) {
      var miss = [verdictHead("warn", L.notFound, body.known ? L.notObserved : L.notKnown)];
      var ls = body.server;
      if (ls) {
        var lpage = typeof ls.page === "string" && /^https:\/\/histor\.modelmarket\.dev\//.test(ls.page) ? ls.page : null;
        miss.push(section(L.server, kv([
          ["name", ls.name, true], ["endpoint", ls.endpoint, true],
          [L.lastStatus, ls.lastStatus, true],
          [L.page, lpage ? h("a", { href: lpage, rel: "noopener", target: "_blank", text: lpage }) : null, false],
        ])));
      }
      return miss;
    }
    var pk = (body.compared || {}).package || {}, rm = (body.compared || {}).remote || {};
    var out = [verdictHead(costKind(pk.share_shorter || 0), num(body.tokens) + " " + L.tokens,
      L.verdictNote.replace("{tools}", num(body.tools)))];
    var stats = h("div", { class: "stat-row" });
    [[num(body.tools), L.tools], [num(body.tokens_per_tool), L.perTool], [pct(body.context_share_200k || 0), L.context]].forEach(function (x) {
      stats.appendChild(h("div", { class: "mini-stat" }, h("b", { text: x[0] }), h("span", { text: x[1] })));
    });
    out.push(stats);
    out.push(section(L.compared, h("ul", { class: "plain" }, [
      h("li", { text: L.shorterPackages.replace("{share}", pct(pk.share_shorter || 0)).replace("{servers}", num(pk.servers || 0)) }),
      h("li", { text: L.shorterRemote.replace("{share}", pct(rm.share_shorter || 0)).replace("{servers}", num(rm.servers || 0)) }),
      h("li", { text: L.timesMedian.replace("{times}", num(pk.times_median || 0)).replace("{median}", num(pk.median || 0)) }),
    ]), h("p", { class: "muted small", text: L.about })));
    var c = body.per_1000_requests_usd || {}, p = body.prices_per_million_usd || {};
    out.push(section(L.money, kv([
      [L.priceSmall.replace("{p}", usd(p.small)), usd(c.small), true],
      [L.priceMid.replace("{p}", usd(p.mid)), usd(c.mid), true],
      [L.priceCached.replace("{p}", usd(p.mid_cached)), usd(c.mid_cached), true],
    ])));
    if ((body.heaviest || []).length) {
      out.push(section(L.heaviest, h("ul", { class: "signal-list" }, body.heaviest.map(function (t) {
        return h("li", null, code(t.name), h("span", { class: "muted", text: " · " + num(t.tokens) + " " + L.tokens }));
      }))));
    }
    if (body.server) {
      var sv = body.server;
      var page = typeof sv.page === "string" && /^https:\/\/histor\.modelmarket\.dev\//.test(sv.page) ? sv.page : null;
      out.push(section(L.server, kv([
        ["name", sv.name, true], ["endpoint", sv.endpoint, true],
        [L.lastObserved, sv.lastObserved ? when(sv.lastObserved) : null, false],
        [L.page, page ? h("a", { href: page, rel: "noopener", target: "_blank", text: page }) : null, false],
      ])));
      var md = "![tool list](" + badgeUrl(sv.endpoint) + ")";
      var pre = h("pre", null, h("code", { text: md }));
      out.push(section(L.badge, h("p", { class: "section-note", text: L.badgeNote }),
        h("div", { class: "pre-wrap" }, pre, copyButton(function () { return md; }, UI))));
    }
    out.push(h("p", { class: "muted small", text: L.method.replace("{date}", (body.snapshot || {}).date || "") }));
    return out;
  }

  var DRAW = { "tool-list-cost": drawCost, "x402-check": drawX402, "mcp-diff": drawDiff, "warden-scan": drawWarden, "histor-check": drawHistor };

  function show(nodes, isError) {
    result.textContent = "";
    result.hidden = false;
    result.classList.toggle("is-error", Boolean(isError));
    add(result, h("h2", { class: "section-title", text: UI.result }));
    add(result, nodes);
    var top = result.getBoundingClientRect().top;
    if (top > window.innerHeight * 0.6 || top < 60) result.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    result.focus({ preventScroll: true });
  }
  function showError(message, detail) {
    show([h("div", { class: "callout callout-bad" }, h("p", { text: message }), detail ? h("p", { class: "mono small", text: detail }) : null)], true);
  }

  var busy = false;
  function run() {
    if (busy) return;
    var body;
    try { body = BUILD[TOOL](); } catch (e) {
      if (e && e.user) { showError(e.message); return; }
      throw e;
    }
    busy = true;
    runBtn.disabled = true;
    runBtn.textContent = UI.running;
    result.setAttribute("aria-busy", "true");
    fetch(D.api, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
      .then(function (res) {
        return res.json().catch(function () { return null; }).then(function (json) { return { status: res.status, json: json }; });
      })
      .then(function (r) {
        var j = r.json || {};
        if (r.status === 429) { showError(j.error === "free_capacity" ? UI.errBusy : UI.errRate); return; }
        if (r.status >= 400 || j.status === "error") { showError(UI.errRefused, j.message || j.error || String(r.status)); return; }
        if (j.status === "input_required") { showError(UI.errRefused, j.message); return; }
        var nodes = DRAW[TOOL](j);
        nodes.push(rawBlock(j));
        show(nodes, false);
      })
      .catch(function () { showError(UI.errNetwork); })
      .then(function () {
        busy = false;
        runBtn.disabled = false;
        runBtn.textContent = UI.run;
        result.removeAttribute("aria-busy");
      });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); run(); });
  form.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); }
  });
  document.getElementById("example").addEventListener("click", function () {
    var ex = D.example || {};
    var fill = function (name, value) {
      var f = field(name);
      if (f) f.value = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    };
    if (TOOL === "x402-check") { fill("payment", ex.payment); fill("requirements", ex.requirements); }
    else if (TOOL === "mcp-diff") { fill("old", ex.old); fill("new", ex.new); }
    else if (TOOL === "warden-scan") { fill("tools", ex.tools); }
    else if (TOOL === "tool-list-cost") { fill("tools", ""); fill("server", ex.server); }
    else { fill("query", ex.query); }
    note.hidden = false;
    run();
  });
  document.getElementById("clear").addEventListener("click", function () {
    Array.prototype.forEach.call(form.querySelectorAll("textarea, input"), function (f) { f.value = ""; });
    note.hidden = true;
    result.hidden = true;
    result.textContent = "";
    var first = form.querySelector("textarea, input");
    if (first) first.focus();
  });
})();
