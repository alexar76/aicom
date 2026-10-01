//! Issuing AWR/2 documents (SPEC §6.2), for the `issue` subcommand of §17.

use crate::didkey::{did_from_public_key, public_key_jwk, verification_method_for};
use crate::encoding::{b64_decode, b64url_encode_nopad, hex_decode, hex_encode, multibase_b58_encode, multibase_decode};
use crate::json::{parse, Value};
use crate::proof::{compute_hash_data, sign, CRYPTOSUITE, PROOF_PURPOSE, PROOF_TYPE};
use crate::timefmt::{format_rfc3339_utc, now_secs, parse_rfc3339_utc};
use crate::{AWR_CONTEXT, AWR_VERSION, DOC_TYPES, VC2_CONTEXT};
use ed25519_dalek::SigningKey;

#[derive(Debug, Clone)]
pub struct IssueOptions {
    pub doc_type: String,
    /// Document `id`; a fresh `urn:uuid:` v4 when absent.
    pub id: Option<String>,
    /// Value for `validFrom` and `proof.created`; wall clock when absent.
    pub now: Option<String>,
    pub issuer_name: Option<String>,
    /// Emit `issuer.publicKeyJwk` as well (§5.2, optional).
    pub include_jwk: bool,
}

impl Default for IssueOptions {
    fn default() -> Self {
        IssueOptions {
            doc_type: "WorkReceipt".to_string(),
            id: None,
            now: None,
            issuer_name: None,
            include_jwk: false,
        }
    }
}

/// 32 bytes from the operating system's entropy source. No RNG crate is used, so
/// the offline dependency set stays at ed25519-dalek + sha2.
pub fn random_bytes<const N: usize>() -> Result<[u8; N], String> {
    use std::io::Read;
    let mut f = std::fs::File::open("/dev/urandom").map_err(|e| format!("/dev/urandom: {}", e))?;
    let mut out = [0u8; N];
    f.read_exact(&mut out).map_err(|e| format!("/dev/urandom: {}", e))?;
    Ok(out)
}

/// RFC 4122 version 4 UUID as a `urn:uuid:` URI.
pub fn urn_uuid_v4() -> Result<String, String> {
    let mut b: [u8; 16] = random_bytes()?;
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    let h = hex_encode(&b);
    Ok(format!(
        "urn:uuid:{}-{}-{}-{}-{}",
        &h[0..8],
        &h[8..12],
        &h[12..16],
        &h[16..20],
        &h[20..32]
    ))
}

pub fn generate_key() -> Result<SigningKey, String> {
    Ok(SigningKey::from_bytes(&random_bytes::<32>()?))
}

/// A key file, as this implementation writes it: an RFC 8037 OKP private JWK
/// (the same document shape §5.2 already references for public keys) with the
/// derived DID alongside for readability.
///
/// IMPLEMENTATION CHOICE: §17 says `issue … --key <file>` without defining the
/// file format at all. An RFC 8037 private JWK was chosen because §5.2 already
/// makes RFC 8037 part of AWR, so no new format is invented. For interoperability
/// with other tooling the reader also accepts `{"seedHex": …}`,
/// `{"privateKeyMultibase": "z…"}` and a bare 64-character hex seed.
pub fn key_file_value(sk: &SigningKey) -> Value {
    let pk = sk.verifying_key().to_bytes();
    Value::object(vec![
        ("kty".to_string(), Value::string("OKP")),
        ("crv".to_string(), Value::string("Ed25519")),
        ("d".to_string(), Value::string(b64url_encode_nopad(&sk.to_bytes()))),
        ("x".to_string(), Value::string(b64url_encode_nopad(&pk))),
        ("did".to_string(), Value::string(did_from_public_key(&pk))),
        (
            "verificationMethod".to_string(),
            Value::string(verification_method_for(&pk)),
        ),
        (
            "privateKeyMultibase".to_string(),
            Value::string(multibase_b58_encode(&sk.to_bytes())),
        ),
    ])
}

/// Read a key file in any of the accepted forms.
pub fn read_key(text: &str) -> Result<SigningKey, String> {
    let trimmed = text.trim();
    let take32 = |raw: Vec<u8>, what: &str| -> Result<SigningKey, String> {
        if raw.len() != 32 {
            return Err(format!("{} must decode to 32 bytes, got {}", what, raw.len()));
        }
        let mut seed = [0u8; 32];
        seed.copy_from_slice(&raw);
        Ok(SigningKey::from_bytes(&seed))
    };
    if trimmed.starts_with('{') {
        let v = parse(trimmed.as_bytes()).map_err(|e| format!("key file is not JSON: {}", e))?;
        if let Some(d) = v.get("d").and_then(|x| x.as_str()) {
            return take32(
                b64_decode(d, false).map_err(|e| format!("key `d` is not base64url: {}", e))?,
                "key `d`",
            );
        }
        if let Some(s) = v.get("seedHex").and_then(|x| x.as_str()) {
            return take32(hex_decode(s)?, "seedHex");
        }
        if let Some(s) = v.get("privateKeyHex").and_then(|x| x.as_str()) {
            return take32(hex_decode(s)?, "privateKeyHex");
        }
        if let Some(s) = v.get("privateKeyMultibase").and_then(|x| x.as_str()) {
            let raw = multibase_decode(s)?;
            // Tolerate a multicodec-prefixed value (0x80 0x26 = ed25519-priv).
            let raw = if raw.len() == 34 && raw[0] == 0x80 && raw[1] == 0x26 {
                raw[2..].to_vec()
            } else {
                raw
            };
            return take32(raw, "privateKeyMultibase");
        }
        return Err("key file has none of `d`, `seedHex`, `privateKeyHex`, `privateKeyMultibase`".to_string());
    }
    if trimmed.len() == 64 && trimmed.bytes().all(|c| c.is_ascii_hexdigit()) {
        return take32(hex_decode(trimmed)?, "hex seed");
    }
    if let Some(rest) = trimmed.strip_prefix('z') {
        let _ = rest;
        return take32(multibase_decode(trimmed)?, "multibase seed");
    }
    Err("unrecognised key file; expected an RFC 8037 OKP JWK with `d`, or a 64-character hex seed".to_string())
}

fn timestamp(now: &Option<String>) -> Result<String, String> {
    match now {
        Some(s) => {
            if parse_rfc3339_utc(s).is_none() {
                return Err(format!("--now {:?} is not an RFC 3339 UTC date-time with a Z offset", s));
            }
            Ok(s.clone())
        }
        None => Ok(format_rfc3339_utc(now_secs())),
    }
}

/// Build and sign a document from a `credentialSubject` (§3, §6.2).
pub fn issue(subject: &Value, sk: &SigningKey, o: &IssueOptions) -> Result<Value, String> {
    if !subject.is_object() {
        return Err(format!("credentialSubject must be a JSON object, found a {}", subject.type_name()));
    }
    if !DOC_TYPES.contains(&o.doc_type.as_str()) {
        return Err(format!("--type must be one of {:?}", DOC_TYPES));
    }
    let pk = sk.verifying_key().to_bytes();
    let created = timestamp(&o.now)?;
    let id = match &o.id {
        Some(i) => i.clone(),
        None => urn_uuid_v4()?,
    };
    let mut issuer = vec![("id".to_string(), Value::string(did_from_public_key(&pk)))];
    if let Some(n) = &o.issuer_name {
        issuer.push(("name".to_string(), Value::string(n.clone())));
    }
    if o.include_jwk {
        issuer.push(("publicKeyJwk".to_string(), public_key_jwk(&pk)));
    }
    let doc = Value::object(vec![
        (
            "@context".to_string(),
            Value::Array(vec![Value::string(VC2_CONTEXT), Value::string(AWR_CONTEXT)]),
        ),
        ("id".to_string(), Value::string(id)),
        (
            "type".to_string(),
            Value::Array(vec![
                Value::string("VerifiableCredential"),
                Value::string(o.doc_type.clone()),
            ]),
        ),
        ("issuer".to_string(), Value::object(issuer)),
        ("validFrom".to_string(), Value::string(created.clone())),
        ("awrVersion".to_string(), Value::string(AWR_VERSION)),
        ("credentialSubject".to_string(), subject.clone()),
    ]);
    attach_proof(doc, sk, &created)
}

/// Sign a document that already has its envelope, filling in whatever §3.1
/// requires and is missing. Used when the input file is a whole unsecured
/// document rather than a bare subject.
pub fn issue_template(template: &Value, sk: &SigningKey, o: &IssueOptions) -> Result<Value, String> {
    let mut doc = template.clone();
    doc.remove("proof");
    let pk = sk.verifying_key().to_bytes();
    let created = timestamp(&o.now)?;
    if doc.get("@context").is_none() {
        doc.set(
            "@context",
            Value::Array(vec![Value::string(VC2_CONTEXT), Value::string(AWR_CONTEXT)]),
        );
    }
    if doc.get("id").is_none() {
        doc.set("id", Value::string(match &o.id {
            Some(i) => i.clone(),
            None => urn_uuid_v4()?,
        }));
    } else if let Some(i) = &o.id {
        doc.set("id", Value::string(i.clone()));
    }
    if doc.get("type").is_none() {
        doc.set(
            "type",
            Value::Array(vec![
                Value::string("VerifiableCredential"),
                Value::string(o.doc_type.clone()),
            ]),
        );
    }
    // The issuer is always this key: signing a document that names someone else
    // as issuer would produce a document that can never verify.
    let mut issuer = doc.get("issuer").cloned().unwrap_or_else(|| Value::object(vec![]));
    if !issuer.is_object() {
        issuer = Value::object(vec![]);
    }
    issuer.set("id", Value::string(did_from_public_key(&pk)));
    if let Some(n) = &o.issuer_name {
        issuer.set("name", Value::string(n.clone()));
    }
    if o.include_jwk {
        issuer.set("publicKeyJwk", public_key_jwk(&pk));
    }
    doc.set("issuer", issuer);
    if doc.get("validFrom").is_none() {
        doc.set("validFrom", Value::string(created.clone()));
    }
    doc.set("awrVersion", Value::string(AWR_VERSION));
    if doc.get("credentialSubject").is_none() {
        return Err("template has no credentialSubject".to_string());
    }
    attach_proof(doc, sk, &created)
}

fn attach_proof(mut doc: Value, sk: &SigningKey, created: &str) -> Result<Value, String> {
    let pk = sk.verifying_key().to_bytes();
    let mut members: Vec<(String, Value)> = Vec::with_capacity(6);
    // §6.2 step 9: emit the document's `@context` in the proof. The signature does not
    // depend on it (step 1 copies the document's value into the proof configuration
    // either way), but an off-the-shelf `eddsa-jcs-2022` verifier rebuilds the proof
    // configuration from the serialized proof alone, so a proof that omits it hashes a
    // different configuration and reports a signature failure over correct bytes.
    if let Some(ctx) = doc.get("@context") {
        members.push(("@context".to_string(), ctx.clone()));
    }
    members.extend([
        ("type".to_string(), Value::string(PROOF_TYPE)),
        ("cryptosuite".to_string(), Value::string(CRYPTOSUITE)),
        ("created".to_string(), Value::string(created)),
        (
            "verificationMethod".to_string(),
            Value::string(verification_method_for(&pk)),
        ),
        ("proofPurpose".to_string(), Value::string(PROOF_PURPOSE)),
    ]);
    let proof = Value::object(members);
    doc.set("proof", proof.clone());
    let hd = compute_hash_data(&doc, &proof).map_err(|e| e.to_string())?;
    let signature = sign(sk, &hd.hash_data);
    let mut signed_proof = proof;
    signed_proof.set("proofValue", Value::string(multibase_b58_encode(&signature)));
    doc.set("proof", signed_proof);
    Ok(doc)
}

/// Recompute `proofValue` for a document whose content changed, keeping its
/// existing proof options. Used by tests that need a valid signature over an
/// edited document.
pub fn resign(doc: &Value, sk: &SigningKey) -> Result<Value, String> {
    let mut out = doc.clone();
    let mut proof = out
        .get("proof")
        .cloned()
        .ok_or_else(|| "document has no proof to re-sign".to_string())?;
    proof.remove("proofValue");
    // §6.2 step 9, as in `attach_proof`. An existing `@context` in the proof is left
    // alone: a test that deliberately set a mismatching one is exercising AWR-PROOF-008
    // and must keep the value it chose.
    if proof.get("@context").is_none() {
        if let Some(ctx) = out.get("@context").cloned() {
            proof.set("@context", ctx);
        }
    }
    out.set("proof", proof.clone());
    let hd = compute_hash_data(&out, &proof).map_err(|e| e.to_string())?;
    let signature = sign(sk, &hd.hash_data);
    proof.set("proofValue", Value::string(multibase_b58_encode(&signature)));
    out.set("proof", proof);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::report::Report;
    use crate::verify::verify_document;

    fn subject(kind: &str) -> Value {
        let src = match kind {
            "WorkReceipt" => format!(
                r#"{{"work":{{"modelId":"m@v","completedAt":"2026-07-31T10:15:30Z","status":"succeeded"}},
                     "inputDigest":"{}","outputDigest":"{}"}}"#,
                crate::sri::sri_of_bytes(b"in"),
                crate::sri::sri_of_bytes(b"")
            ),
            "VerificationVerdict" => format!(
                r#"{{"verifiedWork":{{"id":"urn:uuid:r","digestSRI":"{}"}},"verdict":"inconclusive",
                     "method":{{"id":"urn:example:method:m"}}}}"#,
                crate::sri::sri_of_bytes(b"receipt bytes")
            ),
            _ => format!(
                r#"{{"chain":{{"id":"urn:uuid:c","digestSRI":"{}"}},
                     "blamedWork":{{"id":"urn:uuid:c","digestSRI":"{}"}},
                     "failureClass":"upstream-input","confidence":"0.90",
                     "method":{{"id":"urn:example:method:hop-bisect-v1"}}}}"#,
                crate::sri::sri_of_bytes(b"terminal"),
                crate::sri::sri_of_bytes(b"terminal")
            ),
        };
        parse(src.as_bytes()).unwrap()
    }

    #[test]
    fn round_trip_for_all_three_document_types() {
        let sk = SigningKey::from_bytes(&[11u8; 32]);
        for kind in ["WorkReceipt", "VerificationVerdict", "BlameAttestation"] {
            let o = IssueOptions {
                doc_type: kind.to_string(),
                now: Some("2026-07-31T10:15:30Z".to_string()),
                include_jwk: true,
                ..Default::default()
            };
            let doc = issue(&subject(kind), &sk, &o).unwrap();
            let mut rep = Report::default();
            let env = verify_document(&doc, &mut rep);
            assert!(rep.valid(), "{} did not verify: {:?}", kind, rep.reasons);
            assert_eq!(env.doc_type.as_deref(), Some(kind));
            assert!(doc.get("id").unwrap().as_str().unwrap().starts_with("urn:uuid:"));
            // §5.3 verificationMethod shape
            let vm = doc.get("proof").unwrap().get("verificationMethod").unwrap().as_str().unwrap();
            let did = doc.get("issuer").unwrap().get("id").unwrap().as_str().unwrap();
            assert_eq!(vm, format!("{}#{}", did, &did["did:key:".len()..]));
        }
    }

    #[test]
    fn template_mode_keeps_unknown_members_inside_the_signature() {
        let sk = SigningKey::from_bytes(&[12u8; 32]);
        let mut template = Value::object(vec![
            ("credentialSubject".to_string(), subject("WorkReceipt")),
            ("vendorExtension".to_string(), Value::string("kept")),
        ]);
        template.set("validUntil", Value::string("2027-01-01T00:00:00Z"));
        let doc = issue_template(
            &template,
            &sk,
            &IssueOptions { now: Some("2026-07-31T10:15:30Z".to_string()), ..Default::default() },
        )
        .unwrap();
        assert_eq!(doc.get("vendorExtension").unwrap().as_str(), Some("kept"));
        let mut rep = Report::default();
        verify_document(&doc, &mut rep);
        assert!(rep.valid(), "{:?}", rep.reasons);
    }

    #[test]
    fn key_file_forms_all_read_back() {
        let sk = SigningKey::from_bytes(&[13u8; 32]);
        let jwk = crate::json::to_string_compact(&key_file_value(&sk));
        assert_eq!(read_key(&jwk).unwrap().to_bytes(), sk.to_bytes());
        assert_eq!(read_key(&hex_encode(&sk.to_bytes())).unwrap().to_bytes(), sk.to_bytes());
        assert_eq!(
            read_key(&format!(r#"{{"seedHex":"{}"}}"#, hex_encode(&sk.to_bytes())))
                .unwrap()
                .to_bytes(),
            sk.to_bytes()
        );
        assert_eq!(
            read_key(&multibase_b58_encode(&sk.to_bytes())).unwrap().to_bytes(),
            sk.to_bytes()
        );
        // multicodec-prefixed private key multibase
        let mut prefixed = vec![0x80u8, 0x26];
        prefixed.extend_from_slice(&sk.to_bytes());
        assert_eq!(
            read_key(&format!(
                r#"{{"privateKeyMultibase":"{}"}}"#,
                multibase_b58_encode(&prefixed)
            ))
            .unwrap()
            .to_bytes(),
            sk.to_bytes()
        );
        assert!(read_key("not a key").is_err());
        assert!(read_key(r#"{"kty":"OKP"}"#).is_err());
    }

    #[test]
    fn generated_keys_are_distinct_and_derive_valid_dids() {
        let a = generate_key().unwrap();
        let b = generate_key().unwrap();
        assert_ne!(a.to_bytes(), b.to_bytes());
        let did = did_from_public_key(&a.verifying_key().to_bytes());
        assert_eq!(
            crate::didkey::parse_did_key(&did).unwrap(),
            a.verifying_key().to_bytes()
        );
        let u = urn_uuid_v4().unwrap();
        assert_eq!(u.len(), "urn:uuid:8f14e45f-ea1c-4f38-9b8a-1c2d3e4f5a6b".len());
        assert_eq!(&u[23..24], "4", "version nibble");
    }

    #[test]
    fn rejects_a_bad_type_or_now() {
        let sk = SigningKey::from_bytes(&[14u8; 32]);
        let o = IssueOptions { doc_type: "Nonsense".to_string(), ..Default::default() };
        assert!(issue(&subject("WorkReceipt"), &sk, &o).is_err());
        let o = IssueOptions { now: Some("2026-07-31 10:15:30".to_string()), ..Default::default() };
        assert!(issue(&subject("WorkReceipt"), &sk, &o).is_err());
    }
}
