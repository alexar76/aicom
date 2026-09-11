//! Bundles (SPEC §9): an unsigned transport container for several documents.

use crate::chain::AvailableDoc;
use crate::json::Value;
use crate::report::Report;

pub const BUNDLE_VERSION: &str = "2.0";

/// IMPLEMENTATION CHOICE (§9 defines the container but not how to tell one from
/// a document): a bundle is anything carrying `awrBundle`, or carrying
/// `documents` without a `credentialSubject`. Recognising it by the member
/// rather than by its value means a wrong `awrBundle` version is reported as
/// `AWR-BUNDLE-001` instead of being mistaken for a malformed credential.
pub fn looks_like_bundle(v: &Value) -> bool {
    v.get("awrBundle").is_some() || (v.get("documents").is_some() && v.get("credentialSubject").is_none())
}

/// Validate the container and return its documents (§9).
pub fn documents(v: &Value, rep: &mut Report) -> Vec<Value> {
    // §9: fail closed on an unsupported container version. `awrBundle` is the only
    // statement of the container's schema, so nothing inside may be processed —
    // reaching in to pull out things merely *assumed* to be documents is the
    // verifier deciding for itself which bytes to read. Same gate as §3.1's
    // `awrVersion` (`AWR-DOC-009`). This build used to verify the enclosed receipt
    // and report its documentType and verifiedProof for an `awrBundle: "1.0"`.
    match v.get("awrBundle").and_then(|b| b.as_str()) {
        Some(BUNDLE_VERSION) => {}
        Some(other) => {
            rep.push(
                "AWR-BUNDLE-001",
                format!(
                    "awrBundle is {:?}, expected {:?}; nothing inside an unsupported \
                     bundle version is processed (§9)",
                    other, BUNDLE_VERSION
                ),
            );
            return Vec::new();
        }
        None => {
            rep.push("AWR-BUNDLE-001", "awrBundle missing or not a string");
            return Vec::new();
        }
    }
    match v.get("documents") {
        Some(Value::Array(items)) if !items.is_empty() => items.clone(),
        Some(Value::Array(_)) => {
            rep.push("AWR-BUNDLE-001", "documents is empty");
            Vec::new()
        }
        Some(other) => {
            rep.push(
                "AWR-BUNDLE-001",
                format!("documents is a {}, not an array", other.type_name()),
            );
            Vec::new()
        }
        None => {
            rep.push("AWR-BUNDLE-001", "documents missing");
            Vec::new()
        }
    }
}

/// §9: duplicate `id` values with differing content are an error. Identical
/// bytes under one id are harmless duplication.
pub fn check_duplicate_ids(docs: &[AvailableDoc], rep: &mut Report) {
    for (i, a) in docs.iter().enumerate() {
        for b in docs.iter().skip(i + 1) {
            match (&a.id, &b.id) {
                (Some(x), Some(y)) if x == y && a.digest != b.digest => rep.push(
                    "AWR-BUNDLE-002",
                    format!("two documents share id {} but have different canonical forms", x),
                ),
                _ => {}
            }
        }
    }
}

/// §9: identify the document under evaluation.
///
/// Order of resolution, as the section requires — an explicit caller argument,
/// otherwise "the single `WorkReceipt` not referenced as anyone's parent".
/// Ambiguity is `AWR-BUNDLE-003`, never a guess.
pub fn pick_subject(docs: &[AvailableDoc], explicit_id: Option<&str>, rep: &mut Report) -> Option<usize> {
    if let Some(id) = explicit_id {
        match docs.iter().position(|d| d.id.as_deref() == Some(id)) {
            Some(i) => return Some(i),
            None => {
                rep.push(
                    "AWR-BUNDLE-003",
                    format!("no document in the bundle has id {}", id),
                );
                return None;
            }
        }
    }
    if docs.len() == 1 {
        return Some(0);
    }
    let referenced: Vec<[u8; 32]> = docs
        .iter()
        .filter_map(|d| d.subject())
        .filter_map(|s| s.get("parents").cloned())
        .filter_map(|p| p.as_array().cloned())
        .flatten()
        .filter_map(|entry| entry.get("digestSRI").and_then(|s| crate::sri::parse_sri(s).ok()))
        .collect();
    let candidates: Vec<usize> = docs
        .iter()
        .enumerate()
        .filter(|(_, d)| d.is_receipt() && !referenced.contains(&d.digest))
        .map(|(i, _)| i)
        .collect();
    match candidates.len() {
        1 => Some(candidates[0]),
        0 => {
            rep.push(
                "AWR-BUNDLE-003",
                "no WorkReceipt in the bundle is unreferenced as a parent, so the subject cannot be identified; pass --subject <id>",
            );
            None
        }
        n => {
            rep.push(
                "AWR-BUNDLE-003",
                format!(
                    "{} WorkReceipts in the bundle are unreferenced as a parent, so the subject is ambiguous; pass --subject <id>",
                    n
                ),
            );
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::parse;
    use crate::sri::{sha256, sri_of_bytes, sri_of_digest};

    fn avail(id: &str, ty: &str, parents: &[&str]) -> AvailableDoc {
        let plist: Vec<String> = parents
            .iter()
            .map(|sri| format!(r#"{{"digestSRI":"{}"}}"#, sri))
            .collect();
        let src = format!(
            r#"{{"id":"{}","type":["VerifiableCredential","{}"],"credentialSubject":{{"parents":[{}]}}}}"#,
            id,
            ty,
            plist.join(",")
        );
        let value = parse(src.as_bytes()).unwrap();
        let canonical = crate::json::canonicalize(&value).unwrap();
        AvailableDoc {
            digest: sha256(canonical.as_bytes()),
            canonical,
            id: Some(id.to_string()),
            doc_type: Some(ty.to_string()),
            issuer_id: None,
            valid: true,
            source: id.to_string(),
            value,
        }
    }

    #[test]
    fn container_validation() {
        let mut rep = Report::default();
        let v = parse(br#"{"awrBundle":"2.0","documents":[{"id":"urn:uuid:1"}]}"#).unwrap();
        assert_eq!(documents(&v, &mut rep).len(), 1);
        assert!(rep.valid());

        // §9: an unsupported container version stops the walk, so `documents` is never
        // looked at — one AWR-BUNDLE-001, not two. Nothing inside is processed even
        // though the array here happens to be well-formed-and-empty.
        let mut rep = Report::default();
        let v = parse(br#"{"awrBundle":"1.0","documents":[]}"#).unwrap();
        assert!(documents(&v, &mut rep).is_empty());
        assert_eq!(rep.reasons.iter().filter(|r| r.code == "AWR-BUNDLE-001").count(), 1);

        // A supported version does look at `documents`, so an empty array is reported.
        let mut rep = Report::default();
        let v = parse(br#"{"awrBundle":"2.0","documents":[]}"#).unwrap();
        assert!(documents(&v, &mut rep).is_empty());
        assert_eq!(rep.reasons.iter().filter(|r| r.code == "AWR-BUNDLE-001").count(), 1);

        // And an unsupported version reports nothing about the documents it did not read.
        let mut rep = Report::default();
        let v = parse(br#"{"awrBundle":"3.0","documents":[{"id":"urn:uuid:1"}]}"#).unwrap();
        assert!(documents(&v, &mut rep).is_empty());
        assert_eq!(rep.reasons.len(), 1);
    }

    #[test]
    fn duplicate_ids_with_differing_content() {
        let a = avail("urn:uuid:same", "WorkReceipt", &[]);
        let b = avail("urn:uuid:same", "WorkReceipt", &[&sri_of_bytes(b"x")]);
        let mut rep = Report::default();
        check_duplicate_ids(&[a.clone(), b], &mut rep);
        assert!(rep.has_code("AWR-BUNDLE-002"));
        // identical content under one id is not an error
        let mut rep = Report::default();
        check_duplicate_ids(&[a.clone(), a], &mut rep);
        assert!(rep.valid());
    }

    #[test]
    fn subject_selection() {
        let parent = avail("urn:uuid:parent", "WorkReceipt", &[]);
        let child = avail("urn:uuid:child", "WorkReceipt", &[&sri_of_digest(&parent.digest)]);
        let verdict = avail("urn:uuid:verdict", "VerificationVerdict", &[]);
        let docs = vec![parent.clone(), child.clone(), verdict];
        let mut rep = Report::default();
        assert_eq!(pick_subject(&docs, None, &mut rep), Some(1));
        assert!(rep.valid());

        // Explicit argument wins.
        let mut rep = Report::default();
        assert_eq!(pick_subject(&docs, Some("urn:uuid:parent"), &mut rep), Some(0));

        // Two unreferenced receipts are ambiguous, not guessed.
        let other = avail("urn:uuid:other", "WorkReceipt", &[]);
        let mut rep = Report::default();
        assert_eq!(pick_subject(&[parent, child, other], None, &mut rep), None);
        assert!(rep.has_code("AWR-BUNDLE-003"));

        // No receipt at all.
        let mut rep = Report::default();
        let only_verdicts = vec![
            avail("urn:uuid:v1", "VerificationVerdict", &[]),
            avail("urn:uuid:v2", "VerificationVerdict", &[]),
        ];
        assert_eq!(pick_subject(&only_verdicts, None, &mut rep), None);
        assert!(rep.has_code("AWR-BUNDLE-003"));

        // A single document is the subject whatever its type.
        let mut rep = Report::default();
        assert_eq!(pick_subject(&only_verdicts[..1], None, &mut rep), Some(0));
    }
}
