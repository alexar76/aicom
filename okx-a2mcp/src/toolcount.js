// The count itself, as HISTOR's scripts/tool_list_tokens.py does it: per tool {name, description,
// input_schema} as compact JSON, tokenizer o200k_base, special-token text counted as plain text
// (tiktoken's disallowed_special=()). The table is built on the first count: about 140 MB, so the
// gateway loads this only inside the counting worker (src/toolcount-worker.js).
import { Tiktoken } from "js-tiktoken/lite";
import o200k from "js-tiktoken/ranks/o200k_base";

export const MAX_TOOLS = 3_000;   // the largest observed package lists 2,516

let enc = null;
/** Build the table now (seconds, about 140 MB) rather than inside the first count. */
export function warm() {
  enc ??= new Tiktoken(o200k);
}
const tokens = (value) => {
  warm();
  return enc.encode(JSON.stringify(value), [], []).length;
};

/** Count one tool list. Throws a message string for input that is not a list of tool objects. */
export function countTools(raw) {
  if (!Array.isArray(raw) || raw.length === 0) throw "send tools: the server's tools/list result";
  if (raw.length > MAX_TOOLS) throw `at most ${MAX_TOOLS} tools per count`;
  const per = raw.map((t, i) => {
    if (!t || typeof t !== "object" || Array.isArray(t)) throw `tools[${i}] must be an object`;
    if (typeof t.name !== "string" || !t.name) throw `tools[${i}] needs a string name`;
    const sent = { name: t.name, description: t.description || "", input_schema: t.inputSchema || { type: "object" } };
    // The same split as HISTOR's histor/toolcost.py: each part as it is written in that JSON; the
    // keys and punctuation around them are the rest, so the parts add up to the tool's tokens.
    const n = tokens(sent);
    const name = tokens(sent.name), description = tokens(sent.description), input_schema = tokens(sent.input_schema);
    return { name: t.name.slice(0, 200), tokens: n, description, input_schema, structure: n - name - description - input_schema, nameTokens: name };
  });
  const sum = (k) => per.reduce((a, t) => a + t[k], 0);
  const parts = { names: sum("nameTokens"), descriptions: sum("description"), input_schemas: sum("input_schema"), structure: sum("structure") };
  for (const t of per) delete t.nameTokens;
  return { tools: per.length, tokens: sum("tokens"), listedTokens: tokens(raw), parts, per };
}
