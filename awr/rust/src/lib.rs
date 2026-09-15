//! An independent implementation of **AWR/2** (Agent Work Receipt), written from
//! `awr/SPEC.md` version 2.0.0 alone.
//!
//! Module map:
//!
//! | module | specification section |
//! |---|---|
//! | [`json`] | §4 canonicalization, and the strict parser §4.1 requires |
//! | [`encoding`] | base58btc/multibase (§5.1, §6.1), base64 (§3.2), hex (§17) |
//! | [`didkey`] | §5 issuer identity |
//! | [`sri`] | §3.2 digest references |
//! | [`proof`] | §6 `eddsa-jcs-2022` |
//! | [`decimal`] | §4.3 decimal strings, compared as decimals |
//! | [`timefmt`] | §3.1 RFC 3339 UTC timestamps |
//! | [`report`] | §11.1 result shape and §11.2 reason codes |
//! | [`document`] | §3 envelope and subject checks |
//! | [`chain`] | §8 work chains |
//! | [`bundle`] | §9 bundles |
//! | [`legacy`] | §12 AWR/1 |
//! | [`verify`] | §6.3 orchestration, §10 profiles |
//! | [`issue`] | issuing (§6.2), for the `issue` subcommand of §17 |

pub mod bundle;
pub mod chain;
pub mod decimal;
pub mod didkey;
pub mod document;
pub mod encoding;
pub mod issue;
pub mod json;
pub mod legacy;
pub mod proof;
pub mod report;
pub mod sri;
pub mod timefmt;
pub mod verify;

/// The AWR version this implementation speaks (§3.1).
pub const AWR_VERSION: &str = "2.0.0";

/// Major version accepted in a document's `awrVersion` (§3.1, `AWR-DOC-009`).
pub const AWR_MAJOR: &str = "2";

/// The two required `@context` URIs (§3.1).
pub const VC2_CONTEXT: &str = "https://www.w3.org/ns/credentials/v2";
pub const AWR_CONTEXT: &str = "https://verify.modelmarket.dev/ns/awr/v2";

/// The three AWR document types (§3.1).
pub const DOC_TYPES: [&str; 3] = ["WorkReceipt", "VerificationVerdict", "BlameAttestation"];
