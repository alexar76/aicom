/// AI Market Protocol v2 Consumer SDK for Dart/Flutter.
///
/// Use this to embed marketplace economy into Flutter desktop apps
/// (macOS/Windows/Linux), Dart servers, and any Dart application.
///
/// ## Quick Start
///
/// ```dart
/// import 'package:aimarket_agent/aimarket_agent.dart';
///
/// void main() async {
///   final agent = AimarketAgent(
///     hubUrl: 'https://hub.aicom.io',
///     walletKey: 'your-wallet-private-key-hex',
///   );
///
///   // Phase 1: Discover career capabilities
///   final plan = await agent.discover(
///     intent: 'ATS scoring rules for fintech roles',
///     budget: 1.00,
///     category: 'career',
///   );
///
///   // Phase 2: Open a $5 channel on Base
///   final channel = await agent.openChannel(5.00, token: 'USDT', chain: 'base');
///
///   // Phase 3: Invoke the top result
///   final result = await agent.invoke(
///     capabilityId: plan.first.capability.id,
///     input: {'target_role': 'Senior PM', 'industry': 'fintech'},
///     channelId: channel.id,
///   );
///
///   // Phase 4: Settle the channel
///   await agent.closeChannel(channel.id);
///
///   // Phase 5: Verify TEE receipt (optional)
///   if (result.teeReceipt != null) {
///     final ok = agent.verifyTeeReceipt(
///       result.teeReceipt!,
///       jsonEncode({'target_role': 'Senior PM'}),
///       jsonEncode(result.output),
///     );
///     print('TEE verified: $ok');
///   }
///
///   print('Spent: \$${result.priceUsd}');
///   agent.dispose();
/// }
/// ```
///
/// ## Exports
///
/// This library re-exports all public types from its modules:
///
/// ### Core Agent
/// - [AimarketAgent] — the main consumer agent (5-phase lifecycle)
/// - [AimarketAgentConfig] — configures timeout, retries, TEE, etc.
/// - [AimarketException] — base exception for protocol errors
/// - [AimarketNetworkException] — network-level errors (retried)
/// - [AimarketPaymentException] — payment failures (402)
/// - [AimarketSafetyException] — safety gate blocks (403)
///
/// ### Data Models
/// - [Capability] — a discoverable AI function on the marketplace
/// - [Channel] — a pre-funded payment channel
/// - [InvokeResult] — result of a capability invocation
/// - [TeeAttestation] — TEE attestation (enclave proof)
/// - [TeeReceipt] — TEE execution receipt
/// - [Settlement] — channel close summary
/// - [PlanStep] — discovery result with relevance score
/// - [BillOfMaterials] — full interaction trace
///
/// ### Signing & Crypto
/// - [MarketSigner] — Ed25519 signing (HMAC-SHA256 stub)
/// - [Eip712Domain] — EIP-712 domain parameters
/// - [TypedData] — typed structured data for EIP-712
/// - [jsonRoundTrip] — round-trip serialization helper
///
/// ### TEE Verification
/// - [TeeVerifier] — verifies attestations and receipts
/// - [TeeVerificationResult] — detailed verification outcome
/// - [TrustedHashCache] — TTL-cached trusted code hashes
/// - [TeePlatform] — enum of supported TEE backends
///
/// ## Dependencies
///
/// - `http` for HTTP/HTTPS transport
/// - `crypto` for SHA-256 hashing and HMAC
///
/// ## Platform Support
///
/// | Platform | Status |
/// |----------|--------|
/// | Flutter macOS | Full |
/// | Flutter Windows | Full |
/// | Flutter Linux | Full |
/// | Dart CLI | Full |
/// | Flutter Web | Partial (CORS dependent) |
/// | Flutter iOS/Android | Untested |
library aimarket_agent;

export 'src/agent.dart';
export 'src/models.dart';
export 'src/signer.dart';
export 'src/tee_verifier.dart';
