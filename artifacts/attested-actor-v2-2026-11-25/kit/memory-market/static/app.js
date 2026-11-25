const catalog = document.querySelector("#catalog");
const searchForm = document.querySelector("#search-form");
const actorInput = document.querySelector("#actor");
const drawer = document.querySelector("#create-drawer");
const scrim = document.querySelector("#scrim");
const createForm = document.querySelector("#create-form");
const visibility = document.querySelector("#visibility");
const price = document.querySelector("#price");
const checkoutDrawer = document.querySelector("#checkout-drawer");
const checkoutState = document.querySelector("#checkout-state");
const checkoutOrder = document.querySelector("#checkout-order");
const paymentMessage = document.querySelector("#payment-message");
let currentOrder = null;
let checkoutPoll = null;

async function headers(path, options = {}, includeAuth = false) {
  const result = { "Content-Type": "application/json" };
  const apiKey = document.querySelector("#api-key")?.value.trim();
  if (includeAuth || apiKey) {
    Object.assign(result, await AttestedActor.headers(path, { ...options, audience: "memory-market" }));
    actorInput.value = result["X-Actor-ID"];
    result.Authorization = `Bearer ${apiKey || ""}`;
  }
  return result;
}

function element(name, className, text) {
  const node = document.createElement(name);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function memoryCard(memory) {
  const card = element("article", "memory-card");
  const head = element("div", "memory-card-head");
  const identity = element("div");
  identity.append(element("h3", "", memory.title), element("p", "owner", memory.owner_id));
  head.append(identity, element("span", "visibility", memory.visibility));
  card.append(head);

  const badges = element("div", "badges");
  const truthClass = memory.truth.status === "supported" ? "badge good" : "badge warn";
  badges.append(
    element("span", truthClass, `truth: ${memory.truth.status}`),
    element("span", memory.provenance.status === "attested" ? "badge good" : "badge warn", `lineage: ${memory.provenance.status}`),
  );
  if (memory.price_usdc) badges.append(element("span", "badge", `${memory.price_usdc} USDC / read`));
  card.append(badges);

  if (memory.tags.length) {
    const tags = element("div", "memory-meta");
    memory.tags.slice(0, 5).forEach((tag) => tags.append(element("span", "tag", `#${tag}`)));
    card.append(tags);
  }
  const foot = element("div", "memory-foot");
  foot.append(
    element("span", "", memory.id),
    element("span", "", memory.score_count ? `★ ${memory.average_score} · ${memory.score_count}` : "not rated"),
  );
  card.append(foot);
  if (memory.visibility === "paid") {
    const buy = element("button", "buy-access", `Buy access · ${memory.price_usdc} USDC`);
    buy.type = "button";
    buy.addEventListener("click", () => beginCheckout(memory));
    card.append(buy);
  }
  return card;
}

async function loadCatalog(query = "") {
  catalog.replaceChildren(element("div", "empty", "Loading memory units…"));
  try {
    const response = await fetch(`/v1/catalog?q=${encodeURIComponent(query)}`, { redirect: "error", headers: await headers(`/v1/catalog?q=${encodeURIComponent(query)}`) });
    if (!response.ok) throw new Error("Catalogue unavailable");
    const data = await response.json();
    document.querySelector("#result-count").textContent = `${data.total} accessible record${data.total === 1 ? "" : "s"}`;
    catalog.replaceChildren();
    if (!data.items.length) {
      const empty = element("div", "empty");
      empty.append(element("strong", "", query ? "No matching memory" : "The market is ready"));
      empty.append(element("span", "", query ? "Try a broader query or another actor ID." : "Write the first attested memory to begin."));
      catalog.append(empty);
    } else {
      data.items.forEach((memory) => catalog.append(memoryCard(memory)));
    }
  } catch (error) {
    catalog.replaceChildren(element("div", "empty error", error.message));
  }
}

async function loadStatus() {
  try {
    const [healthResponse, statsResponse, networkResponse] = await Promise.all([
      fetch("/healthz"), fetch("/v1/stats"), fetch("/v1/network"),
    ]);
    const health = await healthResponse.json();
    const stats = await statsResponse.json();
    const network = await networkResponse.json();
    const online = network.nodes.filter((node) => node.status === "online").length;
    document.querySelector("#node-status").textContent = `${online}/3 services · hub ${network.hub.status}`;
    document.querySelector("#stat-total").textContent = stats.discoverable_memories;
    document.querySelector("#stat-attested").textContent = stats.attested_memories;
    document.querySelector("#stat-verified").textContent = stats.verified_memories;
    document.querySelector("#stat-payment").textContent = stats.payment_enabled ? "Enabled" : "Closed";
    document.querySelector("#hub-capability-count").textContent = network.hub.status === "online" ? network.hub.advertised_capabilities : network.capabilities;
    network.nodes.forEach((node) => {
      const topologyNode = document.querySelector(`[data-service="${node.id}"]`);
      const dot = document.querySelector(`[data-service-dot="${node.id}"]`);
      [topologyNode, dot].filter(Boolean).forEach((item) => item.classList.add(node.status));
      if (topologyNode) topologyNode.querySelector("small").textContent = `${node.capabilities} capabilities · ${node.status}`;
    });
    const roots = document.querySelector("#federation-roots");
    roots.replaceChildren();
    network.federation.forEach((peer) => {
      const label = element("span");
      label.append(element("i"), document.createTextNode(new URL(peer.url).hostname));
      roots.append(label);
    });
    const security = document.querySelector(".security-pill");
    const pqReady = network.nodes.every((node) => node.pqc);
    security.lastChild.textContent = pqReady ? " PQC enforced" : " PQC awaiting services";
  } catch {
    document.querySelector("#node-status").textContent = "Status unavailable";
  }
}

function openDrawer() {
  closeCheckout(false);
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  scrim.hidden = false;
  document.querySelector("#api-key").focus();
}

function closeDrawer(restoreFocus = true) {
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  if (!checkoutDrawer.classList.contains("open")) scrim.hidden = true;
  if (restoreFocus) document.querySelector("#open-create").focus();
}

function stopCheckoutPoll() {
  if (checkoutPoll) window.clearTimeout(checkoutPoll);
  checkoutPoll = null;
}

function openCheckout() {
  closeDrawer(false);
  checkoutDrawer.classList.add("open");
  checkoutDrawer.setAttribute("aria-hidden", "false");
  scrim.hidden = false;
}

function closeCheckout(restoreFocus = true) {
  stopCheckoutPoll();
  checkoutDrawer.classList.remove("open");
  checkoutDrawer.setAttribute("aria-hidden", "true");
  if (!drawer.classList.contains("open")) scrim.hidden = true;
  if (restoreFocus) actorInput.focus();
}

function showCheckoutError(message) {
  checkoutOrder.hidden = true;
  checkoutState.replaceChildren(element("div", "empty error", message));
  checkoutState.hidden = false;
}

function orderStateLabel(state) {
  return state === "confirmed" ? "CONFIRMED" : state === "expired" ? "EXPIRED" : "PENDING";
}

function renderOrder(order) {
  currentOrder = order;
  checkoutState.hidden = true;
  checkoutOrder.hidden = false;
  document.querySelector("#order-number").textContent = order.number;
  const state = document.querySelector("#order-state");
  state.textContent = orderStateLabel(order.state);
  state.dataset.state = order.state;
  document.querySelector("#order-memory").textContent = order.memory_title;
  document.querySelector("#order-amount").textContent = order.amount_usdc;
  document.querySelector("#order-recipient").textContent = order.pay_to;
  document.querySelector("#order-confirmations").textContent = `${order.required_confirmations} confirmations`;
  document.querySelector("#order-expiry").textContent = `Expires ${new Date(order.expires_at).toLocaleString()}`;
  const wallet = document.querySelector("#open-wallet");
  wallet.href = order.eip681;
  wallet.setAttribute("aria-disabled", order.state !== "pending" ? "true" : "false");
  const confirmButton = document.querySelector("#confirm-payment-form button");
  confirmButton.disabled = order.state === "confirmed";
  if (order.state === "confirmed") {
    stopCheckoutPoll();
    paymentMessage.className = "form-message success";
    paymentMessage.textContent = `Payment finalized. Access is unlocked for ${order.grantee_id}.`;
    Promise.all([loadCatalog(document.querySelector("#search").value), loadStatus()]);
  } else if (order.state === "expired") {
    paymentMessage.className = "form-message error";
    paymentMessage.textContent = "Quote expired. A transfer may still settle during the displayed grace window; otherwise create a new order.";
    scheduleOrderPoll();
  } else {
    paymentMessage.className = "form-message";
    paymentMessage.textContent = "Waiting for a finalized transfer…";
    scheduleOrderPoll();
  }
}

async function refreshOrder() {
  if (!currentOrder || !checkoutDrawer.classList.contains("open")) return;
  try {
    const response = await fetch(`/v1/billing/orders/${encodeURIComponent(currentOrder.order_id)}`, { redirect: "error", headers: await headers(`/v1/billing/orders/${encodeURIComponent(currentOrder.order_id)}`, {}, true) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not refresh payment order");
    renderOrder(result);
  } catch (error) {
    paymentMessage.className = "form-message error";
    paymentMessage.textContent = `${error.message}. Automatic checking will retry.`;
    scheduleOrderPoll();
  }
}

function scheduleOrderPoll() {
  stopCheckoutPoll();
  if (currentOrder?.state !== "confirmed" && checkoutDrawer.classList.contains("open")) {
    checkoutPoll = window.setTimeout(refreshOrder, 5000);
  }
}

async function beginCheckout(memory) {
  const actor = await AttestedActor.actorId();
  actorInput.value = actor;
  if (!actor) {
    document.querySelector("#node-status").textContent = "Enter an Actor ID before checkout";
    actorInput.focus();
    return;
  }
  currentOrder = null;
  checkoutState.hidden = false;
  checkoutState.replaceChildren();
  const loader = element("div", "checkout-loader");
  loader.append(element("i"), element("span", "", "Preparing an exact USDC quote…"));
  checkoutState.append(loader);
  checkoutOrder.hidden = true;
  openCheckout();
  try {
    const body = JSON.stringify({ memory_id: memory.id, grantee_id: actor });
    const response = await fetch("/v1/billing/orders", {
      method: "POST", redirect: "error", headers: await headers("/v1/billing/orders", {method: "POST", body}, true), body,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not create payment order");
    renderOrder(result);
  } catch (error) {
    showCheckoutError(error.message);
  }
}

document.querySelector("#open-create").addEventListener("click", openDrawer);
document.querySelector("#close-create").addEventListener("click", closeDrawer);
document.querySelector("#close-checkout").addEventListener("click", closeCheckout);
scrim.addEventListener("click", () => { closeDrawer(false); closeCheckout(false); });
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (checkoutDrawer.classList.contains("open")) closeCheckout();
  else if (drawer.classList.contains("open")) closeDrawer();
});
actorInput.addEventListener("change", () => { loadCatalog(document.querySelector("#search").value); loadStatus(); });
searchForm.addEventListener("submit", (event) => { event.preventDefault(); loadCatalog(document.querySelector("#search").value); });
visibility.addEventListener("change", () => { price.disabled = visibility.value !== "paid"; if (price.disabled) price.value = ""; });

document.querySelectorAll("[data-copy]").forEach((button) => button.addEventListener("click", async () => {
  if (!currentOrder) return;
  const value = button.dataset.copy === "amount" ? currentOrder.amount_usdc : currentOrder.pay_to;
  try {
    await navigator.clipboard.writeText(value);
    const original = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(() => { button.textContent = original; }, 1200);
  } catch {
    paymentMessage.className = "form-message error";
    paymentMessage.textContent = "Clipboard access was denied. Select and copy the value manually.";
  }
}));

document.querySelector("#confirm-payment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentOrder) return;
  const button = event.submitter;
  button.disabled = true;
  paymentMessage.className = "form-message";
  paymentMessage.textContent = "Checking the transfer and confirmation depth…";
  try {
    const path = `/v1/billing/orders/${encodeURIComponent(currentOrder.order_id)}/confirm`;
    const body = JSON.stringify({ tx_hash: document.querySelector("#payment-tx").value.trim() });
    const response = await fetch(path, {
      method: "POST", redirect: "error", headers: await headers(path, {method: "POST", body}, true), body,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Transaction could not be verified");
    renderOrder(result);
  } catch (error) {
    button.disabled = false;
    paymentMessage.className = "form-message error";
    paymentMessage.textContent = error.message;
    scheduleOrderPoll();
  }
});

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.querySelector("#form-message");
  const owner = await AttestedActor.actorId();
  actorInput.value = owner;
  const body = {
    title: document.querySelector("#title").value,
    content: document.querySelector("#content").value,
    visibility: visibility.value,
    price_usdc: visibility.value === "paid" ? price.value : null,
    tags: document.querySelector("#tags").value.split(",").map((tag) => tag.trim()).filter(Boolean),
    source_refs: document.querySelector("#sources").value.split("\n").map((source) => source.trim()).filter(Boolean),
  };
  message.className = "form-message";
  message.textContent = "Writing and requesting attestation…";
  try {
    const encoded = JSON.stringify(body);
    const response = await fetch("/v1/memories", { method: "POST", redirect: "error", headers: await headers("/v1/memories", {method: "POST", body: encoded}, true), body: encoded });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not create memory");
    message.textContent = `Created ${result.id} · ${result.provenance.status}`;
    createForm.reset();
    actorInput.value = owner;
    price.disabled = true;
    await Promise.all([loadCatalog(), loadStatus()]);
  } catch (error) {
    message.className = "form-message error";
    message.textContent = error.message;
  }
});

loadCatalog();
loadStatus();

AttestedActor.actorId().then((actor) => { actorInput.value = actor; document.querySelector("#owner-id").value = actor; }).catch(() => {});
