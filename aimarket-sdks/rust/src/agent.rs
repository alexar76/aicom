use crate::models::*;
use crate::signer::MarketSigner;
use reqwest::Client;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum AgentError {
    #[error("HTTP error: {0}")]
    Http(#[from] reqwest::Error),
    #[error("Protocol error: {0}")]
    Protocol(String),
}

pub struct AimarketAgent {
    hub_url: String,
    signer: MarketSigner,
    client: Client,
    affiliate: String,
}

impl AimarketAgent {
    pub fn new(hub_url: &str, wallet_key_hex: &str) -> Self {
        Self {
            hub_url: hub_url.trim_end_matches('/').to_string(),
            signer: MarketSigner::new(wallet_key_hex),
            client: Client::new(),
            affiliate: "aimarket-sdk-rust".to_string(),
        }
    }

    // ── Phase 1: Discovery ────────────────────────────────────────

    pub async fn well_known(&self) -> Result<String, AgentError> {
        let url = format!("{}/.well-known/ai-market.json", self.hub_url);
        let resp = self.client.get(&url).send().await?;
        Ok(resp.text().await?)
    }

    pub async fn discover(
        &self,
        intent: &str,
        budget: Option<f64>,
        limit: Option<i32>,
        category: Option<&str>,
    ) -> Result<Vec<PlanStep>, AgentError> {
        let mut params = vec![("intent".to_string(), intent.to_string())];
        if let Some(b) = budget {
            params.push(("budget_usd".to_string(), b.to_string()));
        }
        if let Some(l) = limit {
            params.push(("limit".to_string(), l.to_string()));
        }
        if let Some(c) = category {
            params.push(("category".to_string(), c.to_string()));
        }

        let url = format!("{}/ai-market/v2/search", self.hub_url);
        let resp = self
            .client
            .get(&url)
            .query(&params)
            .header("X-AIMarket-Affiliate", &self.affiliate)
            .send()
            .await?;

        if !resp.status().is_success() {
            return Err(AgentError::Protocol(format!(
                "Discovery failed: {}",
                resp.status()
            )));
        }

        let data: SearchResponse = resp.json().await?;
        Ok(data.results)
    }

    // ── Phase 2: Channel Open ─────────────────────────────────────

    pub async fn open_channel(
        &self,
        deposit_usd: f64,
        token: &str,
        chain: &str,
    ) -> Result<Channel, AgentError> {
        let url = format!("{}/ai-market/v2/channel/open", self.hub_url);
        let body = serde_json::json!({
            "deposit_usd": deposit_usd,
            "token": token,
            "chain": chain,
        });

        let resp = self
            .client
            .post(&url)
            .json(&body)
            .header("X-AIMarket-Affiliate", &self.affiliate)
            .send()
            .await?;

        if !resp.status().is_success() {
            return Err(AgentError::Protocol(format!(
                "Channel open failed: {}",
                resp.status()
            )));
        }

        Ok(resp.json().await?)
    }

    // ── Phase 3: Invoke ───────────────────────────────────────────

    pub async fn invoke(
        &self,
        capability_id: &str,
        input: serde_json::Value,
        channel_id: &str,
        product_id: Option<&str>,
        source_hub: Option<&str>,
    ) -> Result<InvokeResult, AgentError> {
        let url = format!("{}/ai-market/v2/invoke", self.hub_url);
        let canonical = format!(
            "channel:{}|capability:{}|affiliate:{}",
            channel_id, capability_id, self.affiliate
        );
        let signature = self.signer.sign(&canonical);

        let mut body = serde_json::json!({
            "capability_id": capability_id,
            "input": input,
        });
        if let Some(pid) = product_id {
            body["product_id"] = serde_json::Value::String(pid.to_string());
        }
        if let Some(hub) = source_hub {
            body["source_hub"] = serde_json::Value::String(hub.to_string());
        }

        let resp = self
            .client
            .post(&url)
            .json(&body)
            .header("X-Payment-Channel", channel_id)
            .header("X-AIMarket-Affiliate", &self.affiliate)
            .header("X-Market-Signature", &signature)
            .send()
            .await?;

        match resp.status().as_u16() {
            403 => {
                let data: serde_json::Value = resp.json().await?;
                Ok(InvokeResult {
                    success: false,
                    output: None,
                    price_usd: 0.0,
                    latency_ms: 0.0,
                    safety_blocked: true,
                    safety_reason: data["reason"].as_str().map(|s| s.to_string()),
                    tee_verified: false,
                    tee_attestation: None,
                    tee_receipt: None,
                    error: None,
                })
            }
            402 => Err(AgentError::Protocol(
                "Payment required — channel depleted".into(),
            )),
            _ => Ok(resp.json().await?),
        }
    }

    // ── Phase 4: Settle ───────────────────────────────────────────

    pub async fn close_channel(&self, channel_id: &str) -> Result<Settlement, AgentError> {
        let url = format!("{}/ai-market/v2/channel/close", self.hub_url);
        let resp = self
            .client
            .post(&url)
            .json(&serde_json::json!({"channel_id": channel_id}))
            .header("X-AIMarket-Affiliate", &self.affiliate)
            .send()
            .await?;

        if !resp.status().is_success() {
            return Err(AgentError::Protocol(format!(
                "Settlement failed: {}",
                resp.status()
            )));
        }

        Ok(resp.json().await?)
    }

    // ── Full cycle ────────────────────────────────────────────────

    pub async fn run_once(
        &self,
        intent: &str,
        input: serde_json::Value,
        deposit_usd: Option<f64>,
        category: Option<&str>,
    ) -> Result<BillOfMaterials, AgentError> {
        let deposit = deposit_usd.unwrap_or(5.0);

        let plan = self
            .discover(intent, Some(deposit), Some(5), category)
            .await?;
        if plan.is_empty() {
            return Err(AgentError::Protocol(format!(
                "No capabilities for: {}",
                intent
            )));
        }

        let channel = self.open_channel(deposit, "USDT", "base").await?;
        let step = &plan[0];

        let result = self
            .invoke(
                &step.capability.capability_id,
                input,
                &channel.channel_id,
                Some(&step.capability.product_id),
                Some(&step.capability.source_hub),
            )
            .await?;

        let settlement = self.close_channel(&channel.channel_id).await?;

        Ok(BillOfMaterials {
            task: intent.to_string(),
            plan,
            results: vec![result.clone()],
            settlement: Some(settlement),
            total_spent_usd: result.price_usd,
            protocol_version: "v2".to_string(),
        })
    }
}
