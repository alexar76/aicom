// Paid x402 twins of the hub's direct capabilities (weather, air quality, nearby sensors, fair
// random), so the CDP Bazaar lists what the AIMarket hub sells, not only HISTOR and WARDEN.
//
// The buyer pays this gateway in USDC through the CDP facilitator; the gateway then buys the call
// from the hub with its own credit account (HUB_API_KEY_FILE). That account is a relay, so the
// hub's ecosystem.json must NOT list it under self: these calls are outside demand. The inputs
// mirror the hub's MCP direct tools (aimarket_hub/mcp_gateway.py DIRECT_TOOLS) and the prices
// are the hub's own, so the gateway resells at cost.
import { failure, inputRequired, ok } from "./a2mcp.js";

const LAT = { name: "latitude", type: "number", required: false, description: "latitude in degrees (-90..90)" };
const LON = { name: "longitude", type: "number", required: false, description: "longitude in degrees (-180..180)" };
const CITY = { name: "city", type: "string", required: false, description: "a city instead of coordinates, e.g. Tokyo" };

const num = (v, lo, hi) => (typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi ? v : undefined);

function placeInput(p) {
  const lat = num(p.latitude, -90, 90), lon = num(p.longitude, -180, 180);
  const city = typeof p.city === "string" ? p.city.trim().slice(0, 120) : "";
  if (lat !== undefined && lon !== undefined) return { latitude: lat, longitude: lon };
  if (city) return { city };
  return null;
}

/** The four capabilities, with the hub ids they map to and what an agent sees before it pays. */
export const HUB_TOOLS = {
  "weather-now": {
    product_id: "gaia.gateway", capability_id: "gaia.weather.read@v1", source_hub: "https://iot.modelmarket.dev",
    price: "$0.001",
    description: "Current weather at a place: temperature (°C), humidity (%), pressure (hPa) and wind (m/s) from the nearest live Open-Meteo relay within 75 km, with a signed receipt. Send latitude and longitude, or a city.",
    tags: ["weather", "iot", "data", "signed-receipt"],
    fields: [LAT, LON, CITY],
    build: placeInput,
    need: "send latitude and longitude, or a city",
    example: { latitude: 52.52, longitude: 13.405 },
  },
  "air-quality-now": {
    product_id: "gaia.gateway", capability_id: "gaia.air.read@v1", source_hub: "https://iot.modelmarket.dev",
    price: "$0.001",
    description: "Current air quality at a place: PM2.5 and PM10 (µg/m³), US and European AQI, from Copernicus CAMS via Open-Meteo, with a signed receipt. Send latitude and longitude, or a city.",
    tags: ["air-quality", "pm2.5", "data", "signed-receipt"],
    fields: [LAT, LON, CITY],
    build: placeInput,
    need: "send latitude and longitude, or a city",
    example: { city: "Paris" },
  },
  "nearby-sensors": {
    product_id: "atlas.products", capability_id: "atlas.nearest.read@v1", source_hub: "https://atlas.modelmarket.dev",
    price: "$0.03",
    description: "The nearest live public sensors to a point, one per layer asked for (weather, air, radiation, quake …), each with its reading, distance and source, and a signed receipt.",
    tags: ["sensors", "geo", "data", "signed-receipt"],
    fields: [
      { ...LAT, required: true }, { ...LON, required: true },
      { name: "layers", type: "array", required: false, description: "sensor layers, e.g. [\"weather\",\"air\"]; default weather" },
      { name: "max_km", type: "number", required: false, description: "refuse sensors farther than this" },
    ],
    build(p) {
      const lat = num(p.latitude, -90, 90), lon = num(p.longitude, -180, 180);
      if (lat === undefined || lon === undefined) return null;
      const out = { lat, lon, per_layer: true };
      if (Array.isArray(p.layers) && p.layers.length) out.layers = p.layers.slice(0, 12).map((l) => String(l).slice(0, 32));
      const maxKm = num(p.max_km, 0, 20_000);
      if (maxKm !== undefined) out.max_km = maxKm;
      return out;
    },
    need: "send latitude and longitude",
    example: { latitude: 35.68, longitude: 139.69, layers: ["weather", "air"] },
  },
  "fair-random": {
    product_id: "prod-sortes", capability_id: "sortes.draw@v1", source_hub: "https://oracles.modelmarket.dev/family",
    price: "$0.006",
    description: "Verifiable random bytes for a draw, raffle or tie-break: an ECVRF output over your seed plus a proof anyone can check offline. The same seed always gives the same output, so publish the seed first.",
    tags: ["randomness", "vrf", "fairness", "signed-receipt"],
    fields: [
      { name: "seed", type: "string", required: true, description: "the seed or message the draw is bound to (up to 4096 bytes)" },
      { name: "num_bytes", type: "integer", required: false, description: "output length, 1-64 (default 32)" },
    ],
    build(p) {
      // Never shortened: the proof is bound to exactly these bytes.
      if (typeof p.seed !== "string" || !p.seed.trim() || Buffer.byteLength(p.seed) > 4096) return null;
      const out = { alpha: p.seed };
      const n = num(p.num_bytes, 1, 64);
      if (n !== undefined && Number.isInteger(n)) out.num_bytes = n;
      return out;
    },
    need: "send a seed string of at most 4096 bytes",
    example: { seed: "raffle-2026-10-02:alice,bob,carol" },
  },
};

/**
 * One service per hub tool. ``handle`` refuses unpaid calls: these are bought from the hub, so a
 * free route would spend the gateway's account for anyone.
 */
export function hubServices({ hubUrl, apiKey, fetchImpl = globalThis.fetch, timeoutMs = 30_000 }) {
  if (!hubUrl || !apiKey) return [];
  const base = hubUrl.replace(/\/+$/, "");
  return Object.entries(HUB_TOOLS).map(([id, tool]) => {
    const service = { id, methods: ["POST"], fields: tool.fields, paidOnly: true, price: tool.price };
    service.handle = async (params, ctx = {}) => {
      if (!ctx.paid) {
        return [402, failure(service, "payment_required", `pay ${tool.price} over x402 at POST /x402/${id}`)];
      }
      const input = tool.build(params || {});
      if (!input) return [200, inputRequired(service, tool.need)];
      let res;
      try {
        res = await fetchImpl(`${base}/ai-market/v2/invoke`, {
          method: "POST",
          headers: { "content-type": "application/json", "x-api-key": apiKey, "user-agent": "okx-a2mcp/0.1 (+https://modelmarket.dev)" },
          body: JSON.stringify({ product_id: tool.product_id, capability_id: tool.capability_id, source_hub: tool.source_hub, input }),
          signal: AbortSignal.timeout(timeoutMs),
        });
      } catch {
        return [502, failure(service, "hub_unreachable", "the hub did not answer; you were not charged")];
      }
      let body = null;
      try { body = await res.json(); } catch { body = null; }
      if (!res.ok || !body || body.success === false) {
        // >= 400 means the x402 middleware does not settle: a failed call costs the buyer nothing.
        const status = res.status === 400 || res.status === 422 ? 400 : 502;
        return [status, failure(service, String(body?.error || "hub_error"), String(body?.detail || "the hub refused the call; you were not charged").slice(0, 300))];
      }
      return [200, ok(service, { capability_id: tool.capability_id, result: body.result ?? body.output ?? body, receipt: body.receipt ?? body.signed_receipt ?? null })];
    };
    return service;
  });
}
