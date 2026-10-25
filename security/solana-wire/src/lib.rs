//! Internal compatibility boundary for Anchor/Solana's existing Serde messages.
//!
//! The codec is maintained bincode-next 2.1, not vendored bincode 1.3. Its legacy
//! configuration preserves little-endian fixed-width integers, enum and length
//! tags, and borrowed data. Account padding / loader ELF tails remain accepted.
//! The 16 MiB decode envelope covers Solana's 10 MiB maximum account and the
//! existing 2.2 MiB ZK lookup table. It also bounds native string allocations.
//! This is not a general-purpose hostile-Serde sandbox: callers must use typed
//! SDK schemas, whose dynamic containers have non-zero-sized elements. A byte
//! budget alone cannot bound arbitrary recursive or zero-sized Serde containers.

#![forbid(unsafe_code)]

use bincode_next::{config, enc::write::Writer};
use serde::{Deserialize, Serialize};
use std::io::Write;

pub use bincode_next::error::{DecodeError, EncodeError};

pub const MAX_DECODE_BYTES: usize = 16 * 1024 * 1024;

pub fn serialize<T: Serialize + ?Sized>(value: &T) -> Result<Vec<u8>, EncodeError> {
    bincode_next::serde::encode_to_vec(value, config::legacy())
}

pub fn deserialize<'de, T: Deserialize<'de>>(bytes: &'de [u8]) -> Result<T, DecodeError> {
    if bytes.len() > MAX_DECODE_BYTES {
        return Err(DecodeError::LimitExceeded);
    }
    bincode_next::serde::borrow_decode_from_slice(
        bytes,
        config::legacy().with_limit::<MAX_DECODE_BYTES>(),
    )
    .map(|(value, _consumed)| value)
}

/// Write directly, preserving short-write errors and existing account padding.
/// There is no hidden buffer and the caller's writer is not implicitly flushed.
pub fn serialize_into<W: Write, T: Serialize + ?Sized>(
    mut writer: W,
    value: &T,
) -> Result<(), EncodeError> {
    let mut direct = DirectWriter {
        inner: &mut writer,
        written: 0,
    };
    bincode_next::serde::encode_into_writer(value, &mut direct, config::legacy())
}

pub fn serialized_size<T: Serialize + ?Sized>(value: &T) -> Result<u64, EncodeError> {
    let mut counter = CheckedSize(0);
    bincode_next::serde::encode_into_writer(value, &mut counter, config::legacy())?;
    Ok(counter.0)
}

struct CheckedSize(u64);

impl Writer for CheckedSize {
    fn write(&mut self, bytes: &[u8]) -> Result<(), EncodeError> {
        self.0 = self
            .0
            .checked_add(
                u64::try_from(bytes.len()).map_err(|_| EncodeError::Other("size overflow"))?,
            )
            .ok_or(EncodeError::Other("size overflow"))?;
        Ok(())
    }
}

struct DirectWriter<'a, W> {
    inner: &'a mut W,
    written: usize,
}

impl<W: Write> Writer for DirectWriter<'_, W> {
    fn write(&mut self, bytes: &[u8]) -> Result<(), EncodeError> {
        let next = self
            .written
            .checked_add(bytes.len())
            .ok_or(EncodeError::Other("size overflow"))?;
        self.inner
            .write_all(bytes)
            .map_err(|inner| EncodeError::Io {
                inner,
                index: self.written,
            })?;
        self.written = next;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io;

    #[test]
    fn fixed_width_lengths_borrowing_and_padding_are_legacy_compatible() {
        let bytes = serialize(&(0x01020304u32, Some(9u64), "hello")).unwrap();
        let mut expected = vec![4, 3, 2, 1, 1];
        expected.extend(9u64.to_le_bytes());
        expected.extend(5u64.to_le_bytes());
        expected.extend(b"hello");
        assert_eq!(bytes, expected);
        assert_eq!(
            serialized_size(&(0x01020304u32, Some(9u64), "hello")).unwrap(),
            bytes.len() as u64
        );
        let mut padded = bytes;
        padded.extend([0xde, 0xad, 0xbe, 0xef]);
        let decoded: (u32, Option<u64>, &str) = deserialize(&padded).unwrap();
        assert_eq!(decoded, (0x01020304, Some(9), "hello"));
        assert_eq!(decoded.2.as_ptr(), padded[21..].as_ptr());
    }

    #[test]
    fn truncated_sequences_and_maps_never_become_successful_partial_values() {
        let mut sequence = 2u64.to_le_bytes().to_vec();
        sequence.extend(5u64.to_le_bytes());
        assert!(deserialize::<Vec<u64>>(&sequence).is_err());
        let mut map = sequence.clone();
        map.extend(6u64.to_le_bytes());
        assert!(deserialize::<std::collections::BTreeMap<u64, u64>>(&map).is_err());
        for n in 0..8 {
            assert!(deserialize::<u64>(&5u64.to_le_bytes()[..n]).is_err());
        }
    }

    #[test]
    fn malformed_tags_utf8_and_allocation_headers_fail_closed() {
        assert!(deserialize::<bool>(&[2]).is_err());
        assert!(deserialize::<Option<u64>>(&[2]).is_err());
        let mut invalid_utf8 = 1u64.to_le_bytes().to_vec();
        invalid_utf8.push(0xff);
        assert!(deserialize::<String>(&invalid_utf8).is_err());
        assert!(deserialize::<String>(&u64::MAX.to_le_bytes()).is_err());
        assert!(deserialize::<u8>(&vec![0; MAX_DECODE_BYTES + 1]).is_err());
    }

    #[test]
    fn writer_failures_short_accounts_and_unused_padding_are_preserved() {
        let mut short = [0xee; 7];
        assert!(serialize_into(&mut short[..], &7u64).is_err());
        assert_eq!(short, [7, 0, 0, 0, 0, 0, 0]);
        let mut padded = [0xee; 12];
        serialize_into(&mut padded[..], &7u64).unwrap();
        assert_eq!(&padded[..8], &7u64.to_le_bytes());
        assert_eq!(&padded[8..], &[0xee; 4]);
        struct Fails;
        impl Write for Fails {
            fn write(&mut self, _: &[u8]) -> io::Result<usize> {
                Err(io::Error::other("failed"))
            }
            fn flush(&mut self) -> io::Result<()> {
                panic!("must not flush caller writer")
            }
        }
        assert!(serialize_into(Fails, &1u8).is_err());
    }

    #[test]
    fn counting_cannot_wrap_and_allocating_codec_is_not_used_for_size() {
        let mut counter = CheckedSize(u64::MAX);
        assert!(counter.write(&[0]).is_err());
        assert_eq!(
            serialized_size(vec![0u64; 100_000].as_slice()).unwrap(),
            800_008
        );
    }
}
