//! Work chains (SPEC §8): edge parsing, bounded resolution, cycle detection and
//! blame reachability.
//!
//! Nothing here touches the network: §8.2 and §13.5 forbid fetching a parent, so
//! resolution runs strictly over documents the caller supplied.

use crate::json::Value;
use crate::report::{ChainStats, Report};
use crate::sri::{parse_digest_ref, sri_of_digest, DigestRef};

/// §8.2 default limits. Both are configurable, as the section requires.
pub const DEFAULT_MAX_DEPTH: usize = 64;
pub const DEFAULT_MAX_NODES: usize = 1024;

#[derive(Debug, Clone, Copy)]
pub struct ChainLimits {
    pub max_depth: usize,
    pub max_nodes: usize,
}

impl Default for ChainLimits {
    fn default() -> Self {
        ChainLimits { max_depth: DEFAULT_MAX_DEPTH, max_nodes: DEFAULT_MAX_NODES }
    }
}

/// A document the caller made available for chain resolution, bundle processing
/// and profile evaluation, with everything precomputed that those need.
#[derive(Debug, Clone)]
pub struct AvailableDoc {
    pub value: Value,
    /// RFC 8785 canonical form of the **secured** document (§8.1).
    pub canonical: String,
    pub digest: [u8; 32],
    pub id: Option<String>,
    pub doc_type: Option<String>,
    pub issuer_id: Option<String>,
    /// Whether this document verified on its own (§9: every claim in a bundle is
    /// verified individually).
    pub valid: bool,
    /// Where it came from, for `detail` strings only.
    pub source: String,
}

impl AvailableDoc {
    pub fn subject(&self) -> Option<&Value> {
        self.value.get("credentialSubject")
    }
    pub fn is_receipt(&self) -> bool {
        self.doc_type.as_deref() == Some("WorkReceipt")
    }
}

/// Parse and structurally validate `credentialSubject.parents` (§3.3, §8.1).
///
/// Reports `AWR-CHAIN-001` (no `digestSRI`), `AWR-CHAIN-002` (malformed
/// reference or unknown algorithm) and `AWR-CHAIN-006` (same `id`, conflicting
/// digests — a direct statement that one of the two is forged).
pub fn parse_parents(subject: &Value, rep: &mut Report) -> Vec<DigestRef> {
    let mut out = Vec::new();
    let items = match subject.get("parents") {
        None => return out,
        Some(Value::Array(items)) => items,
        Some(other) => {
            rep.push(
                "AWR-CHAIN-002",
                format!("parents is a {}, not an array of digest references", other.type_name()),
            );
            return out;
        }
    };
    for (n, item) in items.iter().enumerate() {
        match parse_digest_ref(item, &format!("parents[{}]", n)) {
            Ok(r) => {
                if let Some(id) = &r.id {
                    if let Some(prev) = out
                        .iter()
                        .find(|p: &&DigestRef| p.id.as_deref() == Some(id.as_str()) && p.digest != r.digest)
                    {
                        rep.push(
                            "AWR-CHAIN-006",
                            format!(
                                "parents lists {} twice with conflicting digests {} and {}",
                                id, prev.sri, r.sri
                            ),
                        );
                    }
                }
                out.push(r);
            }
            Err(e) => rep.push(e.code, e.detail),
        }
    }
    out
}

/// One resolved or unresolved edge, for the §8.2 report of which edges the
/// verifier resolved.
#[derive(Debug, Clone)]
pub struct EdgeReport {
    pub parent_id: Option<String>,
    pub digest_sri: String,
    pub role: Option<String>,
    pub resolved: bool,
    pub child_id: Option<String>,
}

impl EdgeReport {
    fn to_value(&self) -> Value {
        let mut m = vec![
            ("child".to_string(), match &self.child_id {
                Some(i) => Value::string(i.clone()),
                None => Value::Null,
            }),
            ("parent".to_string(), match &self.parent_id {
                Some(i) => Value::string(i.clone()),
                None => Value::Null,
            }),
            ("digestSRI".to_string(), Value::string(self.digest_sri.clone())),
            ("resolved".to_string(), Value::Bool(self.resolved)),
        ];
        if let Some(r) = &self.role {
            m.push(("role".to_string(), Value::string(r.clone())));
        }
        Value::object(m)
    }
}

pub struct ChainResult {
    pub stats: ChainStats,
    pub edges: Vec<EdgeReport>,
    /// Digests of every receipt reached from the subject, subject included.
    pub reached: Vec<[u8; 32]>,
    /// True when every edge encountered was resolved, i.e. the walk saw the
    /// whole chain.
    pub complete: bool,
}

impl ChainResult {
    pub fn edges_value(&self) -> Value {
        Value::Array(self.edges.iter().map(|e| e.to_value()).collect())
    }
}

/// §8.2: cycle detection keys on document `id`, not on the digest. A cycle in the
/// digests is not constructible — an edge commits to the parent's exact bytes
/// (§8.1), so a digest cycle would be a SHA-256 fixed point — so every cycle that
/// exists runs through identifiers, which is the field an attacker controls and
/// the field AWR/1 left unsigned (§13.1).
fn node_key(doc: &AvailableDoc) -> String {
    match &doc.id {
        Some(id) if !id.is_empty() => format!("id:{}", id),
        _ => format!("sri:{}", sri_of_digest(&doc.digest)),
    }
}

/// Every `(parent id, digest)` pair the resolution observed, with the children
/// that claimed it — §8.2's `AWR-CHAIN-006` is over all edges, not one array.
#[derive(Default)]
struct IdClaims {
    entries: Vec<(String, Vec<String>, Vec<String>)>, // parent id, digests, child ids
}

impl IdClaims {
    fn note(&mut self, parent_id: &str, sri: &str, child_id: Option<&str>) {
        let child = child_id.unwrap_or("").to_string();
        if let Some(e) = self.entries.iter_mut().find(|e| e.0 == parent_id) {
            if !e.1.iter().any(|d| d == sri) {
                e.1.push(sri.to_string());
            }
            if !e.2.contains(&child) {
                e.2.push(child);
            }
            return;
        }
        self.entries.push((parent_id.to_string(), vec![sri.to_string()], vec![child]));
    }
}

/// Resolve the chain rooted at `root` over the supplied documents (§8.2).
pub fn resolve(
    root: &AvailableDoc,
    available: &[AvailableDoc],
    limits: ChainLimits,
    rep: &mut Report,
) -> ChainResult {
    let mut res = ChainResult {
        stats: ChainStats::default(),
        edges: Vec::new(),
        reached: vec![root.digest],
        complete: true,
    };
    let mut visited: Vec<String> = vec![node_key(root)];
    let mut path: Vec<String> = Vec::new();
    let mut limit_reported = false;
    let mut claims = IdClaims::default();
    walk(
        root, available, limits, 0, &mut path, &mut visited, &mut res, rep, &mut limit_reported,
        &mut claims,
    );
    // §8.2: the same parent id claimed with conflicting digests across two
    // different children. A conflict inside one `parents` array is already
    // reported by `parse_parents`, so only the cross-receipt case is added here
    // and the code is never reported twice for the same pair.
    for (parent_id, digests, children) in &claims.entries {
        if digests.len() > 1 && children.len() > 1 {
            rep.push(
                "AWR-CHAIN-006",
                format!(
                    "parent id {} is referenced with {} conflicting digests ({}) by {} different receipts; one of them is forged (§8.2)",
                    parent_id,
                    digests.len(),
                    digests.join(", "),
                    children.len()
                ),
            );
        }
    }
    res.stats.resolved = res.edges.iter().filter(|e| e.resolved).count();
    res.stats.unresolved = res.edges.iter().filter(|e| !e.resolved).count();
    res
}

#[allow(clippy::too_many_arguments)]
fn walk(
    node: &AvailableDoc,
    available: &[AvailableDoc],
    limits: ChainLimits,
    depth: usize,
    path: &mut Vec<String>,
    visited: &mut Vec<String>,
    res: &mut ChainResult,
    rep: &mut Report,
    limit_reported: &mut bool,
    claims: &mut IdClaims,
) {
    let subject = match node.subject() {
        Some(s) => s,
        None => return,
    };
    // Each node is walked at most once (see the `visited` check below), so a
    // structural problem in one node's `parents` is reported exactly once.
    let parents = parse_parents(subject, rep);
    if parents.is_empty() {
        return;
    }
    if depth + 1 > limits.max_depth {
        if !*limit_reported {
            rep.push(
                "AWR-CHAIN-005",
                format!(
                    "chain resolution stopped: depth {} would exceed the configured maximum of {} (§8.2)",
                    depth + 1, limits.max_depth
                ),
            );
            *limit_reported = true;
        }
        res.complete = false;
        return;
    }
    path.push(node_key(node));
    for edge in parents {
        if let Some(id) = &edge.id {
            claims.note(id, &edge.sri, node.id.as_deref());
        }
        let by_digest = available.iter().find(|d| d.digest == edge.digest);
        let report = EdgeReport {
            parent_id: edge.id.clone(),
            digest_sri: edge.sri.clone(),
            role: edge.role.clone(),
            resolved: by_digest.is_some(),
            child_id: node.id.clone(),
        };
        // §8.2 "Locating a parent": by digest first. When no supplied document
        // has the committed digest but one carries the edge's `id`, report
        // AWR-CHAIN-003, count the edge unresolved — nothing the child signed has
        // been confirmed — and still traverse that document, so that a cycle or a
        // digest conflict hidden behind a broken edge is found. Without the
        // traversal AWR-CHAIN-004 is unreachable, because every constructible
        // cycle runs through an edge whose digest does not match.
        let resolved_edge = by_digest.is_some();
        let parent = match by_digest {
            Some(p) => Some(p),
            None => {
                res.complete = false;
                match &edge.id {
                    Some(id) => match available.iter().find(|d| d.id.as_deref() == Some(id.as_str())) {
                        Some(same_id) => {
                            rep.push(
                                "AWR-CHAIN-003",
                                format!(
                                    "parent {} was supplied but its canonical digest is {}, while the edge commits to {}",
                                    id,
                                    sri_of_digest(&same_id.digest),
                                    edge.sri
                                ),
                            );
                            Some(same_id)
                        }
                        None => None,
                    },
                    None => None,
                }
            }
        };
        match parent {
            None => {
                res.edges.push(report);
            }
            Some(parent) => {
                res.edges.push(report);
                // §8.3: a differing input/output pair is a warning, not invalidity.
                let child_input = subject.get("inputDigest").and_then(|v| v.as_str());
                let parent_output = parent
                    .subject()
                    .and_then(|s| s.get("outputDigest"))
                    .and_then(|v| v.as_str());
                if let (Some(ci), Some(po)) = (child_input, parent_output) {
                    if ci != po && resolved_edge {
                        rep.push(
                            "AWR-CHAIN-007",
                            format!(
                                "parent {} outputDigest {} differs from child {} inputDigest {}; a legitimate hop often transforms its input (§8.3)",
                                parent.id.clone().unwrap_or_else(|| "<no id>".into()),
                                po,
                                node.id.clone().unwrap_or_else(|| "<no id>".into()),
                                ci
                            ),
                        );
                    }
                }
                let parent_key = node_key(parent);
                if path.contains(&parent_key) {
                    rep.push(
                        "AWR-CHAIN-004",
                        format!(
                            "cycle: {} is its own ancestor through parents edges (§8.2)",
                            parent.id.clone().unwrap_or_else(|| sri_of_digest(&parent.digest))
                        ),
                    );
                    continue;
                }
                if visited.contains(&parent_key) {
                    // A DAG may reach the same parent by two routes; count the
                    // edge but do not walk the subtree twice.
                    continue;
                }
                if visited.len() + 1 > limits.max_nodes {
                    if !*limit_reported {
                        rep.push(
                            "AWR-CHAIN-005",
                            format!(
                                "chain resolution stopped: node count would exceed the configured maximum of {} (§8.2)",
                                limits.max_nodes
                            ),
                        );
                        *limit_reported = true;
                    }
                    res.complete = false;
                    continue;
                }
                visited.push(parent_key);
                res.reached.push(parent.digest);
                walk(
                    parent,
                    available,
                    limits,
                    depth + 1,
                    path,
                    visited,
                    res,
                    rep,
                    limit_reported,
                    claims,
                );
            }
        }
    }
    path.pop();
}

/// §3.5 / `AWR-BLAME-001`: is `blamed` reachable from `chain_ref` through
/// `parents` edges over the receipts the caller supplied?
///
/// Returns `None` when the question cannot be answered from the available
/// documents — the terminal receipt is missing, or the walk hit an unresolved
/// edge. Only a definite `Some(false)` justifies `AWR-BLAME-001`, because §3.5
/// conditions the error on the verifier *having* the intermediate receipts.
pub fn blame_reachable(
    chain_digest: &[u8; 32],
    blamed_digest: &[u8; 32],
    available: &[AvailableDoc],
    limits: ChainLimits,
) -> Option<bool> {
    if chain_digest == blamed_digest {
        return Some(true); // §3.5: blamedWork MAY equal chain
    }
    let root = available.iter().find(|d| &d.digest == chain_digest)?;
    let mut sink = Report::default();
    let res = resolve(root, available, limits, &mut sink);
    if res.reached.iter().any(|d| d == blamed_digest) {
        return Some(true);
    }
    if res.complete {
        Some(false)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::parse;
    use crate::sri::{sha256, sri_of_bytes};

    fn doc(id: &str, parents: &[(&str, &str)], input: &str, output: &str) -> AvailableDoc {
        let plist: Vec<String> = parents
            .iter()
            .map(|(pid, sri)| format!(r#"{{"id":"{}","digestSRI":"{}"}}"#, pid, sri))
            .collect();
        let src = format!(
            r#"{{"id":"{}","type":["VerifiableCredential","WorkReceipt"],
                  "credentialSubject":{{"inputDigest":"{}","outputDigest":"{}","parents":[{}]}}}}"#,
            id,
            input,
            output,
            plist.join(",")
        );
        let value = parse(src.as_bytes()).unwrap();
        let canonical = crate::json::canonicalize(&value).unwrap();
        AvailableDoc {
            digest: sha256(canonical.as_bytes()),
            canonical,
            id: Some(id.to_string()),
            doc_type: Some("WorkReceipt".to_string()),
            issuer_id: None,
            valid: true,
            source: id.to_string(),
            value,
        }
    }

    fn sri(d: &AvailableDoc) -> String {
        sri_of_digest(&d.digest)
    }

    #[test]
    fn resolved_and_unresolved_edges_are_reported() {
        let a = doc("urn:uuid:a", &[], &sri_of_bytes(b"in-a"), &sri_of_bytes(b"out-a"));
        let b = doc(
            "urn:uuid:b",
            &[("urn:uuid:a", &sri(&a)), ("urn:uuid:missing", &sri_of_bytes(b"nope"))],
            &sri_of_bytes(b"out-a"),
            &sri_of_bytes(b"out-b"),
        );
        let mut rep = Report::default();
        let res = resolve(&b, &[a.clone()], ChainLimits::default(), &mut rep);
        assert_eq!(res.stats.resolved, 1);
        assert_eq!(res.stats.unresolved, 1);
        assert!(!res.complete);
        // outputDigest(a) == inputDigest(b), so no CHAIN-007
        assert!(!rep.has_code("AWR-CHAIN-007"), "{:?}", rep.warnings);
        assert!(rep.valid(), "an unresolved edge is not an error: {:?}", rep.reasons);
    }

    #[test]
    fn input_output_mismatch_is_a_warning_only() {
        let a = doc("urn:uuid:a", &[], &sri_of_bytes(b"in-a"), &sri_of_bytes(b"out-a"));
        let b = doc(
            "urn:uuid:b",
            &[("urn:uuid:a", &sri(&a))],
            &sri_of_bytes(b"something-else"),
            &sri_of_bytes(b"out-b"),
        );
        let mut rep = Report::default();
        resolve(&b, &[a], ChainLimits::default(), &mut rep);
        assert!(rep.has_code("AWR-CHAIN-007"));
        assert!(rep.valid());
    }

    #[test]
    fn digest_mismatch_against_supplied_parent() {
        let a = doc("urn:uuid:a", &[], &sri_of_bytes(b"in-a"), &sri_of_bytes(b"out-a"));
        // b commits to a *different* digest for the same parent id
        let b = doc(
            "urn:uuid:b",
            &[("urn:uuid:a", &sri_of_bytes(b"forged"))],
            &sri_of_bytes(b"out-a"),
            &sri_of_bytes(b"out-b"),
        );
        let mut rep = Report::default();
        let res = resolve(&b, &[a], ChainLimits::default(), &mut rep);
        assert!(rep.has_code("AWR-CHAIN-003"));
        assert_eq!(res.stats.unresolved, 1);
    }

    #[test]
    fn conflicting_parent_ids_are_chain_006() {
        let mut rep = Report::default();
        let subject = parse(
            format!(
                r#"{{"parents":[{{"id":"urn:uuid:a","digestSRI":"{}"}},{{"id":"urn:uuid:a","digestSRI":"{}"}}]}}"#,
                sri_of_bytes(b"one"),
                sri_of_bytes(b"two")
            )
            .as_bytes(),
        )
        .unwrap();
        parse_parents(&subject, &mut rep);
        assert!(rep.has_code("AWR-CHAIN-006"));
    }

    #[test]
    fn missing_digest_sri_is_chain_001() {
        let mut rep = Report::default();
        let subject = parse(br#"{"parents":[{"id":"urn:uuid:a"}]}"#).unwrap();
        parse_parents(&subject, &mut rep);
        assert!(rep.has_code("AWR-CHAIN-001"));
    }

    #[test]
    fn cycle_is_detected() {
        // Content-addressed edges make an honest cycle impossible to construct:
        // a document would have to contain its own digest. The resolution code
        // path is still reachable when a caller supplies a document whose stored
        // digest matches one of its own edges (a forged or mislabelled parent),
        // so that is what is built here: digest D, and a parents edge to D.
        let d = sha256(b"self-referential");
        let mut node = doc(
            "urn:uuid:loop",
            &[("urn:uuid:loop", &sri_of_digest(&d))],
            &sri_of_bytes(b"in"),
            &sri_of_bytes(b"out"),
        );
        node.digest = d;
        let mut rep = Report::default();
        let res = resolve(&node, &[node.clone()], ChainLimits::default(), &mut rep);
        assert!(rep.has_code("AWR-CHAIN-004"), "{:?}", rep.reasons);
        assert_eq!(res.stats.resolved, 1);
    }

    #[test]
    fn depth_limit_is_enforced() {
        // Build a linear chain of 5 receipts and resolve with max_depth 2.
        let mut docs: Vec<AvailableDoc> = Vec::new();
        let mut prev: Option<AvailableDoc> = None;
        for n in 0..5 {
            let d = match &prev {
                None => doc(&format!("urn:uuid:{}", n), &[], &sri_of_bytes(b"in"), &sri_of_bytes(b"out")),
                Some(p) => doc(
                    &format!("urn:uuid:{}", n),
                    &[(p.id.as_deref().unwrap(), &sri(p))],
                    &sri_of_bytes(b"out"),
                    &sri_of_bytes(b"out"),
                ),
            };
            docs.push(d.clone());
            prev = Some(d);
        }
        let leaf = docs.last().unwrap().clone();
        let mut rep = Report::default();
        let res = resolve(&leaf, &docs, ChainLimits { max_depth: 2, max_nodes: 1024 }, &mut rep);
        assert!(rep.has_code("AWR-CHAIN-005"), "{:?}", rep.reasons);
        assert_eq!(res.stats.resolved, 2);

        // The same chain resolves fully under the defaults.
        let mut rep2 = Report::default();
        let res2 = resolve(&leaf, &docs, ChainLimits::default(), &mut rep2);
        assert!(!rep2.has_code("AWR-CHAIN-005"));
        assert_eq!(res2.stats.resolved, 4);
        assert!(res2.complete);
    }

    #[test]
    fn node_limit_is_enforced() {
        let a = doc("urn:uuid:a", &[], &sri_of_bytes(b"in"), &sri_of_bytes(b"out"));
        let b = doc("urn:uuid:b", &[], &sri_of_bytes(b"in"), &sri_of_bytes(b"out2"));
        let c = doc(
            "urn:uuid:c",
            &[("urn:uuid:a", &sri(&a)), ("urn:uuid:b", &sri(&b))],
            &sri_of_bytes(b"out"),
            &sri_of_bytes(b"out3"),
        );
        let mut rep = Report::default();
        resolve(&c, &[a, b], ChainLimits { max_depth: 64, max_nodes: 2 }, &mut rep);
        assert!(rep.has_code("AWR-CHAIN-005"), "{:?}", rep.reasons);
    }

    #[test]
    fn blame_reachability() {
        let a = doc("urn:uuid:a", &[], &sri_of_bytes(b"in"), &sri_of_bytes(b"out-a"));
        let b = doc(
            "urn:uuid:b",
            &[("urn:uuid:a", &sri(&a))],
            &sri_of_bytes(b"out-a"),
            &sri_of_bytes(b"out-b"),
        );
        let orphan = doc("urn:uuid:z", &[], &sri_of_bytes(b"in"), &sri_of_bytes(b"out-z"));
        let all = vec![a.clone(), b.clone(), orphan.clone()];
        let lim = ChainLimits::default();
        assert_eq!(blame_reachable(&b.digest, &a.digest, &all, lim), Some(true));
        assert_eq!(blame_reachable(&b.digest, &b.digest, &all, lim), Some(true));
        assert_eq!(blame_reachable(&b.digest, &orphan.digest, &all, lim), Some(false));
        // Unknown terminal receipt: undecidable, not an error.
        assert_eq!(blame_reachable(&sha256(b"nothing"), &a.digest, &all, lim), None);
        // Incomplete chain: undecidable.
        let c = doc(
            "urn:uuid:c",
            &[("urn:uuid:missing", &sri_of_bytes(b"gone"))],
            &sri_of_bytes(b"in"),
            &sri_of_bytes(b"out-c"),
        );
        assert_eq!(blame_reachable(&c.digest, &a.digest, &[c.clone()], lim), None);
    }
}
