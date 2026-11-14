import { constants, lstatSync, openSync, fsyncSync, closeSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { randomUUID } from "node:crypto";

const token = readFileSync(0, "utf8").trim();
if (!/^[\w.-]{1,8192}$/.test(token)) throw new Error("Did not receive a valid short session");
const path = process.env.ARGUS_ITCH_LASO_SESSION_FILE;
if (path !== "/home/node/.argus/itch-laso-session") throw new Error("Unexpected checkout session path");
const stat = lstatSync(path);
if (!stat.isFile() || stat.uid !== process.getuid() || (stat.mode & 0o077)) throw new Error("Expected existing private checkout session");
const id = readFileSync(process.env.ARGUS_ITCH_LASO_CARD_ID_FILE, "utf8").trim();
const query = new URLSearchParams({ card_id: id });
const verify = await fetch(`https://laso.finance/get-card-data?${query}`, {
  redirect: "error", signal: AbortSignal.timeout(10_000),
  headers: { authorization: `Bearer ${token}`, accept: "application/json" },
});
if (!verify.ok) throw new Error(`Laso card state returned HTTP ${verify.status}`);
const card = await verify.json();
const balance = card.card_details?.available_balance;
if (card.card_id !== id || card.usd_amount !== 5 || card.status !== "ready" || card.country !== "US"
  || !Array.isArray(card.transactions) || typeof balance !== "number" || !Number.isFinite(balance) || balance < 0 || balance > 5) {
  throw new Error("Unexpected card state");
}

const tmp = `${path}.${randomUUID()}.tmp`;
const fd = openSync(tmp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, 0o600);
try { writeFileSync(fd, token); fsyncSync(fd); } finally { closeSync(fd); }
renameSync(tmp, path);
const dir = openSync(dirname(path), constants.O_RDONLY);
try { fsyncSync(dir); } finally { closeSync(dir); }
console.log("Existing checkout session refreshed. Card ready.");
