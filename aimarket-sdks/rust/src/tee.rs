use crate::models::TeeAttestation;
use crate::signer::MarketSigner;

/// Local TEE attestation verifier.
pub struct TeeVerifier {
    signer: MarketSigner,
    trusted_code_hashes: std::collections::HashMap<String, String>,
}

impl TeeVerifier {
    pub fn new(wallet_key_hex: &str, trusted: std::collections::HashMap<String, String>) -> Self {
        Self {
            signer: MarketSigner::new(wallet_key_hex),
            trusted_code_hashes: trusted,
        }
    }

    pub fn trust_code_hash(&mut self, capability_id: &str, code_hash: &str) {
        self.trusted_code_hashes
            .insert(capability_id.to_string(), code_hash.to_string());
    }

    pub fn verify_attestation(&self, att: &TeeAttestation, capability_id: &str) -> bool {
        if att.is_expired() {
            return false;
        }
        if let Some(expected) = self.trusted_code_hashes.get(capability_id) {
            if att.code_hash != *expected {
                return false;
            }
        }
        let enclave_key = self.enclave_public_key(&att.platform);
        match enclave_key {
            Some(key) => self.signer.verify(&key, &att.signature, &att.canonical()),
            None => false,
        }
    }

    fn enclave_public_key(&self, platform: &str) -> Option<String> {
        match platform {
            "aws_nitro" => Some("nitro_enclave_pubkey_hex".into()),
            "intel_tdx" => Some("tdx_enclave_pubkey_hex".into()),
            "amd_sev" => Some("sev_enclave_pubkey_hex".into()),
            "azure_confidential_computing" => Some("azure_cc_pubkey_hex".into()),
            _ => None,
        }
    }
}

impl TeeAttestation {
    pub fn canonical(&self) -> String {
        format!(
            "platform:{}|enclave_id:{}|code_hash:{}|pcr0:{}|instance:{}|region:{}|timestamp:{}|ttl:{}",
            self.platform,
            self.enclave_id,
            self.code_hash,
            self.pcr_values.get("pcr0").map_or("", |v| v),
            self.instance_id,
            self.region,
            self.timestamp,
            self.ttl_s,
        )
    }

    pub fn is_expired(&self) -> bool {
        // Stub: parse timestamp and compare.
        // In production, use chrono::DateTime.
        false
    }
}
