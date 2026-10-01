//! Envelope (§3.1), subject (§3.3–§3.5) and proof-object (§6.1, §5.2–§5.3)
//! checks. Every function records reason codes and keeps going: §11.1 requires
//! all determinable errors, not the first.

use crate::decimal::{cmp_decimal, is_amount, is_unit_interval};
use crate::didkey::{check_public_key_jwk, method_specific_id, parse_did_key};
use crate::encoding::multibase_decode;
use crate::json::{canonicalize, Value};
use crate::proof::{CRYPTOSUITE, PROOF_PURPOSE, PROOF_TYPE};
use crate::report::Report;
use crate::sri::{parse_sri, SriError};
use crate::timefmt::{parse_rfc3339_utc, Timestamp};
use crate::{AWR_CONTEXT, AWR_MAJOR, DOC_TYPES, VC2_CONTEXT};

pub const WORK_STATUS: [&str; 5] = ["succeeded", "failed", "refused", "timeout", "partial"];
pub const VERDICTS: [&str; 3] = ["pass", "fail", "inconclusive"];
pub const FAILURE_CLASSES: [&str; 8] = [
    "wrong-output",
    "malformed-output",
    "unavailable",
    "timeout",
    "policy-violation",
    "upstream-input",
    "cost-overrun",
    "unknown",
];

/// What the envelope check could establish about a document.
#[derive(Debug, Clone, Default)]
pub struct Envelope {
    pub id: Option<String>,
    pub doc_type: Option<String>,
    pub awr_version: Option<String>,
    pub issuer_id: Option<String>,
    pub valid_from: Option<Timestamp>,
    pub valid_until: Option<Timestamp>,
}

/// "Absolute URI" (§3.1) read as "has a scheme", i.e. is not a relative
/// reference (RFC 3986 §4.3 without the no-fragment restriction).
///
/// IMPLEMENTATION CHOICE: RFC 3986's `absolute-URI` production forbids a
/// fragment, but §3.1 only says "absolute URI" while explicitly allowing an
/// HTTPS URL that resolves to the document, and a fragment identifies a part of
/// a retrieved document rather than making the reference relative. A fragment is
/// therefore accepted; a missing scheme, whitespace, or an empty
/// scheme-specific part is not.
pub fn is_absolute_uri(s: &str) -> bool {
    let colon = match s.find(':') {
        Some(i) if i > 0 => i,
        _ => return false,
    };
    let scheme = &s[..colon];
    let mut chars = scheme.chars();
    match chars.next() {
        Some(c) if c.is_ascii_alphabetic() => {}
        _ => return false,
    }
    if !chars.all(|c| c.is_ascii_alphanumeric() || matches!(c, '+' | '-' | '.')) {
        return false;
    }
    let rest = &s[colon + 1..];
    !rest.is_empty() && !s.chars().any(|c| c.is_whitespace())
}

/// §3.1 envelope checks. Reports `AWR-DOC-002`…`AWR-DOC-010`.
pub fn check_envelope(doc: &Value, rep: &mut Report) -> Envelope {
    let mut env = Envelope::default();

    // @context (§3.1): array, first element exactly the VC 2.0 context, and the
    // AWR namespace somewhere in it. Never dereferenced (§13.5).
    match doc.get("@context") {
        Some(Value::Array(items)) => {
            match items.first().and_then(|v| v.as_str()) {
                Some(VC2_CONTEXT) => {}
                Some(other) => rep.push(
                    "AWR-DOC-002",
                    format!("@context[0] is {:?}, expected {:?}", other, VC2_CONTEXT),
                ),
                None => rep.push("AWR-DOC-002", "@context[0] is missing or not a string"),
            }
            if !items.iter().any(|v| v.as_str() == Some(AWR_CONTEXT)) {
                rep.push(
                    "AWR-DOC-003",
                    format!("@context does not contain the AWR namespace {:?}", AWR_CONTEXT),
                );
            }
        }
        Some(other) => {
            rep.push("AWR-DOC-002", format!("@context is a {}, not an array", other.type_name()));
            rep.push("AWR-DOC-003", "AWR namespace URI absent from @context");
        }
        None => {
            rep.push("AWR-DOC-002", "@context missing");
            rep.push("AWR-DOC-003", "AWR namespace URI absent from @context");
        }
    }

    // type (§3.1)
    match doc.get("type") {
        Some(Value::Array(items)) => {
            let strings: Vec<&str> = items.iter().filter_map(|v| v.as_str()).collect();
            if !strings.contains(&"VerifiableCredential") {
                rep.push("AWR-DOC-004", "type does not contain \"VerifiableCredential\"");
            }
            // §3.1: `type` is a set. A repeated member is what makes a reader that takes
            // the first match and a reader that counts matches disagree about the same
            // bytes, so it is rejected rather than de-duplicated. This implementation
            // de-duplicated silently until the rule was written down.
            let mut seen: Vec<&str> = Vec::new();
            let mut repeated: Vec<&str> = Vec::new();
            for s in &strings {
                if seen.contains(s) {
                    if !repeated.contains(s) {
                        repeated.push(s);
                    }
                } else {
                    seen.push(s);
                }
            }
            if !repeated.is_empty() {
                rep.push(
                    "AWR-DOC-005",
                    format!("type is a set and must not repeat a value; repeated: {:?}", repeated),
                );
            }

            let found: Vec<&str> =
                DOC_TYPES.iter().copied().filter(|t| strings.contains(t)).collect();
            match found.len() {
                1 => env.doc_type = Some(found[0].to_string()),
                0 => rep.push(
                    "AWR-DOC-005",
                    format!("type contains none of {:?}", DOC_TYPES),
                ),
                _ => rep.push(
                    "AWR-DOC-005",
                    format!("type contains more than one AWR type: {:?}", found),
                ),
            }
        }
        other => {
            let what = other.map(|v| v.type_name()).unwrap_or("absent");
            rep.push("AWR-DOC-004", format!("type is {}, expected an array", what));
            rep.push("AWR-DOC-005", format!("type is {}, so no AWR document type is declared", what));
        }
    }

    // issuer (§3.1, §5): an object with `id`. A bare string is rejected.
    match doc.get("issuer") {
        Some(Value::Object(_)) => {
            let issuer = doc.get("issuer").unwrap();
            match issuer.get_nonempty_str("id") {
                Some(id) => env.issuer_id = Some(id.to_string()),
                None => rep.push("AWR-DOC-010", "issuer.id missing, empty, or not a string"),
            }
        }
        Some(Value::Str(s)) => rep.push(
            "AWR-DOC-010",
            format!(
                "issuer is the bare string {:?}; AWR/2 requires an object so that `name` has one place to live (§3.1)",
                s
            ),
        ),
        Some(other) => {
            rep.push("AWR-DOC-010", format!("issuer is a {}, not an object", other.type_name()))
        }
        None => rep.push("AWR-DOC-010", "issuer missing"),
    }

    // validFrom / validUntil (§3.1)
    match doc.get("validFrom").and_then(|v| v.as_str()) {
        Some(s) => match parse_rfc3339_utc(s) {
            Some(t) => env.valid_from = Some(t),
            None => rep.push(
                "AWR-DOC-007",
                format!("validFrom {:?} is not an RFC 3339 UTC date-time with a Z offset", s),
            ),
        },
        None => rep.push("AWR-DOC-007", "validFrom missing or not a string"),
    }
    if let Some(vu) = doc.get("validUntil") {
        match vu.as_str().and_then(parse_rfc3339_utc) {
            Some(t) => {
                env.valid_until = Some(t);
                if let Some(vf) = env.valid_from {
                    if t <= vf {
                        rep.push(
                            "AWR-DOC-007",
                            "validUntil is not later than validFrom".to_string(),
                        );
                    }
                }
            }
            None => rep.push(
                "AWR-DOC-007",
                format!(
                    "validUntil {} is not an RFC 3339 UTC date-time with a Z offset",
                    crate::json::to_string_compact(vu)
                ),
            ),
        }
    }

    // awrVersion (§3.1)
    match doc.get("awrVersion") {
        Some(Value::Str(v)) => {
            env.awr_version = Some(v.clone());
            let major = v.split('.').next().unwrap_or("");
            let well_formed = {
                let parts: Vec<&str> = v.split('.').collect();
                parts.len() == 3
                    && parts.iter().all(|p| !p.is_empty() && p.bytes().all(|c| c.is_ascii_digit()))
            };
            if !well_formed {
                rep.push(
                    "AWR-DOC-009",
                    format!("awrVersion {:?} is not a MAJOR.MINOR.PATCH version string", v),
                );
            } else if major != AWR_MAJOR {
                rep.push(
                    "AWR-DOC-009",
                    format!(
                        "awrVersion {:?} has major version {}, which this implementation does not implement",
                        v, major
                    ),
                );
            }
        }
        Some(other) => rep.push(
            "AWR-DOC-009",
            format!("awrVersion is a {}, expected the string \"2.0.0\"", other.type_name()),
        ),
        None => rep.push("AWR-DOC-009", "awrVersion missing"),
    }

    // credentialSubject (§3.1): exactly one object, never an array.
    match doc.get("credentialSubject") {
        Some(Value::Object(_)) => {}
        Some(Value::Array(_)) => rep.push(
            "AWR-DOC-008",
            "credentialSubject is an array; AWR/2 uses a single subject object",
        ),
        Some(other) => rep.push(
            "AWR-DOC-008",
            format!("credentialSubject is a {}, not an object", other.type_name()),
        ),
        None => rep.push("AWR-DOC-008", "credentialSubject missing"),
    }

    // id (§3.1)
    match doc.get("id").and_then(|v| v.as_str()) {
        Some(id) if is_absolute_uri(id) => env.id = Some(id.to_string()),
        Some(id) => rep.push("AWR-DOC-006", format!("id {:?} is not an absolute URI", id)),
        None => rep.push("AWR-DOC-006", "id missing or not a string"),
    }

    env
}

fn check_sri_field(subject: &Value, field: &str, code: &str, rep: &mut Report) {
    match subject.get(field) {
        None => rep.push(code, format!("{} missing", field)),
        Some(v) => match parse_sri(v) {
            Ok(_) => {}
            Err(e) => {
                let detail = match &e {
                    SriError::NotAString(d) | SriError::BadAlgorithm(d) | SriError::Malformed(d) => {
                        d.clone()
                    }
                };
                rep.push(code, format!("{}: {}", field, detail));
            }
        },
    }
}

/// §3.3 `WorkReceipt` subject checks. `parents` is handled by [`crate::chain`].
pub fn check_receipt(subject: &Value, rep: &mut Report) {
    match subject.get("work") {
        Some(Value::Object(_)) => {
            let work = subject.get("work").unwrap();
            if work.get_nonempty_str("modelId").is_none() {
                rep.push("AWR-RCPT-005", "work.modelId missing, empty, or not a string");
            }
            match work.get("status").and_then(|v| v.as_str()) {
                Some(s) if WORK_STATUS.contains(&s) => {}
                Some(s) => rep.push(
                    "AWR-RCPT-006",
                    format!("work.status {:?} is not one of {:?}", s, WORK_STATUS),
                ),
                None => rep.push("AWR-RCPT-006", "work.status missing or not a string"),
            }
            let completed = match work.get("completedAt").and_then(|v| v.as_str()) {
                Some(s) => match parse_rfc3339_utc(s) {
                    Some(t) => Some(t),
                    None => {
                        rep.push(
                            "AWR-RCPT-003",
                            format!("work.completedAt {:?} is not an RFC 3339 UTC date-time", s),
                        );
                        None
                    }
                },
                None => {
                    rep.push("AWR-RCPT-003", "work.completedAt missing or not a string");
                    None
                }
            };
            if let Some(started_v) = work.get("startedAt") {
                match started_v.as_str().and_then(parse_rfc3339_utc) {
                    Some(started) => {
                        if let Some(c) = completed {
                            if c < started {
                                rep.push(
                                    "AWR-RCPT-003",
                                    "work.completedAt is earlier than work.startedAt",
                                );
                            }
                        }
                    }
                    None => rep.push(
                        "AWR-RCPT-003",
                        format!(
                            "work.startedAt {} is not an RFC 3339 UTC date-time",
                            crate::json::to_string_compact(started_v)
                        ),
                    ),
                }
            }
            if let Some(l) = work.get("latencyMs") {
                match l.as_i64() {
                    Some(v) if v >= 0 => {}
                    Some(v) => rep.push("AWR-RCPT-004", format!("work.latencyMs is {}", v)),
                    None => rep.push(
                        "AWR-RCPT-004",
                        format!(
                            "work.latencyMs {} is not a non-negative integer",
                            crate::json::to_string_compact(l)
                        ),
                    ),
                }
            }
        }
        other => {
            let what = other.map(|v| v.type_name()).unwrap_or("absent");
            rep.push("AWR-RCPT-005", format!("credentialSubject.work is {}, so work.modelId is missing", what));
            rep.push("AWR-RCPT-006", format!("credentialSubject.work is {}, so work.status is missing", what));
            rep.push("AWR-RCPT-003", format!("credentialSubject.work is {}, so work.completedAt is missing", what));
        }
    }

    // §3.3: both digests are REQUIRED, including for a failed receipt.
    check_sri_field(subject, "inputDigest", "AWR-RCPT-001", rep);
    check_sri_field(subject, "outputDigest", "AWR-RCPT-001", rep);

    if let Some(price) = subject.get("price") {
        if price.is_object() {
            match price.get("currency").and_then(|v| v.as_str()) {
                Some(c)
                    if (c.len() == 3 && c.bytes().all(|b| b.is_ascii_uppercase()))
                        || c.starts_with("urn:") => {}
                Some(c) => rep.push(
                    "AWR-RCPT-002",
                    format!(
                        "price.currency {:?} is neither an ISO 4217 alphabetic code nor a urn: URI",
                        c
                    ),
                ),
                None => rep.push("AWR-RCPT-002", "price.currency missing or not a string"),
            }
            match price.get("amount") {
                Some(Value::Str(a)) if is_amount(a) => {}
                Some(Value::Str(a)) => rep.push(
                    "AWR-RCPT-002",
                    format!("price.amount {:?} is not a decimal string", a),
                ),
                Some(other) => rep.push(
                    "AWR-RCPT-002",
                    format!(
                        "price.amount is a {}; it MUST be a decimal string, never a JSON number (§4.3)",
                        other.type_name()
                    ),
                ),
                None => rep.push("AWR-RCPT-002", "price.amount missing"),
            }
        } else {
            rep.push("AWR-RCPT-002", format!("price is a {}, not an object", price.type_name()));
        }
    }

    // §7.3: an attestation that is present and unverified is a warning, always.
    if let Some(env) = subject.get("environment") {
        for field in ["teeAttestation", "zkProof"] {
            if let Some(v) = env.get(field) {
                if !v.is_null() {
                    rep.push(
                        "AWR-ENV-001",
                        format!(
                            "environment.{} is present and was not verified: doing so needs the platform's certificate chain, which is outside AWR/2 (§7.3)",
                            field
                        ),
                    );
                }
            }
        }
    }
}

/// §3.4 `VerificationVerdict` subject checks.
pub fn check_verdict(subject: &Value, rep: &mut Report) {
    match subject.get("verifiedWork") {
        Some(v) if v.is_object() => {
            let has_id = v.get_nonempty_str("id").is_some();
            let sri = v.get("digestSRI");
            if !has_id {
                rep.push("AWR-VDCT-001", "verifiedWork.id missing or empty");
            }
            match sri {
                None => rep.push("AWR-VDCT-001", "verifiedWork.digestSRI missing"),
                Some(s) => {
                    if let Err(e) = parse_sri(s) {
                        rep.push("AWR-CHAIN-002", format!("verifiedWork: {}", e.detail()));
                    }
                }
            }
        }
        Some(other) => rep.push(
            "AWR-VDCT-001",
            format!("verifiedWork is a {}, not a digest reference", other.type_name()),
        ),
        None => rep.push("AWR-VDCT-001", "verifiedWork missing"),
    }

    let verdict = subject.get("verdict").and_then(|v| v.as_str());
    match verdict {
        Some(v) if VERDICTS.contains(&v) => {}
        Some(v) => rep.push("AWR-VDCT-004", format!("verdict {:?} is not one of {:?}", v, VERDICTS)),
        None => rep.push("AWR-VDCT-004", "verdict missing or not a string"),
    }

    let score = match subject.get("score") {
        None => None,
        Some(Value::Str(s)) if is_unit_interval(s) => Some(s.clone()),
        Some(Value::Str(s)) => {
            rep.push("AWR-VDCT-002", format!("score {:?} is not a decimal string in [0,1]", s));
            None
        }
        Some(other) => {
            rep.push(
                "AWR-VDCT-002",
                format!(
                    "score is a {}; it MUST be a decimal string, never a JSON number (§4.3)",
                    other.type_name()
                ),
            );
            None
        }
    };

    match subject.get("method") {
        Some(m) if m.is_object() => {
            if m.get_nonempty_str("id").is_none() {
                rep.push("AWR-VDCT-003", "method.id missing or empty");
            }
        }
        Some(other) => rep.push(
            "AWR-VDCT-003",
            format!("method is a {}, not an object", other.type_name()),
        ),
        None => rep.push("AWR-VDCT-003", "method missing"),
    }

    // policy.threshold: §3.4 requires a decimal string in [0,1]. §11.2 registers
    // no dedicated code, so AWR-VDCT-002 (the decimal-in-[0,1] code) is reused.
    let threshold = match subject.get("policy").and_then(|p| p.get("threshold").cloned()) {
        None => None,
        Some(Value::Str(s)) if is_unit_interval(&s) => Some(s),
        Some(Value::Str(s)) => {
            rep.push(
                "AWR-VDCT-002",
                format!("policy.threshold {:?} is not a decimal string in [0,1]", s),
            );
            None
        }
        Some(other) => {
            rep.push(
                "AWR-VDCT-002",
                format!(
                    "policy.threshold is a {}; it MUST be a decimal string (§4.3)",
                    other.type_name()
                ),
            );
            None
        }
    };

    // §3.4: report the inconsistency, do not override the issuer's verdict.
    if let (Some(v), Some(s), Some(t)) = (verdict, score.as_deref(), threshold.as_deref()) {
        if let Some(ord) = cmp_decimal(s, t) {
            let below = ord == std::cmp::Ordering::Less;
            if v == "pass" && below {
                rep.push(
                    "AWR-VDCT-006",
                    format!("verdict is \"pass\" but score {} is below threshold {}", s, t),
                );
            }
            if v == "fail" && !below {
                rep.push(
                    "AWR-VDCT-006",
                    format!("verdict is \"fail\" but score {} meets threshold {}", s, t),
                );
            }
        }
    }

    if let Some(ev) = subject.get("evidence") {
        match ev {
            Value::Array(items) => {
                for (n, item) in items.iter().enumerate() {
                    match item.get("digestSRI") {
                        None => rep.push(
                            "AWR-VDCT-007",
                            format!("evidence[{}] has no digestSRI", n),
                        ),
                        Some(s) => {
                            if let Err(e) = parse_sri(s) {
                                rep.push(
                                    "AWR-CHAIN-002",
                                    format!("evidence[{}]: {}", n, e.detail()),
                                );
                            }
                        }
                    }
                }
            }
            other => rep.push(
                "AWR-VDCT-007",
                format!("evidence is a {}, not an array of digest references", other.type_name()),
            ),
        }
    }
}

/// §3.5 `BlameAttestation` subject checks. Reachability is checked by
/// [`crate::chain`], which needs the other receipts.
pub fn check_blame(subject: &Value, rep: &mut Report) {
    for field in ["chain", "blamedWork"] {
        match subject.get(field) {
            Some(v) if v.is_object() => {
                if v.get_nonempty_str("id").is_none() {
                    rep.push("AWR-BLAME-003", format!("{}.id missing or empty", field));
                }
                match v.get("digestSRI") {
                    None => rep.push("AWR-BLAME-003", format!("{}.digestSRI missing", field)),
                    Some(s) => {
                        if let Err(e) = parse_sri(s) {
                            rep.push("AWR-BLAME-003", format!("{}: {}", field, e.detail()));
                        }
                    }
                }
            }
            Some(other) => rep.push(
                "AWR-BLAME-003",
                format!("{} is a {}, not a digest reference", field, other.type_name()),
            ),
            None => rep.push("AWR-BLAME-003", format!("{} missing", field)),
        }
    }

    match subject.get("failureClass").and_then(|v| v.as_str()) {
        Some(f) if FAILURE_CLASSES.contains(&f) => {}
        Some(f) => rep.push(
            "AWR-BLAME-002",
            format!("failureClass {:?} is not one of {:?}", f, FAILURE_CLASSES),
        ),
        None => rep.push("AWR-BLAME-002", "failureClass missing or not a string"),
    }

    if let Some(c) = subject.get("confidence") {
        match c {
            Value::Str(s) if is_unit_interval(s) => {}
            Value::Str(s) => rep.push(
                "AWR-BLAME-004",
                format!("confidence {:?} is not a decimal string in [0,1]", s),
            ),
            other => rep.push(
                "AWR-BLAME-004",
                format!(
                    "confidence is a {}; it MUST be a decimal string, never a JSON number (§4.3)",
                    other.type_name()
                ),
            ),
        }
    }

    // §3.5 requires `method` with a non-empty id, but §11.2 registers no
    // AWR-BLAME code for it. AWR-VDCT-003 ("method missing or method.id empty")
    // is the registry's only code for this condition, so it is reused here.
    match subject.get("method") {
        Some(m) if m.is_object() => {
            if m.get_nonempty_str("id").is_none() {
                rep.push("AWR-VDCT-003", "method.id missing or empty (BlameAttestation, §3.5)");
            }
        }
        Some(other) => rep.push(
            "AWR-VDCT-003",
            format!("method is a {}, not an object (BlameAttestation, §3.5)", other.type_name()),
        ),
        None => rep.push("AWR-VDCT-003", "method missing (BlameAttestation, §3.5)"),
    }

    if let Some(ev) = subject.get("evidence") {
        if let Value::Array(items) = ev {
            for (n, item) in items.iter().enumerate() {
                if item.get("digestSRI").is_none() {
                    rep.push("AWR-VDCT-007", format!("evidence[{}] has no digestSRI", n));
                }
            }
        }
    }
}

/// One proof object's structural verdict.
#[derive(Debug, Clone)]
pub struct ProofCheck {
    pub index: usize,
    pub verification_method: Option<String>,
    /// Reason codes this proof object failed with, as (code, detail).
    pub failures: Vec<(&'static str, String)>,
    /// 64-byte signature, when `proofValue` was well-formed.
    pub signature: Option<[u8; 64]>,
}

impl ProofCheck {
    pub fn fail(&mut self, code: &'static str, detail: impl Into<String>) {
        self.failures.push((code, detail.into()));
    }
}

/// §6.1 structural checks for one proof object, plus §5.3 verificationMethod.
/// The signature itself is checked by [`crate::verify`], which needs the
/// canonical bytes.
pub fn check_proof_object(
    doc: &Value,
    proof: &Value,
    index: usize,
    issuer_public_key: Option<&[u8; 32]>,
) -> ProofCheck {
    let mut c = ProofCheck {
        index,
        verification_method: proof.get("verificationMethod").and_then(|v| v.as_str()).map(String::from),
        failures: Vec::new(),
        signature: None,
    };
    if !proof.is_object() {
        c.fail("AWR-PROOF-001", format!("proof entry {} is a {}, not an object", index, proof.type_name()));
        return c;
    }
    match proof.get("type").and_then(|v| v.as_str()) {
        Some(PROOF_TYPE) => {}
        Some(other) => c.fail(
            "AWR-PROOF-002",
            format!("proof.type is {:?}, expected {:?}", other, PROOF_TYPE),
        ),
        None => c.fail("AWR-PROOF-002", "proof.type missing or not a string"),
    }
    match proof.get("cryptosuite").and_then(|v| v.as_str()) {
        Some(CRYPTOSUITE) => {}
        Some(other) => c.fail(
            "AWR-PROOF-003",
            format!(
                "cryptosuite {:?} is not supported; AWR/2 registers only {:?} and verifiers must reject unknown suites rather than skipping the proof (§6.4)",
                other, CRYPTOSUITE
            ),
        ),
        None => c.fail("AWR-PROOF-003", "proof.cryptosuite missing or not a string"),
    }
    match proof.get("proofPurpose").and_then(|v| v.as_str()) {
        Some(PROOF_PURPOSE) => {}
        Some(other) => c.fail(
            "AWR-PROOF-004",
            format!("proofPurpose is {:?}, expected {:?}", other, PROOF_PURPOSE),
        ),
        None => c.fail("AWR-PROOF-004", "proof.proofPurpose missing or not a string"),
    }
    match proof.get("created").and_then(|v| v.as_str()) {
        Some(s) => {
            if parse_rfc3339_utc(s).is_none() {
                c.fail(
                    "AWR-PROOF-009",
                    format!("proof.created {:?} is not an RFC 3339 UTC date-time", s),
                );
            }
        }
        None => c.fail("AWR-PROOF-009", "proof.created missing or not a string"),
    }

    // proofValue (§6.1): multibase base58btc of exactly 64 bytes.
    match proof.get("proofValue") {
        Some(Value::Str(pv)) => match multibase_decode(pv) {
            Ok(raw) => {
                if raw.len() == 64 {
                    let mut sig = [0u8; 64];
                    sig.copy_from_slice(&raw);
                    c.signature = Some(sig);
                } else {
                    c.fail(
                        "AWR-PROOF-005",
                        format!("proofValue decodes to {} bytes, expected 64", raw.len()),
                    );
                }
            }
            Err(e) => c.fail(
                "AWR-PROOF-005",
                format!(
                    "proofValue is not multibase base58btc: {} (base64, hex and unprefixed values are rejected, including the AWR/1 legacy form)",
                    e
                ),
            ),
        },
        Some(other) => c.fail(
            "AWR-PROOF-005",
            format!("proofValue is a {}, not a string", other.type_name()),
        ),
        None => c.fail("AWR-PROOF-005", "proofValue missing"),
    }

    // verificationMethod (§5.3)
    if let Some(pk) = issuer_public_key {
        let expected = format!(
            "{}{}#{}",
            crate::didkey::DID_KEY_PREFIX,
            method_specific_id(pk),
            method_specific_id(pk)
        );
        match c.verification_method.as_deref() {
            Some(vm) if vm == expected => {}
            Some(vm) => c.fail(
                "AWR-PROOF-007",
                format!("verificationMethod is {:?}, expected {:?}", vm, expected),
            ),
            None => c.fail("AWR-PROOF-007", "proof.verificationMethod missing or not a string"),
        }
    } else if c.verification_method.is_none() {
        c.fail("AWR-PROOF-007", "proof.verificationMethod missing or not a string");
    }

    // proof.@context vs document @context (§6.2 step 1, AWR-PROOF-008)
    if let Some(pctx) = proof.get("@context") {
        let dctx = doc.get("@context");
        let same = match dctx {
            Some(d) => canonicalize(d).ok() == canonicalize(pctx).ok(),
            None => false,
        };
        if !same {
            c.fail(
                "AWR-PROOF-008",
                "proof.@context differs from the document's @context; §6.2 step 1 requires the proof options to carry the document's value",
            );
        }
    }
    c
}

/// §5 key checks: derive the issuer key and cross-check an optional JWK.
pub fn check_issuer_key(doc: &Value, issuer_id: Option<&str>, rep: &mut Report) -> Option<[u8; 32]> {
    let id = issuer_id?;
    match parse_did_key(id) {
        Ok(pk) => {
            if let Some(jwk) = doc.get("issuer").and_then(|i| i.get("publicKeyJwk")) {
                if let Err(e) = check_public_key_jwk(jwk, &pk) {
                    rep.push(e.code, e.detail);
                }
            }
            Some(pk)
        }
        Err(e) => {
            rep.push(e.code, e.detail);
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::parse;

    fn env_codes(src: &str) -> Vec<String> {
        let mut rep = Report::default();
        let doc = parse(src.as_bytes()).unwrap();
        check_envelope(&doc, &mut rep);
        rep.codes()
    }

    #[test]
    fn absolute_uri_reading() {
        assert!(is_absolute_uri("urn:uuid:8f14e45f-ea1c-4f38-9b8a-1c2d3e4f5a6b"));
        assert!(is_absolute_uri("https://example.com/receipts/1"));
        assert!(is_absolute_uri("https://example.com/r#frag"));
        assert!(!is_absolute_uri("/receipts/1"));
        assert!(!is_absolute_uri("receipts/1"));
        assert!(!is_absolute_uri("8f14e45f"));
        assert!(!is_absolute_uri("urn:"));
        assert!(!is_absolute_uri("1urn:x"));
        assert!(!is_absolute_uri("urn:uu id"));
        assert!(!is_absolute_uri(""));
    }

    #[test]
    fn empty_object_reports_every_envelope_error() {
        let codes = env_codes("{}");
        for expected in [
            "AWR-DOC-002",
            "AWR-DOC-003",
            "AWR-DOC-004",
            "AWR-DOC-005",
            "AWR-DOC-006",
            "AWR-DOC-007",
            "AWR-DOC-008",
            "AWR-DOC-009",
            "AWR-DOC-010",
        ] {
            assert!(codes.contains(&expected.to_string()), "missing {} in {:?}", expected, codes);
        }
    }

    #[test]
    fn bare_string_issuer_is_rejected() {
        let codes = env_codes(r#"{"issuer":"did:key:z6Mk"}"#);
        assert!(codes.contains(&"AWR-DOC-010".to_string()));
    }

    #[test]
    fn two_awr_types_is_doc_005() {
        let src = r#"{"type":["VerifiableCredential","WorkReceipt","VerificationVerdict"]}"#;
        let codes = env_codes(src);
        assert!(codes.contains(&"AWR-DOC-005".to_string()));
        assert!(!codes.contains(&"AWR-DOC-004".to_string()));
    }

    #[test]
    fn awr_version_major_gate() {
        assert!(env_codes(r#"{"awrVersion":"3.0.0"}"#).contains(&"AWR-DOC-009".to_string()));
        assert!(env_codes(r#"{"awrVersion":"2"}"#).contains(&"AWR-DOC-009".to_string()));
        assert!(env_codes(r#"{"awrVersion":2}"#).contains(&"AWR-DOC-009".to_string()));
        let ok = env_codes(r#"{"awrVersion":"2.1.7"}"#);
        assert!(!ok.contains(&"AWR-DOC-009".to_string()), "minor/patch drift is accepted");
    }

    #[test]
    fn valid_until_must_be_later() {
        let codes = env_codes(
            r#"{"validFrom":"2026-07-31T10:15:30Z","validUntil":"2026-07-31T10:15:30Z"}"#,
        );
        assert!(codes.contains(&"AWR-DOC-007".to_string()));
    }

    #[test]
    fn receipt_subject_checks() {
        let mut rep = Report::default();
        let s = parse(
            br#"{"work":{"modelId":"","status":"exploded","startedAt":"2026-07-31T10:15:30Z",
                        "completedAt":"2026-07-31T10:15:00Z","latencyMs":-3},
                 "inputDigest":"sha256-AAAA","price":{"currency":"usd","amount":0.15},
                 "environment":{"teeAttestation":{"quote":"x"}}}"#,
        )
        .unwrap();
        check_receipt(&s, &mut rep);
        let codes = rep.codes();
        for expected in [
            "AWR-RCPT-005",
            "AWR-RCPT-006",
            "AWR-RCPT-003",
            "AWR-RCPT-004",
            "AWR-RCPT-001",
            "AWR-RCPT-002",
            "AWR-ENV-001",
        ] {
            assert!(codes.contains(&expected.to_string()), "missing {} in {:?}", expected, codes);
        }
        // outputDigest missing and inputDigest malformed are both RCPT-001
        assert_eq!(rep.reasons.iter().filter(|r| r.code == "AWR-RCPT-001").count(), 2);
        // the attestation warning must not invalidate
        assert!(rep.warnings.iter().any(|w| w.code == "AWR-ENV-001"));
    }

    #[test]
    fn verdict_subject_checks() {
        let mut rep = Report::default();
        let s = parse(
            br#"{"verifiedWork":{"id":"urn:uuid:1"},"verdict":"maybe","score":"1.5",
                 "policy":{"threshold":"0.8"},"evidence":[{"kind":"trace"}]}"#,
        )
        .unwrap();
        check_verdict(&s, &mut rep);
        let codes = rep.codes();
        for expected in ["AWR-VDCT-001", "AWR-VDCT-004", "AWR-VDCT-002", "AWR-VDCT-003", "AWR-VDCT-007"] {
            assert!(codes.contains(&expected.to_string()), "missing {} in {:?}", expected, codes);
        }
    }

    #[test]
    fn verdict_score_threshold_disagreement_is_a_warning() {
        let mut rep = Report::default();
        let s = parse(
            br#"{"verifiedWork":{"id":"urn:uuid:1","digestSRI":"sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="},
                 "verdict":"pass","score":"0.10","policy":{"threshold":"0.80"},
                 "method":{"id":"urn:example:method:x"}}"#,
        )
        .unwrap();
        check_verdict(&s, &mut rep);
        assert!(rep.valid(), "the issuer's verdict stands: {:?}", rep.reasons);
        assert!(rep.warnings.iter().any(|w| w.code == "AWR-VDCT-006"));
    }

    #[test]
    fn score_as_json_number_is_rejected() {
        let mut rep = Report::default();
        let s = parse(br#"{"score":0.93}"#).unwrap();
        check_verdict(&s, &mut rep);
        assert!(rep.codes().contains(&"AWR-VDCT-002".to_string()));
    }

    #[test]
    fn blame_subject_checks() {
        let mut rep = Report::default();
        let s = parse(br#"{"failureClass":"cosmic-ray","confidence":0.9}"#).unwrap();
        check_blame(&s, &mut rep);
        let codes = rep.codes();
        assert_eq!(codes.iter().filter(|c| *c == "AWR-BLAME-003").count(), 2);
        assert!(codes.contains(&"AWR-BLAME-002".to_string()));
        assert!(codes.contains(&"AWR-BLAME-004".to_string()));
        assert!(codes.contains(&"AWR-VDCT-003".to_string()));
    }

    #[test]
    fn proof_structural_checks() {
        let doc = parse(
            br#"{"@context":["https://www.w3.org/ns/credentials/v2"],
                 "proof":{"type":"Ed25519Signature2018","cryptosuite":"eddsa-rdfc-2022",
                          "proofPurpose":"authentication","created":"yesterday",
                          "proofValue":"AAAA","@context":["urn:other"]}}"#,
        )
        .unwrap();
        let c = check_proof_object(&doc, doc.get("proof").unwrap(), 0, None);
        let codes: Vec<&str> = c.failures.iter().map(|(k, _)| *k).collect();
        for expected in [
            "AWR-PROOF-002",
            "AWR-PROOF-003",
            "AWR-PROOF-004",
            "AWR-PROOF-005",
            "AWR-PROOF-007",
            "AWR-PROOF-008",
            "AWR-PROOF-009",
        ] {
            assert!(codes.contains(&expected), "missing {} in {:?}", expected, codes);
        }
        assert!(c.signature.is_none());
    }

    #[test]
    fn proof_value_must_be_64_bytes_of_base58btc() {
        let short = crate::encoding::multibase_b58_encode(&[7u8; 63]);
        let doc = parse(format!(r#"{{"proof":{{"proofValue":"{}"}}}}"#, short).as_bytes()).unwrap();
        let c = check_proof_object(&doc, doc.get("proof").unwrap(), 0, None);
        assert!(c.failures.iter().any(|(k, d)| *k == "AWR-PROOF-005" && d.contains("63 bytes")));

        let ok = crate::encoding::multibase_b58_encode(&[7u8; 64]);
        let doc = parse(format!(r#"{{"proof":{{"proofValue":"{}"}}}}"#, ok).as_bytes()).unwrap();
        let c = check_proof_object(&doc, doc.get("proof").unwrap(), 0, None);
        assert_eq!(c.signature.unwrap()[0], 7);
        assert!(!c.failures.iter().any(|(k, _)| *k == "AWR-PROOF-005"));

        // base64 of 64 bytes is rejected: the AWR/1 legacy encoding must not pass.
        let b64 = crate::encoding::b64_encode(&[7u8; 64]);
        let doc = parse(format!(r#"{{"proof":{{"proofValue":"{}"}}}}"#, b64).as_bytes()).unwrap();
        let c = check_proof_object(&doc, doc.get("proof").unwrap(), 0, None);
        assert!(c.failures.iter().any(|(k, _)| *k == "AWR-PROOF-005"));
    }
}
