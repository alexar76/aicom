//! Subresource-Integrity digest strings and digest references (SPEC §3.2).

use crate::encoding::{b64_decode, b64_encode};
use crate::json::Value;
use sha2::{Digest, Sha256};

/// The only digest algorithm AWR/2 defines (§3.2).
pub const SRI_PREFIX: &str = "sha256-";

pub fn sha256(bytes: &[u8]) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(bytes);
    let out = h.finalize();
    let mut r = [0u8; 32];
    r.copy_from_slice(&out);
    r
}

/// `sha256-<standard padded base64>` over `bytes`.
pub fn sri_of_bytes(bytes: &[u8]) -> String {
    format!("{}{}", SRI_PREFIX, b64_encode(&sha256(bytes)))
}

pub fn sri_of_digest(digest: &[u8; 32]) -> String {
    format!("{}{}", SRI_PREFIX, b64_encode(digest))
}

/// Why an SRI string was rejected. The caller maps this to a reason code, which
/// differs by field: a bad `inputDigest` is `AWR-RCPT-001`, a bad digest
/// *reference* is `AWR-CHAIN-002` (§3.2 requires the algorithm case to be
/// reported rather than ignored).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SriError {
    /// Present but not a string at all.
    NotAString(String),
    /// Prefix is not `sha256-`.
    BadAlgorithm(String),
    /// base64 or length problem.
    Malformed(String),
}

impl SriError {
    pub fn detail(&self) -> &str {
        match self {
            SriError::NotAString(d) | SriError::BadAlgorithm(d) | SriError::Malformed(d) => d,
        }
    }
}

/// Parse an SRI string into its 32 raw digest bytes.
pub fn parse_sri(v: &Value) -> Result<[u8; 32], SriError> {
    let s = match v.as_str() {
        Some(s) => s,
        None => {
            return Err(SriError::NotAString(format!(
                "digest must be an SRI string, found a {}",
                v.type_name()
            )))
        }
    };
    let dash = match s.find('-') {
        Some(i) => i,
        None => {
            return Err(SriError::BadAlgorithm(format!(
                "SRI string {:?} has no `<alg>-` prefix",
                s
            )))
        }
    };
    let alg = &s[..dash];
    if alg != "sha256" {
        return Err(SriError::BadAlgorithm(format!(
            "digest algorithm {:?} is not defined in AWR/2; only sha256 is (§3.2)",
            alg
        )));
    }
    let raw = b64_decode(&s[dash + 1..], true).map_err(|e| {
        SriError::Malformed(format!("SRI base64 for {:?} is invalid: {}", s, e))
    })?;
    if raw.len() != 32 {
        return Err(SriError::Malformed(format!(
            "sha256 digest must be 32 bytes, {:?} decodes to {}",
            s,
            raw.len()
        )));
    }
    let mut out = [0u8; 32];
    out.copy_from_slice(&raw);
    Ok(out)
}

/// A parsed digest reference (§3.2).
#[derive(Debug, Clone)]
pub struct DigestRef {
    pub id: Option<String>,
    pub sri: String,
    pub digest: [u8; 32],
    pub role: Option<String>,
}

/// Failure of a digest reference, already mapped to its reason code:
/// `AWR-CHAIN-001` for a missing `digestSRI`, `AWR-CHAIN-002` for anything else
/// about its form or algorithm.
#[derive(Debug, Clone)]
pub struct RefError {
    pub code: &'static str,
    pub detail: String,
}

pub fn parse_digest_ref(v: &Value, what: &str) -> Result<DigestRef, RefError> {
    if !v.is_object() {
        return Err(RefError {
            code: "AWR-CHAIN-002",
            detail: format!("{} must be a digest-reference object, found a {}", what, v.type_name()),
        });
    }
    let sri_value = match v.get("digestSRI") {
        Some(s) => s,
        None => {
            return Err(RefError {
                code: "AWR-CHAIN-001",
                detail: format!("{} has no digestSRI", what),
            })
        }
    };
    let digest = parse_sri(sri_value).map_err(|e| RefError {
        code: "AWR-CHAIN-002",
        detail: format!("{}: {}", what, e.detail()),
    })?;
    Ok(DigestRef {
        id: v.get("id").and_then(|i| i.as_str()).map(|s| s.to_string()),
        sri: sri_value.as_str().unwrap_or_default().to_string(),
        digest,
        role: v.get("role").and_then(|r| r.as_str()).map(|s| s.to_string()),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::parse;

    #[test]
    fn empty_string_digest_matches_the_specification_text() {
        // §3.2 prints the SRI of the empty byte string, and §3.3 permits it as
        // the outputDigest of a failed receipt. Computed here, not transcribed.
        assert_eq!(
            sri_of_bytes(b""),
            "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="
        );
    }

    #[test]
    fn parses_and_rejects() {
        let good = Value::string(sri_of_bytes(b"payload"));
        assert_eq!(parse_sri(&good).unwrap(), sha256(b"payload"));
        assert!(matches!(
            parse_sri(&Value::string("sha512-AAAA")).unwrap_err(),
            SriError::BadAlgorithm(_)
        ));
        assert!(matches!(
            parse_sri(&Value::string("47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=")).unwrap_err(),
            SriError::BadAlgorithm(_)
        ));
        assert!(matches!(
            parse_sri(&Value::string("sha256-AAAA")).unwrap_err(),
            SriError::Malformed(_)
        ));
        assert!(matches!(parse_sri(&Value::int(1)).unwrap_err(), SriError::NotAString(_)));
        // base64url instead of standard base64 is not an SRI value
        let urlish = format!("sha256-{}", crate::encoding::b64url_encode_nopad(&sha256(b"x")));
        assert!(matches!(parse_sri(&Value::string(urlish)).unwrap_err(), SriError::Malformed(_)));
    }

    #[test]
    fn digest_reference_codes() {
        let v = parse(format!(r#"{{"id":"urn:uuid:x","digestSRI":"{}","role":"tool"}}"#, sri_of_bytes(b"p")).as_bytes()).unwrap();
        let r = parse_digest_ref(&v, "parents[0]").unwrap();
        assert_eq!(r.id.as_deref(), Some("urn:uuid:x"));
        assert_eq!(r.role.as_deref(), Some("tool"));

        let missing = parse(br#"{"id":"urn:uuid:x"}"#).unwrap();
        assert_eq!(parse_digest_ref(&missing, "parents[0]").unwrap_err().code, "AWR-CHAIN-001");

        let bad_alg = parse(br#"{"digestSRI":"md5-AAAA"}"#).unwrap();
        assert_eq!(parse_digest_ref(&bad_alg, "parents[0]").unwrap_err().code, "AWR-CHAIN-002");

        let not_obj = Value::string("urn:uuid:x");
        assert_eq!(parse_digest_ref(&not_obj, "parents[0]").unwrap_err().code, "AWR-CHAIN-002");
    }
}
