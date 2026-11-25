(function (root) {
  "use strict";

  var identityPromise = null;

  var b64url = function (bytes) {
    var s = "";
    new Uint8Array(bytes).forEach(function (byte) { s += String.fromCharCode(byte); });
    return btoa(s).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
  };
  var hex = function (bytes) {
    return Array.from(new Uint8Array(bytes), function (byte) {
      return byte.toString(16).padStart(2, "0");
    }).join("");
  };

  function identityStore() {
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open("attested-identity", 1);
      request.onupgradeneeded = function () { request.result.createObjectStore("keys"); };
      request.onerror = function () { reject(request.error); };
      request.onsuccess = function () { resolve(request.result); };
    });
  }

  function storeIdentity(database, value) {
    return new Promise(function (resolve, reject) {
      var request = database.transaction("keys", "readwrite").objectStore("keys").put(value, "actor");
      request.onsuccess = resolve;
      request.onerror = function () { reject(request.error); };
    });
  }

  async function hardenIdentity(database, value) {
    if (!value.privateKey.extractable) return value;
    var encoded = await crypto.subtle.exportKey("pkcs8", value.privateKey);
    try {
      var privateKey = await crypto.subtle.importKey(
        "pkcs8", encoded, { name: "Ed25519" }, false, ["sign"]
      );
      var hardened = { privateKey: privateKey, publicKey: value.publicKey };
      await storeIdentity(database, hardened);
      return hardened;
    } finally {
      new Uint8Array(encoded).fill(0);
    }
  }

  async function loadIdentity() {
    var database = await identityStore();
    try {
      var existing = await new Promise(function (resolve, reject) {
        var request = database.transaction("keys").objectStore("keys").get("actor");
        request.onsuccess = function () { resolve(request.result); };
        request.onerror = function () { reject(request.error); };
      });
      if (existing) return hardenIdentity(database, existing);
      var pair = await crypto.subtle.generateKey({ name: "Ed25519" }, false, ["sign", "verify"]);
      var value = { privateKey: pair.privateKey, publicKey: pair.publicKey };
      await storeIdentity(database, value);
      return value;
    } finally {
      database.close();
    }
  }

  function identity() {
    if (!identityPromise) {
      identityPromise = loadIdentity().catch(function (error) {
        identityPromise = null;
        throw error;
      });
    }
    return identityPromise;
  }

  async function target(audience, method, path, body) {
    audience = (root.ATTESTED_ACTOR_AUDIENCES || {})[audience] || audience;
    var url = new URL(path, "https://intent.invalid");
    var query = Array.from(url.searchParams.entries());
    return { audience: audience, method: method.toUpperCase(), path: decodeURIComponent(url.pathname),
      query: query, body_sha256: hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body || ""))) };
  }

  async function targetsFor(path, options) {
    var opts = options || {}, method = (opts.method || "GET").toUpperCase(), body = opts.body || "";
    var url = new URL(path, location.origin), upstream, team, memoryBody;
    if (opts.audience) return [await target(opts.audience, method, url.pathname + url.search, body)];
    if (url.pathname.startsWith("/api/v1/")) {
      return [await target("attested-saas-gateway", method, url.pathname.slice(4) + url.search, body)];
    }
    if (url.pathname.startsWith("/memory/api/")) {
      upstream = url.pathname.slice("/memory/api/".length);
      if (upstream === "search") {
        url.searchParams.set("q", url.searchParams.get("q") || "");
        url.searchParams.set("limit", url.searchParams.get("limit") || "30");
        upstream = "catalog";
      }
      return [await target("memory-market", method, "/v1/" + upstream + url.search, body)];
    }
    if (url.pathname.startsWith("/teams/api/teams")) {
      return [await target("attested-saas-gateway", method, "/v1/teams" + url.pathname.slice("/teams/api/teams".length) + url.search, body)];
    }
    if (url.pathname.startsWith("/teams/api/team-")) {
      team = url.searchParams.get("team_id");
      if (method === "POST" && url.pathname === "/teams/api/team-memories") {
        var parsed = JSON.parse(body); team = parsed.team_id;
        memoryBody = JSON.stringify({ title: parsed.title, content: parsed.content,
          tags: ["team:" + team].concat(parsed.tags || []), visibility: "shared", source_refs: parsed.source_refs || [] });
        upstream = "/v1/memories";
      } else if (url.pathname === "/teams/api/team-search") {
        upstream = "/v1/catalog?" + new URLSearchParams({q: url.searchParams.get("q") || "", limit: url.searchParams.get("limit") || "30"}).toString();
      } else {
        upstream = "/v1/memories/" + url.pathname.slice("/teams/api/team-memories/".length);
      }
      if (!team) throw Error("Team intent requires team_id");
      return [await target("attested-saas-gateway", "GET", "/v1/teams/" + encodeURIComponent(team) + "/assertion", ""),
              await target("memory-market", method, upstream, memoryBody || "")];
    }
    throw Error("No actor intent mapping for this product route");
  }

  async function actorId() {
    var keys = await identity();
    var pub = await crypto.subtle.exportKey("raw", keys.publicKey);
    return "did:actor:" + hex(await crypto.subtle.digest("SHA-256", pub));
  }

  // Sign explicit end-to-end request targets. Proxies cannot broaden these grants.
  async function headers(path, options) {
    if (!path) throw Error("Actor proof v2 requires a destination request");
    var keys = await identity();
    var pub = await crypto.subtle.exportKey("raw", keys.publicKey);
    var actor = "did:actor:" + hex(await crypto.subtle.digest("SHA-256", pub));
    var timestamp = String(Math.floor(Date.now() / 1000));
    var nonce = b64url(crypto.getRandomValues(new Uint8Array(18)));
    var intent = b64url(new TextEncoder().encode(JSON.stringify(await targetsFor(path, options))));
    var message = new TextEncoder().encode("attested-actor/v2\n" + actor + "\n" + timestamp + "\n" + nonce + "\n" + intent);
    var signature = await crypto.subtle.sign("Ed25519", keys.privateKey, message);
    return { "X-Actor-Version": "2", "X-Actor-Intent": intent,
      "X-Actor-ID": actor, "X-Actor-Public-Key": b64url(pub),
      "X-Actor-Timestamp": timestamp, "X-Actor-Nonce": nonce, "X-Actor-Signature": b64url(signature) };
  }

  root.AttestedActor = { headers: headers, identity: identity, actorId: actorId };
})(window);
