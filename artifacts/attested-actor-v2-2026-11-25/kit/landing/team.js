(function () {
  "use strict";

  var KEY = "attested_team_key";
  var TEAM_ID = "attested_team_id";
  var TEAM_NAME = "attested_team_name";
  var lastWrite = null;
  var $ = function (selector) { return document.querySelector(selector); };
  var t = function (key) { return window.AttestedLocale ? AttestedLocale.text(key) : key; };

  function setStatus(node, message, error) {
    if (!node) return;
    node.textContent = message || "";
    node.classList.toggle("is-error", Boolean(error));
    node.classList.toggle("is-ok", !error && Boolean(message));
  }

  function explain(response, value) {
    if (response.status === 401) return t("teamErr401");
    if (response.status === 402) return t("teamErr402");
    if (response.status === 403) return t("teamErr403");
    if (response.status === 429) return t("memoryErr429");
    var detail = value && value.detail;
    if (Array.isArray(detail)) detail = detail.map(function (item) { return item.msg || String(item); }).join(" ");
    return (typeof detail === "string" && detail) || t("teamError");
  }

  function teamKey() { return (sessionStorage.getItem(KEY) || "").trim(); }
  function teamId() { return (sessionStorage.getItem(TEAM_ID) || "").trim(); }

  async function signedHeaders(path, options) {
    var headers = await AttestedActor.headers(path, options);
    headers["X-SaaS-Key"] = teamKey();
    if (options.body) headers["content-type"] = "application/json";
    return headers;
  }

  async function request(path, options) {
    var opts = options || {};
    opts.redirect = "error";
    opts.headers = await signedHeaders("/teams" + path, opts);
    var response = await fetch("/teams" + path, opts);
    var value = await response.json().catch(function () { return {}; });
    if (!response.ok) throw Error(explain(response, value));
    return value;
  }

  function phase(name) {
    ["access", "create", "active"].forEach(function (item) {
      var pane = $("#team-" + item + "-pane");
      if (pane) pane.hidden = item !== name;
      var step = document.querySelector('[data-team-step="' + item + '"]');
      if (step) {
        var order = { access: 0, create: 1, active: 2 };
        step.classList.toggle("is-active", item === name);
        step.classList.toggle("is-complete", order[item] < order[name]);
      }
    });
    var state = $(".team-session-state");
    var label = $("#team-state-label");
    if (state) state.classList.toggle("is-ready", name !== "access");
    if (label) label.textContent = t(name === "access" ? "teamStateLocked" : name === "create" ? "teamStateNamespace" : "teamStateReady");
    if (name === "active") hydrateTeam();
  }

  function hydrateTeam() {
    $("#team-active-id").textContent = teamId();
    $("#team-active-name").textContent = sessionStorage.getItem(TEAM_NAME) || "Team";
  }

  async function showActor() {
    try {
      $("#team-actor-id").textContent = await AttestedActor.actorId();
    } catch (_) {
      $("#team-actor-id").textContent = "actor: unavailable";
    }
  }

  function openTrial() {
    var dialog = $("#team-trial-dialog");
    setStatus($("#team-trial-status"), "", false);
    $("#team-trial-keybox").hidden = true;
    $("#claim-team-trial").disabled = false;
    if (dialog && dialog.showModal) dialog.showModal();
  }

  async function claimTrial() {
    var status = $("#team-trial-status");
    var button = $("#claim-team-trial");
    button.disabled = true;
    setStatus(status, t("statusCreatingProof"), false);
    try {
      var headers = await AttestedActor.headers("/api/v1/trials", {method: "POST", body: JSON.stringify({product: "team"})});
      headers["content-type"] = "application/json";
      var response = await fetch("/api/v1/trials", { method: "POST", redirect: "error", headers: headers, body: JSON.stringify({ product: "team" }) });
      var value = await response.json().catch(function () { return {}; });
      if (!response.ok) throw Error(explain(response, value));
      sessionStorage.setItem(KEY, value.api_key);
      $("#team-trial-key").textContent = value.api_key;
      $("#team-trial-keybox").hidden = false;
      setStatus(status, t(value.recovered ? "statusActiveRecovered" : "statusActivated") + " " + t("statusAccessExpires") + " " + (value.expires_at || ""), false);
      phase("create");
    } catch (error) {
      setStatus(status, error.message, true);
      button.disabled = false;
    }
  }

  function connectKey() {
    var input = $("#team-key");
    var key = input.value.trim();
    if (!key.startsWith("ask_") || key.length < 40) {
      setStatus($("#team-access-status"), t("teamKeyInvalid"), true);
      return;
    }
    sessionStorage.setItem(KEY, key);
    input.value = "";
    setStatus($("#team-access-status"), t("teamKeyConnected"), false);
    phase("create");
  }

  async function createTeam(event) {
    event.preventDefault();
    var status = $("#team-create-status");
    var button = $("#create-team");
    var name = $("#team-name").value.trim();
    if (name.length < 2) return;
    button.disabled = true;
    setStatus(status, t("teamCreating"), false);
    try {
      var value = await request("/api/teams", { method: "POST", body: JSON.stringify({ name: name }) });
      sessionStorage.setItem(TEAM_ID, value.team_id);
      sessionStorage.setItem(TEAM_NAME, value.name || name);
      setStatus(status, t("teamCreated"), false);
      phase("active");
    } catch (error) {
      setStatus(status, error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  async function writeMemory(event) {
    event.preventDefault();
    var status = $("#team-write-status");
    var button = $("#write-team-memory");
    var title = $("#team-memory-title").value.trim();
    var content = $("#team-memory-content").value.trim();
    var tags = $("#team-memory-tags").value.split(",").map(function (tag) { return tag.trim(); }).filter(Boolean);
    button.disabled = true;
    setStatus(status, t("teamWriting"), false);
    try {
      lastWrite = await request("/api/team-memories", { method: "POST", body: JSON.stringify({ team_id: teamId(), title: title, content: content, tags: tags, source_refs: [] }) });
      var provenance = lastWrite.provenance || {};
      $("#team-receipt-memory").textContent = lastWrite.id || "—";
      $("#team-receipt-hash").textContent = lastWrite.content_hash || "—";
      $("#team-receipt-id").textContent = provenance.receipt_id || "—";
      $("#team-receipt").hidden = false;
      setStatus(status, t("teamWritten"), false);
    } catch (error) {
      setStatus(status, error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  async function searchTeam() {
    var status = $("#team-search-status");
    var list = $("#team-search-results");
    list.innerHTML = "";
    setStatus(status, t("teamSearching"), false);
    try {
      var value = await request("/api/team-search?team_id=" + encodeURIComponent(teamId()) + "&q=" + encodeURIComponent($("#team-search-q").value.trim()));
      var items = value.items || [];
      items.forEach(function (item) {
        var row = document.createElement("li");
        row.innerHTML = "<strong></strong><small></small>";
        row.querySelector("strong").textContent = item.title || item.id;
        row.querySelector("small").textContent = [item.id, item.content_hash].filter(Boolean).join(" · ");
        list.appendChild(row);
      });
      setStatus(status, items.length ? "" : t("teamEmptySearch"), false);
    } catch (error) {
      setStatus(status, error.message, true);
    }
  }

  async function inviteMember(event) {
    event.preventDefault();
    var status = $("#team-invite-status");
    var actor = $("#team-member-id").value.trim();
    if (!/^did:actor:[0-9a-f]{64}$/.test(actor)) {
      setStatus(status, t("teamActorInvalid"), true);
      return;
    }
    setStatus(status, t("teamInviting"), false);
    try {
      await request("/api/teams/" + encodeURIComponent(teamId()) + "/members", { method: "POST", body: JSON.stringify({ actor_id: actor, role: $("#team-member-role").value }) });
      $("#team-member-id").value = "";
      setStatus(status, t("teamInvited"), false);
    } catch (error) {
      setStatus(status, error.message, true);
    }
  }

  function copy(value, button, restore) {
    if (!value) return;
    var copied;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      copied = navigator.clipboard.writeText(value);
    } else {
      var area = document.createElement("textarea");
      area.value = value;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      copied = document.execCommand("copy") ? Promise.resolve() : Promise.reject(Error("copy failed"));
      area.remove();
    }
    copied.then(function () {
      button.textContent = t("copied");
      setTimeout(function () { button.textContent = t(restore); }, 1200);
    }).catch(function () { setStatus($("#team-access-status"), value, false); });
  }

  function disconnect() {
    sessionStorage.removeItem(KEY);
    sessionStorage.removeItem(TEAM_ID);
    sessionStorage.removeItem(TEAM_NAME);
    $("#team-receipt").hidden = true;
    phase("access");
    setStatus($("#team-access-status"), t("teamDisconnected"), false);
  }

  $("#open-team-trial").addEventListener("click", openTrial);
  $("#open-team-trial-inline").addEventListener("click", openTrial);
  $("#claim-team-trial").addEventListener("click", claimTrial);
  $("#connect-team-key").addEventListener("click", connectKey);
  $("#team-key").addEventListener("keydown", function (event) { if (event.key === "Enter") { event.preventDefault(); connectKey(); } });
  $("#continue-team-studio").addEventListener("click", function () { $("#team-trial-dialog").close(); $("#team-studio").scrollIntoView({ behavior: "smooth", block: "start" }); phase("create"); });
  $("#copy-team-key").addEventListener("click", function () { copy($("#team-trial-key").textContent, this, "copyKey"); });
  $("#team-create-form").addEventListener("submit", createTeam);
  $("#team-write-form").addEventListener("submit", writeMemory);
  $("#team-search").addEventListener("click", searchTeam);
  $("#team-search-q").addEventListener("keydown", function (event) { if (event.key === "Enter") { event.preventDefault(); searchTeam(); } });
  $("#team-invite-form").addEventListener("submit", inviteMember);
  $("#copy-team-id").addEventListener("click", function () { copy(teamId(), this, "teamCopyId"); });
  $("#disconnect-team").addEventListener("click", disconnect);
  document.querySelectorAll("[data-close]").forEach(function (button) { button.addEventListener("click", function () { var dialog = document.getElementById(button.dataset.close); if (dialog && dialog.close) dialog.close(); }); });
  document.addEventListener("attested:lang", function () { phase(teamId() ? "active" : teamKey() ? "create" : "access"); });

  showActor();
  phase(teamId() && teamKey() ? "active" : teamKey() ? "create" : "access");
  if (new URLSearchParams(location.search).get("trial")) openTrial();
})();
