//! `eddsa-jcs-2022` signing and verification (SPEC §6).

use crate::json::{canonical_bytes, JsonError, Value};
use crate::sri::sha256;
use ed25519_dalek::{Signature, Signer, SigningKey, VerifyingKey};

pub const PROOF_TYPE: &str = "DataIntegrityProof";
pub const CRYPTOSUITE: &str = "eddsa-jcs-2022";
pub const PROOF_PURPOSE: &str = "assertionMethod";

/// Every intermediate value of §6.2, kept separately so that a failing
/// implementation can be localised to one step (§6.2, and the `hashdata`
/// subcommand of §17).
#[derive(Debug, Clone)]
pub struct HashData {
    pub canonical_proof_config: String,
    pub transformed_document: String,
    pub proof_config_hash: [u8; 32],
    pub transformed_document_hash: [u8; 32],
    /// 64 bytes: proof config hash first, then the document hash (§6.2 step 6).
    pub hash_data: Vec<u8>,
}

/// Compute §6.2 steps 1–6 for one proof object of `doc`.
///
/// `doc` is the secured document; `proof` is the proof object being verified or
/// created. Neither is mutated.
pub fn compute_hash_data(doc: &Value, proof: &Value) -> Result<HashData, JsonError> {
    // Step 3: the transformed document is the document with `proof` removed.
    let mut unsecured = doc.clone();
    unsecured.remove("proof");

    // Step 1/2: proof options are the proof object without `proofValue`, with
    // `@context` copied from the document when the document has one.
    let mut options = proof.clone();
    options.remove("proofValue");
    if let Some(ctx) = doc.get("@context") {
        options.set("@context", ctx.clone());
    }

    let canonical_proof_config = crate::json::canonicalize(&options)?;
    let transformed_document = String::from_utf8(canonical_bytes(&unsecured)?)
        .expect("canonical form is UTF-8 by construction");
    let proof_config_hash = sha256(canonical_proof_config.as_bytes());
    let transformed_document_hash = sha256(transformed_document.as_bytes());
    let mut hash_data = Vec::with_capacity(64);
    hash_data.extend_from_slice(&proof_config_hash);
    hash_data.extend_from_slice(&transformed_document_hash);
    Ok(HashData {
        canonical_proof_config,
        transformed_document,
        proof_config_hash,
        transformed_document_hash,
        hash_data,
    })
}

/// Pure Ed25519 over `hashData` (§6.2 step 7).
pub fn sign(signing_key: &SigningKey, hash_data: &[u8]) -> [u8; 64] {
    signing_key.sign(hash_data).to_bytes()
}

/// Verify a 64-byte signature over `hashData` (§6.3 step 6).
///
/// IMPLEMENTATION CHOICE (§6.2 step 7 says "pure EdDSA per RFC 8032" without
/// choosing between RFC 8032's permissive and strict verification rules): this
/// implementation uses `verify_strict` only. It rejects small-order public keys
/// and non-canonically-encoded group elements — precisely the inputs on which
/// two RFC 8032 implementations legitimately disagree about validity, which is
/// the class of divergence §4.3 and §6.2 remove elsewhere in the format. A
/// signature made by any ordinary signer over an ordinary key verifies under
/// both rules, so nothing legitimate is rejected.
pub fn verify(public_key: &[u8; 32], hash_data: &[u8], signature: &[u8; 64]) -> Result<(), String> {
    let vk = VerifyingKey::from_bytes(public_key)
        .map_err(|e| format!("public key is not a valid Ed25519 point: {}", e))?;
    let sig = Signature::from_bytes(signature);
    vk.verify_strict(hash_data, &sig)
        .map_err(|e| format!("Ed25519 verification failed: {}", e))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::encoding::hex_encode;
    use crate::json::parse;

    fn key() -> SigningKey {
        SigningKey::from_bytes(&[42u8; 32])
    }

    #[test]
    fn hash_data_is_config_first_and_64_bytes() {
        let doc = parse(
            br#"{"@context":["https://www.w3.org/ns/credentials/v2"],"id":"urn:uuid:1",
                 "proof":{"type":"DataIntegrityProof","cryptosuite":"eddsa-jcs-2022",
                          "proofValue":"zIGNORED"}}"#,
        )
        .unwrap();
        let proof = doc.get("proof").unwrap();
        let hd = compute_hash_data(&doc, proof).unwrap();
        assert_eq!(hd.hash_data.len(), 64);
        assert_eq!(&hd.hash_data[..32], &hd.proof_config_hash[..]);
        assert_eq!(&hd.hash_data[32..], &hd.transformed_document_hash[..]);
        // proofValue must not appear in the signed bytes, @context must.
        assert!(!hd.canonical_proof_config.contains("zIGNORED"));
        assert!(hd.canonical_proof_config.contains("@context"));
        // The transformed document must not contain the proof at all.
        assert!(!hd.transformed_document.contains("proof"));
        // Sorted canonical form, proof removed:
        assert_eq!(
            hd.transformed_document,
            r#"{"@context":["https://www.w3.org/ns/credentials/v2"],"id":"urn:uuid:1"}"#
        );
        assert_eq!(
            hd.canonical_proof_config,
            r#"{"@context":["https://www.w3.org/ns/credentials/v2"],"cryptosuite":"eddsa-jcs-2022","type":"DataIntegrityProof"}"#
        );
        // Concatenation order is observable: the reversed order differs.
        let mut reversed = hd.transformed_document_hash.to_vec();
        reversed.extend_from_slice(&hd.proof_config_hash);
        assert_ne!(hex_encode(&reversed), hex_encode(&hd.hash_data));
    }

    #[test]
    fn sign_then_verify() {
        let sk = key();
        let pk = sk.verifying_key().to_bytes();
        let msg = b"hashData stand-in";
        let sig = sign(&sk, msg);
        assert!(verify(&pk, msg, &sig).is_ok());
        assert!(verify(&pk, b"other", &sig).is_err());
        let mut tampered = sig;
        tampered[0] ^= 1;
        assert!(verify(&pk, msg, &tampered).is_err());
        let mut other_pk = pk;
        other_pk[0] ^= 1;
        assert!(verify(&other_pk, msg, &sig).is_err());
    }

    #[test]
    fn unknown_members_are_inside_the_signature() {
        let a = parse(br#"{"id":"urn:uuid:1","proof":{"type":"DataIntegrityProof"}}"#).unwrap();
        let b = parse(
            br#"{"id":"urn:uuid:1","vendorExtension":{"x":1},"proof":{"type":"DataIntegrityProof"}}"#,
        )
        .unwrap();
        let ha = compute_hash_data(&a, a.get("proof").unwrap()).unwrap();
        let hb = compute_hash_data(&b, b.get("proof").unwrap()).unwrap();
        assert_ne!(ha.hash_data, hb.hash_data, "an unknown member must change the signed bytes");
    }
}
