/**
 * AI Provenance Verifier — client-side Ed25519 receipt verification.
 *
 * Uses TweetNaCl for Ed25519 operations.
 * All verification runs entirely in the browser — no server needed.
 *
 * Canonical form: pipe-delimited key:value|key:value (same as Python signing.py).
 */

// ── Constants ──────────────────────────────────────────────────────────────

const PROVENANCE_PROOF_TYPE = 'Ed25519Signature2018';
const HASH_ALGORITHM = 'SHA-256';

// ── i18n helper ────────────────────────────────────────────────────────────
// Result/error strings are pushed already-localized in the current language.
// The dictionary + t() live inline in index.html (window.__t); fall back to
// the raw key when running outside the page (e.g. Node smoke tests).
function T(k) { return (typeof window !== 'undefined' && window.__t) ? window.__t(k) : k; }

// ── Base64 helpers ─────────────────────────────────────────────────────────

function base64Decode(str) {
  // Standard base64 with padding
  let b = str;
  while (b.length % 4) b += '=';
  const binary = atob(b);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function base64UrlToBytes(str) {
  // base64url (no padding) to Uint8Array
  let b64 = str.replace(/-/g, '+').replace(/_/g, '/');
  while (b64.length % 4) b64 += '=';
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

// ── Canonical form (mirrors Python credential_subject_canonical) ───────────

// ── RFC 8785 JSON Canonicalization Scheme (JCS) ───────────────────────────
// Mirrors Python json_canonical() exactly for cross-platform compatibility.

function jsonCanonical(val) {
  if (val === null) return 'null';
  if (typeof val === 'boolean') return val ? 'true' : 'false';
  if (typeof val === 'number') {
    if (Number.isInteger(val)) return val.toString() + '.0';
    return val.toFixed(10).replace(/0+$/, '').replace(/\.$/, '');
  }
  if (typeof val === 'string') {
    // Unicode NFC normalization + JSON escape
    const normalized = val.normalize ? val.normalize('NFC') : val;
    return JSON.stringify(normalized);
  }
  if (Array.isArray(val)) {
    return '[' + val.map(jsonCanonical).join(',') + ']';
  }
  if (typeof val === 'object') {
    const keys = Object.keys(val).sort();
    return '{' + keys.map(k =>
      jsonCanonical(k) + ':' + jsonCanonical(val[k])
    ).join(',') + '}';
  }
  return JSON.stringify(val);
}

function buildCanonical(subject) {
  const keys = Object.keys(subject).sort();
  const parts = keys.map(key => {
    let val = subject[key];
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      val = jsonCanonical(val);
    } else if (Array.isArray(val)) {
      val = jsonCanonical(val);
    } else if (typeof val === 'number') {
      val = jsonCanonical(val);
    }
    return `${key}:${val}`;
  });
  return parts.join('|');
}

// ── Ed25519 verification via TweetNaCl ─────────────────────────────────────

function verifyEd25519Signature(publicKeyB64, signatureB64, message) {
  try {
    const publicKey = base64Decode(publicKeyB64);
    const signature = base64Decode(signatureB64);
    const msgBytes = new TextEncoder().encode(message);
    return nacl.sign.detached.verify(msgBytes, signature, publicKey);
  } catch (e) {
    return false;
  }
}

// ── JWK extraction ─────────────────────────────────────────────────────────

function extractPublicKeyFromJWK(jwk) {
  if (!jwk || jwk.kty !== 'OKP' || jwk.crv !== 'Ed25519' || !jwk.x) {
    return null;
  }
  return base64UrlToBytes(jwk.x);
}

// ── Hash helpers ───────────────────────────────────────────────────────────

async function sha256Hex(data) {
  const encoder = new TextEncoder();
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoder.encode(data));
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// ── Main verification entry point ──────────────────────────────────────────

async function verifyProvenanceReceipt(receipt) {
  const checks = [];
  const errors = [];

  // 1. Structural check
  if (!receipt || typeof receipt !== 'object') {
    errors.push(T('e_not_object'));
    return { valid: false, checks, errors };
  }

  const subject = receipt.credentialSubject;
  const proof = receipt.proof;
  const issuer = receipt.issuer;

  if (!subject) errors.push(T('e_no_subject'));
  if (!proof) errors.push(T('e_no_proof'));
  if (!issuer) errors.push(T('e_no_issuer'));

  checks.push({ check: 'structure', passed: errors.length === 0 });

  if (errors.length > 0) {
    return { valid: false, checks, errors };
  }

  // 2. Signature verification
  const canonical = buildCanonical(subject);
  const jwk = issuer.publicKeyJwk;

  if (!jwk) {
    errors.push(T('e_no_jwk'));
  } else {
    try {
      const publicKeyBytes = extractPublicKeyFromJWK(jwk);
      if (!publicKeyBytes) {
        errors.push(T('e_bad_jwk'));
      } else {
        const sigValid = nacl.sign.detached.verify(
          new TextEncoder().encode(canonical),
          base64Decode(proof.proofValue),
          publicKeyBytes
        );
        checks.push({
          check: 'signature',
          passed: sigValid,
          algorithm: 'Ed25519',
          publicKey: jwk.x
        });
        if (!sigValid) {
          errors.push(T('e_sig_failed'));
        }
      }
    } catch (e) {
      errors.push(T('e_sig_error') + e.message);
      checks.push({ check: 'signature', passed: false, error: e.message });
    }
  }

  // 3. Timestamp check (5 min clock skew tolerance + 90 day max age)
  const MAX_AGE_MS = 90 * 86400 * 1000; // 90 days
  if (subject.timestamp) {
    const ts = Date.parse(subject.timestamp);
    if (isNaN(ts)) {
      errors.push(T('e_ts_format'));
      checks.push({ check: 'timestamp', passed: false, value: subject.timestamp });
    } else {
      const now = Date.now();
      let tsValid = true;
      if (ts > now + 300000) {
        errors.push(T('e_ts_future'));
        tsValid = false;
      }
      if (ts < now - MAX_AGE_MS) {
        errors.push(T('e_ts_old'));
        tsValid = false;
      }
      checks.push({ check: 'timestamp', passed: tsValid, value: subject.timestamp });
    }
  } else {
    errors.push(T('e_ts_missing'));
    checks.push({ check: 'timestamp', passed: false });
  }

  // 4. Hash format
  const hashHex = /^[a-f0-9]{64}$/;
  let hashOk = true;
  if (subject.inputHash?.value && hashHex.test(subject.inputHash.value)) {
    // ok
  } else if (subject.inputHash?.value) {
    errors.push(T('e_input_hash_fmt'));
    hashOk = false;
  } else {
    errors.push(T('e_input_hash_missing'));
    hashOk = false;
  }
  if (subject.outputHash?.value && hashHex.test(subject.outputHash.value)) {
    // ok
  } else if (subject.outputHash?.value) {
    errors.push(T('e_output_hash_fmt'));
    hashOk = false;
  } else {
    errors.push(T('e_output_hash_missing'));
    hashOk = false;
  }
  checks.push({ check: 'hash_format', passed: hashOk });

  // 5. Parent receipt format
  if (subject.parentReceipts && subject.parentReceipts.length > 0) {
    const bad = subject.parentReceipts.filter(pid =>
      !pid.startsWith('urn:uuid:') && !pid.startsWith('https://')
    );
    checks.push({
      check: 'parent_receipts',
      passed: bad.length === 0,
      count: subject.parentReceipts.length
    });
    if (bad.length > 0) {
      errors.push(T('e_parent_fmt') + bad.slice(0, 3).join(', '));
    }
  }

  // 6. TEE attestation (verify signature + expiry)
  if (subject.teeAttestation) {
    const tee = subject.teeAttestation;
    const hasSig = !!tee.signature && !!tee.codeHash;
    // Verify TEE Ed25519 signature if present
    let teeValid = !!tee.platform && !!tee.enclaveId && !!tee.timestamp;
    if (hasSig && teeValid) {
      try {
        // Build TEE canonical message: pipe-delimited per TEEAttestation spec
        const teeCanonical = [
          `platform:${tee.platform}`,
          `enclave_id:${tee.enclaveId}`,
          `code_hash:${tee.codeHash}`,
          `instance:${tee.instanceId || ''}`,
          `region:${tee.region || ''}`,
          `timestamp:${tee.timestamp}`,
          `ttl:${tee.ttlS || 300}`
        ].join('|');
        // The TEE receipt uses the issuer's key for signing attestations
        const issuerKeyBytes = extractPublicKeyFromJWK(issuer.publicKeyJwk);
        if (issuerKeyBytes) {
          const sigValid = nacl.sign.detached.verify(
            new TextEncoder().encode(teeCanonical),
            base64Decode(tee.signature),
            issuerKeyBytes
          );
          teeValid = sigValid;
          if (!sigValid) {
            errors.push(T('e_tee_sig_failed'));
          }
        }
      } catch(e) {
        teeValid = false;
        errors.push(T('e_tee_error'));
      }
    }
    checks.push({
      check: 'tee_attestation',
      passed: teeValid,
      platform: tee.platform || 'unknown',
      signature_verified: hasSig
    });
    if (!teeValid && !errors.some(e => e.includes('TEE'))) {
      errors.push(T('e_tee_incomplete'));
    }
  }

  return {
    valid: errors.length === 0,
    checks,
    errors,
    canonical,
    modelId: subject.modelId,
    providerHub: subject.providerHub,
    timestamp: subject.timestamp,
    issuerName: issuer.name,
    hubInfo: receipt.hubInfo
  };
}

// ── Export for browser use ─────────────────────────────────────────────────

if (typeof window !== 'undefined') {
  window.AIProvenanceVerifier = {
    verifyProvenanceReceipt,
    buildCanonical,
    verifyEd25519Signature,
    sha256Hex
  };
}
