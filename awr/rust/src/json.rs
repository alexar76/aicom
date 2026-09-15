//! JSON value model, strict parser, and RFC 8785 (JCS) canonicalizer.
//!
//! Written from SPEC.md §4 alone. A purpose-built value model is used instead of a
//! generic JSON library because AWR/2 requires three properties a generic
//! `Value` cannot express at once (SPEC §3.1, §4.1, §4.2):
//!
//! * duplicate object property names must be **detected**, not resolved
//!   (`AWR-CANON-004`) — the parser must not silently keep the last occurrence;
//! * the lexical integer/non-integer distinction must survive parsing, so that
//!   `AWR-CANON-001` and `AWR-CANON-002` can be reported;
//! * member order and unknown members must be preserved exactly, because a
//!   verifier canonicalizes the document *as received* (§4.2) and must not strip
//!   unknown fields (§3.1).

use std::cmp::Ordering;
use std::fmt::Write as _;

/// Largest magnitude a JSON number may have inside a signed AWR document (§4.3).
pub const MAX_SAFE_INT: i64 = 9_007_199_254_740_991; // 2^53 - 1

/// Nesting limit applied before canonicalization.
///
/// IMPLEMENTATION CHOICE (§13.4 says implementations SHOULD "reject documents
/// with unreasonable nesting depth" and names no number): 256 levels, reported
/// as `AWR-CANON-005` since no dedicated code exists for it.
pub const MAX_DEPTH: usize = 256;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NumberKind {
    /// Lexically an integer and within ±(2^53−1): the only form a signed AWR
    /// document may contain (§4.3).
    Integer(i64),
    /// Lexically non-integer: it has a fraction or an exponent part.
    /// `AWR-CANON-001`.
    NonInteger,
    /// Lexically an integer but outside ±(2^53−1). `AWR-CANON-002`.
    OutOfRange,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Value {
    Null,
    Bool(bool),
    /// `raw` is the exact lexical form as it appeared in the input. It is kept
    /// because the AWR/1 legacy dialects (§12) render numbers from their lexical
    /// form, and because diagnostics quote it.
    Number { raw: String, kind: NumberKind },
    Str(String),
    Array(Vec<Value>),
    /// Object members in **input order**, with duplicate names already rejected
    /// by the parser.
    Object(Vec<(String, Value)>),
}

/// A canonicalization/parsing failure carrying the SPEC §11.2 reason code.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct JsonError {
    pub code: &'static str,
    pub detail: String,
}

impl JsonError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        JsonError { code, detail: detail.into() }
    }
}

impl std::fmt::Display for JsonError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.detail)
    }
}

impl Value {
    pub fn int(v: i64) -> Value {
        Value::Number { raw: v.to_string(), kind: NumberKind::Integer(v) }
    }
    pub fn string(v: impl Into<String>) -> Value {
        Value::Str(v.into())
    }
    pub fn object(pairs: Vec<(String, Value)>) -> Value {
        Value::Object(pairs)
    }

    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Object(m) => m.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }
    pub fn as_object(&self) -> Option<&Vec<(String, Value)>> {
        match self {
            Value::Object(m) => Some(m),
            _ => None,
        }
    }
    pub fn as_array(&self) -> Option<&Vec<Value>> {
        match self {
            Value::Array(a) => Some(a),
            _ => None,
        }
    }
    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::Str(s) => Some(s.as_str()),
            _ => None,
        }
    }
    pub fn as_i64(&self) -> Option<i64> {
        match self {
            Value::Number { kind: NumberKind::Integer(i), .. } => Some(*i),
            _ => None,
        }
    }
    pub fn is_object(&self) -> bool {
        matches!(self, Value::Object(_))
    }
    pub fn is_null(&self) -> bool {
        matches!(self, Value::Null)
    }

    /// Non-empty string convenience: `Some(s)` only when the member is a string
    /// with at least one character.
    pub fn get_nonempty_str(&self, key: &str) -> Option<&str> {
        match self.get(key).and_then(|v| v.as_str()) {
            Some(s) if !s.is_empty() => Some(s),
            _ => None,
        }
    }

    /// Insert or replace a member, preserving the position of an existing one.
    pub fn set(&mut self, key: &str, value: Value) {
        if let Value::Object(m) = self {
            for (k, v) in m.iter_mut() {
                if k == key {
                    *v = value;
                    return;
                }
            }
            m.push((key.to_string(), value));
        }
    }

    /// Remove a member and return it.
    pub fn remove(&mut self, key: &str) -> Option<Value> {
        if let Value::Object(m) = self {
            if let Some(pos) = m.iter().position(|(k, _)| k == key) {
                return Some(m.remove(pos).1);
            }
        }
        None
    }

    pub fn type_name(&self) -> &'static str {
        match self {
            Value::Null => "null",
            Value::Bool(_) => "boolean",
            Value::Number { .. } => "number",
            Value::Str(_) => "string",
            Value::Array(_) => "array",
            Value::Object(_) => "object",
        }
    }
}

// ---------------------------------------------------------------------------
// Parser
// ---------------------------------------------------------------------------

/// Parse JSON bytes strictly.
///
/// Deviations from a permissive parser, all required by §4.1:
/// * duplicate object property names are an error (`AWR-CANON-004`);
/// * `\uD800`-style lone surrogates are an error (`AWR-CANON-003`), never
///   replaced with U+FFFD;
/// * IMPLEMENTATION CHOICE (§4.1(4) covers "lone surrogates and other data that
///   cannot be represented as valid Unicode" without saying where the boundary
///   with malformed JSON lies): bytes inside a string that are not valid UTF-8
///   are `AWR-CANON-003`, while malformed bytes anywhere else are
///   `AWR-CANON-005`;
/// * numbers keep their lexical class so §4.3 can be enforced later.
pub fn parse(bytes: &[u8]) -> Result<Value, JsonError> {
    let mut p = Parser { b: bytes, i: 0, depth: 0 };
    p.ws();
    let v = p.value()?;
    p.ws();
    if p.i != p.b.len() {
        return Err(JsonError::new(
            "AWR-CANON-005",
            format!("trailing content after top-level JSON value at byte offset {}", p.i),
        ));
    }
    Ok(v)
}

struct Parser<'a> {
    b: &'a [u8],
    i: usize,
    depth: usize,
}

impl<'a> Parser<'a> {
    fn ws(&mut self) {
        while self.i < self.b.len() {
            match self.b[self.i] {
                b' ' | b'\t' | b'\n' | b'\r' => self.i += 1,
                _ => break,
            }
        }
    }

    fn err<T>(&self, detail: impl Into<String>) -> Result<T, JsonError> {
        let d: String = detail.into();
        Err(JsonError::new("AWR-CANON-005", format!("{} at byte offset {}", d, self.i)))
    }

    fn peek(&self) -> Option<u8> {
        self.b.get(self.i).copied()
    }

    fn lit(&mut self, s: &str, v: Value) -> Result<Value, JsonError> {
        if self.b[self.i..].starts_with(s.as_bytes()) {
            self.i += s.len();
            Ok(v)
        } else {
            self.err(format!("expected literal `{}`", s))
        }
    }

    fn value(&mut self) -> Result<Value, JsonError> {
        match self.peek() {
            None => self.err("unexpected end of input"),
            Some(b'{') => self.object(),
            Some(b'[') => self.array(),
            Some(b'"') => Ok(Value::Str(self.string()?)),
            Some(b't') => self.lit("true", Value::Bool(true)),
            Some(b'f') => self.lit("false", Value::Bool(false)),
            Some(b'n') => self.lit("null", Value::Null),
            Some(c) if c == b'-' || c.is_ascii_digit() => self.number(),
            Some(c) => self.err(format!("unexpected byte 0x{:02x}", c)),
        }
    }

    fn enter(&mut self) -> Result<(), JsonError> {
        self.depth += 1;
        if self.depth > MAX_DEPTH {
            return Err(JsonError::new(
                "AWR-CANON-005",
                format!("nesting deeper than the {}-level limit (§13.4)", MAX_DEPTH),
            ));
        }
        Ok(())
    }

    fn object(&mut self) -> Result<Value, JsonError> {
        self.enter()?;
        self.i += 1; // '{'
        let mut members: Vec<(String, Value)> = Vec::new();
        self.ws();
        if self.peek() == Some(b'}') {
            self.i += 1;
            self.depth -= 1;
            return Ok(Value::Object(members));
        }
        loop {
            self.ws();
            if self.peek() != Some(b'"') {
                return self.err("expected a `\"`-quoted property name");
            }
            let key = self.string()?;
            if members.iter().any(|(k, _)| *k == key) {
                // §4.1(5): the parser's choice must not decide which bytes were signed.
                return Err(JsonError::new(
                    "AWR-CANON-004",
                    format!("duplicate object property name {:?}", key),
                ));
            }
            self.ws();
            if self.peek() != Some(b':') {
                return self.err("expected `:` after property name");
            }
            self.i += 1;
            self.ws();
            let v = self.value()?;
            members.push((key, v));
            self.ws();
            match self.peek() {
                Some(b',') => {
                    self.i += 1;
                }
                Some(b'}') => {
                    self.i += 1;
                    self.depth -= 1;
                    return Ok(Value::Object(members));
                }
                _ => return self.err("expected `,` or `}` in object"),
            }
        }
    }

    fn array(&mut self) -> Result<Value, JsonError> {
        self.enter()?;
        self.i += 1; // '['
        let mut items = Vec::new();
        self.ws();
        if self.peek() == Some(b']') {
            self.i += 1;
            self.depth -= 1;
            return Ok(Value::Array(items));
        }
        loop {
            self.ws();
            items.push(self.value()?);
            self.ws();
            match self.peek() {
                Some(b',') => {
                    self.i += 1;
                }
                Some(b']') => {
                    self.i += 1;
                    self.depth -= 1;
                    return Ok(Value::Array(items));
                }
                _ => return self.err("expected `,` or `]` in array"),
            }
        }
    }

    fn hex4(&mut self) -> Result<u16, JsonError> {
        if self.i + 4 > self.b.len() {
            return self.err("truncated \\u escape");
        }
        let mut v: u16 = 0;
        for k in 0..4 {
            let c = self.b[self.i + k];
            let d = match c {
                b'0'..=b'9' => c - b'0',
                b'a'..=b'f' => c - b'a' + 10,
                b'A'..=b'F' => c - b'A' + 10,
                _ => return self.err("non-hex digit in \\u escape"),
            };
            v = (v << 4) | d as u16;
        }
        self.i += 4;
        Ok(v)
    }

    fn string(&mut self) -> Result<String, JsonError> {
        self.i += 1; // opening quote
        let mut out: Vec<u8> = Vec::new();
        loop {
            let c = match self.peek() {
                None => return self.err("unterminated string"),
                Some(c) => c,
            };
            match c {
                b'"' => {
                    self.i += 1;
                    // §4.1(4): string data that is not valid Unicode terminates
                    // the implementation with an error rather than being repaired.
                    return String::from_utf8(out).map_err(|_| {
                        JsonError::new(
                            "AWR-CANON-003",
                            "string contains bytes that are not valid UTF-8".to_string(),
                        )
                    });
                }
                b'\\' => {
                    self.i += 1;
                    let e = match self.peek() {
                        None => return self.err("unterminated escape"),
                        Some(e) => e,
                    };
                    self.i += 1;
                    match e {
                        b'"' => out.push(b'"'),
                        b'\\' => out.push(b'\\'),
                        b'/' => out.push(b'/'),
                        b'b' => out.push(0x08),
                        b'f' => out.push(0x0c),
                        b'n' => out.push(b'\n'),
                        b'r' => out.push(b'\r'),
                        b't' => out.push(b'\t'),
                        b'u' => {
                            let hi = self.hex4()?;
                            let cp: u32 = if (0xD800..=0xDBFF).contains(&hi) {
                                // High surrogate: a low surrogate must follow.
                                if self.peek() != Some(b'\\')
                                    || self.b.get(self.i + 1).copied() != Some(b'u')
                                {
                                    return Err(JsonError::new(
                                        "AWR-CANON-003",
                                        format!(
                                            "lone high surrogate \\u{:04x} in string data",
                                            hi
                                        ),
                                    ));
                                }
                                self.i += 2;
                                let lo = self.hex4()?;
                                if !(0xDC00..=0xDFFF).contains(&lo) {
                                    return Err(JsonError::new(
                                        "AWR-CANON-003",
                                        format!(
                                            "high surrogate \\u{:04x} followed by \\u{:04x}, which is not a low surrogate",
                                            hi, lo
                                        ),
                                    ));
                                }
                                0x10000
                                    + (((hi as u32) - 0xD800) << 10)
                                    + ((lo as u32) - 0xDC00)
                            } else if (0xDC00..=0xDFFF).contains(&hi) {
                                return Err(JsonError::new(
                                    "AWR-CANON-003",
                                    format!("lone low surrogate \\u{:04x} in string data", hi),
                                ));
                            } else {
                                hi as u32
                            };
                            let ch = char::from_u32(cp).ok_or_else(|| {
                                JsonError::new(
                                    "AWR-CANON-003",
                                    format!("escape does not denote a Unicode scalar value: U+{:04X}", cp),
                                )
                            })?;
                            let mut buf = [0u8; 4];
                            out.extend_from_slice(ch.encode_utf8(&mut buf).as_bytes());
                        }
                        _ => return self.err(format!("invalid escape `\\{}`", e as char)),
                    }
                }
                0x00..=0x1f => {
                    return self.err(format!("unescaped control character 0x{:02x} in string", c))
                }
                _ => {
                    out.push(c);
                    self.i += 1;
                }
            }
        }
    }

    fn number(&mut self) -> Result<Value, JsonError> {
        let start = self.i;
        if self.peek() == Some(b'-') {
            self.i += 1;
        }
        // int part
        match self.peek() {
            Some(b'0') => {
                self.i += 1;
                if matches!(self.peek(), Some(c) if c.is_ascii_digit()) {
                    return self.err("leading zero in number");
                }
            }
            Some(c) if c.is_ascii_digit() => {
                while matches!(self.peek(), Some(d) if d.is_ascii_digit()) {
                    self.i += 1;
                }
            }
            _ => return self.err("expected a digit in number"),
        }
        let mut non_integer = false;
        if self.peek() == Some(b'.') {
            non_integer = true;
            self.i += 1;
            if !matches!(self.peek(), Some(c) if c.is_ascii_digit()) {
                return self.err("expected a digit after `.` in number");
            }
            while matches!(self.peek(), Some(d) if d.is_ascii_digit()) {
                self.i += 1;
            }
        }
        if matches!(self.peek(), Some(b'e') | Some(b'E')) {
            non_integer = true;
            self.i += 1;
            if matches!(self.peek(), Some(b'+') | Some(b'-')) {
                self.i += 1;
            }
            if !matches!(self.peek(), Some(c) if c.is_ascii_digit()) {
                return self.err("expected a digit in number exponent");
            }
            while matches!(self.peek(), Some(d) if d.is_ascii_digit()) {
                self.i += 1;
            }
        }
        let raw = String::from_utf8(self.b[start..self.i].to_vec())
            .map_err(|_| JsonError::new("AWR-CANON-005", "non-ASCII bytes in number"))?;
        // IMPLEMENTATION CHOICE (§4.3): "integer" is read lexically. A number
        // written `1.0` or `1e2` is a *non-integer JSON number* here even though
        // its value is integral, because §4.3 exists precisely to keep an
        // issuer's int/float distinction out of the signed bytes; accepting
        // `1.0` as 1 would reintroduce the divergence the section removes.
        let kind = if non_integer {
            NumberKind::NonInteger
        } else {
            match raw.parse::<i64>() {
                Ok(v) if v.abs() <= MAX_SAFE_INT => NumberKind::Integer(v),
                _ => NumberKind::OutOfRange,
            }
        };
        Ok(Value::Number { raw, kind })
    }
}

// ---------------------------------------------------------------------------
// Canonicalization (RFC 8785 / SPEC §4)
// ---------------------------------------------------------------------------

/// Compare two property names as arrays of UTF-16 code units, as unsigned
/// integers (§4.1(1), RFC 8785 §3.2.3).
///
/// This is *not* the same as comparing Unicode code points: any name starting
/// with a character in U+E000..U+FFFF sorts after a name starting with a
/// non-BMP character, because the non-BMP character's first code unit is a high
/// surrogate (0xD800..0xDBFF).
pub fn utf16_cmp(a: &str, b: &str) -> Ordering {
    let mut ai = a.encode_utf16();
    let mut bi = b.encode_utf16();
    loop {
        match (ai.next(), bi.next()) {
            (None, None) => return Ordering::Equal,
            (None, Some(_)) => return Ordering::Less,
            (Some(_), None) => return Ordering::Greater,
            (Some(x), Some(y)) => {
                if x != y {
                    return x.cmp(&y);
                }
            }
        }
    }
}

/// Compare property names by Unicode code point. Used **only** by the AWR/1
/// legacy dialect (§12), which sorted by code point.
pub fn codepoint_cmp(a: &str, b: &str) -> Ordering {
    a.chars().cmp(b.chars())
}

/// RFC 8785 canonical form, UTF-8, no trailing newline (§4.1).
pub fn canonicalize(v: &Value) -> Result<String, JsonError> {
    let mut out = String::new();
    write_canonical(&mut out, v)?;
    Ok(out)
}

/// RFC 8785 canonical bytes.
pub fn canonical_bytes(v: &Value) -> Result<Vec<u8>, JsonError> {
    Ok(canonicalize(v)?.into_bytes())
}

fn write_canonical(out: &mut String, v: &Value) -> Result<(), JsonError> {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Number { raw, kind } => match kind {
            NumberKind::Integer(i) => {
                // -0 canonicalizes to 0: ECMAScript number-to-string, which
                // RFC 8785 §3.2.2.3 defers to, has no negative zero literal.
                let _ = write!(out, "{}", i);
            }
            NumberKind::NonInteger => {
                return Err(JsonError::new(
                    "AWR-CANON-001",
                    format!("non-integer JSON number `{}` (§4.3)", raw),
                ))
            }
            NumberKind::OutOfRange => {
                return Err(JsonError::new(
                    "AWR-CANON-002",
                    format!("integer `{}` outside ±(2^53−1) (§4.3)", raw),
                ))
            }
        },
        Value::Str(s) => write_json_string(out, s),
        Value::Array(items) => {
            out.push('[');
            for (n, item) in items.iter().enumerate() {
                if n > 0 {
                    out.push(',');
                }
                write_canonical(out, item)?;
            }
            out.push(']');
        }
        Value::Object(members) => {
            let mut refs: Vec<&(String, Value)> = members.iter().collect();
            refs.sort_by(|a, b| utf16_cmp(&a.0, &b.0));
            out.push('{');
            for (n, (k, val)) in refs.iter().map(|p| (&p.0, &p.1)).enumerate() {
                if n > 0 {
                    out.push(',');
                }
                write_json_string(out, k);
                out.push(':');
                write_canonical(out, val)?;
            }
            out.push('}');
        }
    }
    Ok(())
}

/// String serialization per RFC 8785 §3.2.2.2 (§4.1(3)): the seven two-character
/// escapes where defined, lowercase `\uXXXX` for the remaining C0 controls,
/// every other character literal. No Unicode normalization is applied anywhere
/// (§4.1(2)).
fn write_json_string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{0008}' => out.push_str("\\b"),
            '\u{0009}' => out.push_str("\\t"),
            '\u{000a}' => out.push_str("\\n"),
            '\u{000c}' => out.push_str("\\f"),
            '\u{000d}' => out.push_str("\\r"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

/// The implementation self-check behind `AWR-CANON-006`.
///
/// §11.2 defines `AWR-CANON-006` as "canonical form mismatch — implementation
/// self-check failed", and §4.1(2) points at it for an implementation that
/// normalizes strings. A canonicalizer that applies NFC, sorts by code point,
/// truncates numbers or rewrites escapes is not idempotent: re-parsing its
/// output and canonicalizing again yields different bytes. This check runs that
/// round trip on every document, so a future regression in this module is
/// reported as `AWR-CANON-006` instead of silently producing a signature nobody
/// else can verify.
pub fn self_check(canonical: &str) -> Result<(), JsonError> {
    let reparsed = parse(canonical.as_bytes()).map_err(|e| {
        JsonError::new(
            "AWR-CANON-006",
            format!("the canonical form does not re-parse ({}): {}", e.code, e.detail),
        )
    })?;
    let again = canonicalize(&reparsed)?;
    if again != canonical {
        return Err(JsonError::new(
            "AWR-CANON-006",
            "canonicalization is not idempotent: re-canonicalizing the canonical form produced different bytes",
        ));
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Non-canonical serialization (member order preserved) for CLI output
// ---------------------------------------------------------------------------

/// Compact JSON with member order preserved. Used for this implementation's own
/// output (the §11.1 result), where the reading order of the specification's
/// example is more useful than sorted order.
pub fn to_string_compact(v: &Value) -> String {
    let mut out = String::new();
    write_plain(&mut out, v, None, 0);
    out
}

/// Indented JSON with member order preserved.
pub fn to_string_pretty(v: &Value) -> String {
    let mut out = String::new();
    write_plain(&mut out, v, Some(2), 0);
    out
}

fn write_plain(out: &mut String, v: &Value, indent: Option<usize>, level: usize) {
    let nl = |out: &mut String, level: usize| {
        if let Some(w) = indent {
            out.push('\n');
            for _ in 0..(w * level) {
                out.push(' ');
            }
        }
    };
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number { raw, kind } => match kind {
            NumberKind::Integer(i) => {
                let _ = write!(out, "{}", i);
            }
            _ => out.push_str(raw),
        },
        Value::Str(s) => write_json_string(out, s),
        Value::Array(items) => {
            if items.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push('[');
            for (n, item) in items.iter().enumerate() {
                if n > 0 {
                    out.push(',');
                }
                nl(out, level + 1);
                write_plain(out, item, indent, level + 1);
            }
            nl(out, level);
            out.push(']');
        }
        Value::Object(members) => {
            if members.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push('{');
            for (n, (k, val)) in members.iter().enumerate() {
                if n > 0 {
                    out.push(',');
                }
                nl(out, level + 1);
                write_json_string(out, k);
                out.push(':');
                if indent.is_some() {
                    out.push(' ');
                }
                write_plain(out, val, indent, level + 1);
            }
            nl(out, level);
            out.push('}');
        }
    }
}

// ---------------------------------------------------------------------------
// Number pre-scan (§4.3)
// ---------------------------------------------------------------------------

/// Collect every §4.3 number violation in a document, with its JSON path.
///
/// `canonicalize` stops at the first one; a verifier must report **all** errors
/// it can determine (§11.1), so this walk exists to enumerate them.
pub fn scan_numbers(v: &Value) -> Vec<JsonError> {
    let mut out = Vec::new();
    walk_numbers(v, "$", &mut out);
    out
}

fn walk_numbers(v: &Value, path: &str, out: &mut Vec<JsonError>) {
    match v {
        Value::Number { raw, kind } => match kind {
            NumberKind::NonInteger => out.push(JsonError::new(
                "AWR-CANON-001",
                format!("non-integer JSON number `{}` at {}", raw, path),
            )),
            NumberKind::OutOfRange => out.push(JsonError::new(
                "AWR-CANON-002",
                format!("integer `{}` at {} is outside ±(2^53−1)", raw, path),
            )),
            NumberKind::Integer(_) => {}
        },
        Value::Array(items) => {
            for (n, item) in items.iter().enumerate() {
                walk_numbers(item, &format!("{}[{}]", path, n), out);
            }
        }
        Value::Object(members) => {
            for (k, val) in members {
                walk_numbers(val, &format!("{}.{}", path, k), out);
            }
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(s: &str) -> String {
        canonicalize(&parse(s.as_bytes()).expect("parses")).expect("canonicalizes")
    }

    fn code(s: &str) -> &'static str {
        match parse(s.as_bytes()) {
            Err(e) => e.code,
            Ok(v) => match canonicalize(&v) {
                Err(e) => e.code,
                Ok(out) => panic!("expected failure, got {}", out),
            },
        }
    }

    #[test]
    fn sorts_keys_and_drops_whitespace() {
        assert_eq!(c(" { \"b\" : 1 , \"a\" : [ 2 , 3 ] } "), r#"{"a":[2,3],"b":1}"#);
    }

    #[test]
    fn utf16_key_order_differs_from_codepoint_order() {
        // U+FFFF is one UTF-16 code unit 0xFFFF; U+10000 is the pair
        // 0xD800 0xDC00. By code point U+FFFF < U+10000, by UTF-16 code unit
        // 0xD800 < 0xFFFF, so the non-BMP key must come FIRST in JCS order.
        // This is the case RFC 8785 §3.2.3 calls out and the one a code-point
        // sort gets wrong.
        let src = "{\"\u{ffff}\":1,\"\u{10000}\":2}";
        let out = c(src);
        assert_eq!(out, "{\"\u{10000}\":2,\"\u{ffff}\":1}");
        assert_eq!(utf16_cmp("\u{10000}", "\u{ffff}"), Ordering::Less);
        assert_eq!(codepoint_cmp("\u{10000}", "\u{ffff}"), Ordering::Greater);
    }

    #[test]
    fn utf16_key_order_more_cases() {
        // Ordering is by code unit, then by length for a common prefix.
        let mut keys = vec!["\u{10FFFF}", "\u{E000}", "b", "\u{7F}", "a", "aa", "\u{FFFD}"];
        keys.sort_by(|x, y| utf16_cmp(x, y));
        // U+10FFFF encodes as DBFF DFFF, so it sorts before U+E000 and U+FFFD
        // even though its code point is far higher — the whole point of §4.1(1).
        assert_eq!(keys, vec!["a", "aa", "b", "\u{7F}", "\u{10FFFF}", "\u{E000}", "\u{FFFD}"]);
    }

    #[test]
    fn control_escapes_are_lowercase_and_minimal() {
        let src = r#"{"k":"\u0000\u001F\b\t\n\f\r\"\\\u007f\u0041"}"#;
        assert_eq!(c(src), "{\"k\":\"\\u0000\\u001f\\b\\t\\n\\f\\r\\\"\\\\\u{7f}A\"}");
    }

    #[test]
    fn no_normalization_is_applied() {
        // U+00C5 and U+0041 U+030A are canonically equivalent under NFC; the
        // canonicalizer must keep both exactly as given (§4.1(2)).
        let src = "{\"a\":\"\u{00c5}\",\"b\":\"A\u{030a}\"}";
        let out = c(src);
        assert!(out.contains("\u{00c5}"));
        assert!(out.contains("A\u{030a}"));
        assert_ne!(
            c("{\"a\":\"\u{00c5}\"}"),
            c("{\"a\":\"A\u{030a}\"}"),
            "NFC would collapse these two documents into one canonical form"
        );
    }

    #[test]
    fn literal_non_ascii_is_emitted_literally() {
        assert_eq!(c(r#"{"k":"\u00e9\u20ac\ud83d\ude00"}"#), "{\"k\":\"é€😀\"}");
    }

    #[test]
    fn integers_only() {
        assert_eq!(c("[0,-0,1,9007199254740991,-9007199254740991]"), "[0,0,1,9007199254740991,-9007199254740991]");
        assert_eq!(code("[1.5]"), "AWR-CANON-001");
        assert_eq!(code("[1.0]"), "AWR-CANON-001");
        assert_eq!(code("[1e2]"), "AWR-CANON-001");
        assert_eq!(code("[9007199254740992]"), "AWR-CANON-002");
        assert_eq!(code("[-9007199254740992]"), "AWR-CANON-002");
        assert_eq!(code("[123456789012345678901234567890]"), "AWR-CANON-002");
    }

    #[test]
    fn duplicate_keys_rejected() {
        assert_eq!(code(r#"{"a":1,"a":2}"#), "AWR-CANON-004");
        // Distinct-but-equivalent-looking names are not duplicates.
        assert_eq!(c(r#"{"a":1,"\u0061\u0062":2}"#), r#"{"a":1,"ab":2}"#);
        // An escaped name that decodes to an existing one IS a duplicate.
        assert_eq!(code(r#"{"a":1,"\u0061":2}"#), "AWR-CANON-004");
    }

    #[test]
    fn lone_surrogates_rejected() {
        assert_eq!(code(r#"{"a":"\ud800"}"#), "AWR-CANON-003");
        assert_eq!(code(r#"{"a":"\udc00"}"#), "AWR-CANON-003");
        assert_eq!(code(r#"{"a":"\ud800x"}"#), "AWR-CANON-003");
        assert_eq!(code(r#"{"a":"\ud800\ud800"}"#), "AWR-CANON-003");
        assert_eq!(code(r#"{"\ud800":"x"}"#), "AWR-CANON-003");
        // ... and the well-formed pair is accepted.
        assert_eq!(c(r#"{"a":"\ud800\udc00"}"#), "{\"a\":\"\u{10000}\"}");
    }

    #[test]
    fn invalid_utf8_in_string_is_canon_003() {
        let mut bytes = b"{\"a\":\"".to_vec();
        bytes.push(0xff);
        bytes.extend_from_slice(b"\"}");
        assert_eq!(parse(&bytes).unwrap_err().code, "AWR-CANON-003");
    }

    #[test]
    fn malformed_json_is_canon_005() {
        for src in [
            "", "{", "[1,]", "{\"a\":}", "{'a':1}", "nul", "01", "[+1]", "[.5]", "[1.]",
            "{\"a\":1}{\"b\":2}", "\"a\nb\"", "[1 2]", "{\"a\" 1}",
        ] {
            assert_eq!(code(src), "AWR-CANON-005", "for input {:?}", src);
        }
    }

    #[test]
    fn nesting_limit_enforced() {
        let deep = format!("{}{}", "[".repeat(400), "]".repeat(400));
        let e = parse(deep.as_bytes()).unwrap_err();
        assert_eq!(e.code, "AWR-CANON-005");
        assert!(e.detail.contains("nesting"));
    }

    #[test]
    fn unknown_members_and_order_preserved() {
        let v = parse(br#"{"z":1,"unknown":{"deep":[true,null]}}"#).unwrap();
        // Input order preserved in the value model...
        let members = v.as_object().unwrap();
        assert_eq!(members[0].0, "z");
        assert_eq!(members[1].0, "unknown");
        // ...and nothing is dropped by canonicalization.
        assert_eq!(c(r#"{"z":1,"unknown":{"deep":[true,null]}}"#), r#"{"unknown":{"deep":[true,null]},"z":1}"#);
    }

    #[test]
    fn scan_numbers_reports_every_violation() {
        let v = parse(br#"{"a":1.5,"b":[2,9007199254740992],"c":{"d":-0.1}}"#).unwrap();
        let errs = scan_numbers(&v);
        let codes: Vec<&str> = errs.iter().map(|e| e.code).collect();
        assert_eq!(codes, vec!["AWR-CANON-001", "AWR-CANON-002", "AWR-CANON-001"]);
        assert!(errs[0].detail.contains("$.a"));
        assert!(errs[1].detail.contains("$.b[1]"));
        assert!(errs[2].detail.contains("$.c.d"));
    }

    #[test]
    fn rfc8785_appendix_b_sorting_sample() {
        // The RFC 8785 test-data object, whose expected canonical order is
        // "\u000b", "\u0001\u001f", "1", "\ud83d\ude00" ... i.e. sorted by code
        // unit with the surrogate pair last among these.
        let src = "{\"\\u20ac\":\"Euro Sign\",\"\\r\":\"Carriage Return\",\"\\u000a\":\"Newline\",\"1\":\"One\",\"\\u0080\":\"Control\\u007f\",\"\\ud83d\\ude02\":\"Smiley\",\"\\u00f6\":\"Latin Small Letter O With Diaeresis\",\"\\u0041\":\"Capital A\",\"\\u0000\":\"Null\"}";
        let out = c(src);
        let expected = "{\"\\u0000\":\"Null\",\"\\n\":\"Newline\",\"\\r\":\"Carriage Return\",\"1\":\"One\",\"A\":\"Capital A\",\"\u{80}\":\"Control\u{7f}\",\"ö\":\"Latin Small Letter O With Diaeresis\",\"\u{20ac}\":\"Euro Sign\",\"😂\":\"Smiley\"}";
        assert_eq!(out, expected);
    }

    #[test]
    fn self_check_accepts_this_canonicalizer_and_rejects_a_broken_one() {
        let v = parse(r#"{"b":1,"a":"x","c":[1,{"z":null}]}"#.as_bytes()).unwrap();
        let c = canonicalize(&v).unwrap();
        assert!(self_check(&c).is_ok());
        // Output that is not the canonical form of what it parses to: the symptom
        // of a mis-sorting, over-escaping or whitespace-emitting canonicalizer,
        // which is what AWR-CANON-006 exists to catch. The escape cases are built
        // at run time so that this source file contains no backslash-u literal.
        let bs = '\\';
        let over_escaped = format!("{{\"a\":\"{}u0041\"}}", bs);
        let upper_hex_escape = format!("{{\"a\":\"{}u000A\"}}", bs);
        for broken in [
            r#"{"b":1,"a":"x"}"#.to_string(), // wrong key order
            r#"{ "a" : 1 }"#.to_string(),     // insignificant whitespace kept
            r#"{"a":-0}"#.to_string(),        // negative zero not normalised
            over_escaped,                     // escaped a character that must stay literal
            upper_hex_escape,                 // uppercase hex, and not the two-character escape
        ] {
            assert_eq!(
                self_check(&broken).unwrap_err().code,
                "AWR-CANON-006",
                "should have been rejected: {}",
                broken
            );
        }
        // A section 4.3 violation is reported as itself, not as a self-check failure.
        assert_eq!(self_check(r#"{"a":1.0}"#).unwrap_err().code, "AWR-CANON-001");
    }

    #[test]
    fn set_and_remove_preserve_position() {
        let mut v = parse(br#"{"a":1,"b":2,"c":3}"#).unwrap();
        v.set("b", Value::int(9));
        assert_eq!(to_string_compact(&v), r#"{"a":1,"b":9,"c":3}"#);
        assert_eq!(v.remove("b").unwrap().as_i64(), Some(9));
        assert_eq!(to_string_compact(&v), r#"{"a":1,"c":3}"#);
        v.set("d", Value::string("x"));
        assert_eq!(to_string_compact(&v), r#"{"a":1,"c":3,"d":"x"}"#);
    }
}
