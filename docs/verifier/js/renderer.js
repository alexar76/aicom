/**
 * AI Provenance Verifier — UI renderer.
 *
 * Handles DOM rendering of verification results:
 * - Verdict banner (pass/fail)
 * - Receipt metadata display
 * - Per-check results with icons
 * - TEE attestation badge
 * - Provenance chain visualization
 * - Raw JSON display
 */

// ── i18n helpers ────────────────────────────────────────────────────────────
// The dictionary + t() live inline in index.html (window.__t). Fall back to the
// raw key when running standalone.
function T(k) { return (typeof window !== 'undefined' && window.__t) ? window.__t(k) : k; }
function Tf(k, vars) {
  let s = T(k);
  for (const name in vars) s = s.replace('{' + name + '}', vars[name]);
  return s;
}

// Remember the last verified receipt so a language switch can re-render it.
let __lastReceipt = null;
if (typeof window !== 'undefined') {
  window.__rerender = async function () {
    const rs = document.getElementById('result-section');
    if (!__lastReceipt || !rs || rs.classList.contains('hidden')) return;
    const result = await window.AIProvenanceVerifier.verifyProvenanceReceipt(__lastReceipt);
    renderResult(__lastReceipt, result);
  };
}

document.addEventListener('DOMContentLoaded', () => {
  const inputEl = document.getElementById('receipt-input');
  const verifyBtn = document.getElementById('verify-btn');
  const clearBtn = document.getElementById('clear-btn');
  const exampleBtn = document.getElementById('load-example-btn');
  const errorEl = document.getElementById('error-msg');
  const loadingEl = document.getElementById('loading-msg');
  const resultSection = document.getElementById('result-section');

  // ── Verify button ─────────────────────────────────────────────────
  verifyBtn.addEventListener('click', async () => {
    errorEl.classList.add('hidden');
    loadingEl.classList.remove('hidden');
    resultSection.classList.add('hidden');

    const raw = inputEl.value.trim();
    if (!raw) {
      errorEl.textContent = T('err_empty');
      errorEl.classList.remove('hidden');
      loadingEl.classList.add('hidden');
      return;
    }

    let receipt;
    try {
      receipt = JSON.parse(raw);
    } catch {
      // Maybe it's a receipt ID — try to fetch it
      const id = raw.split('/').pop(); // handle urn:uuid:xxx or just uuid
      try {
        const resp = await fetch(`data/receipts/${id}.json`);
        if (!resp.ok) throw new Error('Not found');
        receipt = await resp.json();
      } catch {
        errorEl.textContent = T('err_notfound');
        errorEl.classList.remove('hidden');
        loadingEl.classList.add('hidden');
        return;
      }
    }

    // Verify
    __lastReceipt = receipt;
    const result = await window.AIProvenanceVerifier.verifyProvenanceReceipt(receipt);
    renderResult(receipt, result);

    loadingEl.classList.add('hidden');
    resultSection.classList.remove('hidden');
    resultSection.scrollIntoView({ behavior: 'smooth' });
  });

  // ── Clear button ──────────────────────────────────────────────────
  clearBtn.addEventListener('click', () => {
    inputEl.value = '';
    resultSection.classList.add('hidden');
    errorEl.classList.add('hidden');
  });

  // ── Example button ────────────────────────────────────────────────
  exampleBtn.addEventListener('click', async () => {
    try {
      const resp = await fetch('data/receipts/example.json');
      if (resp.ok) {
        const example = await resp.json();
        inputEl.value = JSON.stringify(example, null, 2);
      }
    } catch {
      inputEl.value = JSON.stringify(getExampleReceipt(), null, 2);
    }
  });
});

// ── Render results ──────────────────────────────────────────────────────

function renderResult(receipt, result) {
  renderVerdict(result);
  renderMeta(receipt);
  renderChecks(result);
  renderAttestations(receipt);
  renderProvenanceChain(receipt);
  renderRawJson(receipt);
}

function renderVerdict(result) {
  const banner = document.getElementById('verdict-banner');
  if (result.valid) {
    banner.innerHTML = `
      <div class="verdict pass">
        <span class="verdict-icon">&#10003;</span>
        <div>
          <strong>${esc(T('verdict_pass_t'))}</strong>
          <p>${esc(T('verdict_pass_d'))}</p>
        </div>
      </div>`;
  } else {
    banner.innerHTML = `
      <div class="verdict fail">
        <span class="verdict-icon">&#10007;</span>
        <div>
          <strong>${esc(T('verdict_fail_t'))}</strong>
          <p>${esc(Tf('verdict_fail_d', { n: result.errors.length }))}</p>
        </div>
      </div>`;
  }
}

function renderMeta(receipt) {
  const meta = document.getElementById('receipt-meta');
  const subject = receipt.credentialSubject || {};
  const issuer = receipt.issuer || {};
  const hubInfo = receipt.hubInfo || {};

  meta.innerHTML = `
    <div class="meta-grid">
      <div class="meta-item">
        <span class="meta-label">${esc(T('m_model'))}</span>
        <span class="meta-value">${esc(subject.modelId || '—')}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">${esc(T('m_provider'))}</span>
        <span class="meta-value">${esc(subject.providerHub || '—')}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">${esc(T('m_issued'))}</span>
        <span class="meta-value">${esc(subject.timestamp || receipt.issuanceDate || '—')}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">${esc(T('m_latency'))}</span>
        <span class="meta-value">${subject.latencyMs ? subject.latencyMs + ' ms' : '—'}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">${esc(T('m_price'))}</span>
        <span class="meta-value">${subject.priceUsd != null ? '$' + subject.priceUsd : '—'}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">${esc(T('m_receipt_id'))}</span>
        <span class="meta-value mono">${esc(truncate(receipt.id, 40))}</span>
      </div>
    </div>
    <div class="meta-item full-width">
      <span class="meta-label">${esc(T('m_issuer'))}</span>
      <span class="meta-value">${esc(issuer.name || '—')} (${esc(issuer.id || '—')})</span>
    </div>
    ${subject.inputHash ? `
    <details class="hash-section">
      <summary>${esc(T('input_hash'))}</summary>
      <code>${esc(subject.inputHash.value)}</code>
    </details>` : ''}
    ${subject.outputHash ? `
    <details class="hash-section">
      <summary>${esc(T('output_hash'))}</summary>
      <code>${esc(subject.outputHash.value)}</code>
    </details>` : ''}
  `;
}

function renderChecks(result) {
  const container = document.getElementById('checks-list');
  container.innerHTML = result.checks.map(check => {
    const icon = check.passed ? '&#10003;' : '&#10007;';
    const cls = check.passed ? 'check-pass' : 'check-fail';
    let detail = '';
    if (check.algorithm) detail += ` | ${esc(check.algorithm)}`;
    if (check.platform) detail += ` | ${esc(T('lbl_platform'))} ${esc(check.platform)}`;
    if (check.count != null) detail += ` | ${check.count} ${esc(T('lbl_parents'))}`;
    if (check.value) detail += ` | ${esc(check.value)}`;
    return `<div class="check-item ${cls}">
      <span class="check-icon">${icon}</span>
      <span class="check-label">${esc(T('check_' + check.check))}</span>
      <span class="check-detail">${detail}</span>
    </div>`;
  }).join('');

  if (result.errors.length > 0) {
    container.innerHTML += `<div class="errors-list">
      <strong>${esc(T('errors_label'))}</strong>
      <ul>${result.errors.map(e => `<li>${esc(e)}</li>`).join('')}</ul>
    </div>`;
  }
}

function renderAttestations(receipt) {
  const container = document.getElementById('attestation-badges');
  const subject = receipt.credentialSubject || {};
  const badges = [];

  if (subject.teeAttestation) {
    const tee = subject.teeAttestation;
    badges.push(`
      <div class="badge tee-badge">
        <span class="badge-icon">&#128274;</span>
        <div>
          <strong>${esc(T('tee_verified_t'))}</strong>
          <p>${esc(tee.platform || 'Enclave')} — ${esc(tee.enclaveId || '')}</p>
          <p class="badge-detail">${esc(T('tee_code'))} ${esc(truncate(tee.codeHash || '', 20))}</p>
        </div>
      </div>`);
  } else {
    badges.push(`
      <div class="badge tee-badge absent">
        <span class="badge-icon">&#128275;</span>
        <div>
          <strong>${esc(T('tee_none_t'))}</strong>
          <p>${esc(T('tee_none_d'))}</p>
        </div>
      </div>`);
  }

  if (subject.reputationScore != null) {
    const score = subject.reputationScore;
    const pct = Math.round(score * 100);
    badges.push(`
      <div class="badge rep-badge">
        <span class="badge-icon">&#11088;</span>
        <div>
          <strong>${esc(Tf('rep_t', { pct: pct }))}</strong>
          <p>${esc(T('rep_d'))}</p>
        </div>
      </div>`);
  }

  container.innerHTML = badges.join('');
}

function renderProvenanceChain(receipt) {
  const section = document.getElementById('provenance-chain-section');
  const chain = (receipt.credentialSubject || {}).parentReceipts || [];

  if (chain.length === 0) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');

  const container = document.getElementById('provenance-chain');
  container.innerHTML = chain.map((id, i) => `
    <div class="chain-node">
      <span class="chain-step">${esc(Tf('chain_step', { n: i + 1 }))}</span>
      <code>${esc(truncate(id, 30))}</code>
    </div>
    ${i < chain.length - 1 ? '<div class="chain-arrow">&rarr;</div>' : ''}
  `).join('');
}

function renderRawJson(receipt) {
  document.getElementById('raw-json').textContent = JSON.stringify(receipt, null, 2);
}

// ── Helpers ──────────────────────────────────────────────────────────────

function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function truncate(str, len) {
  if (!str) return '';
  return str.length > len ? str.slice(0, len) + '...' : str;
}

function getExampleReceipt() {
  return {
    '@context': [
      'https://www.w3.org/2018/credentials/v1',
      'https://verify.aimarket.org/schemas/provenance-receipt.json'
    ],
    id: 'urn:uuid:example-001',
    type: ['VerifiableCredential', 'AIProvenanceReceipt'],
    issuer: {
      id: 'https://hub.aimarket.org',
      name: 'AIMarket Hub',
      publicKeyJwk: {
        kty: 'OKP',
        crv: 'Ed25519',
        x: '11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo'
      }
    },
    issuanceDate: '2026-05-23T12:00:00Z',
    credentialSubject: {
      modelId: 'claude-sonnet-4@anthropic',
      providerHub: 'https://hub.aimarket.org',
      inputHash: { algorithm: 'SHA-256', value: 'a3f2c8b1e5d4f7a6b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2' },
      outputHash: { algorithm: 'SHA-256', value: 'b4e3d2c1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4' },
      parentReceipts: [],
      timestamp: '2026-05-23T12:00:00Z',
      latencyMs: 2340,
      priceUsd: 0.15
    },
    proof: {
      type: 'Ed25519Signature2018',
      created: '2026-05-23T12:00:01Z',
      verificationMethod: 'did:key:z6MkrJVnaZkeFzdQyMZu1cgjg7k1pZZ6pvBQ7XJPt4swbTQ2',
      proofPurpose: 'assertionMethod',
      proofValue: 'base64signatureplaceholder...'
    },
    hubInfo: {
      hubName: 'AIMarket Hub',
      hubVersion: '3.0.0',
      protocolVersion: 'v2'
    }
  };
}
