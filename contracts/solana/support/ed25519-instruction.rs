/// Parse Ed25519 program instruction data and check if our (pubkey, message, signature)
/// triple is among the verified entries.
pub fn verify_ed25519_ix_data(
    data: &[u8],
    expected_pubkey: &[u8; 32],
    expected_message: &[u8],
    expected_signature: &[u8; 64],
) -> bool {
    const OFFSETS_SIZE: usize = 14;

    if data.len() < 2 {
        return false;
    }
    let num_sigs = data[0] as usize;
    if num_sigs == 0 {
        return false;
    }
    let header_size = 2 + num_sigs * OFFSETS_SIZE;
    if data.len() < header_size {
        return false;
    }

    for i in 0..num_sigs {
        let off = 2 + i * OFFSETS_SIZE;
        // The native verifier can read each component from another instruction.
        // This parser reads only this instruction, so all three references must
        // explicitly name the local data (u16::MAX). Otherwise the bytes below
        // were never the tuple verified by the Ed25519 program.
        if [off + 2, off + 6, off + 12].iter().any(|index| {
            u16::from_le_bytes([data[*index], data[*index + 1]]) != u16::MAX
        }) {
            continue;
        }
        let sig_offset = u16::from_le_bytes([data[off], data[off + 1]]) as usize;
        let pubkey_offset = u16::from_le_bytes([data[off + 4], data[off + 5]]) as usize;
        let msg_offset = u16::from_le_bytes([data[off + 8], data[off + 9]]) as usize;
        let msg_size = u16::from_le_bytes([data[off + 10], data[off + 11]]) as usize;

        if sig_offset.saturating_add(64) > data.len() {
            continue;
        }
        if pubkey_offset.saturating_add(32) > data.len() {
            continue;
        }
        if msg_offset.saturating_add(msg_size) > data.len() {
            continue;
        }

        let sig_slice = &data[sig_offset..sig_offset + 64];
        let pk_slice = &data[pubkey_offset..pubkey_offset + 32];
        let msg_slice = &data[msg_offset..msg_offset + msg_size];

        // Constant-time comparison of the authenticated triple. A timing-variable
        // `==` short-circuits on the first mismatching byte, which can leak the
        // signature/pubkey/message a byte at a time to an on-chain observer who
        // can measure compute-unit consumption. `ct_eq_bytes` always inspects
        // every byte. The message length is non-secret framing, so an early
        // length check is fine; equal-length content is compared in constant time.
        if msg_slice.len() == expected_message.len()
            && ct_eq_bytes(sig_slice, expected_signature.as_ref())
            && ct_eq_bytes(pk_slice, expected_pubkey.as_ref())
            && ct_eq_bytes(msg_slice, expected_message)
        {
            return true;
        }
    }
    false
}

/// Constant-time byte-slice equality.
///
/// Returns `false` immediately on a length mismatch (lengths are not secret),
/// otherwise OR-accumulates the per-byte XOR difference across the *entire*
/// slice so the running time does not depend on the position of the first
/// differing byte. Avoids pulling in an extra crypto dependency for the two
/// fixed-length (signature, pubkey) and one variable-length (message)
/// comparisons performed during debit authorization.
#[inline(never)]
fn ct_eq_bytes(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff: u8 = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}
