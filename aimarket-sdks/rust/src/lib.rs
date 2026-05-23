//! AI Market Protocol v2 consumer SDK for Rust.
//!
//! Target: Tauri desktop apps, native CLI tools.
//!
//! # Example
//! ```no_run
//! use aimarket_agent::AimarketAgent;
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let agent = AimarketAgent::new(
//!         "https://hub.aicom.io",
//!         "your-wallet-private-key-hex",
//!     );
//!
//!     let plan = agent.discover("ATS scoring for fintech roles", Some(1.0), Some(5), Some("career")).await?;
//!     let channel = agent.open_channel(5.0, "USDT", "base").await?;
//!     let result = agent.invoke(&plan[0].capability.capability_id, serde_json::json!({"role": "PM"}), &channel.channel_id, None, None).await?;
//!     let settlement = agent.close_channel(&channel.channel_id).await?;
//!
//!     println!("Spent: ${}", result.price_usd);
//!     Ok(())
//! }
//! ```

pub mod agent;
pub mod models;
pub mod signer;
pub mod tee;

pub use agent::AimarketAgent;
pub use models::*;
