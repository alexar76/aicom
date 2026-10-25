//! Exercise the exact parser imported by the legacy escrow source. The native
//! Ed25519 program verifies the tuple selected by all three instruction indexes.
#[path = "../../../support/ed25519-instruction.rs"]
mod ed25519_instruction;
use ed25519_instruction::verify_ed25519_ix_data;

fn fixture() -> (Vec<u8>, [u8; 32], Vec<u8>, [u8; 64]) {
    let public_key = [7; 32];
    let signature = [9; 64];
    let message = b"the exact channel debit".to_vec();
    let mut data = vec![1, 0];
    for value in [48u16, u16::MAX, 16, u16::MAX, 112, message.len() as u16, u16::MAX] {
        data.extend_from_slice(&value.to_le_bytes());
    }
    data.extend_from_slice(&public_key);
    data.extend_from_slice(&signature);
    data.extend_from_slice(&message);
    (data, public_key, message, signature)
}

#[test]
fn exact_native_ed25519_local_tuple_is_accepted() {
    let (data, key, message, signature) = fixture();
    assert!(verify_ed25519_ix_data(&data, &key, &message, &signature));
    assert!(!verify_ed25519_ix_data(&data, &[8; 32], &message, &signature));
    assert!(!verify_ed25519_ix_data(&data, &key, b"another debit", &signature));
    assert!(!verify_ed25519_ix_data(&data, &key, &message, &[8; 64]));
}

#[test]
fn bytes_not_verified_by_native_program_cannot_authorize_a_debit() {
    let (data, key, message, signature) = fixture();
    for index in [4, 8, 14] {
        for foreign_instruction in [0u16, 1, 17, u16::MAX - 1] {
            let mut malicious = data.clone();
            malicious[index..index + 2].copy_from_slice(&foreign_instruction.to_le_bytes());
            assert!(!verify_ed25519_ix_data(&malicious, &key, &message, &signature));
        }
    }
    for end in 0..data.len() {
        assert!(!verify_ed25519_ix_data(&data[..end], &key, &message, &signature));
    }
}
