// The owner runs this command after the separate purchase command.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { SELLER } from "./transport.mjs";

const directory = dirname(fileURLToPath(import.meta.url));
const resultFile = join(directory, "refund-result.json");
const display = result => console.log(`refund     ${result.status} · ${result.amount_usd} USDC · ${result.transaction || "no confirmed transaction"}`);
if (existsSync(resultFile)) {
  display(JSON.parse(readFileSync(resultFile, "utf8")).result);
  process.exit(0);
}
const saved = JSON.parse(readFileSync(join(directory, "delivery.json"), "utf8"));
if (saved.status !== "delivered" || saved.seller !== SELLER + "/order" || !saved.delivery?.esim_tran_no || !saved.delivery?.status_token) {
  throw Error("No completed test delivery: do not create a second purchase; preserve delivery.json for reconciliation");
}
const response = await fetch(SELLER + "/refund", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ esim_tran_no: saved.delivery.esim_tran_no, status_token: saved.delivery.status_token }),
});
const outcome = await response.json();
if (!response.ok || !outcome.success) throw Error(`Refund not completed: HTTP ${response.status}, ${outcome.error || "unknown"}`);
writeFileSync(resultFile, JSON.stringify(outcome, null, 2) + "\n", { mode: 0o600, flag: "wx" });
display(outcome.result);
if (outcome.result.status !== "refunded" || !outcome.result.transaction) process.exitCode = 2;
