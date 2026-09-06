//! Verification orchestration (SPEC §6.3) and profile evaluation (§10).

use crate::bundle;
use crate::chain::{self, AvailableDoc, ChainLimits};
use crate::document::{
    check_blame, check_envelope, check_issuer_key, check_proof_object, check_receipt, check_verdict,
    Envelope,
};
use crate::json::{canonicalize, parse, scan_numbers, Value};
use crate::legacy;
use crate::proof::compute_hash_data;
use crate::report::{ChainStats, Report};
use crate::sri::{parse_sri, sha256, sri_of_digest};
use crate::timefmt::{now_secs, Timestamp};
use crate::DOC_TYPES;

/// Caller policy. Nothing here reaches the network (§13.5).
#[derive(Debug, Clone)]
pub struct Options {
    /// Profile the caller asks to be checked (§10). `None` means "report the
    /// highest satisfied" without demanding one.
    pub profile: Option<String>,
    /// `--now`, so that the time warnings of §11.2 are testable deterministically.
    pub now: Option<Timestamp>,
    /// Skew allowance for `AWR-TIME-001` (§11.2). Freshness is policy, never
    /// validity (§11.3).
    pub skew_secs: i64,
    pub limits: ChainLimits,
    /// Explicit subject selection inside a bundle (§9).
    pub subject_id: Option<String>,
    /// §12.3/§12.4: `--expected-key` and `--no-legacy`.
    pub legacy: legacy::LegacyOptions,
}

impl Default for Options {
    fn default() -> Self {
        Options {
            profile: None,
            now: None,
            // IMPLEMENTATION CHOICE (§11.2 AWR-TIME-001 says "beyond the
            // caller's skew allowance" and names no default): 300 s, the usual
            // clock-skew tolerance, overridable with --skew.
            skew_secs: 300,
            limits: ChainLimits::default(),
            subject_id: None,
            legacy: legacy::LegacyOptions::default(),
        }
    }
}

pub struct Input {
    pub bytes: Vec<u8>,
    pub source: String,
}

/// The AWR document type declared in `type`, when exactly one is present.
pub fn awr_type(doc: &Value) -> Option<String> {
    let items = doc.get("type")?.as_array()?;
    let found: Vec<&str> = DOC_TYPES
        .iter()
        .copied()
        .filter(|t| items.iter().any(|v| v.as_str() == Some(*t)))
        .collect();
    if found.len() == 1 {
        Some(found[0].to_string())
    } else {
        None
    }
}

fn prepare(value: Value, source: &str) -> Result<AvailableDoc, Vec<crate::json::JsonError>> {
    let errs = scan_numbers(&value);
    if !errs.is_empty() {
        return Err(errs);
    }
    let canonical = canonicalize(&value).map_err(|e| vec![e])?;
    Ok(AvailableDoc {
        digest: sha256(canonical.as_bytes()),
        canonical,
        id: value.get("id").and_then(|v| v.as_str()).map(String::from),
        doc_type: awr_type(&value),
        issuer_id: value
            .get("issuer")
            .and_then(|i| i.get("id"))
            .and_then(|v| v.as_str())
            .map(String::from),
        valid: false,
        source: source.to_string(),
        value,
    })
}

/// Verify one document on its own: §4.3 numbers, §3 structure, §5 keys, §6
/// proof. Chain, bundle and profile checks are the caller's job because they
/// need the other documents.
///
/// The order follows §6.3, but every check runs: §11.1 requires all
/// determinable errors, and a caller diagnosing an interoperability failure from
/// a single early error is what §11.1 exists to prevent. No subject field is
/// ever reported as a fact — the result carries reason codes only.
pub fn verify_document(doc: &Value, rep: &mut Report) -> Envelope {
    verify_document_opts(doc, rep, &legacy::LegacyOptions::default())
}

/// As [`verify_document`], with the caller's §12 controls.
pub fn verify_document_opts(
    doc: &Value,
    rep: &mut Report,
    lopts: &legacy::LegacyOptions,
) -> Envelope {
    let mut env = Envelope::default();
    if !doc.is_object() {
        rep.push("AWR-DOC-001", format!("top-level value is a {}, not a JSON object", doc.type_name()));
        return env;
    }

    // §4.3 applies to the whole document, and a violation also makes the
    // canonical form — and therefore the signature check — impossible.
    let number_errors = scan_numbers(doc);
    for e in &number_errors {
        rep.push(e.code, e.detail.clone());
    }

    // §4.1(2)/§11.2 AWR-CANON-006: prove on every document that this
    // canonicalizer is idempotent, so a regression that normalized, re-sorted or
    // re-escaped anything would be reported rather than producing bytes only
    // this implementation can sign.
    if number_errors.is_empty() {
        if let Ok(c) = canonicalize(doc) {
            if let Err(e) = crate::json::self_check(&c) {
                rep.push(e.code, e.detail);
            }
        }
    }

    // §12.3: the version gate runs before any verification and before the AWR/2
    // envelope checks. Selecting the rule set on `proof.type` alone was an
    // unauthenticated forgery path — AWR/1 signs neither `proof.type` nor
    // `issuer`, so a document claiming to be AWR/2 was verified under AWR/1 rules
    // against a key the sender supplied beside a victim's DID.
    match legacy::classify(doc) {
        legacy::VersionClass::Disagree => {
            env.doc_type = awr_type(doc);
            env.awr_version = doc.get("awrVersion").and_then(|v| v.as_str()).map(String::from);
            rep.push(
                "AWR-LEGACY-003",
                format!(
                    "version signals disagree: the document carries an AWR/1 Ed25519Signature2018 proof and the AWR/2 signal(s) {}. AWR/1 does not sign proof.type or issuer, so honouring the proof suite here would let the sender choose which rules apply to a document that claims to be AWR/2 (\u{a7}12.3); it is verified under neither, and there is no fallback to the other rule set",
                    legacy::awr2_signals(doc).join(", ")
                ),
            );
            return env;
        }
        legacy::VersionClass::Awr1 => {
            env.doc_type = awr_type(doc);
            if lopts.no_legacy {
                rep.push(
                    "AWR-LEGACY-005",
                    "the document is an AWR/1 legacy document (\u{a7}12) and this verifier was asked not to apply the AWR/1 rules; \u{a7}12 support is OPTIONAL",
                );
                return env;
            }
            // §12.3 guarantees no `awrVersion` here: it is an AWR/2 signal and
            // would have been AWR-LEGACY-003.
            env.awr_version = doc.get("awrVersion").and_then(|v| v.as_str()).map(String::from);
            let outcome = legacy::verify_legacy(doc, rep, lopts);
            // §12.4: an AWR/1 result names a KEY, never an issuer.
            rep.set_extra(
                "legacy",
                Value::object(vec![
                    (
                        "dialect".to_string(),
                        match outcome.dialect {
                            Some(d) => Value::string(d.as_str()),
                            None => Value::Null,
                        },
                    ),
                    (
                        "keySource".to_string(),
                        match outcome.key_source {
                            Some(k) => Value::string(k.as_str()),
                            None => Value::Null,
                        },
                    ),
                    // A constant, and present *because* it is a constant: AWR/1
                    // can never attest an issuer, and a member that is always
                    // false is read while an absent one is not.
                    ("issuerAttested".to_string(), Value::Bool(false)),
                    (
                        "verifiedKey".to_string(),
                        match &outcome.verified_key {
                            Some(k) => Value::string(k.as_str()),
                            None => Value::Null,
                        },
                    ),
                    (
                        "unsignedFields".to_string(),
                        Value::Array(
                            legacy::UNSIGNED_FIELDS.iter().map(|f| Value::string(*f)).collect(),
                        ),
                    ),
                    (
                        "attestedFields".to_string(),
                        Value::Array(vec![Value::string("credentialSubject")]),
                    ),
                ]),
            );
            return env;
        }
        legacy::VersionClass::Awr2 => {}
    }

    env = check_envelope(doc, rep);

    if let Some(subject) = doc.get("credentialSubject") {
        if subject.is_object() {
            match env.doc_type.as_deref() {
                Some("WorkReceipt") => check_receipt(subject, rep),
                Some("VerificationVerdict") => check_verdict(subject, rep),
                Some("BlameAttestation") => check_blame(subject, rep),
                _ => {}
            }
        }
    }

    let public_key = check_issuer_key(doc, env.issuer_id.as_deref(), rep);

    // §6.1: an array of proofs is permitted; at least one must verify, and every
    // proof present must be either valid or reported.
    //
    // IMPLEMENTATION CHOICE: "either valid or reported" cannot mean "reported as
    // an error", because that would contradict "at least one MUST verify" for a
    // document carrying one good and one bad proof. So each proof's outcome is
    // reported in the `proofs` array of the result, `verifiedProof` names the one
    // that verified (§6.1's reporting requirement), and `AWR-PROOF-*` errors are
    // raised only when *no* proof verified.
    let proofs: Vec<Value> = match doc.get("proof") {
        None => {
            rep.push("AWR-PROOF-001", "proof missing");
            Vec::new()
        }
        Some(Value::Array(items)) if items.is_empty() => {
            rep.push("AWR-PROOF-001", "proof is an empty array");
            Vec::new()
        }
        Some(Value::Array(items)) => items.clone(),
        Some(p) => vec![p.clone()],
    };

    let mut statuses: Vec<Value> = Vec::new();
    let mut verified_index: Option<usize> = None;
    let mut failures: Vec<(&'static str, String)> = Vec::new();
    let canonicalizable = number_errors.is_empty();
    // §6.3: whether step 6 — the Ed25519 check itself — actually ran for any
    // proof. AWR-PROOF-006 is only for a signature that was checked and failed.
    let mut checked_any = false;

    for (index, p) in proofs.iter().enumerate() {
        let mut check = check_proof_object(doc, p, index, public_key.as_ref());
        let mut detail_extra: Option<String> = None;
        if check.failures.is_empty() {
            match (&public_key, check.signature) {
                (Some(pk), Some(sig)) if canonicalizable => {
                    match compute_hash_data(doc, p) {
                        Ok(hd) => match {
                            checked_any = true;
                            crate::proof::verify(pk, &hd.hash_data, &sig)
                        } {
                            Ok(()) => {
                                if verified_index.is_none() {
                                    verified_index = Some(index);
                                }
                            }
                            Err(e) => {
                                check.fail("AWR-PROOF-006", e);
                            }
                        },
                        Err(e) => {
                            check.fail(e.code, e.detail.clone());
                        }
                    }
                }
                _ => {
                    // The signature could not be checked at all: the key, the
                    // proofValue or the canonical form was unavailable. The
                    // reasons for that are already reported.
                    detail_extra = Some("signature not checked".to_string());
                }
            }
        }
        let ok = check.failures.is_empty() && verified_index == Some(index);
        statuses.push(Value::object(vec![
            ("index".to_string(), Value::int(index as i64)),
            (
                "verificationMethod".to_string(),
                match &check.verification_method {
                    Some(v) => Value::string(v.clone()),
                    None => Value::Null,
                },
            ),
            ("verified".to_string(), Value::Bool(ok)),
            (
                "codes".to_string(),
                Value::Array(
                    check
                        .failures
                        .iter()
                        .map(|(c, _)| Value::string(*c))
                        .chain(detail_extra.iter().map(|d| Value::string(d.clone())))
                        .collect(),
                ),
            ),
        ]));
        failures.extend(check.failures.into_iter());
    }

    if !proofs.is_empty() {
        if let Some(i) = verified_index {
            // §6.1: report which proof verified.
            rep.set_extra("verifiedProof", Value::int(i as i64));
            if proofs.len() > 1 {
                rep.set_extra("proofs", Value::Array(statuses));
            }
        } else {
            for (code, detail) in failures {
                rep.push(code, detail);
            }
            if proofs.len() > 1 {
                rep.set_extra("proofs", Value::Array(statuses));
            }
            // §6.3: AWR-PROOF-006 means the signature WAS checked and did not
            // verify. When an earlier step made the check impossible — no
            // canonical form (AWR-CANON-*), no derivable key (AWR-KEY-* /
            // AWR-DOC-010), a proof configuration that is not AWR/2's
            // (AWR-PROOF-002…005, 007…009) — that step's code is the report and
            // PROOF-006 must NOT be added on top. This implementation used to add
            // it, and the reference did not, which made the two outputs
            // incomparable on six documents.
            if checked_any && !rep.reasons.iter().any(|r| r.code.starts_with("AWR-PROOF-")) {
                // Every structural check passed and yet nothing verified: the
                // only remaining explanation is the signature itself.
                rep.push("AWR-PROOF-006", "no proof verified");
            } else if !checked_any && rep.reasons.is_empty() {
                // Fail closed: the check did not run and nothing said why, which
                // would otherwise be reported as a valid document (§6.3).
                rep.push(
                    "AWR-PROOF-006",
                    "the signature was not checked and no reason was recorded; refusing to report this document as valid",
                );
            }
        }
    }

    env
}

/// Full verification of an input, with auxiliary documents for chain resolution
/// and profile evaluation (§8, §9, §10).
pub fn verify(main: &Input, aux: &[Input], opts: &Options) -> Report {
    let mut rep = Report::default();
    // §11.1: `awrVersion` reports the DOCUMENT's `awrVersion`, not the version this
    // build implements, and is null when the document carries none.  Seeding it with
    // AWR_VERSION here made this build answer "2.0.0" for an AWR/1 document and for
    // bytes that are not JSON at all — the one question the member exists to answer.
    // It is filled in below, from the document, once a document has been parsed.

    // ----- parse and flatten the inputs -------------------------------------
    let main_value = match parse(&main.bytes) {
        Ok(v) => v,
        Err(e) => {
            rep.push(e.code, format!("{}: {}", main.source, e.detail));
            return rep;
        }
    };
    if !main_value.is_object() {
        rep.push(
            "AWR-DOC-001",
            format!("{} is a {}, not a JSON object", main.source, main_value.type_name()),
        );
        return rep;
    }

    let mut subject_candidates: Vec<Value> = Vec::new();
    let mut aux_values: Vec<(Value, String)> = Vec::new();
    let main_is_bundle = bundle::looks_like_bundle(&main_value);
    if main_is_bundle {
        subject_candidates.extend(bundle::documents(&main_value, &mut rep));
        if subject_candidates.is_empty() {
            return rep;
        }
    } else {
        subject_candidates.push(main_value.clone());
    }

    for input in aux {
        match parse(&input.bytes) {
            Ok(v) if bundle::looks_like_bundle(&v) => {
                for d in bundle::documents(&v, &mut rep) {
                    aux_values.push((d, input.source.clone()));
                }
            }
            Ok(v) => aux_values.push((v, input.source.clone())),
            Err(e) => {
                rep.push(e.code, format!("{}: {}", input.source, e.detail));
            }
        }
    }

    // ----- prepare every document ------------------------------------------
    let mut prepared: Vec<AvailableDoc> = Vec::new();
    let mut subject_indices: Vec<usize> = Vec::new();
    for (n, v) in subject_candidates.into_iter().enumerate() {
        let source = if main_is_bundle {
            format!("{}#documents[{}]", main.source, n)
        } else {
            main.source.clone()
        };
        match prepare(v.clone(), &source) {
            Ok(d) => {
                subject_indices.push(prepared.len());
                prepared.push(d);
            }
            Err(errs) => {
                // A document with no canonical form (§4.3) cannot take part in
                // chain resolution or profile evaluation, and its signature
                // cannot be checked at all.
                if main_is_bundle {
                    for e in errs {
                        rep.push(e.code, format!("{}: {}", source, e.detail));
                    }
                } else {
                    // Single-document input: report everything else that is
                    // still determinable (§11.1) and stop.
                    let mut sub = Report::default();
                    let env = verify_document_opts(&v, &mut sub, &opts.legacy);
                    merge(&mut rep, sub);
                    rep.document_type = env.doc_type.clone();
                    if let Some(av) = v.get("awrVersion").and_then(|x| x.as_str()) {
                        rep.awr_version = Some(av.to_string());
                    }
                    return rep;
                }
            }
        }
    }
    for (v, source) in aux_values {
        match prepare(v, &source) {
            Ok(d) => prepared.push(d),
            Err(errs) => {
                for e in errs {
                    rep.push(e.code, format!("{}: {}", source, e.detail));
                }
            }
        }
    }

    // ----- verify each document individually (§9) ---------------------------
    let mut per_doc: Vec<Report> = Vec::with_capacity(prepared.len());
    for d in prepared.iter_mut() {
        let mut r = Report::default();
        let env = verify_document_opts(&d.value, &mut r, &opts.legacy);
        d.valid = r.valid();
        if d.doc_type.is_none() {
            d.doc_type = env.doc_type.clone();
        }
        per_doc.push(r);
    }

    // ----- pick the subject (§9) -------------------------------------------
    let subject_pool: Vec<AvailableDoc> =
        subject_indices.iter().map(|i| prepared[*i].clone()).collect();
    let picked = if main_is_bundle {
        bundle::check_duplicate_ids(&prepared, &mut rep);
        match bundle::pick_subject(&subject_pool, opts.subject_id.as_deref(), &mut rep) {
            Some(i) => subject_indices[i],
            None => return rep,
        }
    } else {
        subject_indices[0]
    };

    // The subject's own reasons are the result's reasons.
    merge(&mut rep, per_doc[picked].clone());
    let subject = prepared[picked].clone();
    rep.document_type = subject.doc_type.clone();
    if let Some(v) = subject.value.get("awrVersion").and_then(|v| v.as_str()) {
        rep.awr_version = Some(v.to_string());
    }
    rep.set_extra("documentDigest", Value::string(sri_of_digest(&subject.digest)));

    // IMPLEMENTATION CHOICE (§11.1 describes the result of verifying *one*
    // document — it has a single `documentType` — while §9 requires every
    // document in a bundle to be verified individually): the subject's reasons
    // are the result's `reasons`, and every other supplied document is reported
    // under `documents` with its own validity and codes. Container-level bundle
    // errors (`AWR-BUNDLE-*`) do go into `reasons`, since they are properties of
    // the input the caller handed over.
    let others: Vec<(usize, &AvailableDoc)> = prepared
        .iter()
        .enumerate()
        .filter(|(i, _)| *i != picked)
        .collect();
    if !others.is_empty() {
        rep.set_extra(
            "documents",
            Value::Array(
                others
                    .iter()
                    .map(|(i, d)| {
                        Value::object(vec![
                            (
                                "id".to_string(),
                                match &d.id {
                                    Some(x) => Value::string(x.clone()),
                                    None => Value::Null,
                                },
                            ),
                            (
                                "documentType".to_string(),
                                match &d.doc_type {
                                    Some(x) => Value::string(x.clone()),
                                    None => Value::Null,
                                },
                            ),
                            ("valid".to_string(), Value::Bool(d.valid)),
                            (
                                "codes".to_string(),
                                Value::Array(
                                    per_doc[*i].codes().iter().map(|c| Value::string(c.clone())).collect(),
                                ),
                            ),
                            ("source".to_string(), Value::string(d.source.clone())),
                        ])
                    })
                    .collect(),
            ),
        );
    }

    let available: Vec<AvailableDoc> = prepared.clone();

    // ----- chain (§8) -------------------------------------------------------
    if subject.is_receipt() {
        let res = chain::resolve(&subject, &available, opts.limits, &mut rep);
        rep.chain = res.stats;
        if !res.edges.is_empty() {
            rep.set_extra("chainEdges", res.edges_value());
        }
    } else {
        rep.chain = ChainStats::default();
    }

    // ----- cross-document checks for verdict and blame subjects -------------
    if subject.doc_type.as_deref() == Some("VerificationVerdict") {
        if let Some(vw) = subject.subject().and_then(|s| s.get("verifiedWork").cloned()) {
            if let Some(digest) = vw.get("digestSRI").and_then(|s| parse_sri(s).ok()) {
                let matching = available.iter().any(|d| d.digest == digest);
                if !matching {
                    if let Some(id) = vw.get("id").and_then(|v| v.as_str()) {
                        if let Some(other) =
                            available.iter().find(|d| d.id.as_deref() == Some(id) && d.is_receipt())
                        {
                            rep.push(
                                "AWR-VDCT-005",
                                format!(
                                    "verifiedWork.digestSRI is {} but the supplied receipt {} canonicalizes to {}",
                                    sri_of_digest(&digest),
                                    id,
                                    sri_of_digest(&other.digest)
                                ),
                            );
                        }
                    }
                }
            }
        }
    }

    if subject.doc_type.as_deref() == Some("BlameAttestation") {
        let s = subject.subject().cloned().unwrap_or(Value::Null);
        let chain_digest = s.get("chain").and_then(|c| c.get("digestSRI")).and_then(|v| parse_sri(v).ok());
        let blamed_digest =
            s.get("blamedWork").and_then(|c| c.get("digestSRI")).and_then(|v| parse_sri(v).ok());
        if let (Some(c), Some(b)) = (chain_digest, blamed_digest) {
            match chain::blame_reachable(&c, &b, &available, opts.limits) {
                Some(true) => rep.set_extra("blameReachable", Value::Bool(true)),
                Some(false) => rep.push(
                    "AWR-BLAME-001",
                    format!(
                        "blamedWork {} is not reachable from chain {} through the parents edges of the supplied receipts",
                        sri_of_digest(&b),
                        sri_of_digest(&c)
                    ),
                ),
                None => rep.set_extra("blameReachable", Value::Null),
            }
        }
    }

    // ----- time warnings (§11.2, §11.3) ------------------------------------
    time_warnings(&subject.value, opts, &mut rep);

    // ----- profiles (§10) ---------------------------------------------------
    let profile = evaluate_profiles(&subject, &available, opts, &mut rep);
    rep.profile = profile;
    // §10.4: the profile of an invalid document is null. Every level in §10 is
    // defined over a *valid* document, so a document whose `valid` is false
    // satisfies none of them — including when the signature verified and the
    // errors are semantic or chain-level, which is exactly the case that used to
    // report `L0` here. A caller reading `profile` alone must never see an
    // assurance level on a document that failed verification.
    if !rep.valid() {
        rep.profile = None;
    }
    // §12 / §10.4: an AWR/1 document satisfies no AWR/2 profile. Its `type` is
    // outside the legacy signature (§13.1), so reading "WorkReceipt" out of it and
    // answering "L0" would grant an assurance level on the strength of a field an
    // intermediary can rewrite. This build reported L0 for both AWR/1 vectors while
    // the other two reported null.
    if legacy::is_legacy(&subject.value) {
        rep.profile = None;
    }

    rep
}

fn merge(into: &mut Report, from: Report) {
    for r in from.reasons {
        into.push(&r.code, r.detail);
    }
    for w in from.warnings {
        into.push(&w.code, w.detail);
    }
    for (k, v) in from.extra {
        into.set_extra(&k, v);
    }
}

fn time_warnings(doc: &Value, opts: &Options, rep: &mut Report) {
    let now = opts.now.unwrap_or(Timestamp { secs: now_secs(), nanos: 0 });
    if let Some(vf) = doc
        .get("validFrom")
        .and_then(|v| v.as_str())
        .and_then(crate::timefmt::parse_rfc3339_utc)
    {
        if vf.secs > now.secs + opts.skew_secs {
            rep.push(
                "AWR-TIME-001",
                format!(
                    "validFrom is {} s in the future, beyond the {} s skew allowance; age is policy, not validity (§11.3)",
                    vf.secs - now.secs,
                    opts.skew_secs
                ),
            );
        }
    }
    if let Some(vu) = doc
        .get("validUntil")
        .and_then(|v| v.as_str())
        .and_then(crate::timefmt::parse_rfc3339_utc)
    {
        if vu.secs < now.secs {
            rep.push(
                "AWR-TIME-002",
                format!(
                    "validUntil passed {} s ago; this is a warning and any age threshold belongs to the caller's policy (§11.3)",
                    now.secs - vu.secs
                ),
            );
        }
    }
}

/// §10.3: an accountability binding is well-formed if it is an object naming a
/// scheme. AWR/2 defines no scheme semantics, so nothing more can be checked —
/// and nothing on-chain may be contacted.
fn binding_ok(v: Option<&Value>) -> bool {
    match v {
        Some(b) if b.is_object() => b.get_nonempty_str("scheme").is_some(),
        _ => false,
    }
}

/// Evaluate L0/L1/L2 (§10) and return the highest satisfied.
///
/// IMPLEMENTATION CHOICE (§10.4): shortfall codes are reported as errors only
/// for a profile the caller *requested*. Without `--profile`, all three levels
/// are still evaluated and the highest satisfied is reported, but a plain L0
/// receipt is not made invalid for lacking verdicts it never claimed.
fn evaluate_profiles(
    subject: &AvailableDoc,
    available: &[AvailableDoc],
    opts: &Options,
    rep: &mut Report,
) -> Option<String> {
    let requested = opts.profile.as_deref();
    if !subject.is_receipt() {
        // Profiles are defined over a WorkReceipt (§10.1). A verdict or blame
        // attestation is verified on its own terms.
        if requested.is_some() {
            rep.set_extra(
                "profileNote",
                Value::string(format!(
                    "profiles are defined over a WorkReceipt; this document is a {}",
                    subject.doc_type.clone().unwrap_or_else(|| "document of unknown type".into())
                )),
            );
        }
        return None;
    }

    let l0 = subject.valid;
    if !l0 {
        return None;
    }

    let receipt_issuer = subject.issuer_id.clone();
    // Verdicts that are valid on their own and commit to this receipt's bytes.
    let mut matching: Vec<&AvailableDoc> = Vec::new();
    for d in available {
        if d.doc_type.as_deref() != Some("VerificationVerdict") || !d.valid {
            continue;
        }
        let digest = d
            .subject()
            .and_then(|s| s.get("verifiedWork"))
            .and_then(|w| w.get("digestSRI"))
            .and_then(|s| parse_sri(s).ok());
        if digest == Some(subject.digest) {
            matching.push(d);
        }
    }
    let independent: Vec<&&AvailableDoc> = matching
        .iter()
        .filter(|d| d.issuer_id.is_some() && d.issuer_id != receipt_issuer)
        .collect();

    let mut level = "L0".to_string();
    let want_l1 = matches!(requested, Some("L1") | Some("L2"));
    let want_l2 = requested == Some("L2");

    let l1 = !independent.is_empty();
    if !l1 && want_l1 {
        if matching.is_empty() {
            rep.push(
                "AWR-PROFILE-001",
                "L1: no valid VerificationVerdict for this receipt was supplied",
            );
        } else {
            rep.push(
                "AWR-PROFILE-002",
                format!(
                    "L1: the only verdict(s) for this receipt are issued by the receipt's own issuer {}; self-verification is the failure mode L1 excludes (§10.2)",
                    receipt_issuer.clone().unwrap_or_else(|| "<unknown>".into())
                ),
            );
        }
    }
    if l1 {
        level = "L1".to_string();
    }

    // §10.3 both conditions.
    let mut issuers: Vec<&str> = Vec::new();
    for d in &independent {
        if let Some(i) = d.issuer_id.as_deref() {
            if !issuers.contains(&i) {
                issuers.push(i);
            }
        }
    }
    let two_issuers = issuers.len() >= 2;
    let settlement = subject.subject().and_then(|s| s.get("settlement"));
    let has_settlement = binding_ok(settlement);
    let all_staked = !independent.is_empty()
        && independent
            .iter()
            .all(|d| binding_ok(d.subject().and_then(|s| s.get("stake"))));
    let binding = has_settlement || all_staked;

    if binding {
        rep.push(
            "AWR-L2-001",
            "an accountability binding is present; its on-chain existence was NOT checked, and a verifier must not contact a chain to do so (§10.3)",
        );
    }
    if l1 && two_issuers && binding {
        level = "L2".to_string();
    } else if want_l2 {
        if !two_issuers {
            rep.push(
                "AWR-PROFILE-003",
                format!(
                    "L2: {} distinct verdict issuer(s) other than the receipt's issuer; two are required",
                    issuers.len()
                ),
            );
        }
        if !binding {
            rep.push(
                "AWR-PROFILE-004",
                "L2: the receipt carries no well-formed `settlement` and not every independent verdict carries a well-formed `stake`",
            );
        }
    }

    // §10.4: report what was evaluated.
    rep.set_extra(
        "profilesEvaluated",
        Value::object(vec![
            ("L0".to_string(), Value::Bool(l0)),
            ("L1".to_string(), Value::Bool(l1)),
            ("L2".to_string(), Value::Bool(l1 && two_issuers && binding)),
            (
                "requested".to_string(),
                match requested {
                    Some(r) => Value::string(r),
                    None => Value::Null,
                },
            ),
            (
                "independentVerdictIssuers".to_string(),
                Value::Array(issuers.iter().map(|i| Value::string(*i)).collect()),
            ),
        ]),
    );

    Some(level)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::issue::{self, IssueOptions};
    use crate::json::to_string_compact;
    use ed25519_dalek::SigningKey;

    fn input(v: &Value, name: &str) -> Input {
        Input { bytes: to_string_compact(v).into_bytes(), source: name.to_string() }
    }

    fn receipt(sk: &SigningKey) -> Value {
        let subject = parse(
            format!(
                r#"{{"work":{{"modelId":"claude-sonnet-5@anthropic","capability":"urn:example:capability:summarise",
                     "startedAt":"2026-07-31T10:15:28Z","completedAt":"2026-07-31T10:15:30Z",
                     "latencyMs":2340,"status":"succeeded"}},
                 "inputDigest":"{}","outputDigest":"{}","nonce":"01J9Z8QK4T7YB2N5V6W8XA3C0D"}}"#,
                crate::sri::sri_of_bytes(b"the input payload"),
                crate::sri::sri_of_bytes(b"the output payload")
            )
            .as_bytes(),
        )
        .unwrap();
        issue::issue(
            &subject,
            sk,
            &IssueOptions {
                doc_type: "WorkReceipt".to_string(),
                id: Some("urn:uuid:8f14e45f-ea1c-4f38-9b8a-1c2d3e4f5a6b".to_string()),
                now: Some("2026-07-31T10:15:30Z".to_string()),
                issuer_name: Some("example-hub".to_string()),
                include_jwk: false,
            },
        )
        .unwrap()
    }

    fn verdict(sk: &SigningKey, receipt: &AvailableDoc, verdict: &str, stake: bool) -> Value {
        let stake_json = if stake {
            r#","stake":{"scheme":"stake-evm-v1","chainId":8453,"amount":{"currency":"USD","amount":"5.00"}}"#
        } else {
            ""
        };
        let subject = parse(
            format!(
                r#"{{"verifiedWork":{{"id":"{}","digestSRI":"{}"}},"verdict":"{}","score":"0.93",
                     "method":{{"id":"urn:example:method:grounded-council-v1"}},
                     "policy":{{"threshold":"0.80"}}{}}}"#,
                receipt.id.clone().unwrap(),
                sri_of_digest(&receipt.digest),
                verdict,
                stake_json
            )
            .as_bytes(),
        )
        .unwrap();
        issue::issue(
            &subject,
            sk,
            &IssueOptions {
                doc_type: "VerificationVerdict".to_string(),
                id: Some(format!("urn:uuid:verdict-{}", sk.verifying_key().to_bytes()[0])),
                now: Some("2026-07-31T10:16:00Z".to_string()),
                issuer_name: None,
                include_jwk: false,
            },
        )
        .unwrap()
    }

    fn prep(v: &Value) -> AvailableDoc {
        let mut d = prepare(v.clone(), "test").unwrap();
        let mut r = Report::default();
        verify_document(&d.value, &mut r);
        d.valid = r.valid();
        d
    }

    fn opts_at(now: &str) -> Options {
        Options {
            now: crate::timefmt::parse_rfc3339_utc(now),
            ..Default::default()
        }
    }

    #[test]
    fn issued_receipt_verifies_and_is_l0() {
        let sk = SigningKey::from_bytes(&[1u8; 32]);
        let r = receipt(&sk);
        let rep = verify(&input(&r, "receipt.awr.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.valid(), "{}", rep.to_json());
        assert_eq!(rep.profile.as_deref(), Some("L0"));
        assert_eq!(rep.document_type.as_deref(), Some("WorkReceipt"));
        assert_eq!(rep.awr_version.as_deref(), Some("2.0.0"));
        assert_eq!(rep.chain.resolved, 0);
        assert!(rep.warnings.is_empty(), "{:?}", rep.warnings);
    }

    #[test]
    fn tampering_with_any_field_breaks_the_proof() {
        let sk = SigningKey::from_bytes(&[1u8; 32]);
        for field in ["id", "issuer", "validFrom", "awrVersion", "credentialSubject"] {
            let mut r = receipt(&sk);
            let replacement = match field {
                "id" => Value::string("urn:uuid:00000000-0000-4000-8000-000000000000"),
                "issuer" => {
                    let mut i = r.get("issuer").unwrap().clone();
                    i.set("name", Value::string("someone-else"));
                    i
                }
                "validFrom" => Value::string("2020-01-01T00:00:00Z"),
                "awrVersion" => Value::string("2.0.1"),
                _ => {
                    let mut s = r.get("credentialSubject").unwrap().clone();
                    s.set("outputDigest", Value::string(crate::sri::sri_of_bytes(b"substituted")));
                    s
                }
            };
            r.set(field, replacement);
            let rep = verify(&input(&r, "t.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
            assert!(
                rep.has_code("AWR-PROOF-006"),
                "editing {} left the signature valid: {}",
                field,
                rep.to_json()
            );
            assert!(!rep.valid());
        }
    }

    #[test]
    fn an_array_of_proofs_needs_one_that_verifies_and_reports_which() {
        // §6.1: "at least one proof MUST verify ... A verifier that accepts an
        // array MUST report which proof it verified."
        let sk = SigningKey::from_bytes(&[1u8; 32]);
        let r = receipt(&sk);
        let good = r.get("proof").unwrap().clone();
        let mut bad = good.clone();
        bad.set(
            "proofValue",
            Value::string(crate::encoding::multibase_b58_encode(&[0u8; 64])),
        );

        let mut doc = r.clone();
        doc.set("proof", Value::Array(vec![bad.clone(), good.clone()]));
        let rep = verify(&input(&doc, "t.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.valid(), "{}", rep.to_json());
        let extra: Vec<&String> = rep.extra.iter().map(|(k, _)| k).collect();
        assert!(extra.contains(&&"verifiedProof".to_string()), "{:?}", extra);
        assert!(extra.contains(&&"proofs".to_string()), "{:?}", extra);
        let verified = rep
            .extra
            .iter()
            .find(|(k, _)| k == "verifiedProof")
            .map(|(_, v)| v.as_i64())
            .unwrap();
        assert_eq!(verified, Some(1), "the second proof is the valid one");

        // Only the bad proof: nothing verifies.
        let mut doc = r.clone();
        doc.set("proof", Value::Array(vec![bad]));
        let rep = verify(&input(&doc, "t.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.has_code("AWR-PROOF-006"), "{}", rep.to_json());
        assert!(!rep.valid());

        // An empty array is a missing proof.
        let mut doc = r.clone();
        doc.set("proof", Value::Array(vec![]));
        let rep = verify(&input(&doc, "t.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.has_code("AWR-PROOF-001"), "{}", rep.to_json());
    }

    #[test]
    fn adding_an_unknown_field_breaks_the_proof() {
        // §3.1: unknown properties are inside the canonical form, so an
        // intermediary cannot add one.
        let sk = SigningKey::from_bytes(&[1u8; 32]);
        let mut r = receipt(&sk);
        r.set("hubInfo", Value::string("added in transit"));
        let rep = verify(&input(&r, "t.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.has_code("AWR-PROOF-006"), "{}", rep.to_json());
    }

    #[test]
    fn wrong_issuer_key_is_proof_006_not_key_002() {
        let sk = SigningKey::from_bytes(&[1u8; 32]);
        let other = SigningKey::from_bytes(&[2u8; 32]);
        let mut r = receipt(&sk);
        let mut issuer = r.get("issuer").unwrap().clone();
        issuer.set(
            "id",
            Value::string(crate::didkey::did_from_public_key(&other.verifying_key().to_bytes())),
        );
        r.set("issuer", issuer);
        let rep = verify(&input(&r, "t.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        // verificationMethod now disagrees with issuer.id, and the signature is
        // not the new issuer's: both are reported.
        assert!(rep.has_code("AWR-PROOF-007"), "{}", rep.to_json());
    }

    #[test]
    fn jwk_mismatch_invalidates() {
        let sk = SigningKey::from_bytes(&[1u8; 32]);
        let mut r = receipt(&sk);
        let mut issuer = r.get("issuer").unwrap().clone();
        issuer.set("publicKeyJwk", crate::didkey::public_key_jwk(&[9u8; 32]));
        r.set("issuer", issuer);
        let rep = verify(&input(&r, "t.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.has_code("AWR-KEY-003"), "{}", rep.to_json());
        assert!(!rep.valid());
    }

    #[test]
    fn time_warnings_are_warnings() {
        let sk = SigningKey::from_bytes(&[1u8; 32]);
        let r = receipt(&sk);
        // validFrom is 2026-07-31T10:15:30Z; verify as if it were a year earlier.
        let rep = verify(&input(&r, "t.json"), &[], &opts_at("2025-07-31T10:15:30Z"));
        assert!(rep.has_code("AWR-TIME-001"));
        assert!(rep.valid(), "freshness is policy, not validity: {}", rep.to_json());

        // A two-year-old document is still valid (§11.3).
        let rep = verify(&input(&r, "t.json"), &[], &opts_at("2028-07-31T10:15:30Z"));
        assert!(rep.valid());
        assert!(!rep.has_code("AWR-TIME-001"));
    }

    #[test]
    fn valid_until_in_the_past_is_a_warning() {
        let sk = SigningKey::from_bytes(&[1u8; 32]);
        let mut r = receipt(&sk);
        r.set("validUntil", Value::string("2026-08-01T00:00:00Z"));
        // resign so the proof stays valid
        let r = issue::resign(&r, &sk).unwrap();
        let rep = verify(&input(&r, "t.json"), &[], &opts_at("2026-09-01T00:00:00Z"));
        assert!(rep.has_code("AWR-TIME-002"), "{}", rep.to_json());
        assert!(rep.valid());
    }

    #[test]
    fn profile_l1_requires_an_independent_verdict() {
        let hub = SigningKey::from_bytes(&[1u8; 32]);
        let judge = SigningKey::from_bytes(&[2u8; 32]);
        let r = receipt(&hub);
        let rd = prep(&r);

        // No verdict at all.
        let mut o = opts_at("2026-07-31T11:00:00Z");
        o.profile = Some("L1".to_string());
        let rep = verify(&input(&r, "r.json"), &[], &o);
        assert!(rep.has_code("AWR-PROFILE-001"), "{}", rep.to_json());
        assert!(!rep.valid());
        // §10.4: the profile of an invalid document is null. Requesting L1 and not
        // reaching it makes the document invalid, so there is no level to report —
        // this build used to answer "L0" here, which put an assurance level on a
        // document it had just rejected.
        assert_eq!(rep.profile, None);

        // Self-issued verdict.
        let self_verdict = verdict(&hub, &rd, "pass", false);
        let rep = verify(&input(&r, "r.json"), &[input(&self_verdict, "v.json")], &o);
        assert!(rep.has_code("AWR-PROFILE-002"), "{}", rep.to_json());

        // Independent verdict.
        let good = verdict(&judge, &rd, "pass", false);
        let rep = verify(&input(&r, "r.json"), &[input(&good, "v.json")], &o);
        assert!(rep.valid(), "{}", rep.to_json());
        assert_eq!(rep.profile.as_deref(), Some("L1"));

        // A `fail` verdict still satisfies L1 structurally (§10.2).
        let failing = verdict(&judge, &rd, "fail", false);
        let rep = verify(&input(&r, "r.json"), &[input(&failing, "v.json")], &o);
        assert_eq!(rep.profile.as_deref(), Some("L1"), "{}", rep.to_json());
    }

    #[test]
    fn profile_l2_needs_two_issuers_and_a_binding() {
        let hub = SigningKey::from_bytes(&[1u8; 32]);
        let j1 = SigningKey::from_bytes(&[2u8; 32]);
        let j2 = SigningKey::from_bytes(&[3u8; 32]);
        let r = receipt(&hub);
        let rd = prep(&r);
        let mut o = opts_at("2026-07-31T11:00:00Z");
        o.profile = Some("L2".to_string());

        // One issuer, no binding.
        let v1 = verdict(&j1, &rd, "pass", false);
        let rep = verify(&input(&r, "r.json"), &[input(&v1, "v1.json")], &o);
        assert!(rep.has_code("AWR-PROFILE-003"), "{}", rep.to_json());
        assert!(rep.has_code("AWR-PROFILE-004"));

        // Two issuers, both staked.
        let v1s = verdict(&j1, &rd, "pass", true);
        let v2s = verdict(&j2, &rd, "pass", true);
        let rep = verify(
            &input(&r, "r.json"),
            &[input(&v1s, "v1.json"), input(&v2s, "v2.json")],
            &o,
        );
        assert!(rep.valid(), "{}", rep.to_json());
        assert_eq!(rep.profile.as_deref(), Some("L2"));
        assert!(rep.has_code("AWR-L2-001"), "on-chain existence must be flagged as unchecked");
        assert!(rep.warnings.iter().any(|w| w.code == "AWR-L2-001"));
    }

    #[test]
    fn verdict_digest_substitution_is_vdct_005() {
        let hub = SigningKey::from_bytes(&[1u8; 32]);
        let judge = SigningKey::from_bytes(&[2u8; 32]);
        let r = receipt(&hub);
        let rd = prep(&r);
        let v = verdict(&judge, &rd, "pass", false);
        // A different receipt under the same id: same id, different bytes.
        let mut r2 = r.clone();
        let mut s = r2.get("credentialSubject").unwrap().clone();
        s.set("nonce", Value::string("01J9Z8QK4T7YB2N5V6W8XA3C0E"));
        r2.set("credentialSubject", s);
        let r2 = issue::resign(&r2, &hub).unwrap();
        let rep = verify(&input(&v, "v.json"), &[input(&r2, "r2.json")], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.has_code("AWR-VDCT-005"), "{}", rep.to_json());
    }

    #[test]
    fn bundle_verification_and_subject_selection() {
        let hub = SigningKey::from_bytes(&[1u8; 32]);
        let judge = SigningKey::from_bytes(&[2u8; 32]);
        let r = receipt(&hub);
        let rd = prep(&r);
        let v = verdict(&judge, &rd, "pass", false);
        let b = Value::object(vec![
            ("awrBundle".to_string(), Value::string("2.0")),
            ("documents".to_string(), Value::Array(vec![r.clone(), v.clone()])),
        ]);
        let mut o = opts_at("2026-07-31T11:00:00Z");
        o.profile = Some("L1".to_string());
        let rep = verify(&input(&b, "b.awrb.json"), &[], &o);
        assert!(rep.valid(), "{}", rep.to_json());
        assert_eq!(rep.document_type.as_deref(), Some("WorkReceipt"));
        assert_eq!(rep.profile.as_deref(), Some("L1"));

        // Wrong container version.
        let bad = Value::object(vec![
            ("awrBundle".to_string(), Value::string("1.0")),
            ("documents".to_string(), Value::Array(vec![r.clone()])),
        ]);
        let rep = verify(&input(&bad, "b.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.has_code("AWR-BUNDLE-001"));
    }

    #[test]
    fn chain_edges_are_reported() {
        let hub = SigningKey::from_bytes(&[1u8; 32]);
        let parent = receipt(&hub);
        let pd = prep(&parent);
        let child_subject = parse(
            format!(
                r#"{{"work":{{"modelId":"m@v","completedAt":"2026-07-31T10:20:00Z","status":"succeeded"}},
                     "inputDigest":"{}","outputDigest":"{}",
                     "parents":[{{"id":"{}","digestSRI":"{}","role":"retrieval"}}]}}"#,
                crate::sri::sri_of_bytes(b"the output payload"),
                crate::sri::sri_of_bytes(b"child output"),
                pd.id.clone().unwrap(),
                sri_of_digest(&pd.digest)
            )
            .as_bytes(),
        )
        .unwrap();
        let child = issue::issue(
            &child_subject,
            &hub,
            &IssueOptions {
                doc_type: "WorkReceipt".to_string(),
                id: Some("urn:uuid:child".to_string()),
                now: Some("2026-07-31T10:20:00Z".to_string()),
                issuer_name: None,
                include_jwk: false,
            },
        )
        .unwrap();

        // With the parent supplied: one resolved edge, no CHAIN-007 (the child's
        // inputDigest equals the parent's outputDigest).
        let rep = verify(
            &input(&child, "c.json"),
            &[input(&parent, "p.json")],
            &opts_at("2026-07-31T11:00:00Z"),
        );
        assert!(rep.valid(), "{}", rep.to_json());
        assert_eq!(rep.chain.resolved, 1);
        assert_eq!(rep.chain.unresolved, 0);
        assert!(!rep.has_code("AWR-CHAIN-007"));

        // Without it: one unresolved edge, still valid (§8.2).
        let rep = verify(&input(&child, "c.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.valid(), "{}", rep.to_json());
        assert_eq!(rep.chain.unresolved, 1);
    }

    #[test]
    fn non_integer_number_blocks_verification_with_canon_001() {
        let sk = SigningKey::from_bytes(&[1u8; 32]);
        let mut r = receipt(&sk);
        let mut s = r.get("credentialSubject").unwrap().clone();
        let mut work = s.get("work").unwrap().clone();
        work.set(
            "latencyMs",
            Value::Number { raw: "2340.5".to_string(), kind: crate::json::NumberKind::NonInteger },
        );
        s.set("work", work);
        r.set("credentialSubject", s);
        let rep = verify(&input(&r, "t.json"), &[], &opts_at("2026-07-31T11:00:00Z"));
        assert!(rep.has_code("AWR-CANON-001"), "{}", rep.to_json());
        assert!(rep.has_code("AWR-RCPT-004"));
        assert!(!rep.valid());
    }

    #[test]
    fn duplicate_key_is_reported_before_anything_else() {
        let raw = br#"{"id":"urn:uuid:1","id":"urn:uuid:2"}"#;
        let rep = verify(
            &Input { bytes: raw.to_vec(), source: "dup.json".to_string() },
            &[],
            &Options::default(),
        );
        assert!(rep.has_code("AWR-CANON-004"), "{}", rep.to_json());
        assert!(!rep.valid());
    }

    #[test]
    fn not_an_object_is_doc_001() {
        let rep = verify(
            &Input { bytes: b"[1,2,3]".to_vec(), source: "arr.json".to_string() },
            &[],
            &Options::default(),
        );
        assert!(rep.has_code("AWR-DOC-001"));
    }

}
