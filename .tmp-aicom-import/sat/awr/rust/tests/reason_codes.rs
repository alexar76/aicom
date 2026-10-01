//! One negative (or warning-producing) case per reason code in SPEC §11.2, plus
//! a coverage assertion that the whole registry is exercised.
//!
//! Every fixture is built here from a real signature over real canonical bytes:
//! nothing in this file is a transcribed constant.

use awr::chain::{self, AvailableDoc, ChainLimits};
use awr::json::{canonicalize, parse, to_string_compact, NumberKind, Value};
use awr::report::{Report, REGISTRY};
use awr::sri::{sha256, sri_of_bytes, sri_of_digest};
use awr::verify::{verify, Input, Options};
use ed25519_dalek::SigningKey;

const NOW: &str = "2026-07-31T11:00:00Z";

fn hub() -> SigningKey {
    SigningKey::from_bytes(&[1u8; 32])
}
fn judge_a() -> SigningKey {
    SigningKey::from_bytes(&[2u8; 32])
}
fn judge_b() -> SigningKey {
    SigningKey::from_bytes(&[3u8; 32])
}

fn opts() -> Options {
    Options { now: awr::timefmt::parse_rfc3339_utc(NOW), ..Default::default() }
}

fn opts_profile(p: &str) -> Options {
    Options { profile: Some(p.to_string()), ..opts() }
}

fn issue(subject: &Value, sk: &SigningKey, kind: &str, id: &str) -> Value {
    awr::issue::issue(
        subject,
        sk,
        &awr::issue::IssueOptions {
            doc_type: kind.to_string(),
            id: Some(id.to_string()),
            now: Some("2026-07-31T10:15:30Z".to_string()),
            issuer_name: None,
            include_jwk: false,
        },
    )
    .expect("issue")
}

fn receipt_subject(extra: &str) -> Value {
    let src = format!(
        r#"{{"work":{{"modelId":"claude-sonnet-5@anthropic","startedAt":"2026-07-31T10:15:28Z",
              "completedAt":"2026-07-31T10:15:30Z","latencyMs":2340,"status":"succeeded"}},
            "inputDigest":"{}","outputDigest":"{}"{}}}"#,
        sri_of_bytes(b"in"),
        sri_of_bytes(b"out"),
        extra
    );
    parse(src.as_bytes()).expect("subject parses")
}

fn base_receipt() -> Value {
    issue(&receipt_subject(""), &hub(), "WorkReceipt", "urn:uuid:receipt-1")
}

fn digest_of(doc: &Value) -> [u8; 32] {
    sha256(canonicalize(doc).expect("canonical").as_bytes())
}

fn verdict_for(doc: &Value, sk: &SigningKey, verdict: &str, id: &str, stake: bool) -> Value {
    let stake_json = if stake {
        r#","stake":{"scheme":"stake-evm-v1","chainId":8453,"contract":"0x00","amount":{"currency":"USD","amount":"5.00"}}"#
    } else {
        ""
    };
    let subject = parse(
        format!(
            r#"{{"verifiedWork":{{"id":"{}","digestSRI":"{}"}},"verdict":"{}","score":"0.93",
                 "method":{{"id":"urn:example:method:grounded-council-v1"}},
                 "policy":{{"threshold":"0.80"}}{}}}"#,
            doc.get("id").unwrap().as_str().unwrap(),
            sri_of_digest(&digest_of(doc)),
            verdict,
            stake_json
        )
        .as_bytes(),
    )
    .expect("verdict subject");
    issue(&subject, sk, "VerificationVerdict", id)
}

fn input(v: &Value) -> Input {
    Input { bytes: to_string_compact(v).into_bytes(), source: "fixture".to_string() }
}

fn raw(s: &str) -> Input {
    Input { bytes: s.as_bytes().to_vec(), source: "fixture".to_string() }
}

/// Edit one member of a signed document and re-sign, so that the structural
/// error under test is the *only* error reported.
fn edit_and_resign(field: &str, value: Value) -> Value {
    let mut doc = base_receipt();
    doc.set(field, value);
    awr::issue::resign(&doc, &hub()).expect("resign")
}

/// Edit the subject of a signed receipt and re-sign.
fn edit_subject_and_resign(mutate: impl FnOnce(&mut Value)) -> Value {
    let mut doc = base_receipt();
    let mut subject = doc.get("credentialSubject").unwrap().clone();
    mutate(&mut subject);
    doc.set("credentialSubject", subject);
    awr::issue::resign(&doc, &hub()).expect("resign")
}

/// Edit the subject without re-signing — necessary when the edit makes the
/// document uncanonicalizable, since then no signature can be computed at all.
fn edit_subject_no_resign(mutate: impl FnOnce(&mut Value)) -> Value {
    let mut doc = base_receipt();
    let mut subject = doc.get("credentialSubject").unwrap().clone();
    mutate(&mut subject);
    doc.set("credentialSubject", subject);
    doc
}

fn edit_proof_and_keep(field: &str, value: Value) -> Value {
    // Proof-object edits are made *after* signing on purpose: changing a proof
    // option changes the signed proof config, so these documents are expected to
    // report the structural code under test (and possibly AWR-PROOF-006 too).
    let mut doc = base_receipt();
    let mut proof = doc.get("proof").unwrap().clone();
    proof.set(field, value);
    doc.set("proof", proof);
    doc
}

/// Every scenario: the code it is meant to produce, a label, and the codes the
/// implementation actually reported.
fn scenarios() -> Vec<(&'static str, String, Vec<String>)> {
    let mut out: Vec<(&'static str, String, Vec<String>)> = Vec::new();
    let mut add = |code: &'static str, label: &str, rep: Report| {
        out.push((code, label.to_string(), rep.codes()));
    };

    // ---- document ---------------------------------------------------------
    add("AWR-DOC-001", "top-level array", verify(&raw("[1,2,3]"), &[], &opts()));
    add(
        "AWR-DOC-002",
        "wrong first @context",
        verify(
            &input(&edit_and_resign(
                "@context",
                Value::Array(vec![
                    Value::string("https://example.com/ctx"),
                    Value::string(awr::AWR_CONTEXT),
                ]),
            )),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-DOC-003",
        "AWR namespace absent",
        verify(
            &input(&edit_and_resign(
                "@context",
                Value::Array(vec![Value::string(awr::VC2_CONTEXT)]),
            )),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-DOC-004",
        "type without VerifiableCredential",
        verify(
            &input(&edit_and_resign("type", Value::Array(vec![Value::string("WorkReceipt")]))),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-DOC-005",
        "two AWR types",
        verify(
            &input(&edit_and_resign(
                "type",
                Value::Array(vec![
                    Value::string("VerifiableCredential"),
                    Value::string("WorkReceipt"),
                    Value::string("BlameAttestation"),
                ]),
            )),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-DOC-006",
        "relative id",
        verify(&input(&edit_and_resign("id", Value::string("receipt-1"))), &[], &opts()),
    );
    add(
        "AWR-DOC-007",
        "validUntil not later than validFrom",
        verify(
            &input(&edit_and_resign("validUntil", Value::string("2026-07-31T10:15:30Z"))),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-DOC-008",
        "credentialSubject array",
        verify(
            &input(&edit_and_resign(
                "credentialSubject",
                Value::Array(vec![receipt_subject("")]),
            )),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-DOC-009",
        "awrVersion 1.0.0",
        verify(&input(&edit_and_resign("awrVersion", Value::string("1.0.0"))), &[], &opts()),
    );
    add(
        "AWR-DOC-010",
        "bare-string issuer",
        verify(
            &input(&edit_and_resign(
                "issuer",
                Value::string(awr::didkey::did_from_public_key(&hub().verifying_key().to_bytes())),
            )),
            &[],
            &opts(),
        ),
    );

    // ---- canonicalization -------------------------------------------------
    add(
        "AWR-CANON-001",
        "non-integer number",
        verify(
            &input(&edit_subject_no_resign(|s| {
                let mut w = s.get("work").unwrap().clone();
                w.set(
                    "latencyMs",
                    Value::Number { raw: "2340.5".to_string(), kind: NumberKind::NonInteger },
                );
                s.set("work", w);
            })),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-CANON-002",
        "integer above 2^53-1",
        verify(
            &raw(&to_string_compact(&edit_subject_no_resign(|s| {
                let mut w = s.get("work").unwrap().clone();
                w.set(
                    "latencyMs",
                    Value::Number {
                        raw: "9007199254740992".to_string(),
                        kind: NumberKind::OutOfRange,
                    },
                );
                s.set("work", w);
            }))),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-CANON-003",
        "lone surrogate",
        verify(&raw(r#"{"id":"urn:uuid:1","x":"\ud800"}"#), &[], &opts()),
    );
    add(
        "AWR-CANON-004",
        "duplicate property name",
        verify(&raw(r#"{"id":"urn:uuid:1","id":"urn:uuid:2"}"#), &[], &opts()),
    );
    add("AWR-CANON-005", "malformed JSON", verify(&raw("{\"id\":}"), &[], &opts()));
    // AWR-CANON-006 is an implementation self-check: with a correct
    // canonicalizer no document can trigger it, so it is exercised against the
    // self-check entry point with output a broken canonicalizer would produce.
    {
        let mut rep = Report::default();
        let e = awr::json::self_check(r#"{"b":1,"a":1}"#).unwrap_err();
        rep.push(e.code, e.detail);
        add("AWR-CANON-006", "non-idempotent canonical form", rep);
    }

    // ---- keys -------------------------------------------------------------
    let issuer_with = |id: &str| -> Value {
        let mut doc = base_receipt();
        let mut issuer = doc.get("issuer").unwrap().clone();
        issuer.set("id", Value::string(id));
        doc.set("issuer", issuer);
        awr::issue::resign(&doc, &hub()).expect("resign")
    };
    add(
        "AWR-KEY-001",
        "https issuer",
        verify(&input(&issuer_with("https://example.com/issuer")), &[], &opts()),
    );
    add(
        "AWR-KEY-002",
        "did:key with a non-base58 character",
        verify(&input(&issuer_with("did:key:z0OIl")), &[], &opts()),
    );
    {
        let mut doc = base_receipt();
        let mut issuer = doc.get("issuer").unwrap().clone();
        issuer.set("publicKeyJwk", awr::didkey::public_key_jwk(&[7u8; 32]));
        doc.set("issuer", issuer);
        let doc = awr::issue::resign(&doc, &hub()).expect("resign");
        add("AWR-KEY-003", "publicKeyJwk disagrees with did:key", verify(&input(&doc), &[], &opts()));
    }
    {
        // A well-formed did:key for a P-256 key.
        let mut multicodec = vec![0x80u8, 0x24];
        multicodec.extend_from_slice(&[4u8; 33]);
        let did = format!("did:key:{}", awr::encoding::multibase_b58_encode(&multicodec));
        add("AWR-KEY-004", "did:key for P-256", verify(&input(&issuer_with(&did)), &[], &opts()));
    }

    // ---- proof ------------------------------------------------------------
    {
        let mut doc = base_receipt();
        doc.remove("proof");
        add("AWR-PROOF-001", "proof missing", verify(&input(&doc), &[], &opts()));
    }
    add(
        "AWR-PROOF-002",
        "proof.type not DataIntegrityProof",
        verify(
            &input(&edit_proof_and_keep("type", Value::string("JsonWebSignature2020"))),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-PROOF-003",
        "unsupported cryptosuite",
        verify(
            &input(&edit_proof_and_keep("cryptosuite", Value::string("eddsa-rdfc-2022"))),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-PROOF-004",
        "proofPurpose not assertionMethod",
        verify(
            &input(&edit_proof_and_keep("proofPurpose", Value::string("authentication"))),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-PROOF-005",
        "base64 proofValue (the AWR/1 encoding)",
        verify(
            &input(&edit_proof_and_keep(
                "proofValue",
                Value::string(awr::encoding::b64_encode(&[9u8; 64])),
            )),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-PROOF-006",
        "subject substituted after signing",
        verify(
            &input(&{
                let mut doc = base_receipt();
                let mut s = doc.get("credentialSubject").unwrap().clone();
                s.set("outputDigest", Value::string(sri_of_bytes(b"substituted")));
                doc.set("credentialSubject", s);
                doc
            }),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-PROOF-007",
        "verificationMethod without the DID fragment",
        verify(
            &input(&edit_proof_and_keep(
                "verificationMethod",
                Value::string(awr::didkey::did_from_public_key(&hub().verifying_key().to_bytes())),
            )),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-PROOF-008",
        "proof.@context differs from the document's",
        verify(
            &input(&edit_proof_and_keep(
                "@context",
                Value::Array(vec![Value::string("https://example.com/other")]),
            )),
            &[],
            &opts(),
        ),
    );
    {
        let mut doc = base_receipt();
        let mut proof = doc.get("proof").unwrap().clone();
        proof.remove("created");
        doc.set("proof", proof);
        add("AWR-PROOF-009", "proof.created missing", verify(&input(&doc), &[], &opts()));
    }

    // ---- receipt ----------------------------------------------------------
    add(
        "AWR-RCPT-001",
        "outputDigest missing",
        verify(&input(&edit_subject_and_resign(|s| { s.remove("outputDigest"); })), &[], &opts()),
    );
    add(
        "AWR-RCPT-002",
        "lowercase currency and numeric amount",
        verify(
            &input(&edit_subject_and_resign(|s| {
                s.set(
                    "price",
                    parse(br#"{"currency":"usd","amount":"0.15."}"#).unwrap(),
                );
            })),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-RCPT-003",
        "completedAt before startedAt",
        verify(
            &input(&edit_subject_and_resign(|s| {
                let mut w = s.get("work").unwrap().clone();
                w.set("completedAt", Value::string("2026-07-31T10:15:00Z"));
                s.set("work", w);
            })),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-RCPT-004",
        "negative latencyMs",
        verify(
            &input(&edit_subject_and_resign(|s| {
                let mut w = s.get("work").unwrap().clone();
                w.set("latencyMs", Value::int(-3));
                s.set("work", w);
            })),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-RCPT-005",
        "empty modelId",
        verify(
            &input(&edit_subject_and_resign(|s| {
                let mut w = s.get("work").unwrap().clone();
                w.set("modelId", Value::string(""));
                s.set("work", w);
            })),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-RCPT-006",
        "status outside the enumeration",
        verify(
            &input(&edit_subject_and_resign(|s| {
                let mut w = s.get("work").unwrap().clone();
                w.set("status", Value::string("exploded"));
                s.set("work", w);
            })),
            &[],
            &opts(),
        ),
    );

    // ---- verdict ----------------------------------------------------------
    let receipt = base_receipt();
    let verdict_edit = |mutate: &dyn Fn(&mut Value)| -> Value {
        let doc = verdict_for(&receipt, &judge_a(), "pass", "urn:uuid:verdict-1", false);
        let mut subject = doc.get("credentialSubject").unwrap().clone();
        mutate(&mut subject);
        let mut out = doc.clone();
        out.set("credentialSubject", subject);
        awr::issue::resign(&out, &judge_a()).expect("resign")
    };
    add(
        "AWR-VDCT-001",
        "verifiedWork without digestSRI",
        verify(
            &input(&verdict_edit(&|s| {
                s.set("verifiedWork", parse(br#"{"id":"urn:uuid:receipt-1"}"#).unwrap());
            })),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-VDCT-002",
        "score outside [0,1]",
        verify(&input(&verdict_edit(&|s| s.set("score", Value::string("1.5")))), &[], &opts()),
    );
    add(
        "AWR-VDCT-003",
        "method missing",
        verify(&input(&verdict_edit(&|s| { s.remove("method"); })), &[], &opts()),
    );
    add(
        "AWR-VDCT-004",
        "verdict outside the enumeration",
        verify(&input(&verdict_edit(&|s| s.set("verdict", Value::string("maybe")))), &[], &opts()),
    );
    {
        // Same receipt id, different bytes: the verdict cannot be re-pointed.
        let mut other = base_receipt();
        let mut s = other.get("credentialSubject").unwrap().clone();
        s.set("nonce", Value::string("01J9Z8QK4T7YB2N5V6W8XA3C0E"));
        other.set("credentialSubject", s);
        let other = awr::issue::resign(&other, &hub()).expect("resign");
        let v = verdict_for(&receipt, &judge_a(), "pass", "urn:uuid:verdict-1", false);
        add(
            "AWR-VDCT-005",
            "supplied receipt has a different digest",
            verify(&input(&v), &[input(&other)], &opts()),
        );
    }
    add(
        "AWR-VDCT-006",
        "pass below threshold",
        verify(&input(&verdict_edit(&|s| s.set("score", Value::string("0.10")))), &[], &opts()),
    );
    add(
        "AWR-VDCT-007",
        "evidence entry without digestSRI",
        verify(
            &input(&verdict_edit(&|s| {
                s.set("evidence", Value::Array(vec![parse(br#"{"kind":"trace"}"#).unwrap()]));
            })),
            &[],
            &opts(),
        ),
    );

    // ---- blame ------------------------------------------------------------
    let blame = |chain_doc: &Value, blamed: &Value, class: &str, confidence: &str| -> Value {
        let subject = parse(
            format!(
                r#"{{"chain":{{"id":"{}","digestSRI":"{}"}},
                     "blamedWork":{{"id":"{}","digestSRI":"{}"}},
                     "failureClass":"{}","confidence":"{}",
                     "method":{{"id":"urn:example:method:hop-bisect-v1"}}}}"#,
                chain_doc.get("id").unwrap().as_str().unwrap(),
                sri_of_digest(&digest_of(chain_doc)),
                blamed.get("id").unwrap().as_str().unwrap(),
                sri_of_digest(&digest_of(blamed)),
                class,
                confidence
            )
            .as_bytes(),
        )
        .expect("blame subject");
        issue(&subject, &judge_a(), "BlameAttestation", "urn:uuid:blame-1")
    };
    {
        // An unrelated receipt is blamed: with both receipts available and the
        // chain fully resolved, §3.5 requires AWR-BLAME-001.
        let unrelated = issue(
            &receipt_subject(r#","nonce":"unrelated""#),
            &judge_b(),
            "WorkReceipt",
            "urn:uuid:unrelated",
        );
        let b = blame(&receipt, &unrelated, "wrong-output", "0.90");
        add(
            "AWR-BLAME-001",
            "blamedWork unreachable from chain",
            verify(&input(&b), &[input(&receipt), input(&unrelated)], &opts()),
        );
    }
    add(
        "AWR-BLAME-002",
        "failureClass outside the enumeration",
        verify(&input(&blame(&receipt, &receipt, "cosmic-ray", "0.90")), &[], &opts()),
    );
    {
        let b = blame(&receipt, &receipt, "wrong-output", "0.90");
        let mut s = b.get("credentialSubject").unwrap().clone();
        s.remove("chain");
        let mut doc = b.clone();
        doc.set("credentialSubject", s);
        let doc = awr::issue::resign(&doc, &judge_a()).expect("resign");
        add("AWR-BLAME-003", "chain reference missing", verify(&input(&doc), &[], &opts()));
    }
    add(
        "AWR-BLAME-004",
        "confidence outside [0,1]",
        verify(&input(&blame(&receipt, &receipt, "wrong-output", "1.5")), &[], &opts()),
    );

    // ---- chain ------------------------------------------------------------
    let with_parents = |parents_json: &str| -> Value {
        let doc = issue(
            &receipt_subject(&format!(r#","parents":{}"#, parents_json)),
            &hub(),
            "WorkReceipt",
            "urn:uuid:child",
        );
        doc
    };
    add(
        "AWR-CHAIN-001",
        "parents entry without digestSRI",
        verify(&input(&with_parents(r#"[{"id":"urn:uuid:receipt-1"}]"#)), &[], &opts()),
    );
    add(
        "AWR-CHAIN-002",
        "unknown digest algorithm",
        verify(
            &input(&with_parents(r#"[{"id":"urn:uuid:receipt-1","digestSRI":"md5-AAAAAAAAAAAAAAAAAAAAAA=="}]"#)),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-CHAIN-003",
        "supplied parent digest mismatch",
        verify(
            &input(&with_parents(&format!(
                r#"[{{"id":"urn:uuid:receipt-1","digestSRI":"{}"}}]"#,
                sri_of_bytes(b"not the parent")
            ))),
            &[input(&receipt)],
            &opts(),
        ),
    );
    {
        // A cycle cannot be built through content-addressed edges, so the
        // resolution path is driven directly (see chain::tests for the same case).
        let d = sha256(b"self-referential");
        let value = parse(
            format!(
                r#"{{"id":"urn:uuid:loop","type":["VerifiableCredential","WorkReceipt"],
                      "credentialSubject":{{"parents":[{{"id":"urn:uuid:loop","digestSRI":"{}"}}]}}}}"#,
                sri_of_digest(&d)
            )
            .as_bytes(),
        )
        .unwrap();
        let node = AvailableDoc {
            canonical: canonicalize(&value).unwrap(),
            digest: d,
            id: Some("urn:uuid:loop".to_string()),
            doc_type: Some("WorkReceipt".to_string()),
            issuer_id: None,
            valid: true,
            source: "fixture".to_string(),
            value,
        };
        let mut rep = Report::default();
        chain::resolve(&node, &[node.clone()], ChainLimits::default(), &mut rep);
        add("AWR-CHAIN-004", "cycle in parents edges", rep);
    }
    {
        // Three-hop chain, depth limit 1.
        let a = base_receipt();
        let b = issue(
            &receipt_subject(&format!(
                r#","parents":[{{"id":"urn:uuid:receipt-1","digestSRI":"{}"}}]"#,
                sri_of_digest(&digest_of(&a))
            )),
            &hub(),
            "WorkReceipt",
            "urn:uuid:mid",
        );
        let c = issue(
            &receipt_subject(&format!(
                r#","parents":[{{"id":"urn:uuid:mid","digestSRI":"{}"}}]"#,
                sri_of_digest(&digest_of(&b))
            )),
            &hub(),
            "WorkReceipt",
            "urn:uuid:leaf",
        );
        let mut o = opts();
        o.limits = ChainLimits { max_depth: 1, max_nodes: 1024 };
        add(
            "AWR-CHAIN-005",
            "depth limit exceeded",
            verify(&input(&c), &[input(&a), input(&b)], &o),
        );
    }
    add(
        "AWR-CHAIN-006",
        "same parent id, conflicting digests",
        verify(
            &input(&with_parents(&format!(
                r#"[{{"id":"urn:uuid:receipt-1","digestSRI":"{}"}},{{"id":"urn:uuid:receipt-1","digestSRI":"{}"}}]"#,
                sri_of_bytes(b"one"),
                sri_of_bytes(b"two")
            ))),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-CHAIN-007",
        "parent outputDigest differs from child inputDigest",
        verify(
            &input(&{
                // the base receipt's outputDigest is sha256("out"), the child's
                // inputDigest is sha256("in")
                with_parents(&format!(
                    r#"[{{"id":"urn:uuid:receipt-1","digestSRI":"{}"}}]"#,
                    sri_of_digest(&digest_of(&receipt))
                ))
            }),
            &[input(&receipt)],
            &opts(),
        ),
    );

    // ---- bundle -----------------------------------------------------------
    let bundle = |version: &str, docs: Vec<Value>| -> Value {
        Value::object(vec![
            ("awrBundle".to_string(), Value::string(version)),
            ("documents".to_string(), Value::Array(docs)),
        ])
    };
    add(
        "AWR-BUNDLE-001",
        "unsupported bundle version",
        verify(&input(&bundle("1.0", vec![receipt.clone()])), &[], &opts()),
    );
    {
        let mut other = base_receipt();
        let mut s = other.get("credentialSubject").unwrap().clone();
        s.set("nonce", Value::string("other"));
        other.set("credentialSubject", s);
        let other = awr::issue::resign(&other, &hub()).expect("resign");
        add(
            "AWR-BUNDLE-002",
            "one id, two different documents",
            verify(&input(&bundle("2.0", vec![receipt.clone(), other])), &[], &opts()),
        );
    }
    {
        let second = issue(
            &receipt_subject(r#","nonce":"second""#),
            &hub(),
            "WorkReceipt",
            "urn:uuid:receipt-2",
        );
        add(
            "AWR-BUNDLE-003",
            "two unreferenced receipts",
            verify(&input(&bundle("2.0", vec![receipt.clone(), second])), &[], &opts()),
        );
    }

    // ---- profiles ---------------------------------------------------------
    add(
        "AWR-PROFILE-001",
        "L1 requested with no verdict",
        verify(&input(&receipt), &[], &opts_profile("L1")),
    );
    add(
        "AWR-PROFILE-002",
        "L1 requested with a self-issued verdict",
        verify(
            &input(&receipt),
            &[input(&verdict_for(&receipt, &hub(), "pass", "urn:uuid:self-verdict", false))],
            &opts_profile("L1"),
        ),
    );
    add(
        "AWR-PROFILE-003",
        "L2 requested with one verdict issuer",
        verify(
            &input(&receipt),
            &[input(&verdict_for(&receipt, &judge_a(), "pass", "urn:uuid:v1", true))],
            &opts_profile("L2"),
        ),
    );
    add(
        "AWR-PROFILE-004",
        "L2 requested with no binding",
        verify(
            &input(&receipt),
            &[
                input(&verdict_for(&receipt, &judge_a(), "pass", "urn:uuid:v1", false)),
                input(&verdict_for(&receipt, &judge_b(), "pass", "urn:uuid:v2", false)),
            ],
            &opts_profile("L2"),
        ),
    );
    add(
        "AWR-L2-001",
        "binding present, on-chain existence not checked",
        verify(
            &input(&receipt),
            &[
                input(&verdict_for(&receipt, &judge_a(), "pass", "urn:uuid:v1", true)),
                input(&verdict_for(&receipt, &judge_b(), "pass", "urn:uuid:v2", true)),
            ],
            &opts_profile("L2"),
        ),
    );

    // ---- environment, time, legacy ---------------------------------------
    add(
        "AWR-ENV-001",
        "unverified TEE attestation",
        verify(
            &input(&issue(
                &receipt_subject(r#","environment":{"teeAttestation":{"quote":"AAAA"}}"#),
                &hub(),
                "WorkReceipt",
                "urn:uuid:tee",
            )),
            &[],
            &opts(),
        ),
    );
    add(
        "AWR-TIME-001",
        "validFrom in the future",
        verify(
            &input(&receipt),
            &[],
            &Options {
                now: awr::timefmt::parse_rfc3339_utc("2025-01-01T00:00:00Z"),
                ..Default::default()
            },
        ),
    );
    add(
        "AWR-TIME-002",
        "validUntil in the past",
        verify(
            &input(&edit_and_resign("validUntil", Value::string("2026-08-01T00:00:00Z"))),
            &[],
            &Options {
                now: awr::timefmt::parse_rfc3339_utc("2026-09-01T00:00:00Z"),
                ..Default::default()
            },
        ),
    );
    {
        let sk = hub();
        let subject = receipt_subject("");
        let message = awr::legacy::legacy_canonical(&subject, awr::legacy::Dialect::B)
            .expect("the AWR/1 rendering is defined for this subject (§12.1)");
        let sig = awr::proof::sign(&sk, message.as_bytes());
        let legacy_doc = parse(
            format!(
                r#"{{"id":"urn:uuid:legacy-1","type":["VerifiableCredential","WorkReceipt"],
                      "issuer":{{"id":"{}"}},"credentialSubject":{},
                      "proof":{{"type":"Ed25519Signature2018","created":"2024-01-01T00:00:00Z",
                                "proofValue":"{}"}}}}"#,
                awr::didkey::did_from_public_key(&sk.verifying_key().to_bytes()),
                to_string_compact(&subject),
                awr::encoding::b64_encode(&sig)
            )
            .as_bytes(),
        )
        .unwrap();
        add("AWR-LEGACY-001", "AWR/1 document, dialect B", verify(&input(&legacy_doc), &[], &opts()));

        let mut tampered = legacy_doc.clone();
        let mut s = tampered.get("credentialSubject").unwrap().clone();
        s.set("outputDigest", Value::string(sri_of_bytes(b"tampered")));
        tampered.set("credentialSubject", s);
        add(
            "AWR-LEGACY-002",
            "AWR/1 document failing under both dialects",
            verify(&input(&tampered), &[], &opts()),
        );

        // §12.3: the same AWR/1 proof, on a document that also claims to be AWR/2.
        // The signature still verifies; the classification is what rejects it.
        let mut downgrade = legacy_doc.clone();
        downgrade.set("awrVersion", Value::string("2.0.0"));
        add(
            "AWR-LEGACY-003",
            "AWR/1 proof on a document claiming awrVersion 2.0.0",
            verify(&input(&downgrade), &[], &opts()),
        );

        // §12.3: support for §12 is OPTIONAL, so a caller may decline the path.
        let declining = Options {
            legacy: awr::legacy::LegacyOptions { no_legacy: true, ..Default::default() },
            ..opts()
        };
        add(
            "AWR-LEGACY-005",
            "AWR/1 document with --no-legacy",
            verify(&input(&legacy_doc), &[], &declining),
        );

        // §12.4: the key came from the document, so no issuer is attested.
        add(
            "AWR-LEGACY-004",
            "AWR/1 document whose key came from the document itself",
            verify(&input(&legacy_doc), &[], &opts()),
        );
    }

    out
}

#[test]
fn each_scenario_reports_its_intended_code() {
    for (code, label, codes) in scenarios() {
        assert!(
            codes.contains(&code.to_string()),
            "scenario `{}` was meant to report {} but reported {:?}",
            label,
            code,
            codes
        );
    }
}

#[test]
fn the_whole_reason_code_registry_is_exercised() {
    let observed: Vec<String> = scenarios().into_iter().flat_map(|(_, _, c)| c).collect();
    let missing: Vec<&str> = REGISTRY
        .iter()
        .map(|(c, _)| *c)
        .filter(|c| !observed.contains(&c.to_string()))
        .collect();
    assert!(missing.is_empty(), "no negative case produced {:?}", missing);
}

#[test]
fn a_correct_document_reports_nothing_at_all() {
    let rep = verify(&input(&base_receipt()), &[], &opts());
    assert!(rep.valid(), "{}", rep.to_json());
    assert!(rep.reasons.is_empty());
    assert!(rep.warnings.is_empty(), "{:?}", rep.warnings);
    assert_eq!(rep.profile.as_deref(), Some("L0"));
}
