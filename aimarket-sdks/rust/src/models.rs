use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Capability {
    pub capability_id: String,
    pub product_id: String,
    pub name: String,
    pub version: String,
    pub description: String,
    #[serde(default)]
    pub input_schema: Option<serde_json::Value>,
    #[serde(default)]
    pub output_schema: Option<serde_json::Value>,
    pub price_per_call_usd: f64,
    #[serde(default)]
    pub p50_latency_ms: Option<f64>,
    #[serde(default)]
    pub success_rate_30d: Option<f64>,
    pub source_hub: String,
    #[serde(default)]
    pub source_hub_name: Option<String>,
    #[serde(default)]
    pub trust_score: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Channel {
    pub channel_id: String,
    pub deposit_usd: f64,
    pub balance_usd: f64,
    pub token: String,
    pub chain: String,
    pub expires_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InvokeResult {
    pub success: bool,
    #[serde(default)]
    pub output: Option<serde_json::Value>,
    pub price_usd: f64,
    pub latency_ms: f64,
    #[serde(default)]
    pub safety_blocked: bool,
    #[serde(default)]
    pub safety_reason: Option<String>,
    #[serde(default)]
    pub tee_verified: bool,
    #[serde(default)]
    pub tee_attestation: Option<TeeAttestation>,
    #[serde(default)]
    pub tee_receipt: Option<TeeReceipt>,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TeeAttestation {
    pub platform: String,
    pub enclave_id: String,
    pub code_hash: String,
    #[serde(default)]
    pub pcr_values: std::collections::HashMap<String, String>,
    pub instance_id: String,
    pub region: String,
    pub timestamp: String,
    pub ttl_s: i64,
    pub signature: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TeeReceipt {
    pub receipt_id: String,
    pub input_hash: String,
    pub output_hash: String,
    pub signature: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanStep {
    pub capability: Capability,
    pub relevance_score: f64,
    pub rationale: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settlement {
    pub channel_id: String,
    pub total_spent_usd: f64,
    pub refund_usd: f64,
    pub invocations: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResponse {
    pub results: Vec<PlanStep>,
    pub total: i64,
    pub hub: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BillOfMaterials {
    pub task: String,
    pub plan: Vec<PlanStep>,
    pub results: Vec<InvokeResult>,
    pub settlement: Option<Settlement>,
    pub total_spent_usd: f64,
    pub protocol_version: String,
}
