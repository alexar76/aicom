// The A2MCP contract OKX.AI calls: an HTTPS endpoint per service, GET or POST,
//   - parameters missing -> 200 {"status":"input_required","fields":[...]} (OKX's self-check
//     is a bare `curl -X POST` and expects 200 from a free endpoint, so this must not be a 4xx),
//   - a result        -> 200 {"status":"ok", ...},
//   - a paid call     -> 402 + PAYMENT-REQUIRED (x402 V2) — not used while every service is free.

export function inputRequired(service, message) {
  return {
    status: "input_required",
    service: service.id,
    message,
    method: service.methods.join(" or "),
    fields: service.fields,
  };
}

export function ok(service, body) {
  return { status: "ok", service: service.id, ...body };
}

export function failure(service, code, message) {
  return { status: "error", service: service.id, error: code, message };
}

/** The parameters of a call: the JSON body for POST, the query string for GET. */
export function paramsOf(req) {
  if (req.method === "GET") return { ...req.query };
  return req.body && typeof req.body === "object" && !Array.isArray(req.body) ? req.body : {};
}
