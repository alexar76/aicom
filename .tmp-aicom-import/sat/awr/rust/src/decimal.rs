//! Decimal strings. SPEC §4.3: "Comparison of such values MUST be performed as
//! decimal arithmetic, never by parsing to a binary float." Nothing in this
//! module converts to `f32`/`f64`.

use std::cmp::Ordering;

/// `price.amount` grammar (§3.3): `^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`.
pub fn is_amount(s: &str) -> bool {
    let (neg, rest) = match s.strip_prefix('-') {
        Some(r) => (true, r),
        None => (false, s),
    };
    let _ = neg;
    let (int_part, frac_part) = match rest.split_once('.') {
        Some((i, f)) => (i, Some(f)),
        None => (rest, None),
    };
    if int_part.is_empty() {
        return false;
    }
    if int_part != "0" && int_part.starts_with('0') {
        return false;
    }
    if !int_part.bytes().all(|c| c.is_ascii_digit()) {
        return false;
    }
    match frac_part {
        None => true,
        Some(f) => !f.is_empty() && f.bytes().all(|c| c.is_ascii_digit()),
    }
}

/// `score`, `confidence`, `policy.threshold` grammar (§3.4, §3.5):
/// `^(0(\.[0-9]+)?|1(\.0+)?)$` — a decimal string in the closed unit interval.
pub fn is_unit_interval(s: &str) -> bool {
    if let Some(rest) = s.strip_prefix('0') {
        if rest.is_empty() {
            return true;
        }
        match rest.strip_prefix('.') {
            Some(f) => !f.is_empty() && f.bytes().all(|c| c.is_ascii_digit()),
            None => false,
        }
    } else if let Some(rest) = s.strip_prefix('1') {
        if rest.is_empty() {
            return true;
        }
        match rest.strip_prefix('.') {
            Some(f) => !f.is_empty() && f.bytes().all(|c| c == b'0'),
            None => false,
        }
    } else {
        false
    }
}

/// Compare two well-formed decimal strings exactly, as decimal arithmetic.
/// Returns `None` if either side is not a valid amount.
pub fn cmp_decimal(a: &str, b: &str) -> Option<Ordering> {
    if !is_amount(a) || !is_amount(b) {
        return None;
    }
    let split = |s: &str| -> (bool, String, String) {
        let (neg, rest) = match s.strip_prefix('-') {
            Some(r) => (true, r),
            None => (false, s),
        };
        let (i, f) = match rest.split_once('.') {
            Some((i, f)) => (i.to_string(), f.trim_end_matches('0').to_string()),
            None => (rest.to_string(), String::new()),
        };
        // -0 == 0
        let is_zero = i.bytes().all(|c| c == b'0') && f.is_empty();
        (neg && !is_zero, i, f)
    };
    let (an, ai, af) = split(a);
    let (bn, bi, bf) = split(b);
    if an != bn {
        return Some(if an { Ordering::Less } else { Ordering::Greater });
    }
    let magnitude = {
        let ai_t = ai.trim_start_matches('0');
        let bi_t = bi.trim_start_matches('0');
        let ord = ai_t.len().cmp(&bi_t.len()).then_with(|| ai_t.cmp(bi_t));
        if ord != Ordering::Equal {
            ord
        } else {
            let width = af.len().max(bf.len());
            let pad = |f: &str| {
                let mut s = f.to_string();
                while s.len() < width {
                    s.push('0');
                }
                s
            };
            pad(&af).cmp(&pad(&bf))
        }
    };
    Some(if an { magnitude.reverse() } else { magnitude })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn amount_grammar() {
        for ok in ["0", "-0", "0.15", "1", "10", "-3.50", "123456789012345678901234567890.5"] {
            assert!(is_amount(ok), "{} should be a valid amount", ok);
        }
        for bad in ["", "-", ".5", "0.", "00", "01", "1.", "+1", "1e3", "0x1", " 1", "1 ", "NaN", "1,5"] {
            assert!(!is_amount(bad), "{} should be rejected", bad);
        }
    }

    #[test]
    fn unit_interval_grammar() {
        for ok in ["0", "1", "0.0", "0.93", "1.0", "1.000", "0.000000001"] {
            assert!(is_unit_interval(ok), "{} should be in [0,1]", ok);
        }
        for bad in ["", "-0", "1.1", "1.01", "2", "0.", ".5", "00.5", "0.5.5", "1e0", "-0.5"] {
            assert!(!is_unit_interval(bad), "{} should be rejected", bad);
        }
    }

    #[test]
    fn decimal_comparison_is_exact() {
        assert_eq!(cmp_decimal("0.80", "0.8"), Some(Ordering::Equal));
        assert_eq!(cmp_decimal("0.93", "0.80"), Some(Ordering::Greater));
        assert_eq!(cmp_decimal("0.1", "0.10000000000000000001"), Some(Ordering::Less));
        assert_eq!(cmp_decimal("-0", "0"), Some(Ordering::Equal));
        assert_eq!(cmp_decimal("-1", "0"), Some(Ordering::Less));
        assert_eq!(cmp_decimal("-1.5", "-1.25"), Some(Ordering::Less));
        assert_eq!(cmp_decimal("10", "9.99"), Some(Ordering::Greater));
        assert_eq!(cmp_decimal("1", "1.0"), Some(Ordering::Equal));
        // A value beyond f64 precision still compares exactly.
        assert_eq!(
            cmp_decimal("9007199254740993", "9007199254740992"),
            Some(Ordering::Greater)
        );
        assert_eq!(cmp_decimal("x", "1"), None);
    }
}
