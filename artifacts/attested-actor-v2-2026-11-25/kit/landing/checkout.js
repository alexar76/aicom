(function () {
  "use strict";
  var trialDialog = document.querySelector("#trial-dialog"), checkoutDialog = document.querySelector("#checkout-dialog"), trialProduct = "personal", plan = "", order = null, pollTimer = null;
  var products = { personal: ["trialPersonalTitle", "trialPersonalDesc"], team: ["trialTeamTitle", "trialTeamDesc"], "expert-market": ["trialMarketTitle", "trialMarketDesc"] };
  var $ = function (selector) { return document.querySelector(selector); };
  var t = function (key) { return AttestedLocale.text(key); };
  var apiError = function (value, fallback) { return value && value.detail === "SAAS_PAYMENT_RECIPIENT is not configured" ? t("statusPaymentDisabled") : (value && value.detail) || t(fallback); };
  var orderStatus = document.createElement("p");
  orderStatus.className = "notice";
  orderStatus.id = "order-status";
  orderStatus.setAttribute("role", "status");
  $("#order-form").appendChild(orderStatus);
  async function actorHeaders() { return AttestedActor.headers("/api/v1/trials", {method: "POST", body: JSON.stringify({product: trialProduct})}); }
  function updateTrialCopy() { var copy = products[trialProduct]; $("#trial-title").textContent = t(copy[0]); $("#trial-description").textContent = t(copy[1]); }
  function openTrial(product) { trialProduct = products[product] ? product : "personal"; updateTrialCopy(); $("#trial-status").textContent = ""; $("#trial-keybox").hidden = true; $("#claim-trial").disabled = false; trialDialog.showModal(); }
  function saveCheckout() { if (!order) return; sessionStorage.setItem("attested_checkout", JSON.stringify({ plan: plan, order: order })); }
  function clearCheckout() { sessionStorage.removeItem("attested_checkout"); }
  function showInvoice(value) { order = value; $("#amount").textContent = value.amount_usdc; $("#recipient").textContent = value.pay_to; $("#wallet").href = value.eip681 || "#"; $("#payment").hidden = false; $("#order-form").hidden = true; $("#order-status").textContent = ""; $("#payment-status").textContent = t(value.recovered ? "statusCheckoutRecovered" : "statusInvoiceReady"); saveCheckout(); startPolling(); }
  function showPaid(value) { $("#paid-key").textContent = value.api_key; $("#paid-keybox").hidden = false; $("#confirm").disabled = true; $("#payment-status").textContent = t("statusPaymentConfirmed"); clearInterval(pollTimer); clearCheckout(); }
  function openCheckout(selectedPlan) { plan = selectedPlan; $("#checkout-title").textContent = selectedPlan.replaceAll(".", " / "); $("#paid-keybox").hidden = true; $("#order-status").textContent = ""; $("#payment-status").textContent = ""; $("#confirm").disabled = false; var saved = null; try { saved = JSON.parse(sessionStorage.getItem("attested_checkout")); } catch (_) {} if (saved && saved.plan === plan && saved.order) { showInvoice(saved.order); } else { $("#order-form").hidden = false; $("#payment").hidden = true; order = null; } checkoutDialog.showModal(); }
  async function checkOrder() { if (!order || !order.order_id || !order.checkout_token) return; try { var response = await fetch("/api/v1/billing/orders/" + order.order_id, { headers: { "X-Checkout-Token": order.checkout_token } }), value = await response.json(); if (!response.ok) throw Error(value.detail || t("statusPaymentCheckFailed")); if (value.api_key) showPaid(value); else $("#payment-status").textContent = value.state === "pending" ? t("statusWatching") : t("statusOrderState") + " " + value.state; } catch (error) { $("#payment-status").textContent = error.message; } }
  function startPolling() { clearInterval(pollTimer); pollTimer = setInterval(checkOrder, 6000); }

  document.querySelectorAll(".trial-open").forEach(function (button) { button.onclick = function () { openTrial(button.dataset.product); }; });
  document.querySelectorAll(".buy").forEach(function (button) { button.onclick = function () { openCheckout(button.dataset.plan); }; });
  document.querySelectorAll("[data-close]").forEach(function (button) { button.onclick = function () { document.getElementById(button.dataset.close).close(); }; });
  document.querySelectorAll(".copy-key").forEach(function (button) { button.onclick = function () { var value = document.getElementById(button.dataset.target).textContent; navigator.clipboard.writeText(value).then(function () { button.textContent = t("copied"); setTimeout(function () { button.textContent = t(button.dataset.target === "recipient" ? "copyAddress" : "copyKey"); }, 1200); }); }; });
  $("#claim-trial").onclick = async function () { var status = $("#trial-status"); status.textContent = t("statusCreatingProof"); try { var headers = await actorHeaders(); headers["content-type"] = "application/json"; var response = await fetch("/api/v1/trials", { method: "POST", redirect: "error", headers: headers, body: JSON.stringify({ product: trialProduct }) }), value = await response.json(); if (!response.ok) throw Error(value.detail || t("statusTrialFailed")); $("#trial-key").textContent = value.api_key; $("#trial-keybox").hidden = false; $("#claim-trial").disabled = true; status.textContent = t(value.recovered ? "statusActiveRecovered" : "statusActivated") + " " + t("statusAccessExpires") + " " + value.expires_at; } catch (error) { status.textContent = error.message; } };
  $("#order-form").onsubmit = async function (event) { event.preventDefault(); var status = $("#order-status"); status.textContent = t("statusCreatingInvoice"); try { var idempotency = crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random().toString(16).slice(2); var response = await fetch("/api/v1/billing/orders", { method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": idempotency }, body: JSON.stringify({ plan: plan, payer: $("#payer").value.trim() }) }), value = await response.json(); if (!response.ok) throw Error(apiError(value, "statusInvoiceFailed")); showInvoice(value); } catch (error) { status.textContent = error.message; } };
  $("#confirm").onclick = async function () { if (!order) return; $("#payment-status").textContent = t("statusCheckingFinality"); try { var response = await fetch("/api/v1/billing/orders/" + order.order_id + "/confirm", { method: "POST", headers: { "content-type": "application/json", "X-Checkout-Token": order.checkout_token }, body: JSON.stringify({ tx_hash: $("#tx").value.trim() }) }), value = await response.json(); if (!response.ok) throw Error(value.detail || t("statusPaymentCheckFailed")); if (value.api_key) showPaid(value); else $("#payment-status").textContent = t("statusPaymentNotFinal"); } catch (error) { $("#payment-status").textContent = error.message; } };
  document.addEventListener("attested:lang", function () { if (trialDialog.open) updateTrialCopy(); });

  var query = new URLSearchParams(location.search), queryPlan = query.get("plan"), queryTrial = query.get("trial");
  if (queryPlan) openCheckout(queryPlan);
  else if (queryTrial) openTrial(queryTrial);
})();
