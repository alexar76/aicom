//! The §11.1 verification result and the §11.2 reason-code registry.

use crate::json::{to_string_compact, Value};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Error,
    Warning,
}

impl Severity {
    pub fn as_str(self) -> &'static str {
        match self {
            Severity::Error => "error",
            Severity::Warning => "warning",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Reason {
    pub code: String,
    pub severity: Severity,
    pub detail: String,
}

impl Reason {
    pub fn to_value(&self) -> Value {
        Value::object(vec![
            ("code".to_string(), Value::string(self.code.clone())),
            ("severity".to_string(), Value::string(self.severity.as_str())),
            ("detail".to_string(), Value::string(self.detail.clone())),
        ])
    }
}

/// The complete registry of §11.2, with the severity the specification assigns.
/// Codes marked *(warning)* in the specification appear here as warnings; every
/// other code is an error. Used by `Report::push` to guarantee this
/// implementation can never emit a warning code as an error or vice versa, and
/// never emit a code the specification does not define.
pub const REGISTRY: &[(&str, Severity)] = &[
    // Document
    ("AWR-DOC-001", Severity::Error),
    ("AWR-DOC-002", Severity::Error),
    ("AWR-DOC-003", Severity::Error),
    ("AWR-DOC-004", Severity::Error),
    ("AWR-DOC-005", Severity::Error),
    ("AWR-DOC-006", Severity::Error),
    ("AWR-DOC-007", Severity::Error),
    ("AWR-DOC-008", Severity::Error),
    ("AWR-DOC-009", Severity::Error),
    ("AWR-DOC-010", Severity::Error),
    // Canonicalization
    ("AWR-CANON-001", Severity::Error),
    ("AWR-CANON-002", Severity::Error),
    ("AWR-CANON-003", Severity::Error),
    ("AWR-CANON-004", Severity::Error),
    ("AWR-CANON-005", Severity::Error),
    ("AWR-CANON-006", Severity::Error),
    // Keys
    ("AWR-KEY-001", Severity::Error),
    ("AWR-KEY-002", Severity::Error),
    ("AWR-KEY-003", Severity::Error),
    ("AWR-KEY-004", Severity::Error),
    // Proof
    ("AWR-PROOF-001", Severity::Error),
    ("AWR-PROOF-002", Severity::Error),
    ("AWR-PROOF-003", Severity::Error),
    ("AWR-PROOF-004", Severity::Error),
    ("AWR-PROOF-005", Severity::Error),
    ("AWR-PROOF-006", Severity::Error),
    ("AWR-PROOF-007", Severity::Error),
    ("AWR-PROOF-008", Severity::Error),
    ("AWR-PROOF-009", Severity::Error),
    // Receipt
    ("AWR-RCPT-001", Severity::Error),
    ("AWR-RCPT-002", Severity::Error),
    ("AWR-RCPT-003", Severity::Error),
    ("AWR-RCPT-004", Severity::Error),
    ("AWR-RCPT-005", Severity::Error),
    ("AWR-RCPT-006", Severity::Error),
    // Verdict
    ("AWR-VDCT-001", Severity::Error),
    ("AWR-VDCT-002", Severity::Error),
    ("AWR-VDCT-003", Severity::Error),
    ("AWR-VDCT-004", Severity::Error),
    ("AWR-VDCT-005", Severity::Error),
    ("AWR-VDCT-006", Severity::Warning),
    ("AWR-VDCT-007", Severity::Error),
    // Blame
    ("AWR-BLAME-001", Severity::Error),
    ("AWR-BLAME-002", Severity::Error),
    ("AWR-BLAME-003", Severity::Error),
    ("AWR-BLAME-004", Severity::Error),
    // Chain
    ("AWR-CHAIN-001", Severity::Error),
    ("AWR-CHAIN-002", Severity::Error),
    ("AWR-CHAIN-003", Severity::Error),
    ("AWR-CHAIN-004", Severity::Error),
    ("AWR-CHAIN-005", Severity::Error),
    ("AWR-CHAIN-006", Severity::Error),
    ("AWR-CHAIN-007", Severity::Warning),
    // Bundle
    ("AWR-BUNDLE-001", Severity::Error),
    ("AWR-BUNDLE-002", Severity::Error),
    ("AWR-BUNDLE-003", Severity::Error),
    // Profile
    ("AWR-PROFILE-001", Severity::Error),
    ("AWR-PROFILE-002", Severity::Error),
    ("AWR-PROFILE-003", Severity::Error),
    ("AWR-PROFILE-004", Severity::Error),
    ("AWR-L2-001", Severity::Warning),
    // Environment, time, legacy
    ("AWR-ENV-001", Severity::Warning),
    ("AWR-TIME-001", Severity::Warning),
    ("AWR-TIME-002", Severity::Warning),
    ("AWR-LEGACY-001", Severity::Warning),
    ("AWR-LEGACY-002", Severity::Error),
    ("AWR-LEGACY-003", Severity::Error),
    ("AWR-LEGACY-004", Severity::Warning),
    ("AWR-LEGACY-005", Severity::Error),
];

pub fn registry_severity(code: &str) -> Option<Severity> {
    REGISTRY.iter().find(|(c, _)| *c == code).map(|(_, s)| *s)
}

#[derive(Debug, Clone, Copy, Default)]
pub struct ChainStats {
    pub resolved: usize,
    pub unresolved: usize,
}

/// The §11.1 result.
#[derive(Debug, Clone, Default)]
pub struct Report {
    pub awr_version: Option<String>,
    pub document_type: Option<String>,
    pub profile: Option<String>,
    pub reasons: Vec<Reason>,
    pub warnings: Vec<Reason>,
    pub chain: ChainStats,
    /// Extra members, appended after the required ones. §11.1 requires "at
    /// least" the listed fields, so additional reporting lives here.
    pub extra: Vec<(String, Value)>,
}

impl Report {
    /// Record a reason. The severity comes from the §11.2 registry, so the
    /// call site cannot misclassify a code; an unknown code panics in debug
    /// builds and is recorded as an error otherwise.
    pub fn push(&mut self, code: &str, detail: impl Into<String>) {
        let severity = match registry_severity(code) {
            Some(s) => s,
            None => {
                debug_assert!(false, "reason code {} is not in the §11.2 registry", code);
                Severity::Error
            }
        };
        let reason = Reason { code: code.to_string(), severity, detail: detail.into() };
        let bucket = match severity {
            Severity::Error => &mut self.reasons,
            Severity::Warning => &mut self.warnings,
        };
        // Identical (code, detail) pairs are recorded once; distinct details for
        // the same code are all kept, because §11.1 requires all errors.
        if !bucket.iter().any(|r| r.code == reason.code && r.detail == reason.detail) {
            bucket.push(reason);
        }
    }

    pub fn has_code(&self, code: &str) -> bool {
        self.reasons.iter().chain(self.warnings.iter()).any(|r| r.code == code)
    }

    pub fn codes(&self) -> Vec<String> {
        self.reasons
            .iter()
            .chain(self.warnings.iter())
            .map(|r| r.code.clone())
            .collect()
    }

    /// §11.1: `valid` is true iff `reasons` holds no error-severity entry.
    pub fn valid(&self) -> bool {
        !self.reasons.iter().any(|r| r.severity == Severity::Error)
    }

    pub fn set_extra(&mut self, key: &str, value: Value) {
        for (k, v) in self.extra.iter_mut() {
            if k == key {
                *v = value;
                return;
            }
        }
        self.extra.push((key.to_string(), value));
    }

    /// §11.1: `verifiedProof` is non-null **if and only if** the result reports
    /// no `AWR-CANON-*`, no `AWR-KEY-*` and no `AWR-PROOF-*` code — exactly the
    /// conditions §6.3 lists as making step 6 impossible, plus step 6's own
    /// failure. Deriving it from the codes rather than trusting the call site is
    /// what stopped this build reporting `verifiedProof: 0` beside
    /// `AWR-KEY-003`, where §5.2 leaves no authoritative key to check against.
    fn verified_proof(&self) -> Value {
        let blocked = self.reasons.iter().any(|r| {
            r.code.starts_with("AWR-CANON-")
                || r.code.starts_with("AWR-KEY-")
                || r.code.starts_with("AWR-PROOF-")
        });
        if blocked {
            return Value::Null;
        }
        self.extra
            .iter()
            .find(|(k, _)| k == "verifiedProof")
            .map(|(_, v)| v.clone())
            .unwrap_or(Value::Null)
    }

    /// §11.1: `awrVersion` and `documentType` are null whenever any `AWR-CANON-*`
    /// code is reported. A document with no canonical form (§4) has no confirmed
    /// content — §4.3 exists because the bytes it canonicalizes to are not the
    /// bytes its issuer signed — and leaving the two free made them a property of
    /// the parser's architecture rather than of the document: this build reads
    /// `type` off the `2340.0` document, which the other two reject before they see
    /// it, and cannot read it off the lone-surrogate document, which they can.
    fn no_canonical_form(&self) -> bool {
        self.reasons.iter().any(|r| r.code.starts_with("AWR-CANON-"))
    }

    pub fn to_value(&self) -> Value {
        let opt = |o: &Option<String>| match o {
            Some(s) => Value::string(s.clone()),
            None => Value::Null,
        };
        // §11.1: null when the document has no canonical form; see no_canonical_form.
        let received = |o: &Option<String>| {
            if self.no_canonical_form() {
                Value::Null
            } else {
                opt(o)
            }
        };
        let mut members = vec![
            ("valid".to_string(), Value::Bool(self.valid())),
            ("awrVersion".to_string(), received(&self.awr_version)),
            ("documentType".to_string(), received(&self.document_type)),
            ("profile".to_string(), opt(&self.profile)),
            (
                "reasons".to_string(),
                Value::Array(self.reasons.iter().map(|r| r.to_value()).collect()),
            ),
            (
                "warnings".to_string(),
                Value::Array(self.warnings.iter().map(|r| r.to_value()).collect()),
            ),
            (
                "chain".to_string(),
                Value::object(vec![
                    ("resolved".to_string(), Value::int(self.chain.resolved as i64)),
                    ("unresolved".to_string(), Value::int(self.chain.unresolved as i64)),
                ]),
            ),
            // §11.1: present on every result, so a caller can read it without
            // knowing which implementation produced the result.
            ("verifiedProof".to_string(), self.verified_proof()),
        ];
        // `verifiedProof` is a required member above; skip the staging copy that
        // `set_extra` left behind so it is not emitted twice.
        members.extend(
            self.extra
                .iter()
                .filter(|(k, _)| k != "verifiedProof")
                .cloned(),
        );
        Value::object(members)
    }

    pub fn to_json(&self) -> String {
        to_string_compact(&self.to_value())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_has_no_duplicates_and_covers_the_specification() {
        let mut seen: Vec<&str> = Vec::new();
        for (c, _) in REGISTRY {
            assert!(!seen.contains(c), "duplicate registry entry {}", c);
            seen.push(c);
        }
        // Counts from §11.2, per family.
        let count = |prefix: &str| REGISTRY.iter().filter(|(c, _)| c.starts_with(prefix)).count();
        assert_eq!(count("AWR-DOC-"), 10);
        assert_eq!(count("AWR-CANON-"), 6);
        assert_eq!(count("AWR-KEY-"), 4);
        assert_eq!(count("AWR-PROOF-"), 9);
        assert_eq!(count("AWR-RCPT-"), 6);
        assert_eq!(count("AWR-VDCT-"), 7);
        assert_eq!(count("AWR-BLAME-"), 4);
        assert_eq!(count("AWR-CHAIN-"), 7);
        assert_eq!(count("AWR-BUNDLE-"), 3);
        assert_eq!(count("AWR-PROFILE-"), 4);
        assert_eq!(count("AWR-L2-"), 1);
        assert_eq!(count("AWR-ENV-"), 1);
        assert_eq!(count("AWR-TIME-"), 2);
        assert_eq!(count("AWR-LEGACY-"), 5);
        assert_eq!(REGISTRY.len(), 69);
        // Exactly the eight codes the specification marks *(warning)*.
        let warnings: Vec<&str> = REGISTRY
            .iter()
            .filter(|(_, s)| *s == Severity::Warning)
            .map(|(c, _)| *c)
            .collect();
        assert_eq!(
            warnings,
            vec![
                "AWR-VDCT-006",
                "AWR-CHAIN-007",
                "AWR-L2-001",
                "AWR-ENV-001",
                "AWR-TIME-001",
                "AWR-TIME-002",
                "AWR-LEGACY-001",
                "AWR-LEGACY-004",
            ]
        );
    }

    #[test]
    fn valid_tracks_error_severity_only() {
        let mut r = Report::default();
        assert!(r.valid());
        r.push("AWR-ENV-001", "attestation present");
        assert!(r.valid(), "a warning must not invalidate");
        assert_eq!(r.warnings.len(), 1);
        assert!(r.reasons.is_empty());
        r.push("AWR-PROOF-006", "signature failed");
        assert!(!r.valid());
    }

    #[test]
    fn identical_reasons_are_deduplicated() {
        let mut r = Report::default();
        r.push("AWR-CHAIN-003", "same");
        r.push("AWR-CHAIN-003", "same");
        r.push("AWR-CHAIN-003", "other");
        assert_eq!(r.reasons.len(), 2);
    }

    #[test]
    fn result_shape_matches_the_specification_example() {
        let mut r = Report::default();
        r.awr_version = Some("2.0.0".to_string());
        r.document_type = Some("WorkReceipt".to_string());
        r.push("AWR-PROOF-006", "…");
        r.push("AWR-ENV-001", "…");
        r.chain = ChainStats { resolved: 1, unresolved: 2 };
        assert_eq!(
            r.to_json(),
            r#"{"valid":false,"awrVersion":"2.0.0","documentType":"WorkReceipt","profile":null,"reasons":[{"code":"AWR-PROOF-006","severity":"error","detail":"…"}],"warnings":[{"code":"AWR-ENV-001","severity":"warning","detail":"…"}],"chain":{"resolved":1,"unresolved":2},"verifiedProof":null}"#
        );
    }

    /// §11.1: `verifiedProof` is non-null iff no `AWR-CANON-*`, `AWR-KEY-*` or
    /// `AWR-PROOF-*` code is reported. The interesting half is the second: a
    /// semantic or chain error leaves the signature check untouched, so the index
    /// survives an invalid document.
    #[test]
    fn verified_proof_is_a_function_of_the_codes_reported() {
        let mut r = Report::default();
        r.set_extra("verifiedProof", Value::int(0));
        assert!(r.to_json().contains(r#""verifiedProof":0"#));

        // A chain error does not prevent §6.3 step 6, so the index stays.
        let mut chained = r.clone();
        chained.push("AWR-CHAIN-003", "parent digest mismatch");
        assert!(chained.to_json().contains(r#""verifiedProof":0"#));

        // Each of the three blocking families nulls it.
        for code in ["AWR-CANON-003", "AWR-KEY-003", "AWR-PROOF-002"] {
            let mut blocked = r.clone();
            blocked.push(code, "…");
            assert!(
                blocked.to_json().contains(r#""verifiedProof":null"#),
                "{} must null verifiedProof, got {}",
                code,
                blocked.to_json()
            );
        }
        // And it is never emitted twice, even though it is staged in `extra`.
        assert_eq!(r.to_json().matches("verifiedProof").count(), 1);
    }
}
