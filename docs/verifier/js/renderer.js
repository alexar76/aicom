/**
 * AWR/2 verifier — UI renderer.
 *
 * Renders the §11.1 verification result: the verdict, the per-stage checks, and
 * — the part that matters for interoperability reports — every reason and
 * warning with its STABLE REASON CODE next to the localized meaning, so a user
 * can quote `AWR-PROOF-006` to an issuer without knowing what language the page
 * was in.
 *
 * Localization: strings come from the inline dictionary in index.html through
 * window.__t (see the i18n block there). Reason codes use the flat keys
 * `c_AWR-XXX-000`, so a code with no translation still renders — as the bare
 * code, never as an empty string.
 */

// ── i18n helpers ────────────────────────────────────────────────────────────
function T(k) { return (typeof window !== 'undefined' && window.__t) ? window.__t(k) : k; }
function Tf(k, vars) {
  var s = T(k);
  for (var name in vars) s = s.replace('{' + name + '}', vars[name]);
  return s;
}
/** Localized meaning of a §11.2 reason code; '' when the code is unknown. */
function Tcode(code) {
  var v = T('c_' + code);
  return v === 'c_' + code ? '' : v;
}

// Remember the last verified document so a language switch can re-render it.
var __lastDoc = null;
var __lastResult = null;
if (typeof window !== 'undefined') {
  window.__rerender = function () {
    var rs = document.getElementById('result-section');
    if (!__lastDoc || !__lastResult || !rs || rs.classList.contains('hidden')) return;
    renderResult(__lastDoc, __lastResult);
  };
}

// The caller's freshness policy (SPEC.md §11.3: age is policy, never
// validity). The page keeps surfacing the 90-day mark it always showed, but as
// an AWR-TIME-002 warning instead of a hard failure.
var VERIFY_OPTS = { maxAgeDays: 90 };

document.addEventListener('DOMContentLoaded', function () {
  var inputEl = document.getElementById('receipt-input');
  var verifyBtn = document.getElementById('verify-btn');
  var clearBtn = document.getElementById('clear-btn');
  var exampleBtn = document.getElementById('load-example-btn');
  var errorEl = document.getElementById('error-msg');
  var loadingEl = document.getElementById('loading-msg');
  var resultSection = document.getElementById('result-section');

  function begin(messageKey) {
    errorEl.classList.add('hidden');
    loadingEl.textContent = T(messageKey || 'loading');
    loadingEl.classList.remove('hidden');
    resultSection.classList.add('hidden');
  }

  function endWithError(messageKey) {
    errorEl.textContent = T(messageKey);
    errorEl.classList.remove('hidden');
    loadingEl.classList.add('hidden');
  }

  function proceed(document_) {
    __lastDoc = document_;
    return window.AWR.verify(document_, VERIFY_OPTS).then(function (result) {
      __lastResult = result;
      renderResult(document_, result);
      loadingEl.classList.add('hidden');
      resultSection.classList.remove('hidden');
      var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      resultSection.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' });
    });
  }

  function renderParseFailure(parseFinding) {
    __lastDoc = null;
    __lastResult = {
      valid: false, awrVersion: null, documentType: null, profile: null,
      reasons: [parseFinding], warnings: [], chain: { resolved: 0, unresolved: 0 },
      // §11.1: verifiedProof is present on every result; null here because the bytes
      // never reached §6.3 step 6.
      verifiedProof: null,
      checks: [{ check: 'canonical', passed: false }], legacy: null, errors: []
    };
    renderResult(null, __lastResult);
    loadingEl.classList.add('hidden');
    resultSection.classList.remove('hidden');
  }

  function verifyRawText(rawText, allowId) {
    begin('loading');
    rawText = String(rawText || '').trim();

    if (!rawText) {
      endWithError('err_empty');
      return;
    }

    // §4.1(5): duplicate property names are rejected, which means the document
    // must be parsed from the received TEXT, not from a re-serialization.
    var doc = null, parseFinding = null;
    try {
      doc = window.AWR.parseAwrJson(rawText);
    } catch (e) {
      parseFinding = { code: e.code || 'AWR-CANON-005', severity: 'error', detail: e.detail || e.message };
    }

    if (doc !== null && typeof doc === 'object') { proceed(doc); return; }

    // Not JSON (or JSON we refuse): maybe it is a receipt id we can load.
    var looksLikeId = allowId !== false && /^[A-Za-z0-9:_.-]+$/.test(rawText) && rawText.length < 200;
    if (!looksLikeId) {
      // Show the real reason rather than "not found": a duplicate key or a
      // malformed document is a finding, not a lookup miss.
      renderParseFailure(parseFinding);
      return;
    }
    var id = rawText.split(/[:/]/).pop();
    fetch('data/receipts/' + id + '.json')
      .then(function (resp) {
        if (!resp.ok) throw new Error('not found');
        return resp.text();
      })
      .then(function (text) { return proceed(window.AWR.parseAwrJson(text)); })
      .catch(function () {
        endWithError('err_notfound');
      });
  }

  verifyBtn.addEventListener('click', function () {
    verifyRawText(inputEl.value, true);
  });

  clearBtn.addEventListener('click', function () {
    inputEl.value = '';
    resultSection.classList.add('hidden');
    errorEl.classList.add('hidden');
  });

  exampleBtn.addEventListener('click', function () {
    fetch('data/receipts/example.json')
      .then(function (resp) {
        if (!resp.ok) throw new Error('no example');
        return resp.json();
      })
      .then(function (example) { inputEl.value = JSON.stringify(example, null, 2); })
      .catch(function () {
        // Offline / file:// fallback. This is the same document as
        // data/receipts/example.json, signed with the demo key; it verifies.
        inputEl.value = JSON.stringify(getExampleReceipt(), null, 2);
      });
  });

  // Share-link handoff: retrieve the canonical primary document, then perform
  // exactly the same in-browser verification as a manual paste.  Fetching the
  // document is online; the cryptographic check that follows makes no request.
  var hasReceiptUrl = new URLSearchParams(window.location.search).has('receipt_url');
  if (hasReceiptUrl && window.AWRReceiptUrl) {
    var handoff = window.AWRReceiptUrl.fromSearch(window.location.search);
    if (!handoff.ok) {
      endWithError(handoff.code === 'host' ? 'err_url_host' : 'err_url_invalid');
      return;
    }

    begin('loading_url');
    var controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timeout = window.setTimeout(function () {
      if (controller) controller.abort();
    }, 8000);

    fetch(handoff.url, {
      method: 'GET',
      cache: 'no-store',
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      headers: { Accept: 'application/vc, application/json' },
      signal: controller ? controller.signal : undefined
    }).then(function (resp) {
      if (!resp.ok) throw { code: 'fetch' };
      var declared = Number(resp.headers.get('content-length') || 0);
      if (declared > window.AWRReceiptUrl.MAX_RECEIPT_BYTES) throw { code: 'size' };
      var contentType = String(resp.headers.get('content-type') || '').toLowerCase();
      if (contentType && !/(application\/(vc|json)|\+json)/.test(contentType)) {
        throw { code: 'type' };
      }
      return resp.text();
    }).then(function (text) {
      var bytes = typeof TextEncoder !== 'undefined' ? new TextEncoder().encode(text).length : text.length;
      if (bytes > window.AWRReceiptUrl.MAX_RECEIPT_BYTES) throw { code: 'size' };
      inputEl.value = text;
      return verifyRawText(text, false);
    }).catch(function (error) {
      var key = error && error.code === 'size' ? 'err_url_size'
        : error && error.code === 'type' ? 'err_url_type'
        : 'err_url_fetch';
      endWithError(key);
    }).finally(function () {
      window.clearTimeout(timeout);
    });
  }
});

// ── Render ──────────────────────────────────────────────────────────────────

function renderResult(doc, result) {
  renderVerdict(result);
  renderMeta(doc, result);
  renderChecks(result);
  renderAttestations(doc, result);
  renderProvenanceChain(doc, result);
  renderRawJson(doc);
}

function renderVerdict(result) {
  var banner = document.getElementById('verdict-banner');
  var errorCount = result.reasons ? result.reasons.length : 0;
  var parts = [];

  if (result.valid) {
    parts.push('<div class="verdict pass">' +
      '<span class="verdict-icon">&#10003;</span><div>' +
      '<strong>' + esc(T('verdict_pass_t')) + '</strong>' +
      '<p>' + esc(T('verdict_pass_d')) + '</p></div></div>');
  } else {
    parts.push('<div class="verdict fail">' +
      '<span class="verdict-icon">&#10007;</span><div>' +
      '<strong>' + esc(T('verdict_fail_t')) + '</strong>' +
      '<p>' + esc(Tf('verdict_fail_d', { n: errorCount })) + '</p></div></div>');
  }

  // §10.4: report the profile, and never let a document claim one. An AWR/1
  // document has no AWR/2 profile at all — saying "None, did not verify" about
  // a legacy document that DID verify under §12 would be simply false.
  var profKey = result.profile ? 'prof_' + result.profile
              : (result.legacy ? 'prof_legacy' : 'prof_none');
  parts.push('<div class="profile-line"><span class="meta-label">' + esc(T('prof_label')) +
    '</span> <strong>' + esc(result.profile || '—') + '</strong> — ' + esc(T(profKey)) + '</div>');

  // §12: an AWR/1 document verifies far less than an AWR/2 one. Say so.
  if (result.legacy) {
    parts.push('<div class="legacy-note"><strong>' + esc(T('legacy_t')) + '</strong>' +
      '<p>' + esc(T('legacy_d')) + '</p>' +
      (result.legacy.dialect
        ? '<p class="badge-detail">' + esc(T('dialect_label')) + ' ' + esc(result.legacy.dialect) + '</p>'
        : '') +
      '<p class="badge-detail">' + esc(T('unsigned_label')) + ' <code>' +
      esc((result.legacy.unsignedFields || []).join(', ')) + '</code></p></div>');
  }

  parts.push(findingsBlock('reasons_h', result.reasons || [], 'reason-error'));
  parts.push(findingsBlock('warnings_h', result.warnings || [], 'reason-warning'));
  if ((result.reasons || []).length === 0 && (result.warnings || []).length === 0) {
    parts.push('<p class="no-issues">' + esc(T('no_issues')) + '</p>');
  }

  // §13.7: validity is attribution, not truth.
  parts.push('<details class="meaning-note"><summary>' + esc(T('meaning_h')) + '</summary><p>' +
    esc(T('meaning_d')) + '</p></details>');

  banner.innerHTML = parts.join('');
}

/**
 * One finding per row: the STABLE CODE first (so it can be reported verbatim),
 * then the localized meaning, then the issuer-facing English detail.
 */
function findingsBlock(titleKey, list, cls) {
  if (!list || list.length === 0) return '';
  var rows = list.map(function (r) {
    if (!r) return '';
    var meaning = Tcode(r.code);
    return '<li class="' + cls + '">' +
      '<code class="reason-code">' + esc(r.code) + '</code>' +
      (meaning ? '<span class="reason-meaning">' + esc(meaning) + '</span>' : '') +
      (r.detail ? '<span class="reason-detail">' + esc(r.detail) + '</span>' : '') +
      '</li>';
  }).join('');
  return '<div class="findings"><strong>' + esc(T(titleKey)) + ' (' + list.length + ')</strong>' +
         '<ul>' + rows + '</ul></div>';
}

function renderMeta(doc, result) {
  var meta = document.getElementById('receipt-meta');
  if (!doc) { meta.innerHTML = ''; return; }
  var subject = doc.credentialSubject || {};
  var work = subject.work || {};
  var issuer = doc.issuer || {};
  // AWR/2 field names, falling back to the AWR/1 ones for legacy documents.
  var modelId = work.modelId || subject.modelId || '';
  var capability = work.capability || '';
  var status = work.status || '';
  var issued = doc.validFrom || subject.timestamp || doc.issuanceDate || '';
  var latency = work.latencyMs != null ? work.latencyMs : subject.latencyMs;
  var price = subject.price
    ? (subject.price.amount + ' ' + subject.price.currency)
    : (subject.priceUsd != null ? '$' + subject.priceUsd : '');
  var issuerId = typeof issuer === 'string' ? issuer : (issuer.id || '');
  var issuerName = typeof issuer === 'string' ? '' : (issuer.name || '');
  var inputDigest = typeof subject.inputDigest === 'string'
    ? subject.inputDigest : (subject.inputHash && subject.inputHash.value);
  var outputDigest = typeof subject.outputDigest === 'string'
    ? subject.outputDigest : (subject.outputHash && subject.outputHash.value);

  function cell(label, value, mono) {
    var text = value || '—';
    var title = '';
    if (text !== '—') {
      title = ' title="' + esc(text).replace(/"/g, '&quot;') + '"';
    }
    return '<div class="meta-item"><span class="meta-label">' + esc(label) + '</span>' +
      '<span class="meta-value' + (mono ? ' mono' : '') + '"' + title + '>' +
      esc(text) + '</span></div>';
  }

  // SPEC section 12.4: an AWR/1 `issuer` is outside the signature. Printing it beside a
  // green badge is the whole exploit -- the reader sees a DID and a tick and concludes
  // that DID's owner signed something. On the legacy path the page prints the KEY the
  // signature verified under, and shows the document's own issuer under "outside the
  // signature", where it belongs.
  var issuerBlock = result.legacy
    ? '<div class="meta-item full-width"><span class="meta-label">' + esc(T('m_issuer')) +
        '</span><span class="meta-value mono"><code>' +
        esc(result.legacy.verifiedKey || '—') + '</code></span></div>' +
      '<div class="meta-item full-width"><span class="meta-label">' + esc(T('unsigned_label')) +
        '</span><span class="meta-value">' + esc(issuerName || '—') + ' <code>' +
        esc(issuerId || '—') + '</code></span></div>'
    : '<div class="meta-item full-width"><span class="meta-label">' + esc(T('m_issuer')) +
        '</span><span class="meta-value">' + esc(issuerName || '—') + ' <code>' +
        esc(issuerId || '—') + '</code></span></div>';

  meta.innerHTML =
    '<div class="meta-grid">' +
      cell(T('m_doctype'), result.documentType || (result.legacy ? 'AWR/1' : '—')) +
      cell(T('m_model'), modelId, true) +
      cell(T('m_capability'), capability, true) +
      cell(T('m_status'), status) +
      cell(T('m_issued'), issued) +
      cell(T('m_latency'), latency != null ? latency + ' ms' : '') +
      cell(T('m_price'), price) +
      cell(T('m_receipt_id'), truncate(doc.id, 44), true) +
    '</div>' +
    issuerBlock +
    (inputDigest ? '<details class="hash-section"><summary>' + esc(T('input_hash')) +
      '</summary><code>' + esc(inputDigest) + '</code></details>' : '') +
    (outputDigest ? '<details class="hash-section"><summary>' + esc(T('output_hash')) +
      '</summary><code>' + esc(outputDigest) + '</code></details>' : '');
}

function renderChecks(result) {
  var container = document.getElementById('checks-list');
  var checks = result.checks || [];
  container.innerHTML = checks.map(function (check) {
    var icon = check.passed ? '&#10003;' : '&#10007;';
    var cls = check.passed ? 'check-pass' : 'check-fail';
    var detail = '';
    if (check.algorithm) detail += ' | ' + esc(check.algorithm);
    if (check.value) detail += ' | ' + esc(check.value);
    return '<div class="check-item ' + cls + '">' +
      '<span class="check-icon">' + icon + '</span>' +
      '<span class="check-label">' + esc(T('check_' + check.check)) + '</span>' +
      '<span class="check-detail">' + detail + '</span></div>';
  }).join('');
}

function renderAttestations(doc, result) {
  var container = document.getElementById('attestation-badges');
  if (!doc) { container.innerHTML = ''; return; }
  var subject = doc.credentialSubject || {};
  var env = subject.environment || {};
  // AWR/1 carried the attestation directly on the subject.
  var present = [];
  if (env.teeAttestation) present.push({ kind: 'teeAttestation', body: env.teeAttestation });
  if (env.zkProof) present.push({ kind: 'zkProof', body: env.zkProof });
  if (subject.teeAttestation) present.push({ kind: 'teeAttestation', body: subject.teeAttestation });

  var badges = [];
  if (present.length === 0) {
    badges.push('<div class="badge tee-badge absent"><span class="badge-icon">&#128275;</span><div>' +
      '<strong>' + esc(T('tee_none_t')) + '</strong><p>' + esc(T('tee_none_d')) + '</p></div></div>');
  } else {
    // §7.3: opaque. There is no "TEE Verified" state in this verifier, because
    // the only key it holds is the receipt issuer's, and checking a hardware
    // attestation with the claimant's own key proves nothing at all.
    present.forEach(function (att) {
      var body = att.body || {};
      badges.push('<div class="badge tee-badge unverified"><span class="badge-icon">&#9888;</span><div>' +
        '<strong>' + esc(T('tee_unverified_t')) + '</strong>' +
        '<p><code>' + esc(att.kind) + '</code>' +
        (body.platform ? ' — ' + esc(body.platform) : '') +
        (body.enclaveId ? ' <code>' + esc(body.enclaveId) + '</code>' : '') + '</p>' +
        (body.codeHash ? '<p class="badge-detail">' + esc(T('tee_code')) + ' ' +
          esc(truncate(body.codeHash, 24)) + '</p>' : '') +
        '<p class="badge-detail"><code class="reason-code">AWR-ENV-001</code> ' +
        esc(T('tee_unverified_d')) + '</p></div></div>');
    });
  }
  container.innerHTML = badges.join('');
}

function renderProvenanceChain(doc, result) {
  var section = document.getElementById('provenance-chain-section');
  var container = document.getElementById('provenance-chain');
  if (!doc) { section.classList.add('hidden'); return; }
  var subject = doc.credentialSubject || {};
  var parents = Array.isArray(subject.parents) ? subject.parents : [];
  var legacyParents = Array.isArray(subject.parentReceipts) ? subject.parentReceipts : [];
  var chain = result.chain || { resolved: 0, unresolved: 0 };

  if (parents.length === 0 && legacyParents.length === 0) {
    section.classList.remove('hidden');
    container.innerHTML = '<p class="no-issues">' + esc(T('chain_none')) + '</p>';
    return;
  }
  section.classList.remove('hidden');

  var summary = '<p class="chain-summary"><span class="meta-label">' + esc(T('chain_label')) + '</span> ' +
    esc(Tf('chain_resolved', { n: chain.resolved })) + ' &middot; ' +
    esc(Tf('chain_unresolved', { n: chain.unresolved })) + '</p>';

  var nodes = parents.map(function (ref, i) {
    return '<div class="chain-node">' +
      '<span class="chain-step">' + esc(Tf('chain_step', { n: i + 1 })) + '</span>' +
      (ref.role ? '<span class="chain-role">' + esc(ref.role) + '</span>' : '') +
      '<code>' + esc(truncate(ref.id || '', 40)) + '</code>' +
      '<code class="chain-digest">' + esc(truncate(ref.digestSRI || '', 24)) + '</code></div>';
  }).concat(legacyParents.map(function (id, i) {
    // AWR/1 edges are identifiers only: not content-addressed, hence re-pointable.
    return '<div class="chain-node"><span class="chain-step">' +
      esc(Tf('chain_step', { n: i + 1 })) + '</span><code>' + esc(truncate(String(id), 40)) +
      '</code><code class="reason-code">AWR-CHAIN-001</code></div>';
  })).join('<div class="chain-arrow">&rarr;</div>');

  container.innerHTML = summary + nodes;
}

function renderRawJson(doc) {
  document.getElementById('raw-json').textContent = doc ? JSON.stringify(doc, null, 2) : '';
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function esc(str) {
  if (str === null || str === undefined || str === '') return '';
  var div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function truncate(str, len) {
  if (!str) return '';
  str = String(str);
  return str.length > len ? str.slice(0, len) + '…' : str;
}

/**
 * Offline fallback for "Load Example" — byte-identical to
 * data/receipts/example.json. Every value here was produced by signing that
 * document with the demo key; it verifies as a real L0 receipt, and its
 * attestation deliberately triggers the AWR-ENV-001 warning.
 */
function getExampleReceipt() {
  return {
    '@context': [
      'https://www.w3.org/ns/credentials/v2',
      'https://verify.modelmarket.dev/ns/awr/v2'
    ],
    id: 'urn:uuid:7a8b9c0d-1e2f-4a3b-8c4d-5e6f708192a3',
    type: ['VerifiableCredential', 'WorkReceipt'],
    issuer: {
      id: 'did:key:z6Mkm81s5Do97Q6cEy8guhZLNGEvDGY6cTBbx4KWVNSk4B1W',
      name: 'modelmarket-hub (demo key)'
    },
    validFrom: '2026-07-30T10:15:30Z',
    awrVersion: '2.0.0',
    credentialSubject: {
      work: {
        modelId: 'claude-sonnet-5@anthropic',
        capability: 'urn:example:capability:summarise',
        startedAt: '2026-07-30T10:15:28Z',
        completedAt: '2026-07-30T10:15:30Z',
        latencyMs: 2340,
        status: 'succeeded'
      },
      inputDigest: 'sha256-RwiL7tqwTemBqsWP1cmHuVuhYx1PibORCO0O11vAQi4=',
      outputDigest: 'sha256-FBSXJZyIaUdzfGG+jQxE5cQtIv2BxmXL98x9NRcTWuI=',
      price: { currency: 'USD', amount: '0.15' },
      nonce: '01J9Z8QK4T7YB2N5V6W8XA3C0D',
      environment: {
        teeAttestation: {
          platform: 'aws-nitro',
          enclaveId: 'i-0abcd1234efgh5678',
          codeHash: 'c4551a6b17b69e1860b71875805ac7c515c690f44a675cba62187faa15ab8b0e',
          document: 'b3BhcXVlIGF0dGVzdGF0aW9uIGRvY3VtZW50'
        }
      },
      awrProfile: 'L0'
    },
    proof: {
      type: 'DataIntegrityProof',
      cryptosuite: 'eddsa-jcs-2022',
      created: '2026-07-30T10:15:30Z',
      verificationMethod: 'did:key:z6Mkm81s5Do97Q6cEy8guhZLNGEvDGY6cTBbx4KWVNSk4B1W#z6Mkm81s5Do97Q6cEy8guhZLNGEvDGY6cTBbx4KWVNSk4B1W',
      proofPurpose: 'assertionMethod',
      proofValue: 'z4yGjKpEjFuSxcDuPmkSHgtzpSYyCz2X2Qjo2casMo4hw84CATarQaSF6BqeRD1vqp92k1k1wr4wpPRVNTwtCHur8'
    }
  };
}
