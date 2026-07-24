const runBtn = document.getElementById("run");
const out = document.getElementById("out");
const nameInput = document.getElementById("name");

async function invokeGreet() {
  const name = (nameInput?.value || "Operator").trim();
  if (window.__TAURI__?.core?.invoke) {
    const msg = await window.__TAURI__.core.invoke("greet", { name });
    if (out) out.textContent = msg;
    return;
  }
  if (out) out.textContent = `Hello, ${name} — running locally (browser preview).`;
}

runBtn?.addEventListener("click", () => {
  invokeGreet().catch((err) => {
    if (out) out.textContent = String(err);
  });
});
