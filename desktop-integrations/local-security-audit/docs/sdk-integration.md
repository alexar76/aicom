# SDK Integration

Local Security Audit uses the [`aimarket-agent`](https://crates.io/crates/aimarket-agent) crate to discover, purchase, and verify security intelligence feeds from the AI Market Hub.

## Adding the dependency

In `Cargo.toml`:

```toml
[dependencies]
aimarket-agent = { git = "https://github.com/alexar76/aimarket-sdks.git", package = "aimarket-agent" }
```

Or from a local path:

```toml
[dependencies]
aimarket-agent = { path = "../../aimarket-sdks/rust" }
```

## Initializing the agent

```rust
use aimarket_agent::AimarketAgent;

let agent = AimarketAgent::new(
    "https://hub.aicom.io",   // AI Market Hub URL
    "your-wallet-private-key-hex",  // Ed25519 wallet key
);
```

The agent handles:
- Request signing with the wallet key (Ed25519 via HMAC-SHA256 stub, full Ed25519 in production)
- HTTP transport to the hub
- Payment channel lifecycle

## Discovering security capabilities

```rust
// Discover fresh CVE feeds for the npm ecosystem
let plan = agent
    .discover(
        "fresh CVE feeds for npm ecosystem",
        Some(1.0),   // budget per call (USD)
        Some(5),     // max results
        Some("security"),  // category filter
    )
    .await?;

for step in &plan {
    println!(
        "[{:.1}%] {} — {}",
        step.relevance_score * 100.0,
        step.capability.name,
        step.capability.description
    );
    println!("       Price: ${:.2}/call", step.capability.price_per_call_usd);
    println!("       Trust score: {:.0}%", step.capability.trust_score.unwrap_or(0.0) * 100.0);
}
```

## Purchasing a feed (open channel + invoke + close)

```rust
use serde_json::json;

// 1. Open a payment channel
let channel = agent.open_channel(5.0, "USDT", "base").await?;
println!("Channel {} opened with ${} balance", channel.channel_id, channel.balance_usd);

// 2. Invoke the capability (buy the feed)
let capability_id = &plan[0].capability.capability_id;
let input = json!({
    "ecosystem": "npm",
    "include_exploit_db": true,
    "freshness_hours": 24,
});

let result = agent
    .invoke(
        capability_id,
        input,
        &channel.channel_id,
        Some(&plan[0].capability.product_id),
        Some(&plan[0].capability.source_hub),
    )
    .await?;

if result.success {
    println!("Feed purchased successfully");
    println!("Price: ${}", result.price_usd);

    // Check TEE verification
    if result.tee_verified {
        if let Some(ref attestation) = result.tee_attestation {
            println!("TEE attestation from: {}", attestation.platform);
            println!("Enclave ID: {}", attestation.enclave_id);
        }
        if let Some(ref receipt) = result.tee_receipt {
            println!("TEE receipt: {}", receipt.receipt_id);
        }
    }

    // The output contains the rule data
    if let Some(ref output) = result.output {
        // Cache the rules locally
        cache_rules_locally(output)?;
    }
} else {
    eprintln!("Feed purchase failed: {:?}", result.error);
}

// 3. Close the channel and settle
let settlement = agent.close_channel(&channel.channel_id).await?;
println!("Settlement: ${} spent, ${} refunded", settlement.total_spent_usd, settlement.refund_usd);
```

## Verifying TEE attestations

```rust
use std::collections::HashMap;
use aimarket_agent::TeeVerifier;

// Initialize the verifier with known trusted code hashes
let mut trusted = HashMap::new();
trusted.insert(
    "cve-feed-npm-v1".to_string(),
    "abc123def456...".to_string(), // known good code hash
);

let verifier = TeeVerifier::new(
    "your-wallet-private-key-hex",
    trusted,
);

// Verify an attestation from a purchase
if let Some(ref attestation) = result.tee_attestation {
    if verifier.verify_attestation(attestation, &capability_id) {
        println!("Attestation verified — feed is authentic");
    } else {
        eprintln!("Attestation FAILED verification — possible tampering");
    }
}
```

## Selling anti-pattern signatures

When the local scanner finds an anti-pattern, it can be listed on the marketplace:

```rust
async fn sell_signature(
    agent: &AimarketAgent,
    signature_hash: &str,
    severity: &str,
    ecosystem: &str,
    pattern_category: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let channel = agent.open_channel(1.0, "USDT", "base").await?;

    let capability_id = "marketplace-list-signature";  // well-known capability
    let input = json!({
        "signature_hash": signature_hash,
        "metadata": {
            "severity": severity,
            "ecosystem": ecosystem,
            "pattern_category": pattern_category,
            "scanner_version": env!("CARGO_PKG_VERSION"),
        }
    });

    let result = agent
        .invoke(capability_id, input, &channel.channel_id, None, None)
        .await?;

    let _settlement = agent.close_channel(&channel.channel_id).await?;

    if result.success {
        println!("Signature listed on marketplace: {}", signature_hash);
    }

    Ok(())
}
```

## Full lifecycle example

```rust
use aimarket_agent::AimarketAgent;

async fn refresh_cve_feeds(agent: &AimarketAgent) -> Result<(), Box<dyn std::error::Error>> {
    // Discover — search for security feeds
    let plan = agent
        .discover("fresh CVE feeds for npm ecosystem", Some(1.0), Some(5), Some("security"))
        .await?;

    if plan.is_empty() {
        println!("No security feeds available on the marketplace");
        return Ok(());
    }

    // Open channel
    let channel = agent.open_channel(10.0, "USDT", "base").await?;

    // Buy each relevant feed
    for step in &plan {
        let result = agent
            .invoke(
                &step.capability.capability_id,
                serde_json::json!({"ecosystem": "npm", "freshness_hours": 24}),
                &channel.channel_id,
                Some(&step.capability.product_id),
                Some(&step.capability.source_hub),
            )
            .await?;

        if result.success {
            println!("Bought: {} (${})", step.capability.name, result.price_usd);

            // Verify TEE attestation
            if let Some(ref att) = result.tee_attestation {
                println!("  Verified enclave: {} on {}", att.enclave_id, att.platform);
            }
        }
    }

    // Settle
    let settlement = agent.close_channel(&channel.channel_id).await?;
    println!("Total spent: ${}", settlement.total_spent_usd);

    Ok(())
}
```

## Error handling

| Error | Meaning | Recovery |
|-------|---------|----------|
| `AgentError::Http` | Network failure | Retry with backoff |
| `AgentError::Protocol("Payment required")` | Channel depleted | Open a new channel |
| `AgentError::Protocol("Discovery failed: 4xx")` | No matching capabilities | Broaden search terms |
| `safety_blocked == true` | Input rejected by safety filter | Adjust input parameters |

## Local caching

After purchasing a feed, cache the rules locally using the TEE receipt as a cache key:

```rust
use std::path::PathBuf;
use std::fs;

fn cache_rules_locally(output: &serde_json::Value) -> std::io::Result<()> {
    let cache_dir = dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("local-security-audit")
        .join("cache");

    fs::create_dir_all(&cache_dir)?;

    let feed_id = output["feed_id"].as_str().unwrap_or("unknown");
    let path = cache_dir.join(format!("{}.msgpack", feed_id));

    let bytes = rmp_serde::to_vec(output)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
    fs::write(&path, bytes)?;

    Ok(())
}
```

## Configuration

Store the wallet key and hub URL in a local config file (never committed):

```json
{
  "hub_url": "https://hub.aicom.io",
  "wallet_key_hex": "...",
  "default_budget_usd": 5.0,
  "cache_ttl_hours": 24,
  "auto_refresh_feeds": true
}
```
