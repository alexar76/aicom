//! The §17 CLI contract, driven through the real binary: payload on stdout,
//! diagnostics on stderr, and the four documented exit codes.

use awr::encoding::hex_decode;
use awr::json::{parse, to_string_compact, Value};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn bin() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_awr"))
}

/// A directory per test: the tests run in parallel and each one issues its own
/// documents, so a shared path would race.
fn tmpdir(test: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("awr-cli-{}-{}", std::process::id(), test));
    std::fs::create_dir_all(&dir).expect("temp dir");
    dir
}

fn write(dir: &Path, name: &str, contents: &str) -> PathBuf {
    let p = dir.join(name);
    std::fs::write(&p, contents).expect("write fixture");
    p
}

fn run(args: &[&str]) -> (i32, String, String) {
    let out: Output = Command::new(bin()).args(args).output().expect("run awr");
    (
        out.status.code().expect("exit code"),
        String::from_utf8(out.stdout).expect("stdout is UTF-8"),
        String::from_utf8(out.stderr).expect("stderr is UTF-8"),
    )
}

fn keyfile(dir: &Path, name: &str) -> PathBuf {
    let (code, out, err) = run(&["keygen"]);
    assert_eq!(code, 0, "keygen failed: {}", err);
    let key = parse(out.as_bytes()).expect("key file is JSON");
    assert_eq!(key.get("kty").unwrap().as_str(), Some("OKP"));
    assert!(key.get("did").unwrap().as_str().unwrap().starts_with("did:key:z6Mk"));
    write(dir, name, &out)
}

fn subject_file(dir: &Path) -> PathBuf {
    write(
        dir,
        "subject.json",
        &format!(
            r#"{{"work":{{"modelId":"claude-sonnet-5@anthropic",
                 "capability":"urn:example:capability:summarise",
                 "startedAt":"2026-07-31T10:15:28Z","completedAt":"2026-07-31T10:15:30Z",
                 "latencyMs":2340,"status":"succeeded"}},
              "inputDigest":"{}","outputDigest":"{}",
              "nonce":"01J9Z8QK4T7YB2N5V6W8XA3C0D",
              "price":{{"currency":"USD","amount":"0.15"}}}}"#,
            awr::sri::sri_of_bytes(b"the input payload"),
            awr::sri::sri_of_bytes(b"the output payload")
        ),
    )
}

fn issue_receipt(dir: &Path) -> (PathBuf, String) {
    let key = keyfile(dir, "key.json");
    let subject = subject_file(dir);
    let (code, out, err) = run(&[
        "issue",
        subject.to_str().unwrap(),
        "--key",
        key.to_str().unwrap(),
        "--now",
        "2026-07-31T10:15:30Z",
        "--issuer-name",
        "example-hub",
    ]);
    assert_eq!(code, 0, "issue failed: {}", err);
    let text = out.trim_end_matches('\n').to_string();
    let path = write(dir, "receipt.awr.json", &text);
    (path, text)
}

#[test]
fn canonicalize_sorts_and_emits_no_trailing_newline() {
    let d = tmpdir("canon");
    let f = write(&d, "canon.json", " { \"b\" : 1 , \"a\" : [ 2 , 3 ] } ");
    let (code, out, err) = run(&["canonicalize", f.to_str().unwrap()]);
    assert_eq!(code, 0, "{}", err);
    assert_eq!(out, r#"{"a":[2,3],"b":1}"#);
    assert!(!out.ends_with('\n'), "§17 forbids a trailing newline");
    assert!(err.is_empty(), "stderr must stay empty on success: {}", err);
}

#[test]
fn canonicalize_rejects_the_negative_cases_with_a_reason_code() {
    let d = tmpdir("canon-neg");
    for (name, body, code_expected) in [
        ("neg1.json", "{\"a\":1.5}", "AWR-CANON-001"),
        ("neg2.json", "{\"a\":9007199254740992}", "AWR-CANON-002"),
        ("neg3.json", "{\"a\":\"\\ud800\"}", "AWR-CANON-003"),
        ("neg4.json", "{\"a\":1,\"a\":2}", "AWR-CANON-004"),
        ("neg5.json", "{\"a\":}", "AWR-CANON-005"),
    ] {
        let f = write(&d, name, body);
        let (code, out, err) = run(&["canonicalize", f.to_str().unwrap()]);
        assert_eq!(code, 1, "{} should exit 1", name);
        assert!(out.is_empty(), "nothing may be written to stdout on failure");
        assert!(err.contains(code_expected), "{} reported {}", name, err);
    }
}

#[test]
fn digest_is_the_sri_of_the_canonical_bytes() {
    let d = tmpdir("digest");
    let f = write(&d, "dig.json", r#"{"b":1,"a":"x"}"#);
    let (_, canonical, _) = run(&["canonicalize", f.to_str().unwrap()]);
    let (code, out, err) = run(&["digest", f.to_str().unwrap()]);
    assert_eq!(code, 0, "{}", err);
    assert_eq!(out.trim_end(), awr::sri::sri_of_bytes(canonical.as_bytes()));
    assert!(out.trim_end().starts_with("sha256-"));
}

#[test]
fn hashdata_prints_three_hex_lines_in_the_documented_order() {
    let d = tmpdir("hashdata");
    let (receipt, _) = issue_receipt(&d);
    let (code, out, err) = run(&["hashdata", receipt.to_str().unwrap()]);
    assert_eq!(code, 0, "{}", err);
    let lines: Vec<&str> = out.trim_end().split('\n').collect();
    assert_eq!(lines.len(), 3, "expected three lines, got {:?}", lines);
    let config = hex_decode(lines[0]).expect("hex");
    let document = hex_decode(lines[1]).expect("hex");
    let hash_data = hex_decode(lines[2]).expect("hex");
    assert_eq!(config.len(), 32);
    assert_eq!(document.len(), 32);
    assert_eq!(hash_data.len(), 64);
    // §6.2 step 6: proof config hash FIRST.
    assert_eq!(&hash_data[..32], &config[..]);
    assert_eq!(&hash_data[32..], &document[..]);
    assert_ne!(config, document);
}

#[test]
fn issue_then_verify_round_trip() {
    let d = tmpdir("roundtrip");
    let (receipt, text) = issue_receipt(&d);
    // The issued document is already in canonical form.
    let (_, canonical, _) = run(&["canonicalize", receipt.to_str().unwrap()]);
    assert_eq!(canonical, text, "issue emits the canonical bytes it signed");

    let (code, out, err) = run(&["verify", receipt.to_str().unwrap(), "--now", "2026-07-31T10:20:00Z"]);
    assert_eq!(code, 0, "verify failed: {} {}", out, err);
    assert!(err.is_empty(), "stderr must stay empty: {}", err);
    let result = parse(out.as_bytes()).expect("result is JSON");
    assert_eq!(result.get("valid"), Some(&Value::Bool(true)));
    assert_eq!(result.get("documentType").unwrap().as_str(), Some("WorkReceipt"));
    assert_eq!(result.get("awrVersion").unwrap().as_str(), Some("2.0.0"));
    assert_eq!(result.get("profile").unwrap().as_str(), Some("L0"));
    assert_eq!(result.get("reasons").unwrap().as_array().unwrap().len(), 0);
    assert_eq!(result.get("warnings").unwrap().as_array().unwrap().len(), 0);
    assert_eq!(result.get("chain").unwrap().get("resolved").unwrap().as_i64(), Some(0));
    assert_eq!(result.get("chain").unwrap().get("unresolved").unwrap().as_i64(), Some(0));
}

#[test]
fn verify_of_a_tampered_document_exits_1_with_a_result() {
    let d = tmpdir("tampered");
    let (receipt, text) = issue_receipt(&d);
    let mut doc = parse(text.as_bytes()).unwrap();
    let mut subject = doc.get("credentialSubject").unwrap().clone();
    subject.set("outputDigest", Value::string(awr::sri::sri_of_bytes(b"substituted")));
    doc.set("credentialSubject", subject);
    let tampered = write(&d, "tampered.awr.json", &to_string_compact(&doc));
    let _ = receipt;

    let (code, out, _) = run(&["verify", tampered.to_str().unwrap(), "--now", "2026-07-31T10:20:00Z"]);
    assert_eq!(code, 1, "an invalid document exits 1, with a result: {}", out);
    let result = parse(out.as_bytes()).expect("result is JSON even when invalid");
    assert_eq!(result.get("valid"), Some(&Value::Bool(false)));
    let codes: Vec<String> = result
        .get("reasons")
        .unwrap()
        .as_array()
        .unwrap()
        .iter()
        .map(|r| r.get("code").unwrap().as_str().unwrap().to_string())
        .collect();
    assert!(codes.contains(&"AWR-PROOF-006".to_string()), "{:?}", codes);
}

#[test]
fn verify_with_profile_and_parents() {
    let d = tmpdir("profiles");
    let (receipt, receipt_text) = issue_receipt(&d);
    // A second key issues the verdict.
    let (_, judge_text, _) = run(&["keygen"]);
    let judge = write(&d, "judge.json", &judge_text);

    let (_, digest, _) = run(&["digest", receipt.to_str().unwrap()]);
    let receipt_doc = parse(receipt_text.as_bytes()).unwrap();
    let verdict_subject = write(
        &d,
        "verdict-subject.json",
        &format!(
            r#"{{"verifiedWork":{{"id":"{}","digestSRI":"{}"}},"verdict":"pass","score":"0.93",
                 "method":{{"id":"urn:example:method:grounded-council-v1"}},
                 "policy":{{"threshold":"0.80"}}}}"#,
            receipt_doc.get("id").unwrap().as_str().unwrap(),
            digest.trim_end()
        ),
    );
    let (code, verdict_out, err) = run(&[
        "issue",
        verdict_subject.to_str().unwrap(),
        "--key",
        judge.to_str().unwrap(),
        "--type",
        "VerificationVerdict",
        "--now",
        "2026-07-31T10:16:00Z",
    ]);
    assert_eq!(code, 0, "{}", err);
    let verdict = write(&d, "verdict.awr.json", verdict_out.trim_end());

    // L1 with an independent verdict supplied via --parents.
    let (code, out, _) = run(&[
        "verify",
        receipt.to_str().unwrap(),
        "--profile",
        "L1",
        "--parents",
        verdict.to_str().unwrap(),
        "--now",
        "2026-07-31T10:20:00Z",
    ]);
    assert_eq!(code, 0, "{}", out);
    let result = parse(out.as_bytes()).unwrap();
    assert_eq!(result.get("profile").unwrap().as_str(), Some("L1"));

    // L1 without it: AWR-PROFILE-001 and exit 1.
    let (code, out, _) =
        run(&["verify", receipt.to_str().unwrap(), "--profile", "L1", "--now", "2026-07-31T10:20:00Z"]);
    assert_eq!(code, 1);
    assert!(out.contains("AWR-PROFILE-001"), "{}", out);

    // L2 with only one verdict issuer.
    let (code, out, _) = run(&[
        "verify",
        receipt.to_str().unwrap(),
        "--profile",
        "L2",
        "--parents",
        verdict.to_str().unwrap(),
        "--now",
        "2026-07-31T10:20:00Z",
    ]);
    assert_eq!(code, 1);
    assert!(out.contains("AWR-PROFILE-003"), "{}", out);
}

#[test]
fn usage_and_io_errors_exit_2() {
    let (code, _, err) = run(&["verify"]);
    assert_eq!(code, 2);
    assert!(!err.is_empty());

    let (code, _, err) = run(&["verify", "/nonexistent/path.json"]);
    assert_eq!(code, 2, "{}", err);

    let (code, _, _) = run(&["verify", "x.json", "--profile", "L9"]);
    assert_eq!(code, 2);

    let (code, _, _) = run(&["issue", "x.json"]);
    assert_eq!(code, 2, "issue without --key is a usage error");

    let (code, _, _) = run(&[]);
    assert_eq!(code, 2, "no subcommand is a usage error");
}

#[test]
fn an_unimplemented_subcommand_exits_3() {
    let (code, out, err) = run(&["frobnicate", "x.json"]);
    assert_eq!(code, 3);
    assert!(out.is_empty(), "nothing on stdout for an unknown subcommand");
    assert!(err.contains("unimplemented"), "{}", err);
}

#[test]
fn verify_of_a_bundle_selects_the_subject() {
    let d = tmpdir("bundle");
    let (_, receipt_text) = issue_receipt(&d);
    let receipt = parse(receipt_text.as_bytes()).unwrap();
    let bundle = Value::object(vec![
        ("awrBundle".to_string(), Value::string("2.0")),
        ("documents".to_string(), Value::Array(vec![receipt])),
    ]);
    let f = write(&d, "bundle.awrb.json", &to_string_compact(&bundle));
    let (code, out, err) = run(&["verify", f.to_str().unwrap(), "--now", "2026-07-31T10:20:00Z"]);
    assert_eq!(code, 0, "{} {}", out, err);
    let result = parse(out.as_bytes()).unwrap();
    assert_eq!(result.get("documentType").unwrap().as_str(), Some("WorkReceipt"));
}

#[test]
fn help_and_version_are_available() {
    let (code, out, _) = run(&["--help"]);
    assert_eq!(code, 0);
    assert!(out.contains("canonicalize"));
    let (code, out, _) = run(&["--version"]);
    assert_eq!(code, 0);
    assert!(out.contains("2.0.0"));
}
