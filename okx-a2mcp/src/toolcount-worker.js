// The counting worker (src/toolcost.js starts it): one count per message, in arrival order.
import { parentPort } from "node:worker_threads";
import { countTools, warm } from "./toolcount.js";

warm();
parentPort.postMessage({ ready: true });

parentPort.on("message", ({ id, tools }) => {
  try {
    parentPort.postMessage({ id, result: countTools(tools) });
  } catch (e) {
    parentPort.postMessage({ id, error: typeof e === "string" ? e : "the count failed" });
  }
});
