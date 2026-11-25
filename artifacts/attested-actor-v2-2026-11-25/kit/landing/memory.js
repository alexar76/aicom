(function () {
  "use strict";

  var KEY = "attested_saas_key";
  var EXPIRES = "attested_personal_expires";
  var lastWrite = null;
  var $ = function (selector) { return document.querySelector(selector); };
  var t = function (key) {
    return window.AttestedLocale ? AttestedLocale.text(key) : key;
  };

  function track(_name) {
    /* first-party only; Google tags removed */
  }

  function saasKey() {
    return (sessionStorage.getItem(KEY) || "").trim();
  }

  function setKey(value) {
    sessionStorage.setItem(KEY, value);
  }

  function detailText(value) {
    if (!value) return "";
    var detail = value.detail;
    if (Array.isArray(detail)) {
      return detail.map(function (item) {
        return item && item.msg ? item.msg : String(item);
      }).join(" ");
    }
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") return JSON.stringify(detail);
    return value.message || "";
  }

  function explainError(response, value) {
    var status = response && response.status;
    if (status === 401) return t("memoryErr401");
    if (status === 402) return t("memoryErr402");
    if (status === 403) return t("memoryErr403");
    if (status === 429) {
      var retry = response.headers && response.headers.get("Retry-After");
      return t("memoryErr429") + (retry ? " Retry-After: " + retry + "s." : "");
    }
    var expired = /invalid or expired/i.test(detailText(value));
    if (expired) return t("memoryErr402");
    return detailText(value) || t("memoryErrGeneric");
  }

  function setStatus(node, message, kind) {
    if (!node) return;
    node.textContent = message || "";
    node.classList.toggle("is-error", kind === "error");
    node.classList.toggle("is-ok", kind === "ok");
  }

  function unlockStudio() {
    var key = saasKey();
    var ready = key.indexOf("ask_") === 0;
    var locked = $("#studio-locked");
    var form = $("#studio-form");
    var connected = $("#studio-connected");
    if (locked) locked.hidden = ready;
    if (form) form.hidden = !ready;
    if (connected) {
      connected.hidden = !ready;
      if (ready) connected.textContent = t("memoryConnected");
    }
    if ($("#studio")) $("#studio").classList.toggle("is-ready", ready);
    refreshUpgrade();
    return ready;
  }

  function scrollStudio() {
    var studio = $("#studio");
    if (studio && studio.scrollIntoView) studio.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function applyPlaceholders() {
    var title = $("#memory-title");
    var content = $("#memory-content");
    var tags = $("#memory-tags");
    var search = $("#search-q");
    if (title) title.placeholder = t("memoryTitlePh");
    if (content) content.placeholder = t("memoryContentPh");
    if (tags) tags.placeholder = t("memoryTagsPh");
    if (search) search.placeholder = t("memorySearchPh");
  }

  function citePack(unit) {
    var prov = unit.provenance || {};
    var truth = unit.truth || {};
    return [
      "Attested Memory Unit",
      "id: " + (unit.id || ""),
      "title: " + (unit.title || ""),
      "content_hash: " + (unit.content_hash || ""),
      "receipt: " + (prov.receipt_id || ""),
      "lineage_root: " + (prov.lineage_root || ""),
      "truth: " + (truth.status || ""),
      "provenance: " + (prov.status || ""),
      "url: https://attestedmemory.net/memory"
    ].join("\n");
  }

  function showReceipt(unit) {
    lastWrite = unit;
    var panel = $("#receipt");
    var prov = unit.provenance || {};
    var truth = unit.truth || {};
    $("#receipt-hash").textContent = unit.content_hash || "—";
    $("#receipt-id").textContent = prov.receipt_id || "—";
    $("#receipt-mem").textContent = unit.id || "—";
    $("#receipt-lineage").textContent = prov.lineage_root || "—";
    $("#receipt-truth").textContent = truth.status || "—";
    $("#receipt-prov").textContent = prov.status || "—";
    $("#receipt-created").textContent = unit.created_at || "—";
    if (panel) {
      panel.hidden = false;
      panel.classList.add("is-live");
    }
    refreshUpgrade();
    if (panel && panel.scrollIntoView) panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function refreshUpgrade() {
    var box = $("#upgrade");
    var body = $("#upgrade-body");
    if (!box) return;
    box.hidden = !lastWrite;
    if (!body) return;
    var expires = sessionStorage.getItem(EXPIRES) || "";
    var prefix = expires ? t("memoryTrialEnds") + " " + expires + " · " : "";
    body.textContent = prefix + t("memoryUpgradeBody");
  }

  async function signedHeaders(path, options, extra) {
    var headers = await AttestedActor.headers(path, options);
    var key = saasKey();
    if (key) headers["X-SaaS-Key"] = key;
    if (extra) Object.keys(extra).forEach(function (name) { headers[name] = extra[name]; });
    return headers;
  }

  function openTrial() {
    var dialog = $("#trial-dialog");
    $("#trial-status").textContent = "";
    $("#trial-keybox").hidden = true;
    $("#claim-trial").disabled = false;
    if (dialog && dialog.showModal) dialog.showModal();
  }

  async function connectFromInput() {
    var input = $("#key");
    var status = $("#status");
    var button = $("#connect-key");
    var key = (input.value || "").trim();
    if (!key.startsWith("ask_")) {
      setStatus(status, t("memoryInvalidKey"), "error");
      return false;
    }
    button.disabled = true;
    setStatus(status, t("memorySearching"), "ok");
    try {
      sessionStorage.setItem(KEY, key);
      var headers = await signedHeaders("/memory/api/search?q=");
      var response = await fetch("/memory/api/search?q=", { redirect: "error", headers: headers });
      var value = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        sessionStorage.removeItem(KEY);
        throw Error(explainError(response, value));
      }
      input.value = "";
      setStatus(status, t("memoryConnected"), "ok");
      unlockStudio();
      scrollStudio();
      return true;
    } catch (error) {
      setStatus(status, error.message, "error");
      unlockStudio();
      return false;
    } finally {
      button.disabled = false;
    }
  }

  async function claimTrial() {
    var status = $("#trial-status");
    status.textContent = t("statusCreatingProof");
    try {
      var headers = await AttestedActor.headers("/api/v1/trials", {method: "POST", body: JSON.stringify({product: "personal"})});
      headers["content-type"] = "application/json";
      var response = await fetch("/api/v1/trials", {
        method: "POST",
        redirect: "error", headers: headers,
        body: JSON.stringify({ product: "personal" })
      });
      var value = await response.json().catch(function () { return {}; });
      if (!response.ok) throw Error(explainError(response, value) || t("statusTrialFailed"));
      $("#trial-key").textContent = value.api_key;
      $("#trial-keybox").hidden = false;
      $("#claim-trial").disabled = true;
      setKey(value.api_key);
      if (value.expires_at) sessionStorage.setItem(EXPIRES, value.expires_at);
      status.textContent = t(value.recovered ? "statusActiveRecovered" : "statusActivated")
        + " " + t("statusAccessExpires") + " " + (value.expires_at || "");
      track("trial_claim");
      unlockStudio();
    } catch (error) {
      status.textContent = error.message;
    }
  }

  async function writeMemory(event) {
    event.preventDefault();
    var status = $("#write-status");
    var button = $("#write-memory");
    if (!saasKey().startsWith("ask_")) {
      setStatus(status, t("memoryInvalidKey"), "error");
      return;
    }
    var title = $("#memory-title").value.trim();
    var content = $("#memory-content").value.trim();
    var tags = $("#memory-tags").value.split(",").map(function (tag) { return tag.trim(); }).filter(Boolean);
    if (!title || !content) {
      setStatus(status, t("memoryWriteNeed"), "error");
      return;
    }
    button.disabled = true;
    setStatus(status, t("memoryWriting"), "ok");
    try {
      var headers = await signedHeaders("/memory/api/memories", {method: "POST", body: JSON.stringify({ title: title, content: content, visibility: "private", tags: tags })}, { "content-type": "application/json" });
      var response = await fetch("/memory/api/memories", {
        method: "POST",
        redirect: "error", headers: headers,
        body: JSON.stringify({ title: title, content: content, visibility: "private", tags: tags })
      });
      var value = await response.json().catch(function () { return {}; });
      if (!response.ok) throw Error(explainError(response, value));
      setStatus(status, "", "ok");
      showReceipt(value);
      track("memory_write");
    } catch (error) {
      setStatus(status, error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function runSearch() {
    var panel = $("#search-panel");
    var list = $("#search-results");
    var status = $("#search-status");
    var query = ($("#search-q").value || (lastWrite && lastWrite.title) || "").trim();
    if (panel) panel.hidden = false;
    list.innerHTML = "";
    setStatus(status, t("memorySearching"), "ok");
    try {
      var headers = await signedHeaders("/memory/api/search?q=" + encodeURIComponent(query));
      var response = await fetch("/memory/api/search?q=" + encodeURIComponent(query), { redirect: "error", headers: headers });
      var value = await response.json().catch(function () { return {}; });
      if (!response.ok) throw Error(explainError(response, value));
      var items = value.items || [];
      if (!items.length) {
        setStatus(status, t("memoryEmptySearch"), "ok");
        return;
      }
      items.forEach(function (item) {
        var li = document.createElement("li");
        var hash = item.content_hash || "";
        var receipt = item.provenance && item.provenance.receipt_id ? item.provenance.receipt_id : "";
        li.innerHTML = "<strong></strong><small></small>";
        li.querySelector("strong").textContent = item.title || item.id;
        li.querySelector("small").textContent = [item.id, hash, receipt].filter(Boolean).join(" · ");
        list.appendChild(li);
      });
      setStatus(status, "", "ok");
    } catch (error) {
      setStatus(status, error.message, "error");
    }
  }

  function copyText(value, button, restoreKey) {
    navigator.clipboard.writeText(value).then(function () {
      button.textContent = t("copied");
      setTimeout(function () { button.textContent = t(restoreKey); }, 1200);
    });
  }

  $("#open-trial").addEventListener("click", openTrial);
  $("#open-trial-locked").addEventListener("click", openTrial);
  $("#connect-key").addEventListener("click", connectFromInput);
  $("#key").addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      connectFromInput();
    }
  });
  $("#claim-trial").addEventListener("click", claimTrial);
  $("#continue-studio").addEventListener("click", function () {
    var dialog = $("#trial-dialog");
    if (dialog && dialog.close) dialog.close();
    unlockStudio();
    scrollStudio();
  });
  $("#studio-form").addEventListener("submit", writeMemory);
  $("#copy-cite").addEventListener("click", function () {
    if (!lastWrite) return;
    copyText(citePack(lastWrite), $("#copy-cite"), "memoryCopyCite");
    track("cite_copy");
  });
  $("#copy-json").addEventListener("click", function () {
    if (!lastWrite) return;
    copyText(JSON.stringify(lastWrite, null, 2), $("#copy-json"), "memoryCopyJson");
  });
  $("#write-another").addEventListener("click", function () {
    $("#memory-title").value = "";
    $("#memory-content").value = "";
    $("#memory-tags").value = "";
    scrollStudio();
    $("#memory-title").focus();
  });
  $("#search-mine").addEventListener("click", function () {
    if (lastWrite && lastWrite.title) $("#search-q").value = lastWrite.title;
    runSearch();
  });
  $("#search-run").addEventListener("click", runSearch);
  $("#upgrade-cta").addEventListener("click", function () { track("upgrade_click"); });
  document.querySelectorAll("[data-close]").forEach(function (button) {
    button.addEventListener("click", function () {
      var dialog = document.getElementById(button.dataset.close);
      if (dialog && dialog.close) dialog.close();
    });
  });
  document.querySelectorAll(".copy-key").forEach(function (button) {
    button.addEventListener("click", function () {
      var node = document.getElementById(button.dataset.target);
      copyText(node.textContent, button, "copyKey");
    });
  });
  document.addEventListener("attested:lang", function () {
    applyPlaceholders();
    unlockStudio();
    refreshUpgrade();
  });

  applyPlaceholders();
  unlockStudio();
  var trialQuery = new URLSearchParams(location.search).get("trial");
  if (trialQuery && trialQuery !== "0" && trialQuery !== "false") openTrial();
})();
