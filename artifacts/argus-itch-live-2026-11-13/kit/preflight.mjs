import { readFileSync } from "node:fs";
import { createLasoCheckoutCard } from "./dist/checkout/laso-card.js";
import { openItchCheckout, ItchCheckoutError } from "./dist/checkout/itch-browser.js";

const read = name => readFileSync(process.env[name], "utf8").trim();
const laso = createLasoCheckoutCard({ id: read("ARGUS_ITCH_LASO_CARD_ID_FILE"),
  token: async () => read("ARGUS_ITCH_LASO_SESSION_FILE") });
const signal = AbortSignal.timeout(65_000);
let stage = "laso";
try {
  const [accepted, state] = await Promise.all([laso.accepted(signal), laso.read(signal)]);
  if (!accepted || state.balanceCents !== 500 || state.itchDebits.length) throw Error("Laso preflight");
  stage = "merchant";
  const checkout = await openItchCheckout({ email: read("ARGUS_ITCH_RECEIPT_EMAIL_FILE"), billing: state.billing,
    browserWsEndpoint: read("ARGUS_ITCH_BROWSER_WS_FILE"), signal });
  try {
    console.log(JSON.stringify({accepted,cardAvailableCents:state.balanceCents,totalCents:checkout.totalCents,taxCents:checkout.taxCents,chargeSent:false}));
  } finally { await checkout.close(); }
} catch (error) {
  console.log(JSON.stringify({stage,error:error instanceof ItchCheckoutError ? error.code : "preflight_unavailable",chargeSent:false}));
  process.exitCode = 1;
}
