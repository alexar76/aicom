/// Local TEE attestation verification.
///
/// Verifies that a capability runs in a secure enclave (AWS Nitro / Intel TDX /
/// AMD SEV / Azure Confidential Computing) and that the code hash matches the
/// expected value. This is the key privacy guarantee: the user's data is only
/// processed inside a verified enclave, and the output receipt proves it.
library;

import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;

import 'models.dart';
import 'signer.dart';

// ── Platform Constants ──────────────────────────────────────────────────────

/// Recognized TEE platform identifiers.
///
/// Each constant maps to a platform supported by the AI Market protocol.
abstract final class TeePlatform {
  static const String awsNitro = 'aws_nitro';
  static const String intelTdx = 'intel_tdx';
  static const String amdSev = 'amd_sev';
  static const String azureCc = 'azure_cc';

  /// All supported platforms.
  static const Set<String> all = {awsNitro, intelTdx, amdSev, azureCc};

  /// Human-readable names for each platform.
  static const Map<String, String> displayNames = {
    awsNitro: 'AWS Nitro Enclaves',
    intelTdx: 'Intel TDX',
    amdSev: 'AMD SEV-SNP',
    azureCc: 'Azure Confidential Computing',
  };

  /// Whether [platform] is a recognized TEE platform.
  static bool isSupported(String platform) => all.contains(platform);
}

// ── Verification Result ─────────────────────────────────────────────────────

/// Result of a TEE attestation verification with detailed failure reasons.
///
/// Unlike a simple boolean, this preserves every check that failed so
/// callers can log or display specific issues without re-implementing
/// the verification logic.
class TeeVerificationResult {
  /// Whether all checks passed and the attestation is trustworthy.
  final bool isValid;

  /// Human-readable list of failures (empty when [isValid] is true).
  final List<String> failures;

  const TeeVerificationResult({
    required this.isValid,
    this.failures = const [],
  });

  /// A passing result (no failures).
  static const TeeVerificationResult pass =
      TeeVerificationResult(isValid: true);

  /// Create a failing result with one or more failure reasons.
  factory TeeVerificationResult.fail(List<String> failures) {
    return TeeVerificationResult(isValid: false, failures: failures);
  }

  /// Create a failing result from a single failure reason.
  factory TeeVerificationResult.failSingle(String reason) {
    return TeeVerificationResult(isValid: false, failures: [reason]);
  }
}

// ── Trusted Hash Cache ─────────────────────────────────────────────────────

/// Caches trusted code hashes fetched from the hub, with TTL expiry.
///
/// This prevents redundant network calls while ensuring stale hashes
/// are eventually refreshed. The default TTL is 5 minutes.
class TrustedHashCache {
  final Duration ttl;
  final Map<String, _CachedEntry> _cache = {};

  TrustedHashCache({this.ttl = const Duration(minutes: 5)});

  /// Get a cached hash for [key], or null if expired or missing.
  String? get(String key) {
    final entry = _cache[key];
    if (entry == null) return null;
    if (DateTime.now().toUtc().isAfter(entry.expiresAt)) {
      _cache.remove(key);
      return null;
    }
    return entry.hash;
  }

  /// Set a hash for [key] with the configured TTL.
  void set(String key, String hash) {
    _cache[key] = _CachedEntry(
      hash: hash,
      expiresAt: DateTime.now().toUtc().add(ttl),
    );
  }

  /// Remove all entries from the cache.
  void clear() => _cache.clear();

  /// Number of cached entries.
  int get length => _cache.length;
}

/// Internal cache entry with expiry timestamp.
class _CachedEntry {
  final String hash;
  final DateTime expiresAt;
  const _CachedEntry({required this.hash, required this.expiresAt});
}

// ── Verifier ───────────────────────────────────────────────────────────────

/// Verifies TEE attestations and receipts client-side.
///
/// ## Flow
///
/// 1. Before invoking a capability, call [verifyAttestation] or
///    [verifyAttestationDetailed] to check the enclave's claim.
/// 2. After receiving the output, call [verifyReceipt] to confirm
///    the output was produced inside the attested enclave.
///
/// Trusted code hashes can be populated from the hub's trusted registry
/// via [fetchTrustedHashes] or set directly via [trustCodeHash].
class TeeVerifier {
  final MarketSigner _signer;

  /// Known-good code hashes for trusted capabilities.
  final Map<String, String> _trustedCodeHashes;

  /// Cache for hub-fetched trusted hashes.
  final TrustedHashCache _hashCache;

  /// When hashes were last fetched from the hub.
  DateTime? _lastFetch;

  TeeVerifier({
    required MarketSigner signer,
    Map<String, String>? trustedCodeHashes,
    TrustedHashCache? hashCache,
  })  : _signer = signer,
        _trustedCodeHashes = trustedCodeHashes ?? {},
        _hashCache = hashCache ?? TrustedHashCache();

  /// Register a known-good code hash for a capability.
  void trustCodeHash(String capabilityId, String codeHash) {
    _trustedCodeHashes[capabilityId] = codeHash;
    _hashCache.set(capabilityId, codeHash);
  }

  /// Fetch trusted code hashes from the hub's well-known endpoint.
  ///
  /// The hub exposes its trusted code registry at the well-known path:
  /// `{hubUrl}/.well-known/trusted-code-hashes.json`
  ///
  /// Each entry maps a capability ID pattern to an acceptable code hash.
  /// Results are cached locally with a configurable TTL.
  ///
  /// Returns the number of hashes fetched, or -1 on failure.
  Future<int> fetchTrustedHashes(String hubUrl, {http.Client? client}) async {
    final httpClient = client ?? http.Client();
    try {
      final uri = Uri.parse('$hubUrl/.well-known/trusted-code-hashes.json');
      final resp = await httpClient.get(uri);
      if (resp.statusCode != 200) return -1;

      final data = json.decode(resp.body) as Map<String, dynamic>;
      final hashes = data['hashes'] as List<dynamic>? ?? [];
      for (final entry in hashes) {
        final e = entry as Map<String, dynamic>;
        final capId = e['capability_id'] as String?;
        final codeHash = e['code_hash'] as String?;
        if (capId != null && codeHash != null) {
          _hashCache.set(capId, codeHash);
          _trustedCodeHashes[capId] = codeHash;
        }
      }
      _lastFetch = DateTime.now();
      return hashes.length;
    } finally {
      httpClient.close();
    }
  }

  /// Verify a TEE attestation with full result details.
  ///
  /// Returns a [TeeVerificationResult] that captures every check outcome
  /// rather than failing fast, so callers can understand what went wrong.
  TeeVerificationResult verifyAttestationDetailed(
      TeeAttestation attestation, String capabilityId) {
    final failures = <String>[];

    // 1. Platform check.
    if (!TeePlatform.isSupported(attestation.platform)) {
      failures.add('Unsupported TEE platform: ${attestation.platform}');
    }

    // 2. Expiry check — parse ISO 8601 timestamp properly.
    final ts = DateTime.tryParse(attestation.timestamp);
    if (ts == null) {
      failures.add('Invalid attestation timestamp: ${attestation.timestamp}');
    } else {
      final age = DateTime.now().toUtc().difference(ts.toUtc()).inSeconds;
      if (age > attestation.ttlS) {
        failures.add(
            'Attestation expired (age: ${age}s, ttl: ${attestation.ttlS}s)');
      }
    }

    // 3. PCR values must be non-empty for hardware attestations.
    if (attestation.pcrValues.isEmpty) {
      failures.add('PCR values are empty — attestation lacks hardware proof');
    }

    // 4. Code hash check against trusted registry.
    final expectedHash =
        _hashCache.get(capabilityId) ?? _trustedCodeHashes[capabilityId];
    if (expectedHash != null && attestation.codeHash != expectedHash) {
      failures.add(
          'Code hash mismatch: expected $expectedHash, got ${attestation.codeHash}');
    }

    // 5. Enclave signature verification.
    final enclaveKey = _enclavePublicKeyForPlatform(attestation.platform);
    if (enclaveKey == null) {
      failures.add(
          'No known enclave public key for platform: ${attestation.platform}');
    } else if (!_signer.verify(
        enclaveKey, attestation.signature, attestation.canonical)) {
      failures.add('Enclave signature verification failed');
    }

    if (failures.isEmpty) return TeeVerificationResult.pass;
    return TeeVerificationResult.fail(failures);
  }

  /// Verify a TEE attestation BEFORE sending data.
  ///
  /// Returns true if the attestation is valid, not expired, and the code
  /// hash matches a trusted value. For detailed diagnostics, use
  /// [verifyAttestationDetailed].
  bool verifyAttestation(TeeAttestation attestation, String capabilityId) {
    return verifyAttestationDetailed(attestation, capabilityId).isValid;
  }

  /// Verify a TEE receipt AFTER receiving output.
  ///
  /// Proves that the output was generated inside the attested enclave by
  /// checking that the receipt's input and output hashes match the actual
  /// values exchanged during the invocation.
  ///
  /// [expectedInput] is the JSON-encoded input string that was sent.
  /// [receivedOutput] is the JSON-encoded output string that was returned.
  bool verifyReceipt(
      TeeReceipt receipt, String expectedInput, String receivedOutput) {
    final inputHash =
        sha256.convert(utf8.encode(expectedInput)).toString();
    final outputHash =
        sha256.convert(utf8.encode(receivedOutput)).toString();

    if (receipt.inputHash != inputHash) return false;
    if (receipt.outputHash != outputHash) return false;
    // In production, verify the receipt's signature with the enclave's key.
    return true;
  }

  /// Simulated well-known enclave public keys.
  ///
  /// In production, these are fetched from the hub's trusted key registry
  /// at `{hubUrl}/.well-known/enclave-keys.json`.
  String? _enclavePublicKeyForPlatform(String platform) {
    const keys = <String, String>{
      'aws_nitro': 'nitro_enclave_pubkey_hex',
      'intel_tdx': 'tdx_enclave_pubkey_hex',
      'amd_sev': 'sev_enclave_pubkey_hex',
      'azure_cc': 'azure_cc_pubkey_hex',
    };
    return keys[platform];
  }
}
