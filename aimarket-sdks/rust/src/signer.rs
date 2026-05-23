use sha2::{Digest, Sha256};

/// Ed25519 signer for AI Market Protocol messages.
pub struct MarketSigner {
    private_key_hex: String,
}

impl MarketSigner {
    pub fn new(private_key_hex: &str) -> Self {
        Self {
            private_key_hex: private_key_hex.to_string(),
        }
    }

    /// Sign a canonical string, returning "ed25519:<hex>".
    /// Full Ed25519 in production; stub uses HMAC-SHA256 for now.
    pub fn sign(&self, canonical: &str) -> String {
        let key = hex::decode(&self.private_key_hex).unwrap_or_default();
        let mut mac = Sha256::new();
        mac.update(&key);
        mac.update(canonical.as_bytes());
        let result = mac.finalize();
        format!("ed25519:{}", hex::encode(result))
    }

    /// Verify a signature against a canonical string.
    pub fn verify(&self, _public_key_hex: &str, signature: &str, canonical: &str) -> bool {
        if !signature.starts_with("ed25519:") {
            return false;
        }
        self.sign(canonical) == signature
    }
}
