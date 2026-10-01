//! `did:key` derivation and parsing for Ed25519 (SPEC §5).

use crate::encoding::{b58_encode, b64_decode, b64url_encode_nopad, multibase_decode};
use crate::json::Value;

/// Multicodec identifier for `ed25519-pub`, unsigned-varint (SPEC §5.1).
pub const ED25519_PUB_MULTICODEC: [u8; 2] = [0xed, 0x01];

pub const DID_KEY_PREFIX: &str = "did:key:";

/// A reason code plus detail, ready to be turned into a §11.1 entry.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct KeyError {
    pub code: &'static str,
    pub detail: String,
}

fn err(code: &'static str, detail: impl Into<String>) -> KeyError {
    KeyError { code, detail: detail.into() }
}

/// Known non-Ed25519 multicodecs.
///
/// IMPLEMENTATION CHOICE (§11.2 registers both `AWR-KEY-002` "bad multibase,
/// multicodec, or key length" and `AWR-KEY-004` "unsupported key type" without
/// separating them): a DID that decodes cleanly to a *recognised* other key type
/// is `AWR-KEY-004`; anything else structural is `AWR-KEY-002`.
fn named_multicodec(prefix: &[u8]) -> Option<&'static str> {
    let two = |a: u8, b: u8| prefix.len() >= 2 && prefix[0] == a && prefix[1] == b;
    if two(0xec, 0x01) {
        Some("x25519-pub")
    } else if two(0xe7, 0x01) {
        Some("secp256k1-pub")
    } else if two(0x80, 0x24) {
        Some("p256-pub")
    } else if two(0x81, 0x24) {
        Some("p384-pub")
    } else if two(0x82, 0x24) {
        Some("p521-pub")
    } else if two(0xeb, 0x01) {
        Some("bls12_381-g2-pub")
    } else if two(0x85, 0x24) {
        Some("rsa-pub")
    } else {
        None
    }
}

/// The multibase string that follows `did:key:` — also the fragment used in
/// `verificationMethod` (§5.3).
pub fn method_specific_id(public_key: &[u8; 32]) -> String {
    let mut multicodec = Vec::with_capacity(34);
    multicodec.extend_from_slice(&ED25519_PUB_MULTICODEC);
    multicodec.extend_from_slice(public_key);
    let mut s = String::with_capacity(48);
    s.push('z');
    s.push_str(&b58_encode(&multicodec));
    s
}

/// `did:key:z…` for an Ed25519 public key (§5.1).
pub fn did_from_public_key(public_key: &[u8; 32]) -> String {
    format!("{}{}", DID_KEY_PREFIX, method_specific_id(public_key))
}

/// `did:key:z…#z…` (§5.3).
pub fn verification_method_for(public_key: &[u8; 32]) -> String {
    let msi = method_specific_id(public_key);
    format!("{}{}#{}", DID_KEY_PREFIX, msi, msi)
}

/// Decode an Ed25519 public key from a `did:key` DID.
///
/// * a value that is not a `did:key` at all → `AWR-KEY-001`
/// * bad multibase / multicodec / length → `AWR-KEY-002`
/// * a well-formed `did:key` for a different key type → `AWR-KEY-004`
pub fn parse_did_key(did: &str) -> Result<[u8; 32], KeyError> {
    if !did.starts_with(DID_KEY_PREFIX) {
        return Err(err(
            "AWR-KEY-001",
            format!(
                "issuer identifier {:?} is not a did:key; AWR/2 supports no other DID method or an HTTPS issuer (§5.1)",
                did
            ),
        ));
    }
    let msi = &did[DID_KEY_PREFIX.len()..];
    if msi.is_empty() {
        return Err(err("AWR-KEY-002", "did:key with an empty method-specific identifier"));
    }
    // IMPLEMENTATION CHOICE (§5.1 gives the did:key form without saying whether
    // a path, query or fragment may follow): they are rejected as
    // `AWR-KEY-002`, because §5.3 builds verificationMethod by appending
    // `#<msi>` to issuer.id, and a fragment already present there would make the
    // two statements of the key disagree silently.
    if let Some(bad) = msi.chars().find(|c| matches!(c, '#' | '?' | '/')) {
        return Err(err(
            "AWR-KEY-002",
            format!("issuer.id must be a bare did:key; it contains `{}`", bad),
        ));
    }
    let bytes = multibase_decode(msi)
        .map_err(|e| err("AWR-KEY-002", format!("did:key multibase decode failed: {}", e)))?;
    if bytes.len() < 2 {
        return Err(err("AWR-KEY-002", "did:key decodes to fewer than 2 bytes"));
    }
    if bytes[0..2] != ED25519_PUB_MULTICODEC {
        if let Some(name) = named_multicodec(&bytes) {
            return Err(err(
                "AWR-KEY-004",
                format!(
                    "did:key names a {} key; AWR/2 defines Ed25519 (0xed 0x01) only (§5.1)",
                    name
                ),
            ));
        }
        return Err(err(
            "AWR-KEY-002",
            format!(
                "multicodec prefix 0x{:02x} 0x{:02x} is not ed25519-pub (0xed 0x01)",
                bytes[0], bytes[1]
            ),
        ));
    }
    let key = &bytes[2..];
    if key.len() != 32 {
        return Err(err(
            "AWR-KEY-002",
            format!("Ed25519 public key must be 32 bytes, got {}", key.len()),
        ));
    }
    let mut out = [0u8; 32];
    out.copy_from_slice(key);
    Ok(out)
}

/// Check an optional `issuer.publicKeyJwk` against the DID-derived key (§5.2).
///
/// A mismatch is `AWR-KEY-003` and invalidates the document: two disagreeing
/// statements of the signing key inside one signed document are a downgrade
/// surface, not a redundancy.
pub fn check_public_key_jwk(jwk: &Value, expected: &[u8; 32]) -> Result<(), KeyError> {
    let obj = match jwk {
        Value::Object(_) => jwk,
        _ => {
            return Err(err(
                "AWR-KEY-003",
                format!("issuer.publicKeyJwk is a {}, not an object", jwk.type_name()),
            ))
        }
    };
    match obj.get("kty").and_then(|v| v.as_str()) {
        Some("OKP") => {}
        Some(other) => {
            return Err(err(
                "AWR-KEY-003",
                format!("publicKeyJwk.kty is {:?}, expected \"OKP\" (RFC 8037)", other),
            ))
        }
        None => return Err(err("AWR-KEY-003", "publicKeyJwk.kty missing")),
    }
    match obj.get("crv").and_then(|v| v.as_str()) {
        Some("Ed25519") => {}
        Some(other) => {
            return Err(err(
                "AWR-KEY-003",
                format!("publicKeyJwk.crv is {:?}, expected \"Ed25519\"", other),
            ))
        }
        None => return Err(err("AWR-KEY-003", "publicKeyJwk.crv missing")),
    }
    let x = match obj.get("x").and_then(|v| v.as_str()) {
        Some(x) => x,
        None => return Err(err("AWR-KEY-003", "publicKeyJwk.x missing or not a string")),
    };
    let raw = b64_decode(x, false)
        .map_err(|e| err("AWR-KEY-003", format!("publicKeyJwk.x is not base64url: {}", e)))?;
    if raw.as_slice() != expected.as_slice() {
        return Err(err(
            "AWR-KEY-003",
            format!(
                "publicKeyJwk.x decodes to a different key than issuer.id: {} vs {}",
                x,
                b64url_encode_nopad(expected)
            ),
        ));
    }
    Ok(())
}

/// Build an RFC 8037 OKP/Ed25519 JWK for a public key (used by `issue`).
pub fn public_key_jwk(public_key: &[u8; 32]) -> Value {
    Value::object(vec![
        ("kty".to_string(), Value::string("OKP")),
        ("crv".to_string(), Value::string("Ed25519")),
        ("x".to_string(), Value::string(b64url_encode_nopad(public_key))),
    ])
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::parse;

    #[test]
    fn derivation_shape_matches_spec() {
        // §5.1: the method-specific identifier is 48 characters and begins z6Mk.
        // Checked over many keys, since the property is a consequence of the
        // 0xed 0x01 prefix rather than of any single key.
        for seed in 0u8..32 {
            let pk = [seed; 32];
            let msi = method_specific_id(&pk);
            assert_eq!(msi.len(), 48, "key {:?} produced {}", seed, msi);
            assert!(msi.starts_with("z6Mk"), "key {:?} produced {}", seed, msi);
            let did = did_from_public_key(&pk);
            assert_eq!(parse_did_key(&did).unwrap(), pk);
            assert_eq!(verification_method_for(&pk), format!("{}#{}", did, msi));
        }
    }

    #[test]
    fn rejects_non_didkey_and_malformed() {
        assert_eq!(parse_did_key("https://example.com/issuer").unwrap_err().code, "AWR-KEY-001");
        assert_eq!(parse_did_key("did:web:example.com").unwrap_err().code, "AWR-KEY-001");
        assert_eq!(parse_did_key("did:key:").unwrap_err().code, "AWR-KEY-002");
        // base64 multibase prefix instead of base58btc
        assert_eq!(parse_did_key("did:key:mSGVsbG8").unwrap_err().code, "AWR-KEY-002");
        // wrong length: 31-byte key
        let short = {
            let mut v = ED25519_PUB_MULTICODEC.to_vec();
            v.extend_from_slice(&[7u8; 31]);
            format!("did:key:z{}", crate::encoding::b58_encode(&v))
        };
        assert_eq!(parse_did_key(&short).unwrap_err().code, "AWR-KEY-002");
        // fragment inside issuer.id
        let pk = [3u8; 32];
        let with_frag = format!("{}#{}", did_from_public_key(&pk), method_specific_id(&pk));
        assert_eq!(parse_did_key(&with_frag).unwrap_err().code, "AWR-KEY-002");
    }

    #[test]
    fn rejects_other_key_types_as_key_004() {
        let mut v = vec![0x80, 0x24];
        v.extend_from_slice(&[1u8; 33]);
        let did = format!("did:key:z{}", crate::encoding::b58_encode(&v));
        let e = parse_did_key(&did).unwrap_err();
        assert_eq!(e.code, "AWR-KEY-004");
        assert!(e.detail.contains("p256-pub"));
    }

    #[test]
    fn jwk_consistency() {
        let pk = [9u8; 32];
        assert!(check_public_key_jwk(&public_key_jwk(&pk), &pk).is_ok());
        let other = [8u8; 32];
        assert_eq!(check_public_key_jwk(&public_key_jwk(&other), &pk).unwrap_err().code, "AWR-KEY-003");
        let bad_kty = parse(br#"{"kty":"EC","crv":"Ed25519","x":"AAAA"}"#).unwrap();
        assert_eq!(check_public_key_jwk(&bad_kty, &pk).unwrap_err().code, "AWR-KEY-003");
        let bad_crv = parse(br#"{"kty":"OKP","crv":"X25519","x":"AAAA"}"#).unwrap();
        assert_eq!(check_public_key_jwk(&bad_crv, &pk).unwrap_err().code, "AWR-KEY-003");
        let no_x = parse(br#"{"kty":"OKP","crv":"Ed25519"}"#).unwrap();
        assert_eq!(check_public_key_jwk(&no_x, &pk).unwrap_err().code, "AWR-KEY-003");
    }
}
