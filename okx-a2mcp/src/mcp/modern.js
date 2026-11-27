// The per-request envelope of MCP 2026-07-28 over Streamable HTTP, for a server that also keeps
// the handshake revisions. Since 2026-07-28 there is no `initialize`: every request states its
// protocol version and the client's capabilities in `params._meta` and mirrors the version, the
// method and (for a call) the name into HTTP headers. This file holds what does not depend on the
// tools a server offers: which era a request belongs to, the validation the specification asks of
// a server before it acts, and the fields every modern result carries.
//
// References (revision 2026-07-28): Versioning and Compatibility; Streamable HTTP, "Request
// Metadata" and "Server Validation"; Overview, "Error Codes" and "_meta"; Discovery; Caching.
// The Python twin is aimarket-hub/aimarket_hub/mcp_modern.py; keep the two in step.

export const MODERN_VERSIONS = ["2026-07-28"];
const FIRST_MODERN_VERSION = "2026-07-28";

export const META_PROTOCOL = "io.modelcontextprotocol/protocolVersion";
export const META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo";
export const META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities";
export const META_SERVER_INFO = "io.modelcontextprotocol/serverInfo";

export const HEADER_MISMATCH = -32020;
export const UNSUPPORTED_PROTOCOL_VERSION = -32022;

const CACHEABLE = new Set(["server/discover", "tools/list", "prompts/list", "resources/list", "resources/templates/list", "resources/read"]);
const NAMED = { "tools/call": "name", "prompts/get": "name", "resources/read": "uri" };
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const SENTINEL = /^=\?base64\?([\s\S]*)\?=$/;
const BASE64 = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;

/** A request the envelope rules reject before the server does anything with it. */
export class Refusal extends Error {
  constructor(status, code, message, data) {
    super(message);
    this.status = status; this.code = code; this.data = data;
  }
  body(id) {
    const error = { code: this.code, message: this.message };
    if (this.data !== undefined) error.data = this.data;
    return { jsonrpc: "2.0", id: id ?? null, error };
  }
}

const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
/** A caller-supplied value as it may appear in an error message: short and printable. */
const shown = (value, limit = 60) => String(typeof value === "string" ? value : JSON.stringify(value) ?? "undefined")
  .slice(0, limit).replace(/[^ -~]/g, "?");

/**
 * Whether one JSON-RPC message is written for a per-request-metadata revision. The body decides;
 * the header alone decides only when it names a revision of the modern era, so a handshake client
 * that sends `MCP-Protocol-Version: 2025-06-18` after `initialize` stays on the handshake path.
 */
export function isModern(message, header) {
  if (!isObject(message)) return false;
  const meta = isObject(message.params) ? message.params._meta : undefined;
  if (isObject(meta) && (META_PROTOCOL in meta || META_CAPABILITIES in meta)) return true;
  if (message.method === "server/discover") return true;
  const version = String(header("mcp-protocol-version") ?? "").trim();
  return DATE.test(version) && version >= FIRST_MODERN_VERSION;
}

/** A `Mcp-Name` header value as the body would spell it: plain ASCII, or `=?base64?…?=`. */
export function decodeHeaderValue(raw) {
  const match = SENTINEL.exec(raw);
  if (!match) return raw;
  if (!BASE64.test(match[1])) throw new Error("not Base64");
  return new TextDecoder("utf-8", { fatal: true }).decode(Buffer.from(match[1], "base64"));
}

const mismatch = (message) => new Refusal(400, HEADER_MISMATCH, `Header mismatch: ${message}`);

/**
 * Validate one modern request and return its `_meta`. `header(name)` reads a request header
 * case-insensitively; `supported` lists every revision the server speaks in either era.
 */
export function check(message, header, supported) {
  const { method } = message;
  if (typeof method !== "string") throw new Refusal(400, -32600, "Invalid request: method must be a string");
  const params = message.params ?? {};
  if (!isObject(params)) throw new Refusal(400, -32602, "Invalid params: params must be an object");
  const meta = params._meta ?? {};
  if (!isObject(meta)) throw new Refusal(400, -32602, "Invalid params: _meta must be an object");

  const sent = String(header("mcp-protocol-version") ?? "").trim();
  const body = meta[META_PROTOCOL];
  if (!sent) throw mismatch("required header MCP-Protocol-Version is missing");
  if (typeof body !== "string") {
    throw mismatch(`MCP-Protocol-Version header value '${shown(sent)}' has no matching ${META_PROTOCOL} in the request body`);
  }
  if (sent !== body) throw mismatch(`MCP-Protocol-Version header value '${shown(sent)}' does not match body value '${shown(body)}'`);
  if (!MODERN_VERSIONS.includes(body)) {
    throw new Refusal(400, UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version", { supported: [...supported], requested: shown(body, 40) });
  }

  const sentMethod = header("mcp-method");
  if (sentMethod === undefined || sentMethod === null) throw mismatch("required header Mcp-Method is missing");
  if (String(sentMethod).trim() !== method) {
    throw mismatch(`Mcp-Method header value '${shown(String(sentMethod))}' does not match body value '${shown(method)}'`);
  }

  const field = NAMED[method];
  if (field) {
    const named = params[field];
    const sentName = header("mcp-name");
    if (sentName === undefined || sentName === null) throw mismatch("required header Mcp-Name is missing");
    let decoded;
    try { decoded = decodeHeaderValue(String(sentName).trim()); } catch { throw mismatch("Mcp-Name header value is not valid Base64 of UTF-8 text"); }
    if (typeof named !== "string" || decoded !== named) {
      throw mismatch(`Mcp-Name header value '${shown(decoded)}' does not match body value '${shown(named)}'`);
    }
  }

  if (!isObject(meta[META_CAPABILITIES])) {
    throw new Refusal(400, -32602, `Invalid params: ${META_CAPABILITIES} is required and must be an object`);
  }
  return meta;
}

/** Add what every modern result carries; for the cacheable methods also `ttlMs` and `cacheScope`. */
export function finish(result, method, { name, version, ttlMs = 0, cacheScope = "private" }) {
  result.resultType = "complete";
  result._meta = { ...(isObject(result._meta) ? result._meta : {}), [META_SERVER_INFO]: { name, version } };
  if (CACHEABLE.has(method)) {
    result.ttlMs = Math.max(0, Math.trunc(ttlMs));
    result.cacheScope = cacheScope === "public" ? "public" : "private";
  }
  return result;
}
