//! Hand-written base58btc / multibase / base64 / hex codecs.
//!
//! SPEC §5.1 fixes the base58btc alphabet and the `z` multibase prefix; §3.2
//! fixes standard padded base64 for SRI; §5.2 implies base64url for an RFC 8037
//! JWK `x`; §17 asks for hex on the `hashdata` output.

/// Bitcoin base58 alphabet (SPEC §5.1).
pub const B58_ALPHABET: &[u8; 58] =
    b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

/// Multibase prefix for base58btc (SPEC §5.1, §6.1).
pub const MULTIBASE_B58BTC: char = 'z';

fn b58_index(c: u8) -> Option<u8> {
    B58_ALPHABET.iter().position(|&a| a == c).map(|p| p as u8)
}

/// base58btc encode. Each leading zero byte becomes one `1`; the remainder is a
/// base-256 → base-58 conversion of the whole value.
pub fn b58_encode(input: &[u8]) -> String {
    let zeros = input.iter().take_while(|&&b| b == 0).count();
    let mut digits: Vec<u8> = Vec::with_capacity(input.len() * 138 / 100 + 1);
    for &byte in &input[zeros..] {
        let mut carry = byte as u32;
        for d in digits.iter_mut() {
            carry += (*d as u32) << 8;
            *d = (carry % 58) as u8;
            carry /= 58;
        }
        while carry > 0 {
            digits.push((carry % 58) as u8);
            carry /= 58;
        }
    }
    let mut out = String::with_capacity(zeros + digits.len());
    for _ in 0..zeros {
        out.push('1');
    }
    for d in digits.iter().rev() {
        out.push(B58_ALPHABET[*d as usize] as char);
    }
    out
}

/// base58btc decode. Rejects any character outside the alphabet, which also
/// rejects the visually confusable `0`, `O`, `I`, `l`.
pub fn b58_decode(s: &str) -> Result<Vec<u8>, String> {
    let bytes = s.as_bytes();
    let zeros = bytes.iter().take_while(|&&b| b == b'1').count();
    let mut acc: Vec<u8> = Vec::with_capacity(bytes.len());
    for &c in &bytes[zeros..] {
        let val = b58_index(c).ok_or_else(|| {
            if c.is_ascii_graphic() {
                format!("`{}` is not a base58btc character", c as char)
            } else {
                format!("byte 0x{:02x} is not a base58btc character", c)
            }
        })?;
        let mut carry = val as u32;
        for b in acc.iter_mut() {
            carry += (*b as u32) * 58;
            *b = (carry & 0xff) as u8;
            carry >>= 8;
        }
        while carry > 0 {
            acc.push((carry & 0xff) as u8);
            carry >>= 8;
        }
    }
    let mut out = vec![0u8; zeros];
    out.extend(acc.iter().rev());
    Ok(out)
}

/// Encode as multibase base58btc: `z` followed by base58btc.
pub fn multibase_b58_encode(input: &[u8]) -> String {
    let mut s = String::with_capacity(input.len() * 2);
    s.push(MULTIBASE_B58BTC);
    s.push_str(&b58_encode(input));
    s
}

/// Decode a multibase string, accepting only base58btc (`z`). Any other prefix
/// — including an unprefixed value or a base64 one — is an error, per §6.1.
pub fn multibase_decode(s: &str) -> Result<Vec<u8>, String> {
    let mut it = s.chars();
    match it.next() {
        None => Err("empty multibase string".to_string()),
        Some(MULTIBASE_B58BTC) => b58_decode(&s[MULTIBASE_B58BTC.len_utf8()..]),
        Some(c) => Err(format!(
            "multibase prefix `{}` is not base58btc (`z`); AWR/2 defines no other encoding",
            c
        )),
    }
}

const B64_STD: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const B64_URL: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

fn b64_encode_with(alphabet: &[u8; 64], input: &[u8], pad: bool) -> String {
    let mut out = String::with_capacity((input.len() + 2) / 3 * 4);
    for chunk in input.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = *chunk.get(1).unwrap_or(&0) as u32;
        let b2 = *chunk.get(2).unwrap_or(&0) as u32;
        let n = (b0 << 16) | (b1 << 8) | b2;
        out.push(alphabet[((n >> 18) & 0x3f) as usize] as char);
        out.push(alphabet[((n >> 12) & 0x3f) as usize] as char);
        if chunk.len() > 1 {
            out.push(alphabet[((n >> 6) & 0x3f) as usize] as char);
        } else if pad {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(alphabet[(n & 0x3f) as usize] as char);
        } else if pad {
            out.push('=');
        }
    }
    out
}

/// Standard base64 with padding and the `+/` alphabet — the SRI encoding (§3.2).
pub fn b64_encode(input: &[u8]) -> String {
    b64_encode_with(B64_STD, input, true)
}

/// base64url without padding — the JWK encoding (RFC 8037, §5.2).
pub fn b64url_encode_nopad(input: &[u8]) -> String {
    b64_encode_with(B64_URL, input, false)
}

fn b64_value(c: u8) -> Option<u32> {
    match c {
        b'A'..=b'Z' => Some((c - b'A') as u32),
        b'a'..=b'z' => Some((c - b'a' + 26) as u32),
        b'0'..=b'9' => Some((c - b'0' + 52) as u32),
        b'+' | b'-' => Some(62),
        b'/' | b'_' => Some(63),
        _ => None,
    }
}

/// Decode base64. Accepts both the `+/` and the `-_` alphabet and both padded
/// and unpadded input, but rejects any other character, a wrong length, and
/// non-zero padding bits.
///
/// Callers that must distinguish the alphabets check the string themselves; the
/// one place where AWR is strict is the SRI form (§3.2, `strict_std` = true),
/// which requires the padded `+/` form.
pub fn b64_decode(s: &str, strict_std: bool) -> Result<Vec<u8>, String> {
    let raw = s.as_bytes();
    if strict_std {
        if raw.iter().any(|&c| c == b'-' || c == b'_') {
            return Err("base64url alphabet where standard base64 (`+/`) is required".to_string());
        }
        if raw.len() % 4 != 0 {
            return Err("standard base64 must be padded to a multiple of 4 characters".to_string());
        }
    }
    let body: &[u8] = {
        let mut end = raw.len();
        while end > 0 && raw[end - 1] == b'=' {
            end -= 1;
        }
        if raw.len() - end > 2 {
            return Err("more than two padding characters".to_string());
        }
        &raw[..end]
    };
    if body.len() % 4 == 1 {
        return Err("base64 length is not a valid encoding of any byte string".to_string());
    }
    let mut out = Vec::with_capacity(body.len() / 4 * 3 + 2);
    for chunk in body.chunks(4) {
        let mut acc: u32 = 0;
        for (n, &c) in chunk.iter().enumerate() {
            let v = b64_value(c).ok_or_else(|| {
                if c.is_ascii_graphic() {
                    format!("`{}` is not a base64 character", c as char)
                } else {
                    format!("byte 0x{:02x} is not a base64 character", c)
                }
            })?;
            acc |= v << (18 - 6 * n);
        }
        match chunk.len() {
            4 => {
                out.push((acc >> 16) as u8);
                out.push((acc >> 8) as u8);
                out.push(acc as u8);
            }
            3 => {
                if acc & 0xff != 0 {
                    return Err("non-zero trailing bits in base64".to_string());
                }
                out.push((acc >> 16) as u8);
                out.push((acc >> 8) as u8);
            }
            2 => {
                if acc & 0xffff != 0 {
                    return Err("non-zero trailing bits in base64".to_string());
                }
                out.push((acc >> 16) as u8);
            }
            _ => unreachable!(),
        }
    }
    Ok(out)
}

pub fn hex_encode(input: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut s = String::with_capacity(input.len() * 2);
    for b in input {
        s.push(HEX[(b >> 4) as usize] as char);
        s.push(HEX[(b & 0x0f) as usize] as char);
    }
    s
}

pub fn hex_decode(s: &str) -> Result<Vec<u8>, String> {
    let raw = s.as_bytes();
    if raw.len() % 2 != 0 {
        return Err("hex string has an odd number of characters".to_string());
    }
    let mut out = Vec::with_capacity(raw.len() / 2);
    let nib = |c: u8| -> Result<u8, String> {
        match c {
            b'0'..=b'9' => Ok(c - b'0'),
            b'a'..=b'f' => Ok(c - b'a' + 10),
            b'A'..=b'F' => Ok(c - b'A' + 10),
            _ => Err(format!("`{}` is not a hex digit", c as char)),
        }
    };
    for pair in raw.chunks(2) {
        out.push((nib(pair[0])? << 4) | nib(pair[1])?);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base58_known_answer_hello_world() {
        // The canonical multibase/base58btc known answer.
        assert_eq!(b58_encode(b"hello world"), "StV1DL6CwTryKyV");
        assert_eq!(b58_decode("StV1DL6CwTryKyV").unwrap(), b"hello world".to_vec());
        assert_eq!(multibase_b58_encode(b"hello world"), "zStV1DL6CwTryKyV");
        assert_eq!(multibase_decode("zStV1DL6CwTryKyV").unwrap(), b"hello world".to_vec());
    }

    #[test]
    fn base58_leading_zeros_and_edges() {
        assert_eq!(b58_encode(b""), "");
        assert_eq!(b58_encode(&[0]), "1");
        assert_eq!(b58_encode(&[0, 0, 0]), "111");
        assert_eq!(b58_encode(&[0, 0, 1]), "112");
        assert_eq!(b58_encode(&[57]), "z");
        assert_eq!(b58_encode(&[58]), "21");
        assert_eq!(b58_decode("111").unwrap(), vec![0, 0, 0]);
        assert_eq!(b58_decode("112").unwrap(), vec![0, 0, 1]);
        assert_eq!(b58_decode("").unwrap(), Vec::<u8>::new());
        // The four confusable characters are not in the alphabet.
        for bad in ["0", "O", "I", "l", "StV1DL6CwTryKy0", "hello world"] {
            assert!(b58_decode(bad).is_err(), "{} should not decode", bad);
        }
    }

    #[test]
    fn base58_roundtrips_every_length() {
        for len in 0..40usize {
            let mut v = Vec::with_capacity(len);
            for i in 0..len {
                // deterministic pseudo-random bytes
                v.push(((i as u32 * 167 + 13) % 256) as u8);
            }
            assert_eq!(b58_decode(&b58_encode(&v)).unwrap(), v, "length {}", len);
        }
        // and with leading zeros
        let v = vec![0u8, 0, 0, 9, 8, 7];
        assert_eq!(b58_decode(&b58_encode(&v)).unwrap(), v);
    }

    #[test]
    fn multibase_rejects_other_prefixes() {
        assert!(multibase_decode("mSGVsbG8=").is_err());
        assert!(multibase_decode("StV1DL6CwTryKyV").is_err());
        assert!(multibase_decode("").is_err());
    }

    #[test]
    fn base64_known_answers() {
        // The SRI value the specification prints for the empty byte string
        // (§3.2, §3.3) must be reproducible from a real SHA-256.
        assert_eq!(b64_encode(b""), "");
        assert_eq!(b64_encode(b"f"), "Zg==");
        assert_eq!(b64_encode(b"fo"), "Zm8=");
        assert_eq!(b64_encode(b"foo"), "Zm9v");
        assert_eq!(b64_encode(b"foob"), "Zm9vYg==");
        assert_eq!(b64_decode("Zm9vYg==", true).unwrap(), b"foob".to_vec());
        assert_eq!(b64_decode("Zm9v", true).unwrap(), b"foo".to_vec());
        assert_eq!(b64_encode(&[0xff, 0xef]), "/+8=");
        assert_eq!(b64url_encode_nopad(&[0xff, 0xef]), "_-8");
        assert_eq!(b64_decode("_-8", false).unwrap(), vec![0xff, 0xef]);
        assert!(b64_decode("_-8", true).is_err(), "url alphabet must fail strict std");
        assert!(b64_decode("Zm9", true).is_err(), "unpadded must fail strict std");
        assert!(b64_decode("Zg=A", true).is_err());
        assert!(b64_decode("Zm9vYg=", true).is_err());
        assert!(b64_decode("Zm9*", true).is_err());
        // Non-zero trailing bits.
        assert!(b64_decode("Zh==", true).is_err());
    }

    #[test]
    fn hex_roundtrip() {
        assert_eq!(hex_encode(&[0, 1, 0x0f, 0xff]), "00010fff");
        assert_eq!(hex_decode("00010FFF").unwrap(), vec![0, 1, 0x0f, 0xff]);
        assert!(hex_decode("abc").is_err());
        assert!(hex_decode("zz").is_err());
    }
}
