//! RFC 3339 UTC timestamps, without a date library.
//!
//! SPEC §3.1 requires `validFrom`/`validUntil` to be "an RFC 3339 `date-time` in
//! UTC with a `Z` offset and second precision or finer"; §6.1 says the same of
//! `proof.created` and §3.3 of `work.startedAt`/`work.completedAt`.

/// An instant as whole seconds since the Unix epoch plus a nanosecond part.
/// Nanoseconds only ever refine ordering; AWR never re-serializes a parsed
/// timestamp, so no precision is lost in the signed bytes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Timestamp {
    pub secs: i64,
    pub nanos: u32,
}

fn is_leap(y: i64) -> bool {
    (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
}

fn days_in_month(y: i64, m: u32) -> u32 {
    match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if is_leap(y) {
                29
            } else {
                28
            }
        }
        _ => 0,
    }
}

/// Days from 1970-01-01 for a proleptic Gregorian date (Howard Hinnant's
/// `days_from_civil`).
fn days_from_civil(y: i64, m: u32, d: u32) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400; // [0, 399]
    let mp = (m as i64 + 9) % 12; // Mar = 0
    let doy = (153 * mp + 2) / 5 + d as i64 - 1; // [0, 365]
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy; // [0, 146096]
    era * 146097 + doe - 719468
}

/// Inverse of `days_from_civil`.
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = z - era * 146097; // [0, 146096]
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (if m <= 2 { y + 1 } else { y }, m, d)
}

/// Parse `YYYY-MM-DDTHH:MM:SS[.frac]Z`.
///
/// IMPLEMENTATION CHOICE (§3.1): only the `Z` (or `z`) offset form is accepted.
/// `+00:00` denotes the same instant but the specification says "in UTC with a
/// `Z` offset", and accepting a numeric offset would make two byte-different
/// documents equally conformant for no gain. A leap second (`:60`) is rejected.
pub fn parse_rfc3339_utc(s: &str) -> Option<Timestamp> {
    let b = s.as_bytes();
    if b.len() < 20 {
        return None;
    }
    let digits = |from: usize, len: usize| -> Option<i64> {
        let mut v: i64 = 0;
        for k in 0..len {
            let c = *b.get(from + k)?;
            if !c.is_ascii_digit() {
                return None;
            }
            v = v * 10 + (c - b'0') as i64;
        }
        Some(v)
    };
    if b[4] != b'-' || b[7] != b'-' {
        return None;
    }
    if !(b[10] == b'T' || b[10] == b't') {
        return None;
    }
    if b[13] != b':' || b[16] != b':' {
        return None;
    }
    let year = digits(0, 4)?;
    let month = digits(5, 2)? as u32;
    let day = digits(8, 2)? as u32;
    let hour = digits(11, 2)?;
    let minute = digits(14, 2)?;
    let second = digits(17, 2)?;
    if month < 1 || month > 12 {
        return None;
    }
    if day < 1 || day > days_in_month(year, month) {
        return None;
    }
    if hour > 23 || minute > 59 || second > 59 {
        return None;
    }
    let mut idx = 19;
    let mut nanos: u32 = 0;
    if b.get(idx) == Some(&b'.') {
        idx += 1;
        let start = idx;
        while matches!(b.get(idx), Some(c) if c.is_ascii_digit()) {
            idx += 1;
        }
        if idx == start {
            return None; // "." with no digits
        }
        let frac = &s[start..idx];
        let mut scaled = String::with_capacity(9);
        for k in 0..9 {
            scaled.push(frac.as_bytes().get(k).map(|c| *c as char).unwrap_or('0'));
        }
        nanos = scaled.parse::<u32>().ok()?;
    }
    match b.get(idx) {
        Some(b'Z') | Some(b'z') => {}
        _ => return None,
    }
    if idx + 1 != b.len() {
        return None;
    }
    let secs = days_from_civil(year, month, day) * 86400 + hour * 3600 + minute * 60 + second;
    Some(Timestamp { secs, nanos })
}

/// Format whole seconds as `YYYY-MM-DDTHH:MM:SSZ` — the form this
/// implementation issues.
pub fn format_rfc3339_utc(secs: i64) -> String {
    let days = secs.div_euclid(86400);
    let rem = secs.rem_euclid(86400);
    let (y, m, d) = civil_from_days(days);
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        y,
        m,
        d,
        rem / 3600,
        (rem % 3600) / 60,
        rem % 60
    )
}

/// Wall-clock now, in whole seconds since the epoch.
pub fn now_secs() -> i64 {
    match std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH) {
        Ok(d) => d.as_secs() as i64,
        Err(e) => -(e.duration().as_secs() as i64),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_the_specification_examples() {
        let t = parse_rfc3339_utc("2026-07-31T10:15:30Z").unwrap();
        assert_eq!(format_rfc3339_utc(t.secs), "2026-07-31T10:15:30Z");
        assert!(parse_rfc3339_utc("2026-07-31T10:15:28Z").unwrap() < t);
        // sub-second precision is "second precision or finer"
        let f = parse_rfc3339_utc("2026-07-31T10:15:30.123456789Z").unwrap();
        assert_eq!(f.secs, t.secs);
        assert_eq!(f.nanos, 123456789);
        assert!(t < f);
    }

    #[test]
    fn epoch_and_roundtrip() {
        assert_eq!(parse_rfc3339_utc("1970-01-01T00:00:00Z").unwrap().secs, 0);
        for s in [
            "1970-01-01T00:00:00Z",
            "2000-02-29T23:59:59Z",
            "2024-12-31T00:00:01Z",
            "2100-03-01T12:00:00Z",
            "1900-01-01T00:00:00Z",
        ] {
            let t = parse_rfc3339_utc(s).unwrap();
            assert_eq!(format_rfc3339_utc(t.secs), s, "roundtrip of {}", s);
        }
    }

    #[test]
    fn rejects_non_utc_and_malformed() {
        for s in [
            "2026-07-31T10:15:30+00:00",
            "2026-07-31T10:15:30",
            "2026-07-31 10:15:30Z",
            "2026-07-31T10:15Z",
            "2026-13-01T00:00:00Z",
            "2026-02-30T00:00:00Z",
            "2023-02-29T00:00:00Z",
            "2026-07-31T24:00:00Z",
            "2026-07-31T23:60:00Z",
            "2026-07-31T23:59:60Z",
            "2026-07-31T10:15:30.Z",
            "2026-07-31T10:15:30Z ",
            "26-07-31T10:15:30Z",
            "",
            "not a date",
        ] {
            assert!(parse_rfc3339_utc(s).is_none(), "{} should not parse", s);
        }
        // 2024 is a leap year, 2023 is not
        assert!(parse_rfc3339_utc("2024-02-29T00:00:00Z").is_some());
    }
}
