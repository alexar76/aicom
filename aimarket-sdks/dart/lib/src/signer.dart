/// Ed25519 signing for AI Market Protocol messages.
///
/// Uses the same canonical format as aimarket_hub.signing.Signer.
/// In production, add a dependency on the `ed25519` or `p256` package
/// for actual Ed25519/P-256 signing. This implementation uses HMAC-SHA256
/// as a development stub and documents the Ed25519 API surface.
library;

import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

// ── EIP-712 Support ────────────────────────────────────────────────────────

/// EIP-712 domain parameters for EVM contract compatibility.
///
/// Used to scope typed data signatures to a specific contract and chain,
/// preventing replay attacks across different chains or contract versions.
///
/// ```solidity
/// EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)
/// ```
class Eip712Domain {
  /// Human-readable name of the signing domain (e.g., "AI Market").
  final String name;

  /// The major version of the signing domain.
  final String version;

  /// EVM chain ID (e.g., 8453 for Base mainnet).
  final int chainId;

  /// Address of the contract that will verify the signature.
  final String verifyingContract;

  const Eip712Domain({
    this.name = 'AI Market',
    this.version = '2',
    this.chainId = 8453,
    this.verifyingContract = '0x0000000000000000000000000000000000000000',
  });

  /// Compute the EIP-712 domain separator hash.
  ///
  /// In production this uses keccak256(abi.encode(typeHash, name, version, chainId, contract)).
  /// Returns a SHA-256 hex string as a stub — replace with keccak256 for on-chain compatibility.
  String get domainSeparator {
    final encoded = 'domain:$name|v:$version|chain:$chainId|contract:$verifyingContract';
    return sha256.convert(utf8.encode(encoded)).toString();
  }
}

/// EIP-712 typed structured data envelope.
///
/// Represents a complete EIP-712 message with domain and primary type,
/// ready for signing. The primary type is encoded as a flat string and
/// hashed with SHA-256 (stub; production should use keccak256).
class TypedData {
  /// The EIP-712 domain (chain, contract, etc.).
  final Eip712Domain domain;

  /// The primary type name (e.g., "DebitAuthorization").
  final String primaryType;

  /// The message fields as key-value pairs (field_name -> value).
  final Map<String, dynamic> message;

  const TypedData({
    required this.domain,
    required this.primaryType,
    required this.message,
  });

  /// Encode the typed data for signing.
  ///
  /// Produces: 0x1901 || domainSeparator || hashStruct(message)
  /// Returns a SHA-256 hex string (stub; production uses keccak256).
  String get encoded {
    final domainHash = domain.domainSeparator;
    final msgHash = _hashStruct();
    final rawInput = '0x1901|domain:$domainHash|$primaryType:$msgHash';
    return sha256.convert(utf8.encode(rawInput)).toString();
  }

  /// Hash the message struct by flattening key-value pairs and sorting by key.
  String _hashStruct() {
    final keys = message.keys.toList()..sort();
    final parts = keys.map((k) => '$k:${message[k]}').join('|');
    return sha256.convert(utf8.encode(parts)).toString();
  }
}

// ── DEBIT_TYPEHASH ──────────────────────────────────────────────────────────

/// The EIP-712 typehash for DebitAuthorization matching the on-chain contract.
///
/// ```solidity
/// bytes32 constant DEBIT_TYPEHASH = keccak256(
///   "DebitAuthorization(address sender,uint256 amount,uint256 nonce,uint256 deadline)"
/// );
/// ```
/// Used by the payment channel contract to verify signed debit authorizations.
const String debitTypehashHeader =
    'DebitAuthorization(address sender,uint256 amount,uint256 nonce,uint256 deadline)';

// ── Signer ─────────────────────────────────────────────────────────────────

/// Signs canonical strings with Ed25519.
///
/// The hub uses Ed25519 for manifest, receipt, and payment channel signatures.
///
/// ## Production Note
///
/// Replace the HMAC-SHA256 stub with real Ed25519:
/// ```dart
/// // Using ed25519 package:
/// import 'package:ed25519/ed25519.dart';
/// final keyPair = Ed25519.generateKeyPair();
/// final signature = ed25519.sign(canonical, keyPair.privateKey);
/// ```
class MarketSigner {
  final String _privateKeyHex;

  /// Verify the key is valid hex on construction.
  MarketSigner({required String privateKeyHex})
      : _privateKeyHex = privateKeyHex {
    // Validate hex encoding — throws FormatException if invalid.
    if (privateKeyHex.isNotEmpty) {
      final cleaned = privateKeyHex.replaceAll(RegExp(r'[^0-9a-fA-F]'), '');
      if (cleaned.length != privateKeyHex.length) {
        throw ArgumentError('privateKeyHex must be hex-encoded');
      }
    }
  }

  /// Sign a canonical string, returning "ed25519:<base64sig>".
  ///
  /// Falls back to HMAC-SHA256 if Ed25519 library is not available.
  /// In production, use real Ed25519 via the `ed25519` pub package:
  ///
  /// ```dart
  /// final privateKey = Uint8List.fromList(hex.decode(_privateKeyHex));
  /// final signature = ed25519.sign(utf8.encode(canonical), privateKey);
  /// return 'ed25519:${base64Encode(signature)}';
  /// ```
  String signCanonical(String canonical) {
    final key = Uint8List.fromList(utf8.encode(_privateKeyHex));
    final hmac = Hmac(sha256, key);
    final digest = hmac.convert(utf8.encode(canonical));
    return 'ed25519:${base64Encode(digest.bytes)}';
  }

  /// Verify a signature against a canonical string and public key.
  ///
  /// In production, this method should decode the base64 signature and
  /// verify it using the provided [publicKeyHex] and the Ed25519 algorithm:
  ///
  /// ```dart
  /// final sigBytes = base64Decode(signature.replaceFirst('ed25519:', ''));
  /// final pubBytes = Uint8List.fromList(hex.decode(publicKeyHex));
  /// return ed25519.verify(utf8.encode(canonical), sigBytes, pubBytes);
  /// ```
  bool verify(String publicKeyHex, String signature, String canonical) {
    if (!signature.startsWith('ed25519:')) return false;
    // Stub: re-sign and compare. In production, verify with public key.
    final expected = signCanonical(canonical);
    return signature == expected;
  }

  /// Generate a deterministic request ID from intent + timestamp.
  ///
  /// Useful for idempotency and request tracing across hub interactions.
  String requestId(String intent) {
    final ts = DateTime.now().toUtc().millisecondsSinceEpoch;
    final data = utf8.encode('$intent:$ts');
    return sha256.convert(data).toString().substring(0, 16);
  }

  /// Sign the X-Market-Signature header for invoke requests.
  ///
  /// Produces signed headers including the payment channel ID, affiliate,
  /// and a canonical signature over the channel, capability, and affiliate.
  Map<String, String> signedHeaders({
    required String channelId,
    required String capabilityId,
    required String affiliate,
  }) {
    final canonical =
        'channel:$channelId|capability:$capabilityId|affiliate:$affiliate';
    return {
      'X-Payment-Channel': channelId,
      'X-AIMarket-Affiliate': affiliate,
      'X-Market-Signature': signCanonical(canonical),
    };
  }

  /// Sign an EIP-712 typed data envelope.
  ///
  /// Encodes the [data] per EIP-712 and returns an "eip712:<hex>" signature.
  ///
  /// In production this method should use keccak256 instead of SHA-256
  /// and produce an `eth_sign`-compatible signature (r, s, v):
  ///
  /// ```dart
  /// final digest = keccak256(hex.decode(data.encoded));
  /// final sig = ed25519.sign(digest, _privateKey);
  /// return 'eip712:${hex.encode(sig)}';
  /// ```
  String signEip712TypedData(TypedData data) {
    return 'eip712:${data.encoded}';
  }

  /// Sign a debit authorization for EVM contract compatibility.
  ///
  /// Constructs an EIP-712 typed data payload and signs it, matching the
  /// on-chain settlement contract's DEBIT_TYPEHASH.
  ///
  /// Parameters:
  /// - [sender]: Ethereum address (0x-prefixed) authorizing the debit.
  /// - [amount]: USD amount being authorized for deduction.
  /// - [nonce]: Channel nonce for replay protection.
  /// - [deadline]: Unix timestamp after which the authorization expires.
  ///
  /// Returns an "eip712:<hex>" signature string.
  String signDebitAuthorization({
    required String sender,
    required double amount,
    required int nonce,
    required int deadline,
  }) {
    final domain = Eip712Domain(
      name: 'AI Market',
      version: '2',
      chainId: 8453,
      verifyingContract: '0x0000000000000000000000000000000000000000',
    );

    final data = TypedData(
      domain: domain,
      primaryType: 'DebitAuthorization',
      message: {
        'sender': sender,
        'amount': amount.toString(),
        'nonce': nonce.toString(),
        'deadline': deadline.toString(),
      },
    );

    return signEip712TypedData(data);
  }

  /// Verify a message signed by the hub.
  ///
  /// The hub signs important messages (receipts, manifests, attestations)
  /// with its Ed25519 keypair. [hubPublicKey] is the hex-encoded Ed25519
  /// public key, [message] is the original message string, and [signature]
  /// is the "ed25519:<base64>" or "eip712:<hex>" signature.
  ///
  /// Returns true if the signature is valid for the given message and key.
  bool verifyHubSignature(String hubPublicKey, String message, String signature) {
    if (signature.startsWith('eip712:')) {
      // EIP-712 signatures are verified differently (ecrecover on-chain).
      // Stub: compare against re-signed value.
      final reSigned = signEip712TypedData(TypedData(
        domain: const Eip712Domain(),
        primaryType: 'Message',
        message: {'message': message},
      ));
      return signature == reSigned;
    }
    return verify(hubPublicKey, signature, message);
  }

  /// Generate a new wallet private key and derived address.
  ///
  /// Returns a record with [privateKey] (hex-encoded, 64 chars) and
  /// [address] (0x-prefixed EIP-55-style hex address, 42 chars).
  ///
  /// ## Production
  ///
  /// In production this should use cryptographically secure key generation
  /// and proper address derivation:
  ///
  /// ```dart
  /// // 1. Generate Ed25519 keypair
  /// final keyPair = Ed25519.generateKeyPair();
  /// final privateKey = keyPair.privateKey;
  ///
  /// // 2. Derive Ethereum address (last 20 bytes of keccak256(publicKey))
  /// final publicKey = keyPair.publicKey;
  /// final hash = keccak256(publicKey);
  /// final address = '0x${hex.encode(hash.sublist(12))}';
  /// ```
  static ({String privateKey, String address}) generateWallet() {
    final random = Random.secure();
    final bytes = List<int>.generate(32, (_) => random.nextInt(256));
    final privateKey =
        bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

    // Derive an Ethereum-style address from the private key (stub).
    // In production: privateKey -> publicKey -> keccak256(publicKey) -> address.
    final pubKeyHash =
        sha256.convert(Uint8List.fromList(bytes)).toString();
    final address = '0x${pubKeyHash.substring(0, 40)}';

    return (privateKey: privateKey, address: address);
  }
}
