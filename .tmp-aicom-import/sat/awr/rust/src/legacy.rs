//! AWR/1 legacy verification (SPEC §12).
//!
//! §12 is the least determined part of the specification: it says the legacy
//! signature covers "a pipe-delimited rendering of `credentialSubject` only",
//! that keys were sorted by code point, that strings were NFC-normalized, and
//! that two dialects differ in whether an integer renders as `2340` or
//! `2340.0` — but it does not give the rendering's grammar. Everything below
//! marked IMPLEMENTATION CHOICE is this implementation's reading; see the
//! findings list that accompanies it.
//!
//! Consequences that are *not* choices: `AWR-LEGACY-001` is reported on every
//! AWR/1 document, both dialects are tried, failure under both is
//! `AWR-LEGACY-002`, and `id`/`type`/`issuer`/`hubInfo` are reported as
//! unsigned.

use crate::didkey::{did_from_public_key, parse_did_key};
use crate::encoding::b64_decode;
use crate::json::{codepoint_cmp, NumberKind, Value};
use crate::report::Report;

pub const LEGACY_PROOF_TYPE: &str = "Ed25519Signature2018";
pub const AWR2_PROOF_TYPE: &str = "DataIntegrityProof";

/// Fields §12 requires a verifier to treat as unsigned in AWR/1.
pub const UNSIGNED_FIELDS: [&str; 4] = ["id", "type", "issuer", "hubInfo"];

/// §12.3 signal 2. Either URI is an AWR/2 claim: the VC 2.0 context postdates
/// AWR/1 (VC 1.1) and the AWR namespace names this specification.
pub const AWR2_CONTEXT_URIS: [&str; 2] = [
    "https://www.w3.org/ns/credentials/v2",
    "https://verify.modelmarket.dev/ns/awr/v2",
];
/// §12.3 signals 4 and 5. `credentialSubject.parents` is deliberately absent:
/// Appendix D records that AWR/1 carried `parents` too, as identifier strings, so
/// it is not an AWR/2 claim.
pub const AWR2_ENVELOPE_MEMBERS: [&str; 2] = ["validFrom", "validUntil"];
pub const AWR2_SUBJECT_MEMBERS: [&str; 1] = ["settlement"];

/// Caller-supplied controls over the §12 path.
#[derive(Debug, Clone, Default)]
pub struct LegacyOptions {
    /// `--expected-key`: the signing key supplied OUT OF BAND (§12.4). When set
    /// it is the only key tried; nothing the document carries is substituted for
    /// it or used as a fallback.
    pub expected_key: Option<[u8; 32]>,
    /// `--no-legacy`: decline §12 entirely (`AWR-LEGACY-005`). §12 support is
    /// OPTIONAL and a deployment with no AWR/1 corpus is better off refusing it.
    pub no_legacy: bool,
}

/// The three outcomes of the §12.3 version gate.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VersionClass {
    Awr2,
    Awr1,
    /// The document makes an AWR/2 claim *and* carries an AWR/1 proof suite.
    Disagree,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Dialect {
    /// integer-preserving: a JSON integer renders as `2340`
    A,
    /// float-coercing: the same integer renders as `2340.0`
    B,
}

impl Dialect {
    pub fn as_str(self) -> &'static str {
        match self {
            Dialect::A => "A",
            Dialect::B => "B",
        }
    }
}

/// Every proof object, whether `proof` is one object or an array (§12.3).
///
/// Position must not matter. Reading `proof[0]` — which two of the three
/// implementations did — let an attacker pick the rule set by ordering the array,
/// and the three then disagreed about the same bytes.
fn proof_objects(doc: &Value) -> Vec<&Value> {
    match doc.get("proof") {
        Some(Value::Array(items)) => items.iter().filter(|p| p.is_object()).collect(),
        Some(p) if p.is_object() => vec![p],
        _ => Vec::new(),
    }
}

/// The §12.3 AWR/2 signals the document carries, named for the reason detail.
///
/// The list is closed: a signal one verifier honours and another ignores is a
/// document the two disagree about.
pub fn awr2_signals(doc: &Value) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    if !doc.is_object() {
        return out;
    }
    if doc.get("awrVersion").is_some() {
        out.push("awrVersion".to_string());
    }
    if let Some(ctx) = doc.get("@context") {
        let hit = |v: &Value| {
            v.as_str().map(|s| AWR2_CONTEXT_URIS.contains(&s)).unwrap_or(false)
        };
        let found = match ctx {
            Value::Array(items) => items.iter().any(hit),
            v => hit(v),
        };
        if found {
            out.push("the AWR/2 @context".to_string());
        }
    }
    if proof_objects(doc)
        .iter()
        .any(|p| p.get("type").and_then(|t| t.as_str()) == Some(AWR2_PROOF_TYPE))
    {
        out.push("proof.type DataIntegrityProof".to_string());
    }
    for m in AWR2_ENVELOPE_MEMBERS {
        if doc.get(m).is_some() {
            out.push(m.to_string());
        }
    }
    if let Some(s) = doc.get("credentialSubject") {
        if s.is_object() {
            for m in AWR2_SUBJECT_MEMBERS {
                if s.get(m).is_some() {
                    out.push(format!("credentialSubject.{}", m));
                }
            }
        }
    }
    out
}

/// True when any proof object declares the AWR/1 suite (§12.3).
pub fn has_awr1_proof(doc: &Value) -> bool {
    proof_objects(doc)
        .iter()
        .any(|p| p.get("type").and_then(|t| t.as_str()) == Some(LEGACY_PROOF_TYPE))
}

/// The §12.3 version gate, run before any verification.
///
/// Selecting the rule set on `proof.type` alone — the reading every
/// implementation arrived at from the earlier text — is an unauthenticated
/// forgery path: AWR/1 signs neither `proof.type` nor `issuer`, so a document
/// carrying `awrVersion: "2.0.0"` and a victim's DID was verified under AWR/1
/// rules against a key the attacker supplied beside it.
pub fn classify(doc: &Value) -> VersionClass {
    let awr1 = has_awr1_proof(doc);
    let awr2 = !awr2_signals(doc).is_empty();
    match (awr1, awr2) {
        (true, true) => VersionClass::Disagree,
        (true, false) => VersionClass::Awr1,
        _ => VersionClass::Awr2,
    }
}

/// True when the document is to be verified under §12.
///
/// Narrower than "carries an AWR/1 proof": a document that also makes an AWR/2
/// claim is neither, and its caller reports `AWR-LEGACY-003`.
pub fn is_legacy(doc: &Value) -> bool {
    classify(doc) == VersionClass::Awr1
}

/// The AWR/1 canonical form, per SPEC §12.1:
///
/// ```text
/// form  = [ entry *( "|" entry ) ]      entry = path "=" leaf
/// path  = segment *( "." segment )
/// ```
///
/// The entries are the leaves of `credentialSubject`: object members visited in
/// ascending Unicode code-point order of the member name, array elements in index
/// order with the index as the path segment. An empty object or array has no
/// leaves and contributes **no entry**. The entries are then sorted by whole
/// path, which is observable (`a!` sorts before `a.z`, because `!` precedes `.`).
///
/// Leaf rendering: a string as its NFC-normalized characters, unquoted;
/// `true`/`false`; `null` as `null`; an integer as its digits (dialect A) or with
/// a `.0` suffix (dialect B); any other number with exactly ten fractional
/// digits, trailing zeros kept.
///
/// Returns `Err` when a value falls outside the range §12.1 defines the rendering
/// for (|x| >= 10^15), where the caller reports `AWR-LEGACY-002` rather than
/// choosing a rendering of its own.
///
/// NFC: §12.1 requires it. This implementation carries no Unicode normalization
/// tables and therefore passes strings through unchanged, which is exactly NFC
/// for ASCII (ASCII is NFC-stable). A legacy document with non-ASCII string data
/// may fail here where the original verifier succeeded; `AWR-LEGACY-002` then
/// says so, and `has_non_ascii` puts the reason in the detail.
pub fn legacy_canonical(subject: &Value, dialect: Dialect) -> Result<String, String> {
    let mut entries: Vec<(String, String)> = Vec::new();
    walk(subject, "", dialect, &mut entries)?;
    // §12.1(3): sort by whole path, in code-point order.
    entries.sort_by(|a, b| codepoint_cmp(&a.0, &b.0));
    Ok(entries
        .iter()
        .map(|(p, leaf)| format!("{}={}", p, leaf))
        .collect::<Vec<String>>()
        .join("|"))
}

fn walk(
    v: &Value,
    path: &str,
    dialect: Dialect,
    out: &mut Vec<(String, String)>,
) -> Result<(), String> {
    let join = |p: &str, k: &str| -> String {
        if p.is_empty() {
            k.to_string()
        } else {
            format!("{}.{}", p, k)
        }
    };
    match v {
        // §12.1(2): an empty container has no leaves, so it contributes no entry.
        Value::Object(members) => {
            let mut refs: Vec<&(String, Value)> = members.iter().collect();
            refs.sort_by(|a, b| codepoint_cmp(&a.0, &b.0));
            for (k, val) in refs.iter().map(|p| (&p.0, &p.1)) {
                walk(val, &join(path, k), dialect, out)?;
            }
        }
        Value::Array(items) => {
            for (n, item) in items.iter().enumerate() {
                walk(item, &join(path, &n.to_string()), dialect, out)?;
            }
        }
        leaf => out.push((path.to_string(), render_leaf(leaf, dialect)?)),
    }
    Ok(())
}

const LEGACY_RANGE: i64 = 1_000_000_000_000_000;

fn out_of_range(raw: &str) -> String {
    format!(
        "number {} is outside the range in which the AWR/1 rendering is defined (|x| < 10^15, \u{a7}12.1)",
        raw
    )
}

fn render_leaf(v: &Value, dialect: Dialect) -> Result<String, String> {
    Ok(match v {
        Value::Null => "null".to_string(),
        Value::Bool(b) => (if *b { "true" } else { "false" }).to_string(),
        Value::Str(s) => s.clone(),
        Value::Number { raw, kind } => match kind {
            NumberKind::Integer(i) => {
                if i.abs() >= LEGACY_RANGE {
                    return Err(out_of_range(raw));
                }
                match dialect {
                    Dialect::A => i.to_string(),
                    Dialect::B => format!("{}.0", i),
                }
            }
            // AWR/1 had no §4.3 restriction, but §12.1 defines no rendering this
            // far out either: two languages print such a double differently.
            NumberKind::OutOfRange => return Err(out_of_range(raw)),
            NumberKind::NonInteger => match raw.parse::<f64>() {
                Ok(f) if f.abs() < 1e15 => {
                    if f == f.trunc() {
                        // §12.1: an integral value written with a fraction or an
                        // exponent renders as an integer, per dialect.
                        match dialect {
                            Dialect::A => format!("{}", f as i64),
                            Dialect::B => format!("{}.0", f as i64),
                        }
                    } else {
                        format!("{:.10}", f)
                    }
                }
                _ => return Err(out_of_range(raw)),
            },
        },
        // Unreachable: `walk` routes containers, never passing one here.
        Value::Object(_) | Value::Array(_) => String::new(),
    })
}

fn has_non_ascii(v: &Value) -> bool {
    match v {
        Value::Str(s) => !s.is_ascii(),
        Value::Array(items) => items.iter().any(has_non_ascii),
        Value::Object(members) => members.iter().any(|(k, val)| !k.is_ascii() || has_non_ascii(val)),
        _ => false,
    }
}

/// What a §12 verification established, in the terms §12.4 requires.
pub struct LegacyOutcome {
    pub dialect: Option<Dialect>,
    /// Where the key came from: the caller (out of band) or the document itself.
    pub key_source: Option<KeySource>,
    /// The `did:key` form of the key the signature actually verified under. §12.4:
    /// an AWR/1 result names a KEY, never an issuer — whose key it is, is the
    /// caller's to decide.
    pub verified_key: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KeySource {
    Caller,
    Document,
}

impl KeySource {
    pub fn as_str(self) -> &'static str {
        match self {
            KeySource::Caller => "caller",
            KeySource::Document => "document",
        }
    }
}

impl LegacyOutcome {
    fn failed(key_source: Option<KeySource>) -> Self {
        LegacyOutcome { dialect: None, key_source, verified_key: None }
    }
}

/// The AWR/1 signing key *carried by the document* (§12.2): `publicKeyJwk`, then
/// `publicKeyBase64`, then `issuer.id` when it happens to be a genuine `did:key`.
///
/// None of these is inside the AWR/1 signature (§12.4), which is why the caller
/// reports `AWR-LEGACY-004` when this is the source.
fn document_key(doc: &Value) -> Option<[u8; 32]> {
    let issuer = doc.get("issuer")?;
    if let Some(jwk) = issuer.get("publicKeyJwk") {
        if jwk.get("kty").and_then(|v| v.as_str()) == Some("OKP")
            && jwk.get("crv").and_then(|v| v.as_str()) == Some("Ed25519")
        {
            if let Some(raw) = jwk
                .get("x")
                .and_then(|x| x.as_str())
                .and_then(|x| b64_decode(x, false).ok())
            {
                if raw.len() == 32 {
                    let mut pk = [0u8; 32];
                    pk.copy_from_slice(&raw);
                    return Some(pk);
                }
            }
        }
    }
    if let Some(raw) = issuer
        .get("publicKeyBase64")
        .and_then(|v| v.as_str())
        .and_then(|v| b64_decode(v, false).ok())
    {
        if raw.len() == 32 {
            let mut pk = [0u8; 32];
            pk.copy_from_slice(&raw);
            return Some(pk);
        }
    }
    issuer.get("id").and_then(|v| v.as_str()).and_then(|s| parse_did_key(s).ok())
}

/// The key `issuer.id` names, or None when it names none (§12.4).
///
/// A `did:key` bearing a `#` fragment — the §5.3 `verificationMethod` string —
/// names the same key as the bare DID and MUST be read as such.
fn issuer_id_key(doc: &Value) -> Option<[u8; 32]> {
    let id = doc.get("issuer")?.get("id")?.as_str()?;
    if !id.starts_with("did:key:") {
        return None;
    }
    parse_did_key(id.split('#').next().unwrap_or(id)).ok()
}

/// Verify an AWR/1 document (§12). `AWR-LEGACY-001` is always reported.
///
/// IMPLEMENTATION CHOICE: the §3.1 envelope rules are **not** applied to an
/// AWR/1 document. `awrVersion` MUST be "2.0.0" only "for documents conforming
/// to this specification", and the AWR/2 `@context`, object-form `issuer` and
/// digest-reference `parents` postdate AWR/1 by definition; applying them would
/// make every legacy document invalid for reasons §12 does not state.
///
/// IMPLEMENTATION CHOICE: the signing key is taken from
/// `issuer.publicKeyJwk` when present, otherwise from `issuer.id` when it
/// happens to be a real `did:key`. Appendix D records that the AWR/1 identifier
/// was `did:key:` plus the first 32 characters of a base64 public key, which
/// names no recoverable key; when neither source yields one, this implementation
/// reports `AWR-LEGACY-002` rather than pretending to verify.
pub fn verify_legacy(doc: &Value, rep: &mut Report, opts: &LegacyOptions) -> LegacyOutcome {
    rep.push(
        "AWR-LEGACY-001",
        format!(
            "verified under the AWR/1 legacy rules (§12); {} are outside the legacy signature and are NOT attested",
            UNSIGNED_FIELDS.join(", ")
        ),
    );

    // §12.4 step 2.
    let subject = match doc.get("credentialSubject") {
        Some(s) if s.is_object() => s,
        _ => {
            rep.push("AWR-DOC-008", "credentialSubject missing or not an object");
            return LegacyOutcome::failed(None);
        }
    };

    let proof = match doc.get("proof") {
        Some(Value::Array(items)) => match items.iter().find(|p| {
            p.get("type").and_then(|t| t.as_str()) == Some(LEGACY_PROOF_TYPE)
        }) {
            Some(p) => p.clone(),
            None => {
                rep.push("AWR-PROOF-001", "no Ed25519Signature2018 proof in the proof array");
                return LegacyOutcome::failed(None);
            }
        },
        Some(p) => p.clone(),
        None => {
            rep.push("AWR-PROOF-001", "proof missing");
            return LegacyOutcome::failed(None);
        }
    };

    // §12.4 step 3: the caller's out-of-band key wins outright. Nothing the
    // document carries is substituted for it, and nothing is tried as a fallback
    // when it fails — a fallback hands the choice of key back to the sender.
    let (public_key, key_source) = match opts.expected_key {
        Some(k) => (k, KeySource::Caller),
        None => match document_key(doc) {
            Some(k) => {
                rep.push(
                    "AWR-LEGACY-004",
                    "the AWR/1 signature was checked against key material carried by the document itself, which the AWR/1 signature does not cover; this shows only that the file is internally consistent and attests NO issuer identity (§12.4) — supply the expected key out of band to learn who signed",
                );
                (k, KeySource::Document)
            }
            None => {
                // §12.2: no usable key material, so the document cannot be
                // checked at all. The code is AWR-KEY-001, not AWR-LEGACY-002.
                rep.push(
                    "AWR-KEY-001",
                    "no AWR/1 signing key could be recovered: issuer.publicKeyJwk, issuer.publicKeyBase64 or a genuine did:key issuer.id is required (\u{a7}12.2), or an expected key supplied out of band (\u{a7}12.4); Appendix D records that AWR/1 identifiers named no key",
                );
                return LegacyOutcome::failed(Some(KeySource::Document));
            }
        },
    };

    // §12.4 step 4: two disagreeing statements about the signer are an error, and
    // the fragment form `did:key:z6Mk…#z6Mk…` (§5.3) names the same key as the
    // bare DID. An implementation that parsed only the bare form let an attacker
    // keep the victim's DID as a literal prefix of `issuer.id` while supplying
    // their own `publicKeyJwk`, and reported valid: true.
    if let Some(named) = issuer_id_key(doc) {
        if named != public_key {
            rep.push(
                "AWR-KEY-003",
                format!(
                    "issuer.id names {} but the AWR/1 signature was to be checked against {}; AWR/1 signs neither, so there is no way to tell which the issuer meant (\u{a7}12.4)",
                    did_from_public_key(&named),
                    did_from_public_key(&public_key)
                ),
            );
            return LegacyOutcome::failed(Some(key_source));
        }
    }

    // §12.4 step 5 / §12.2: a base64 proofValue (§6.1's multibase rule is an
    // AWR/2 rule), and a value that is not base64 or does not decode to 64 bytes
    // is AWR-PROOF-005 — not AWR-LEGACY-002, which means specifically that both
    // dialects were tried against a usable key and signature and both failed.
    let signature: [u8; 64] = match proof.get("proofValue").and_then(|v| v.as_str()) {
        Some(pv) => match b64_decode(pv, false) {
            Ok(raw) if raw.len() == 64 => {
                let mut s = [0u8; 64];
                s.copy_from_slice(&raw);
                s
            }
            Ok(raw) => {
                rep.push(
                    "AWR-PROOF-005",
                    format!("legacy base64 proofValue decodes to {} bytes, expected 64", raw.len()),
                );
                return LegacyOutcome::failed(Some(key_source));
            }
            Err(e) => {
                rep.push("AWR-PROOF-005", format!("legacy proofValue is not base64: {}", e));
                return LegacyOutcome::failed(Some(key_source));
            }
        },
        None => {
            rep.push("AWR-PROOF-005", "legacy proofValue missing");
            return LegacyOutcome::failed(Some(key_source));
        }
    };

    // §12.4 step 6.
    for dialect in [Dialect::A, Dialect::B] {
        let message = match legacy_canonical(subject, dialect) {
            Ok(m) => m,
            Err(e) => {
                // §12.1: the subject holds a value the legacy form does not define
                // a rendering for, so there is nothing to check the signature over.
                rep.push("AWR-LEGACY-002", e);
                return LegacyOutcome::failed(Some(key_source));
            }
        };
        if crate::proof::verify(&public_key, message.as_bytes(), &signature).is_ok() {
            return LegacyOutcome {
                dialect: Some(dialect),
                key_source: Some(key_source),
                verified_key: Some(did_from_public_key(&public_key)),
            };
        }
    }

    let nfc_note = if has_non_ascii(subject) {
        "; the subject contains non-ASCII string data, and this implementation does not apply the NFC normalization the legacy form used"
    } else {
        ""
    };
    rep.push(
        "AWR-LEGACY-002",
        format!(
            "both legacy canonical dialects failed to verify (integer-preserving and float-coercing){}",
            nfc_note
        ),
    );
    LegacyOutcome::failed(Some(key_source))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::didkey::did_from_public_key;
    use crate::encoding::b64_encode;
    use crate::json::parse;
    use ed25519_dalek::SigningKey;

    fn subject() -> Value {
        parse(
            br#"{"work":{"latencyMs":2340,"modelId":"m@v"},"outputDigest":"sha256-x","flag":true,
                 "none":null,"parents":[{"id":"urn:uuid:p"}],"empty":{}}"#,
        )
        .unwrap()
    }

    #[test]
    fn dialects_differ_only_in_integer_rendering() {
        let a = legacy_canonical(&subject(), Dialect::A).unwrap();
        let b = legacy_canonical(&subject(), Dialect::B).unwrap();
        assert!(a.contains("work.latencyMs=2340"), "{}", a);
        assert!(b.contains("work.latencyMs=2340.0"), "{}", b);
        assert_eq!(a.replace("2340", "2340.0"), b);
        // §12.1: dotted paths, pipe delimiter, entries sorted by whole path, `null` for
        // null, and an empty object contributing NO entry (`empty={}` is absent).
        assert_eq!(
            a,
            "flag=true|none=null|outputDigest=sha256-x|parents.0.id=urn:uuid:p|work.latencyMs=2340|work.modelId=m@v"
        );
    }

    #[test]
    fn a_number_outside_the_defined_range_has_no_legacy_form() {
        // §12.1: |x| >= 10^15 has no defined rendering, so the caller reports
        // AWR-LEGACY-002 instead of inventing one.
        let v = parse(br#"{"huge":1000000000000000}"#).unwrap();
        assert!(legacy_canonical(&v, Dialect::A).is_err());
        let f = parse(br#"{"huge":1e300}"#).unwrap();
        assert!(legacy_canonical(&f, Dialect::B).is_err());
    }

    #[test]
    fn entries_are_sorted_by_whole_path_not_per_level() {
        // §12.1(3): `a!` precedes `a.z`, because `!` (U+0021) precedes `.` (U+002E).
        let v = parse(br#"{"a":{"z":"nested"},"a!":"scalar"}"#).unwrap();
        assert_eq!(legacy_canonical(&v, Dialect::A).unwrap(), "a!=scalar|a.z=nested");
    }

    fn legacy_doc(sk: &SigningKey, dialect: Dialect, jwk: bool) -> Value {
        let subject = subject();
        let msg = legacy_canonical(&subject, dialect).expect("renderable");
        let sig = crate::proof::sign(sk, msg.as_bytes());
        let pk = sk.verifying_key().to_bytes();
        let issuer = if jwk {
            format!(
                r#"{{"id":"did:key:{}","publicKeyJwk":{}}}"#,
                // the AWR/1 identifier form: not a real did:key
                &crate::encoding::b64_encode(&pk)[..32],
                crate::json::to_string_compact(&crate::didkey::public_key_jwk(&pk))
            )
        } else {
            format!(r#"{{"id":"{}"}}"#, did_from_public_key(&pk))
        };
        parse(
            format!(
                r#"{{"id":"urn:uuid:legacy","type":["VerifiableCredential","WorkReceipt"],
                      "issuer":{},"hubInfo":{{"note":"unsigned"}},
                      "credentialSubject":{},
                      "proof":{{"type":"Ed25519Signature2018","proofValue":"{}"}}}}"#,
                issuer,
                crate::json::to_string_compact(&subject),
                b64_encode(&sig)
            )
            .as_bytes(),
        )
        .unwrap()
    }

    #[test]
    fn both_dialects_are_accepted() {
        let sk = SigningKey::from_bytes(&[5u8; 32]);
        for (dialect, jwk) in [(Dialect::A, false), (Dialect::B, false), (Dialect::A, true), (Dialect::B, true)] {
            let doc = legacy_doc(&sk, dialect, jwk);
            assert!(is_legacy(&doc));
            let mut rep = Report::default();
            let out = verify_legacy(&doc, &mut rep, &LegacyOptions::default());
            assert_eq!(out.dialect, Some(dialect), "reasons {:?}", rep.reasons);
            assert!(rep.valid(), "{:?}", rep.reasons);
            assert!(rep.has_code("AWR-LEGACY-001"));
        }
    }

    #[test]
    fn tampered_legacy_document_fails_under_both_dialects() {
        let sk = SigningKey::from_bytes(&[5u8; 32]);
        let mut doc = legacy_doc(&sk, Dialect::A, false);
        let mut subject = doc.get("credentialSubject").unwrap().clone();
        subject.set("outputDigest", Value::string("sha256-tampered"));
        doc.set("credentialSubject", subject);
        let mut rep = Report::default();
        assert_eq!(verify_legacy(&doc, &mut rep, &LegacyOptions::default()).dialect, None);
        assert!(rep.has_code("AWR-LEGACY-002"));
        assert!(!rep.valid());
    }

    #[test]
    fn changing_an_unsigned_field_does_not_break_the_legacy_signature() {
        // This is the AWR/1 weakness §13.1 describes, demonstrated: `id` is
        // outside the signature, so renaming the document keeps it "valid".
        let sk = SigningKey::from_bytes(&[5u8; 32]);
        let mut doc = legacy_doc(&sk, Dialect::A, false);
        doc.set("id", Value::string("urn:uuid:renamed-by-an-intermediary"));
        let mut rep = Report::default();
        assert_eq!(verify_legacy(&doc, &mut rep, &LegacyOptions::default()).dialect, Some(Dialect::A));
        assert!(rep.valid());
    }

    #[test]
    fn unrecoverable_key_is_key_001() {
        let sk = SigningKey::from_bytes(&[5u8; 32]);
        let mut doc = legacy_doc(&sk, Dialect::A, false);
        // the historical identifier form: did:key: + 32 base64 characters
        let pk = sk.verifying_key().to_bytes();
        doc.set(
            "issuer",
            parse(format!(r#"{{"id":"did:key:{}"}}"#, &b64_encode(&pk)[..32]).as_bytes()).unwrap(),
        );
        let mut rep = Report::default();
        assert_eq!(verify_legacy(&doc, &mut rep, &LegacyOptions::default()).dialect, None);
        // §12.2: no usable key material is AWR-KEY-001. AWR-LEGACY-002 means both
        // dialects were tried against a usable key and signature and both failed,
        // which is a different statement and was what this build used to report.
        assert!(rep.has_code("AWR-KEY-001"), "{:?}", rep.reasons);
        assert!(!rep.has_code("AWR-LEGACY-002"), "{:?}", rep.reasons);
    }

    #[test]
    fn awr2_document_is_not_legacy() {
        let doc = parse(br#"{"proof":{"type":"DataIntegrityProof"}}"#).unwrap();
        assert!(!is_legacy(&doc));
    }
}
