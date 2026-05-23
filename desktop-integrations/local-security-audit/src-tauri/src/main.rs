//! Local Security Audit — Tauri desktop app
//!
//! Scans local git repositories for secrets, CVEs, and anti-patterns.
//! Integrates with the AI Market Protocol via the `aimarket-agent` SDK
//! for fresh security intelligence feeds. Code never leaves the device.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use aimarket_agent::AimarketAgent;
use serde::{Deserialize, Serialize};
use std::sync::Mutex;
use tauri::State;

// ── App state ──────────────────────────────────────────────────────

struct AppState {
    agent: Mutex<AimarketAgent>,
    cache: Mutex<sled::Db>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct ScanResult {
    repo_path: String,
    total_commits: u64,
    secrets_found: Vec<Finding>,
    cvEs: Vec<CveEntry>,
    anti_patterns: Vec<Finding>,
    scanned_at: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct Finding {
    severity: String,
    description: String,
    file_path: String,
    line_number: u64,
    pattern_id: Option<String>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct CveEntry {
    id: String,
    severity: String,
    package_name: String,
    installed_version: String,
    fixed_version: Option<String>,
    description: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct FeedInfo {
    feed_id: String,
    name: String,
    ecosystem: String,
    price_usd: f64,
    tee_verified: bool,
}

// ── Tauri commands ─────────────────────────────────────────────────

/// Discover available security feeds on the marketplace.
#[tauri::command]
async fn discover_feeds(
    state: State<'_, AppState>,
    intent: String,
    budget: Option<f64>,
    limit: Option<i32>,
) -> Result<Vec<FeedInfo>, String> {
    let agent = state.agent.lock().map_err(|e| e.to_string())?;
    let plan = agent
        .discover(&intent, budget, limit, Some("security"))
        .await
        .map_err(|e| e.to_string())?;

    let feeds: Vec<FeedInfo> = plan
        .into_iter()
        .map(|step| FeedInfo {
            feed_id: step.capability.capability_id.clone(),
            name: step.capability.name.clone(),
            ecosystem: "npm".to_string(), // derived from intent in production
            price_usd: step.capability.price_per_call_usd,
            tee_verified: step.capability.trust_score.unwrap_or(0.0) > 0.8,
        })
        .collect();

    Ok(feeds)
}

/// Purchase a security feed from the marketplace.
#[tauri::command]
async fn buy_feed(
    state: State<'_, AppState>,
    capability_id: String,
    product_id: String,
    source_hub: String,
    deposit_usd: f64,
) -> Result<String, String> {
    let agent = state.agent.lock().map_err(|e| e.to_string())?;

    // Open a payment channel
    let channel = agent
        .open_channel(deposit_usd, "USDT", "base")
        .await
        .map_err(|e| format!("Channel open failed: {}", e))?;

    // Invoke the capability (buy the feed)
    let input = serde_json::json!({
        "freshness_hours": 24,
        "include_exploit_db": true,
    });

    let result = agent
        .invoke(
            &capability_id,
            input,
            &channel.channel_id,
            Some(&product_id),
            Some(&source_hub),
        )
        .await
        .map_err(|e| format!("Invoke failed: {}", e))?;

    if !result.success {
        return Err(format!(
            "Feed purchase failed: {:?}",
            result.error.unwrap_or_default()
        ));
    }

    // Cache the purchased feed locally
    if let Some(ref output) = result.output {
        let cache = state.cache.lock().map_err(|e| e.to_string())?;
        let key = format!("feed:{}", &capability_id);
        let value = serde_json::to_vec(output).map_err(|e| e.to_string())?;
        cache.insert(key.as_bytes(), value).map_err(|e| e.to_string())?;
        cache.flush().map_err(|e| e.to_string())?;
    }

    // Close channel and settle
    let settlement = agent
        .close_channel(&channel.channel_id)
        .await
        .map_err(|e| format!("Settlement failed: {}", e))?;

    Ok(format!(
        "Feed purchased. Spent ${:.2}, refunded ${:.2}",
        settlement.total_spent_usd, settlement.refund_usd
    ))
}

/// Scan a local git repository at the given path.
#[tauri::command]
async fn scan_repo(
    state: State<'_, AppState>,
    repo_path: String,
) -> Result<ScanResult, String> {
    // Open the git repo (local only — no network)
    let repo = git2::Repository::open(&repo_path)
        .map_err(|e| format!("Cannot open git repo at {}: {}", repo_path, e))?;

    // Count reachable commits
    let mut revwalk = repo.revwalk().map_err(|e| e.to_string())?;
    revwalk.push_head().map_err(|e| e.to_string())?;
    let total_commits = revwalk.count() as u64;

    // ── Secret scanning (stub — production uses regex + entropy) ───
    let secrets_found: Vec<Finding> = Vec::new();

    // ── Dependency scanning (stub — production parses manifests) ───
    let cvEs: Vec<CveEntry> = Vec::new();

    // ── Anti-pattern scanning (stub) ───────────────────────────────
    let anti_patterns: Vec<Finding> = Vec::new();

    let result = ScanResult {
        repo_path,
        total_commits,
        secrets_found,
        cvEs,
        anti_patterns,
        scanned_at: chrono::Utc::now().to_rfc3339(),
    };

    Ok(result)
}

/// Get a cached feed by capability ID.
#[tauri::command]
fn get_cached_feed(state: State<'_, AppState>, capability_id: String) -> Result<Option<serde_json::Value>, String> {
    let cache = state.cache.lock().map_err(|e| e.to_string())?;
    let key = format!("feed:{}", capability_id);
    match cache.get(key.as_bytes()).map_err(|e| e.to_string())? {
        Some(bytes) => {
            let value: serde_json::Value =
                serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
            Ok(Some(value))
        }
        None => Ok(None),
    }
}

/// Sell an anti-pattern signature to the marketplace.
/// Only the signature hash is transmitted — never the source code.
#[tauri::command]
async fn sell_signature(
    state: State<'_, AppState>,
    signature_hash: String,
    severity: String,
    ecosystem: String,
    pattern_category: String,
) -> Result<String, String> {
    let agent = state.agent.lock().map_err(|e| e.to_string())?;

    let channel = agent
        .open_channel(1.0, "USDT", "base")
        .await
        .map_err(|e| format!("Channel open failed: {}", e))?;

    let input = serde_json::json!({
        "signature_hash": signature_hash,
        "metadata": {
            "severity": severity,
            "ecosystem": ecosystem,
            "pattern_category": pattern_category,
        }
    });

    let result = agent
        .invoke("marketplace-list-signature", input, &channel.channel_id, None, None)
        .await
        .map_err(|e| format!("Signature listing failed: {}", e))?;

    let _settlement = agent.close_channel(&channel.channel_id).await.map_err(|e| e.to_string())?;

    if result.success {
        Ok(format!("Signature {} listed successfully", signature_hash))
    } else {
        Err(format!(
            "Listing rejected: {:?}",
            result.safety_reason.unwrap_or_default()
        ))
    }
}

// ── Entry point ────────────────────────────────────────────────────

fn main() {
    env_logger::init();

    // Load config from ~/.config/local-security-audit/config.json
    let config_path = dirs::config_dir()
        .unwrap_or_else(|| std::path::PathBuf::from("."))
        .join("local-security-audit")
        .join("config.json");

    let config: serde_json::Value = if config_path.exists() {
        let content = std::fs::read_to_string(&config_path).unwrap_or_else(|_| "{}".into());
        serde_json::from_str(&content).unwrap_or_default()
    } else {
        serde_json::json!({
            "hub_url": "https://hub.aicom.io",
            "wallet_key_hex": "",
        })
    };

    let hub_url = config["hub_url"]
        .as_str()
        .unwrap_or("https://hub.aicom.io");
    let wallet_key = config["wallet_key_hex"].as_str().unwrap_or("");

    // Initialize the AI market agent
    let agent = AimarketAgent::new(hub_url, wallet_key);

    // Open or create the local cache database
    let cache_dir = dirs::data_dir()
        .unwrap_or_else(|| std::path::PathBuf::from("."))
        .join("local-security-audit")
        .join("cache");

    std::fs::create_dir_all(&cache_dir).expect("Failed to create cache directory");

    let db = sled::open(cache_dir.join("feeds.db"))
        .expect("Failed to open local cache database");

    tauri::Builder::default()
        .manage(AppState {
            agent: Mutex::new(agent),
            cache: Mutex::new(db),
        })
        .invoke_handler(tauri::generate_handler![
            discover_feeds,
            buy_feed,
            scan_repo,
            get_cached_feed,
            sell_signature,
        ])
        .run(tauri::generate_context!())
        .expect("Error running Local Security Audit");
}
