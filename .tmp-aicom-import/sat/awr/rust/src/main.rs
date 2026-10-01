//! The §17 CLI contract.
//!
//! ```text
//! awr verify <file> [--profile L0|L1|L2] [--parents <file>…] [--now <rfc3339>]
//!                   [--subject <id>] [--skew <seconds>] [--max-depth N] [--max-nodes N]
//! awr canonicalize <file>
//! awr digest <file>
//! awr hashdata <file>
//! awr issue <subject-file> --key <file> [--type <type>] [--id <uri>] [--now <rfc3339>]
//!                          [--issuer-name <name>] [--jwk]
//! awr keygen                                (extension: writes a key file to stdout)
//! ```
//!
//! Exit codes (§17): 0 = valid / succeeded, 1 = invalid document (a result was
//! produced), 2 = usage or I/O error, 3 = unimplemented subcommand.
//! Only the specified payload goes to stdout; diagnostics go to stderr.

use awr::chain::ChainLimits;
use awr::encoding::hex_encode;
use awr::issue::{self, IssueOptions};
use awr::json::{canonicalize, parse, to_string_pretty, Value};
use awr::proof::compute_hash_data;
use awr::sri::sri_of_bytes;
use awr::timefmt::parse_rfc3339_utc;
use awr::verify::{self, Input, Options};
use std::io::Write;
use std::process::ExitCode;

const USAGE: &str = "\
awr — an independent AWR/2 implementation (SPEC.md §17 CLI contract)

USAGE:
  awr verify <file> [--profile L0|L1|L2] [--parents <file>...] [--now <rfc3339>]
                    [--subject <id>] [--skew <seconds>] [--max-depth <n>] [--max-nodes <n>]
  awr canonicalize <file>
  awr digest <file>
  awr hashdata <file>
  awr issue <subject-file> --key <file> [--type WorkReceipt|VerificationVerdict|BlameAttestation]
                    [--id <uri>] [--now <rfc3339>] [--issuer-name <name>] [--jwk] [--pretty]
  awr keygen [--out <file>]

EXIT CODES:
  0  valid / operation succeeded
  1  invalid document (a result was produced)
  2  usage or I/O error
  3  unimplemented subcommand
";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() {
        eprint!("{}", USAGE);
        return ExitCode::from(2);
    }
    let cmd = args[0].as_str();
    let rest = &args[1..];
    let code = match cmd {
        "verify" => cmd_verify(rest),
        "canonicalize" | "canonicalise" => cmd_canonicalize(rest),
        "digest" => cmd_digest(rest),
        "hashdata" => cmd_hashdata(rest),
        "issue" => cmd_issue(rest),
        "keygen" => cmd_keygen(rest),
        "-h" | "--help" | "help" => {
            print!("{}", USAGE);
            0
        }
        "--version" | "version" => {
            println!("awr {} (AWR/{} implementation)", env!("CARGO_PKG_VERSION"), awr::AWR_VERSION);
            0
        }
        other => {
            eprintln!("awr: unimplemented subcommand `{}`", other);
            eprint!("{}", USAGE);
            3
        }
    };
    ExitCode::from(code)
}

fn read_file(path: &str) -> Result<Vec<u8>, u8> {
    std::fs::read(path).map_err(|e| {
        eprintln!("awr: cannot read {}: {}", path, e);
        2u8
    })
}

fn parse_document(path: &str) -> Result<Value, u8> {
    let bytes = read_file(path)?;
    match parse(&bytes) {
        Ok(v) => Ok(v),
        Err(e) => {
            eprintln!("awr: {}: {}: {}", path, e.code, e.detail);
            // A canonicalization/parse failure is a document-level failure with a
            // reason code, so it exits 1 rather than 2 (§17: 1 = invalid document).
            Err(1)
        }
    }
}

struct Flags {
    positional: Vec<String>,
    named: Vec<(String, String)>,
    switches: Vec<String>,
}

fn take_flags(args: &[String], multi: &[&str], switch_names: &[&str]) -> Result<Flags, u8> {
    let mut f = Flags { positional: Vec::new(), named: Vec::new(), switches: Vec::new() };
    let mut i = 0;
    while i < args.len() {
        let a = &args[i];
        if let Some(name) = a.strip_prefix("--") {
            if switch_names.contains(&name) {
                f.switches.push(name.to_string());
                i += 1;
                continue;
            }
            let value = match args.get(i + 1) {
                Some(v) if !v.starts_with("--") => v.clone(),
                _ => {
                    eprintln!("awr: --{} needs a value", name);
                    return Err(2);
                }
            };
            f.named.push((name.to_string(), value));
            i += 2;
            // `--parents a b c` takes every following non-flag argument.
            if multi.contains(&name) {
                while let Some(v) = args.get(i) {
                    if v.starts_with("--") {
                        break;
                    }
                    f.named.push((name.to_string(), v.clone()));
                    i += 1;
                }
            }
        } else {
            f.positional.push(a.clone());
            i += 1;
        }
    }
    Ok(f)
}

impl Flags {
    fn one(&self, name: &str) -> Option<&str> {
        self.named.iter().find(|(k, _)| k == name).map(|(_, v)| v.as_str())
    }
    fn all(&self, name: &str) -> Vec<&str> {
        self.named.iter().filter(|(k, _)| k == name).map(|(_, v)| v.as_str()).collect()
    }
    fn has(&self, name: &str) -> bool {
        self.switches.iter().any(|s| s == name)
    }
    fn unknown(&self, known: &[&str]) -> Option<&str> {
        self.named
            .iter()
            .map(|(k, _)| k.as_str())
            .chain(self.switches.iter().map(|s| s.as_str()))
            .find(|k| !known.contains(k))
    }
}

/// 64 hex characters to 32 bytes, for `--expected-key` (§17).
fn hex32(text: &str) -> Option<[u8; 32]> {
    if text.len() != 64 {
        return None;
    }
    let bytes = text.as_bytes();
    let mut out = [0u8; 32];
    for i in 0..32 {
        let hi = (bytes[2 * i] as char).to_digit(16)?;
        let lo = (bytes[2 * i + 1] as char).to_digit(16)?;
        out[i] = (hi * 16 + lo) as u8;
    }
    Some(out)
}

fn cmd_verify(args: &[String]) -> u8 {
    let f = match take_flags(args, &["parents"], &["no-legacy"]) {
        Ok(f) => f,
        Err(c) => return c,
    };
    if let Some(u) = f.unknown(&[
        "profile", "parents", "now", "subject", "skew", "max-depth", "max-nodes",
        "expected-key", "no-legacy",
    ]) {
        eprintln!("awr: unknown option --{}", u);
        return 2;
    }
    if f.positional.len() != 1 {
        eprintln!("awr: verify takes exactly one <file>");
        return 2;
    }
    let mut opts = Options::default();
    if let Some(p) = f.one("profile") {
        if !["L0", "L1", "L2"].contains(&p) {
            eprintln!("awr: --profile must be L0, L1 or L2");
            return 2;
        }
        opts.profile = Some(p.to_string());
    }
    if let Some(n) = f.one("now") {
        match parse_rfc3339_utc(n) {
            Some(t) => opts.now = Some(t),
            None => {
                eprintln!("awr: --now must be an RFC 3339 UTC date-time with a Z offset");
                return 2;
            }
        }
    }
    if let Some(s) = f.one("skew") {
        match s.parse::<i64>() {
            Ok(v) if v >= 0 => opts.skew_secs = v,
            _ => {
                eprintln!("awr: --skew must be a non-negative integer number of seconds");
                return 2;
            }
        }
    }
    let mut limits = ChainLimits::default();
    for (name, target) in [("max-depth", 0), ("max-nodes", 1)] {
        if let Some(s) = f.one(name) {
            match s.parse::<usize>() {
                Ok(v) if v > 0 => {
                    if target == 0 {
                        limits.max_depth = v;
                    } else {
                        limits.max_nodes = v;
                    }
                }
                _ => {
                    eprintln!("awr: --{} must be a positive integer", name);
                    return 2;
                }
            }
        }
    }
    opts.limits = limits;
    opts.subject_id = f.one("subject").map(String::from);

    // §12.4: an AWR/1 signature checked against a key the document itself carries
    // attests no identity, so every §12 verifier must let the caller name the key
    // out of band. §17 spells it --expected-key: a did:key or 64 hex characters.
    if let Some(k) = f.one("expected-key") {
        let trimmed = k.trim();
        let parsed = if let Some(rest) = trimmed.strip_prefix("did:key:") {
            let bare = format!("did:key:{}", rest.split('#').next().unwrap_or(rest));
            awr::didkey::parse_did_key(&bare).ok()
        } else {
            hex32(trimmed)
        };
        match parsed {
            Some(pk) => opts.legacy.expected_key = Some(pk),
            None => {
                eprintln!("awr: --expected-key must be a did:key or 64 hex characters");
                return 2;
            }
        }
    }
    opts.legacy.no_legacy = f.has("no-legacy");

    let main_path = &f.positional[0];
    let main_bytes = match read_file(main_path) {
        Ok(b) => b,
        Err(c) => return c,
    };
    let mut aux: Vec<Input> = Vec::new();
    for p in f.all("parents") {
        match read_file(p) {
            Ok(b) => aux.push(Input { bytes: b, source: p.to_string() }),
            Err(c) => return c,
        }
    }
    let report = verify::verify(
        &Input { bytes: main_bytes, source: main_path.clone() },
        &aux,
        &opts,
    );
    println!("{}", report.to_json());
    if report.valid() {
        0
    } else {
        1
    }
}

fn cmd_canonicalize(args: &[String]) -> u8 {
    if args.len() != 1 || args[0].starts_with("--") {
        eprintln!("awr: canonicalize takes exactly one <file>");
        return 2;
    }
    let value = match parse_document(&args[0]) {
        Ok(v) => v,
        Err(c) => return c,
    };
    match canonicalize(&value) {
        Ok(s) => {
            // §17: no trailing newline.
            let mut out = std::io::stdout();
            if out.write_all(s.as_bytes()).and_then(|_| out.flush()).is_err() {
                return 2;
            }
            0
        }
        Err(e) => {
            eprintln!("awr: {}: {}: {}", args[0], e.code, e.detail);
            1
        }
    }
}

fn cmd_digest(args: &[String]) -> u8 {
    if args.len() != 1 || args[0].starts_with("--") {
        eprintln!("awr: digest takes exactly one <file>");
        return 2;
    }
    let value = match parse_document(&args[0]) {
        Ok(v) => v,
        Err(c) => return c,
    };
    match canonicalize(&value) {
        Ok(s) => {
            println!("{}", sri_of_bytes(s.as_bytes()));
            0
        }
        Err(e) => {
            eprintln!("awr: {}: {}: {}", args[0], e.code, e.detail);
            1
        }
    }
}

fn cmd_hashdata(args: &[String]) -> u8 {
    if args.len() != 1 || args[0].starts_with("--") {
        eprintln!("awr: hashdata takes exactly one <file>");
        return 2;
    }
    let value = match parse_document(&args[0]) {
        Ok(v) => v,
        Err(c) => return c,
    };
    let proof = match value.get("proof") {
        Some(Value::Array(items)) => match items.first() {
            Some(p) => p.clone(),
            None => {
                eprintln!("awr: AWR-PROOF-001: proof is an empty array");
                return 1;
            }
        },
        Some(p) => p.clone(),
        None => {
            eprintln!("awr: AWR-PROOF-001: proof missing, so there are no proof options to hash");
            return 1;
        }
    };
    match compute_hash_data(&value, &proof) {
        Ok(hd) => {
            println!("{}", hex_encode(&hd.proof_config_hash));
            println!("{}", hex_encode(&hd.transformed_document_hash));
            println!("{}", hex_encode(&hd.hash_data));
            0
        }
        Err(e) => {
            eprintln!("awr: {}: {}: {}", args[0], e.code, e.detail);
            1
        }
    }
}

fn cmd_issue(args: &[String]) -> u8 {
    let f = match take_flags(args, &[], &["jwk", "pretty"]) {
        Ok(f) => f,
        Err(c) => return c,
    };
    if let Some(u) = f.unknown(&["key", "type", "id", "now", "issuer-name", "jwk", "pretty"]) {
        eprintln!("awr: unknown option --{}", u);
        return 2;
    }
    if f.positional.len() != 1 {
        eprintln!("awr: issue takes exactly one <subject-file>");
        return 2;
    }
    let key_path = match f.one("key") {
        Some(k) => k,
        None => {
            eprintln!("awr: issue requires --key <file>");
            return 2;
        }
    };
    let key_text = match read_file(key_path) {
        Ok(b) => match String::from_utf8(b) {
            Ok(s) => s,
            Err(_) => {
                eprintln!("awr: key file {} is not UTF-8 text", key_path);
                return 2;
            }
        },
        Err(c) => return c,
    };
    let sk = match issue::read_key(&key_text) {
        Ok(k) => k,
        Err(e) => {
            eprintln!("awr: cannot read key {}: {}", key_path, e);
            return 2;
        }
    };
    let input = match parse_document(&f.positional[0]) {
        Ok(v) => v,
        Err(c) => return c,
    };
    let opts = IssueOptions {
        doc_type: f.one("type").unwrap_or("WorkReceipt").to_string(),
        id: f.one("id").map(String::from),
        now: f.one("now").map(String::from),
        issuer_name: f.one("issuer-name").map(String::from),
        include_jwk: f.has("jwk"),
    };
    // IMPLEMENTATION CHOICE (§17): a file that already carries
    // `credentialSubject` is treated as a whole unsecured document to be
    // completed and signed; anything else is treated as the `credentialSubject`
    // itself. §17 names the argument `<subject-file>` but issuers routinely have
    // a full envelope in hand, and guessing wrong is loud rather than silent.
    let result = if input.get("credentialSubject").is_some() {
        issue::issue_template(&input, &sk, &opts)
    } else {
        issue::issue(&input, &sk, &opts)
    };
    match result {
        Ok(doc) => {
            if f.has("pretty") {
                println!("{}", to_string_pretty(&doc));
            } else {
                // The canonical form is emitted, so that `issue | digest` and
                // `issue | verify` see exactly the bytes that were signed.
                match canonicalize(&doc) {
                    Ok(s) => println!("{}", s),
                    Err(e) => {
                        eprintln!("awr: {}: {}", e.code, e.detail);
                        return 1;
                    }
                }
            }
            0
        }
        Err(e) => {
            eprintln!("awr: cannot issue: {}", e);
            2
        }
    }
}

fn cmd_keygen(args: &[String]) -> u8 {
    let f = match take_flags(args, &[], &[]) {
        Ok(f) => f,
        Err(c) => return c,
    };
    if let Some(u) = f.unknown(&["out"]) {
        eprintln!("awr: unknown option --{}", u);
        return 2;
    }
    let sk = match issue::generate_key() {
        Ok(k) => k,
        Err(e) => {
            eprintln!("awr: cannot generate a key: {}", e);
            return 2;
        }
    };
    let text = to_string_pretty(&issue::key_file_value(&sk));
    match f.one("out") {
        Some(path) => {
            if let Err(e) = std::fs::write(path, format!("{}\n", text)) {
                eprintln!("awr: cannot write {}: {}", path, e);
                return 2;
            }
            eprintln!("awr: wrote a new Ed25519 key to {}", path);
            0
        }
        None => {
            println!("{}", text);
            0
        }
    }
}
