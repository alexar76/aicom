/**
 * AI Market embed — pay-to-call widget for external sites.
 *
 * Usage:
 *   <script src="https://your-factory.example/aimarket.js"
 *           data-product="prod-..."
 *           data-price="9.99"
 *           data-label="Hire this AI"></script>
 */
(function aimarketEmbed() {
  var script = document.currentScript;
  if (!script) return;

  var productId = script.getAttribute('data-product') || '';
  var price = script.getAttribute('data-price') || '9.99';
  var label = script.getAttribute('data-label') || 'Hire this AI';
  var base = script.getAttribute('data-base') || (function () {
    try {
      var u = new URL(script.src);
      return u.origin;
    } catch (e) {
      return '';
    }
  })();

  if (!productId || !base) {
    console.warn('[aimarket] data-product and valid script src required');
    return;
  }

  var root = document.createElement('div');
  root.className = 'aimarket-root';
  root.style.cssText = 'font-family:system-ui,sans-serif;display:inline-block';
  script.parentNode.insertBefore(root, script.nextSibling);

  var btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = label + ' · $' + price;
  btn.style.cssText =
    'cursor:pointer;border:none;border-radius:999px;padding:10px 18px;font-weight:600;' +
    'background:linear-gradient(135deg,#6366f1,#06b6d4);color:#fff;box-shadow:0 8px 24px rgba(99,102,241,.35)';
  root.appendChild(btn);

  var modal = document.createElement('div');
  modal.hidden = true;
  modal.style.cssText =
    'position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:99999';
  modal.innerHTML =
    '<div style="background:#0f172a;color:#e2e8f0;border-radius:16px;padding:24px;max-width:420px;width:90%">' +
    '<h3 style="margin:0 0 8px;font-size:18px">AI Market</h3>' +
    '<p style="margin:0 0 12px;font-size:13px;color:#94a3b8">Connect wallet, send ' + price + ' USDT, receive license key.</p>' +
    '<input id="aimarket-wallet" placeholder="0x… wallet" style="width:100%;padding:10px;border-radius:8px;border:1px solid #334155;background:#020617;color:#fff;margin-bottom:8px"/>' +
    '<input id="aimarket-tx" placeholder="tx hash after payment" style="width:100%;padding:10px;border-radius:8px;border:1px solid #334155;background:#020617;color:#fff;margin-bottom:12px"/>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end">' +
    '<button type="button" id="aimarket-cancel" style="padding:8px 14px;border-radius:8px;border:1px solid #475569;background:transparent;color:#cbd5e1">Cancel</button>' +
    '<button type="button" id="aimarket-settle" style="padding:8px 14px;border-radius:8px;border:none;background:#6366f1;color:#fff;font-weight:600">Confirm</button>' +
    '</div><pre id="aimarket-result" style="margin-top:12px;font-size:11px;white-space:pre-wrap;color:#86efac"></pre></div>';
  document.body.appendChild(modal);

  btn.addEventListener('click', function () {
    modal.hidden = false;
  });
  modal.querySelector('#aimarket-cancel').addEventListener('click', function () {
    modal.hidden = true;
  });
  modal.addEventListener('click', function (ev) {
    if (ev.target === modal) modal.hidden = true;
  });

  modal.querySelector('#aimarket-settle').addEventListener('click', function () {
    var wallet = modal.querySelector('#aimarket-wallet').value.trim();
    var tx = modal.querySelector('#aimarket-tx').value.trim();
    var out = modal.querySelector('#aimarket-result');
    out.textContent = 'Confirming…';
    fetch(base + '/api/ai-market/pilot/settlement/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_id: productId,
        amount: parseFloat(price),
        wallet_address: wallet,
        tx_hash: tx,
      }),
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (_ref) {
        var ok = _ref.ok;
        var j = _ref.j;
        if (!ok) throw new Error(j.detail || 'settlement failed');
        out.textContent = 'license_key: ' + (j.license_key || '(see response)') + '\n' + JSON.stringify(j, null, 2);
      })
      .catch(function (err) {
        out.textContent = 'Error: ' + (err && err.message ? err.message : String(err));
      });
  });
})();
