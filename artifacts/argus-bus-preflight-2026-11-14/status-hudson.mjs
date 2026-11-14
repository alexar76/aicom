import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { loadConfig } from "./dist/config.js";
import { createLasoCheckoutCard } from "./dist/checkout/laso-card.js";

const { config } = loadConfig();
const path = join(config.stateDir, "hudson-link-purchase.json");
const journal = existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : undefined;
const read = name => readFileSync(process.env[name], "utf8").trim();
const card = createLasoCheckoutCard({ id: read("ARGUS_ITCH_LASO_CARD_ID_FILE"), token: async () => read("ARGUS_ITCH_LASO_SESSION_FILE") });
const state = await card.read(AbortSignal.timeout(12_000)).catch(() => undefined);
console.log(JSON.stringify({
  enabled: process.env.ARGUS_HUDSON_PURCHASE_ENABLED === "1",
  journal_stage: journal?.stage ?? "no_submission",
  merchant_receipt_verified_in_journal: journal?.receiptVerified === true,
  issuer_reconciled_in_journal: journal?.reconciled === true,
  laso_balance_cents: state?.balanceCents,
  laso_hudson_debits_275_cents: state?.hudsonDebits?.filter(cents => cents === 275).length,
}));
