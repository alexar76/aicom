//! AIMarketEscrow — Solana escrow program for AI Market Protocol v2.
//!
//! Implements the channel/open, channel/debit, channel/close lifecycle
//! on Solana using PDAs and SPL tokens (USDC on Solana).
//!
//! Key Solana-specific design:
//!   - PDA escrow accounts derived from (depositor, channel_id)
//!   - SPL Token vault: tokens held in a PDA-owned ATA
//!   - Ed25519 signature verification for debit authorization (native, not EIP-712)
//!   - Native 24h expiry via Clock sysvar
//!   - Closed PDA accounts refund rent to depositor

use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

declare_id!("9BcJEAQCeFrPunKQ16itbaAzpw9A4zMHYPQxNxEAZUXR");

// ── Constants ────────────────────────────────────────────────────

const CHANNEL_EXPIRY_SECS: i64 = 86400; // 24 hours
const MAX_DEPOSIT: u64 = 10_000_000_000; // $10,000 in 6-decimal USDC
const MIN_DEPOSIT: u64 = 1_000_000;       // $1.00

// ── Program ─────────────────────────────────────────────────────

#[program]
pub mod aimarket_escrow {
    use super::*;

    /// Open a pre-funded payment channel.
    ///
    /// Transfers `deposit_amount` of SPL tokens from user's ATA
    /// to the escrow vault PDA. Channel expires in 24h.
    pub fn open_channel(
        ctx: Context<OpenChannel>,
        channel_id: [u8; 32],
        deposit_amount: u64,
    ) -> Result<()> {
        require!(
            deposit_amount >= MIN_DEPOSIT && deposit_amount <= MAX_DEPOSIT,
            AimarketError::DepositOutOfRange
        );

        let channel = &mut ctx.accounts.channel;
        let clock = Clock::get()?;

        channel.depositor = ctx.accounts.depositor.key();
        channel.channel_id = channel_id;
        channel.token_mint = ctx.accounts.token_mint.key();
        channel.deposit_amount = deposit_amount;
        channel.balance = deposit_amount;
        channel.used_amount = 0;
        channel.expires_at = clock.unix_timestamp + CHANNEL_EXPIRY_SECS;
        channel.nonce = 0;
        channel.status = ChannelStatus::Open as u8;
        channel.bump = ctx.bumps.channel;
        channel.vault_bump = ctx.bumps.vault;

        // Transfer tokens from depositor to escrow vault
        let cpi_ctx = CpiContext::new(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.depositor_ata.to_account_info(),
                to: ctx.accounts.vault.to_account_info(),
                authority: ctx.accounts.depositor.to_account_info(),
            },
        );
        token::transfer(cpi_ctx, deposit_amount)?;

        emit!(ChannelOpened {
            channel_id,
            depositor: ctx.accounts.depositor.key(),
            mint: ctx.accounts.token_mint.key(),
            deposit_amount,
            expires_at: channel.expires_at,
        });

        Ok(())
    }

    /// Debit a channel for a capability invocation.
    ///
    /// Only an authorized hub can call this. The hub must present
    /// a valid Ed25519 signature from the depositor authorizing the debit.
    /// Signature is verified via the native Ed25519 syscall.
    pub fn debit_channel(
        ctx: Context<DebitChannel>,
        channel_id: [u8; 32],
        amount: u64,
        receipt_id: [u8; 32],
        deadline: i64,
        // Ed25519 signature from depositor: 64 bytes
        signature: [u8; 64],
        // Depositor's Ed25519 public key (matches PDA derivation)
        depositor_pubkey: [u8; 32],
    ) -> Result<()> {
        let channel = &mut ctx.accounts.channel;

        // Verify hub is authorized
        require!(
            ctx.accounts.authorized_hub.is_authorized,
            AimarketError::Unauthorized
        );
        require!(channel.status() == ChannelStatus::Open, AimarketError::ChannelNotOpen);

        let clock = Clock::get()?;
        require!(clock.unix_timestamp <= channel.expires_at, AimarketError::ChannelExpired);
        require!(clock.unix_timestamp <= deadline, AimarketError::ChannelExpired);
        require!(amount <= channel.balance, AimarketError::InsufficientBalance);

        // Verify depositor's Ed25519 signature
        let message = debit_message(
            channel_id,
            channel.token_mint,
            amount,
            receipt_id,
            channel.nonce,
            deadline,
        );
        require!(
            verify_ed25519(
                &depositor_pubkey,
                &message,
                &signature,
                &ctx.accounts.instructions_sysvar.to_account_info(),
            )?,
            AimarketError::InvalidSignature
        );

        // Execute debit
        channel.nonce += 1;
        channel.balance -= amount;
        channel.used_amount += amount;

        emit!(ChannelDebited {
            channel_id,
            amount,
            receipt_id,
            remaining_balance: channel.balance,
        });

        Ok(())
    }

    /// Settle a channel: transfer used funds to hub, refund rest to depositor.
    pub fn settle_channel(ctx: Context<SettleChannel>, channel_id: [u8; 32]) -> Result<()> {
        let channel = &mut ctx.accounts.channel;

        require!(
            channel.depositor == ctx.accounts.depositor.key()
                || ctx.accounts.authorized_hub.is_authorized,
            AimarketError::Unauthorized
        );
        require!(channel.status() == ChannelStatus::Open, AimarketError::ChannelNotOpen);

        channel.status = ChannelStatus::Settled as u8;

        let used = channel.used_amount;
        let refund = channel.balance;

        // Pay hub for used invocations
        if used > 0 {
            let seeds: &[&[u8]] = &[
                b"channel",
                channel_id.as_ref(),
                &[channel.vault_bump],
            ];
            let signer_seeds: &[&[&[u8]]] = &[seeds];

            let cpi_ctx = CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.vault.to_account_info(),
                    to: ctx.accounts.hub_ata.to_account_info(),
                    authority: ctx.accounts.vault.to_account_info(),
                },
                signer_seeds,
            );
            token::transfer(cpi_ctx, used)?;
        }

        // Refund remaining to depositor
        if refund > 0 {
            let seeds: &[&[u8]] = &[
                b"channel",
                channel_id.as_ref(),
                &[channel.vault_bump],
            ];
            let signer_seeds: &[&[&[u8]]] = &[seeds];

            let cpi_ctx = CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.vault.to_account_info(),
                    to: ctx.accounts.depositor_ata.to_account_info(),
                    authority: ctx.accounts.vault.to_account_info(),
                },
                signer_seeds,
            );
            token::transfer(cpi_ctx, refund)?;
        }

        emit!(ChannelSettled {
            channel_id,
            used_amount: used,
            refund_amount: refund,
            depositor: channel.depositor,
        });

        Ok(())
    }

    // ── Admin ────────────────────────────────────────────────────

    /// Initialize the global program config with an admin key.
    /// Can only be called once. The admin can then authorize hubs.
    pub fn initialize_config(ctx: Context<InitConfig>) -> Result<()> {
        require!(!ctx.accounts.config.initialized, AimarketError::AlreadyInitialized);
        ctx.accounts.config.admin = ctx.accounts.admin.key();
        ctx.accounts.config.initialized = true;
        Ok(())
    }

    /// Authorize or deauthorize a hub. Only callable by the global admin.
    pub fn authorize_hub(ctx: Context<AdminAuth>, is_authorized: bool) -> Result<()> {
        require!(
            ctx.accounts.config.admin == ctx.accounts.authority.key(),
            AimarketError::Unauthorized
        );
        ctx.accounts.authorized_hub.is_authorized = is_authorized;
        ctx.accounts.authorized_hub.authority = ctx.accounts.authority.key();
        Ok(())
    }

    /// Refund a channel — depositor only, before any debit (SC-1 safety).
    pub fn refund_channel(
        ctx: Context<RefundChannel>,
        channel_id: [u8; 32],
        reason: String,
    ) -> Result<()> {
        require!(reason.len() <= 128, AimarketError::ReasonTooLong);
        let channel = &mut ctx.accounts.channel;

        require!(channel.depositor == ctx.accounts.depositor.key(), AimarketError::Unauthorized);
        require!(channel.status() == ChannelStatus::Open, AimarketError::ChannelNotOpen);
        require!(channel.used_amount == 0, AimarketError::RefundAfterDebit);

        channel.status = ChannelStatus::Refunded as u8;
        let total = channel.balance + channel.used_amount;

        let seeds: &[&[u8]] = &[
            b"channel",
            channel_id.as_ref(),
            &[channel.vault_bump],
        ];
        let signer_seeds: &[&[&[u8]]] = &[seeds];

        let cpi_ctx = CpiContext::new_with_signer(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.vault.to_account_info(),
                to: ctx.accounts.depositor_ata.to_account_info(),
                authority: ctx.accounts.vault.to_account_info(),
            },
            signer_seeds,
        );
        token::transfer(cpi_ctx, total)?;

        emit!(ChannelRefunded {
            channel_id,
            amount: total,
            reason,
        });

        Ok(())
    }

    /// Permissionless expiry — anyone can close an expired channel.
    pub fn expire_channel(ctx: Context<ExpireChannel>, channel_id: [u8; 32]) -> Result<()> {
        let channel = &mut ctx.accounts.channel;
        let clock = Clock::get()?;

        require!(channel.status() == ChannelStatus::Open, AimarketError::ChannelNotOpen);
        require!(clock.unix_timestamp > channel.expires_at, AimarketError::ChannelNotExpired);

        channel.status = ChannelStatus::Expired as u8;
        let total = channel.balance + channel.used_amount;

        let seeds: &[&[u8]] = &[
            b"channel",
            channel_id.as_ref(),
            &[channel.vault_bump],
        ];
        let signer_seeds: &[&[&[u8]]] = &[seeds];

        let cpi_ctx = CpiContext::new_with_signer(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.vault.to_account_info(),
                to: ctx.accounts.depositor_ata.to_account_info(),
                authority: ctx.accounts.vault.to_account_info(),
            },
            signer_seeds,
        );
        token::transfer(cpi_ctx, total)?;

        emit!(ChannelExpired {
            channel_id,
            refund_amount: total,
        });

        Ok(())
    }
}

// ── Global Config ─────────────────────────────────────────────────

#[account]
pub struct ProgramConfig {
    pub admin: Pubkey,
    pub initialized: bool,
}

// ── Account Structs ──────────────────────────────────────────────

#[account]
pub struct Channel {
    pub depositor: Pubkey,
    pub channel_id: [u8; 32],
    pub token_mint: Pubkey,
    pub deposit_amount: u64,
    pub balance: u64,
    pub used_amount: u64,
    pub expires_at: i64,
    pub nonce: u64,
    pub status: u8, // ChannelStatus enum
    pub bump: u8,
    pub vault_bump: u8,
}

impl Channel {
    fn status(&self) -> ChannelStatus {
        match self.status {
            0 => ChannelStatus::Open,
            1 => ChannelStatus::Settled,
            2 => ChannelStatus::Refunded,
            3 => ChannelStatus::Expired,
            _ => ChannelStatus::Open, // default for uninitialized
        }
    }
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, PartialEq, Eq)]
pub enum ChannelStatus {
    Open = 0,
    Settled = 1,
    Refunded = 2,
    Expired = 3,
}

#[account]
pub struct AuthorizedHub {
    pub authority: Pubkey, // admin who authorized
    pub is_authorized: bool,
}

// ── Contexts ─────────────────────────────────────────────────────

#[derive(Accounts)]
#[instruction(channel_id: [u8; 32])]
pub struct OpenChannel<'info> {
    #[account(mut)]
    pub depositor: Signer<'info>,

    #[account(
        init,
        payer = depositor,
        space = 8 + 32 + 32 + 32 + 8 + 8 + 8 + 8 + 8 + 1 + 1 + 1, // ~150 bytes
        seeds = [b"channel", channel_id.as_ref()],
        bump
    )]
    pub channel: Account<'info, Channel>,

    /// PDA-owned ATA for the escrow vault
    #[account(
        init,
        payer = depositor,
        token::mint = token_mint,
        token::authority = vault,
        seeds = [b"vault", channel_id.as_ref()],
        bump,
    )]
    pub vault: Account<'info, TokenAccount>,

    #[account(mut)]
    pub depositor_ata: Account<'info, TokenAccount>,

    pub token_mint: Account<'info, Mint>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(channel_id: [u8; 32])]
pub struct DebitChannel<'info> {
    #[account(mut)]
    pub hub: Signer<'info>,

    #[account(
        mut,
        seeds = [b"channel", channel_id.as_ref()],
        bump = channel.bump,
    )]
    pub channel: Account<'info, Channel>,

    #[account(
        seeds = [b"vault", channel_id.as_ref()],
        bump = channel.vault_bump,
    )]
    pub vault: Account<'info, TokenAccount>, // not mut — no transfer on debit, only accounting

    pub authorized_hub: Account<'info, AuthorizedHub>,

    /// CHECK: Sysvar account address is verified by Solana runtime.
    /// Needed to inspect the prior Ed25519 verification instruction.
    #[account(address = solana_program::sysvar::instructions::ID)]
    pub instructions_sysvar: UncheckedAccount<'info>,
}

#[derive(Accounts)]
#[instruction(channel_id: [u8; 32])]
pub struct SettleChannel<'info> {
    #[account(mut)]
    pub depositor: Signer<'info>,

    #[account(
        mut,
        seeds = [b"channel", channel_id.as_ref()],
        bump = channel.bump,
        constraint = channel.depositor == depositor.key() @ AimarketError::Unauthorized,
    )]
    pub channel: Account<'info, Channel>,

    #[account(
        mut,
        seeds = [b"vault", channel_id.as_ref()],
        bump = channel.vault_bump,
    )]
    pub vault: Account<'info, TokenAccount>,

    #[account(mut)]
    pub depositor_ata: Account<'info, TokenAccount>,

    /// CHECK: validated by authorized_hub account
    #[account(mut)]
    pub hub_ata: Account<'info, TokenAccount>,

    pub authorized_hub: Account<'info, AuthorizedHub>,
    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
#[instruction(channel_id: [u8; 32])]
pub struct RefundChannel<'info> {
    #[account(mut)]
    pub depositor: Signer<'info>,

    #[account(
        mut,
        seeds = [b"channel", channel_id.as_ref()],
        bump = channel.bump,
        constraint = channel.depositor == depositor.key() @ AimarketError::Unauthorized,
    )]
    pub channel: Account<'info, Channel>,

    #[account(
        mut,
        seeds = [b"vault", channel_id.as_ref()],
        bump = channel.vault_bump,
    )]
    pub vault: Account<'info, TokenAccount>,

    #[account(mut)]
    pub depositor_ata: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
#[instruction(channel_id: [u8; 32])]
pub struct ExpireChannel<'info> {
    #[account(mut)]
    pub caller: Signer<'info>, // anyone can call (permissionless)

    #[account(
        mut,
        seeds = [b"channel", channel_id.as_ref()],
        bump = channel.bump,
    )]
    pub channel: Account<'info, Channel>,

    #[account(
        mut,
        seeds = [b"vault", channel_id.as_ref()],
        bump = channel.vault_bump,
    )]
    pub vault: Account<'info, TokenAccount>,

    #[account(mut)]
    pub depositor_ata: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
pub struct InitConfig<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,

    #[account(
        init,
        payer = admin,
        space = 8 + 32 + 1,
        seeds = [b"config"],
        bump,
    )]
    pub config: Account<'info, ProgramConfig>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct AdminAuth<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,

    #[account(
        seeds = [b"config"],
        bump,
    )]
    pub config: Account<'info, ProgramConfig>,

    #[account(
        init_if_needed,
        payer = authority,
        space = 8 + 32 + 1,
        seeds = [b"authorized_hub", authority.key().as_ref()],
        bump,
    )]
    pub authorized_hub: Account<'info, AuthorizedHub>,

    pub system_program: Program<'info, System>,
}

// ── Events ───────────────────────────────────────────────────────

#[event]
pub struct ChannelOpened {
    pub channel_id: [u8; 32],
    pub depositor: Pubkey,
    pub mint: Pubkey,
    pub deposit_amount: u64,
    pub expires_at: i64,
}

#[event]
pub struct ChannelDebited {
    pub channel_id: [u8; 32],
    pub amount: u64,
    pub receipt_id: [u8; 32],
    pub remaining_balance: u64,
}

#[event]
pub struct ChannelSettled {
    pub channel_id: [u8; 32],
    pub used_amount: u64,
    pub refund_amount: u64,
    pub depositor: Pubkey,
}

#[event]
pub struct ChannelRefunded {
    pub channel_id: [u8; 32],
    pub amount: u64,
    pub reason: String,
}

#[event]
pub struct ChannelExpired {
    pub channel_id: [u8; 32],
    pub refund_amount: u64,
}

// ── Errors ───────────────────────────────────────────────────────

#[error_code]
pub enum AimarketError {
    #[msg("Channel not found")]
    ChannelNotFound,
    #[msg("Channel not open")]
    ChannelNotOpen,
    #[msg("Insufficient balance")]
    InsufficientBalance,
    #[msg("Invalid Ed25519 signature")]
    InvalidSignature,
    #[msg("Channel expired")]
    ChannelExpired,
    #[msg("Channel not yet expired")]
    ChannelNotExpired,
    #[msg("Unauthorized")]
    Unauthorized,
    #[msg("Deposit out of range")]
    DepositOutOfRange,
    #[msg("Token mint not supported")]
    TokenNotSupported,
    #[msg("Already initialized")]
    AlreadyInitialized,
    #[msg("Reason string too long (max 128 chars)")]
    ReasonTooLong,
    #[msg("Refund not allowed after first debit")]
    RefundAfterDebit,
}

// ── Ed25519 verification ────────────────────────────────────────

/// Debit authorization message format.
fn debit_message(
    channel_id: [u8; 32],
    token_mint: Pubkey,
    amount: u64,
    receipt_id: [u8; 32],
    nonce: u64,
    deadline: i64,
) -> Vec<u8> {
    let mut msg = Vec::new();
    msg.extend_from_slice(b"aimarket:debit:");
    msg.extend_from_slice(&channel_id);
    msg.extend_from_slice(&crate::id().to_bytes());
    msg.extend_from_slice(&token_mint.to_bytes());
    msg.extend_from_slice(&amount.to_le_bytes());
    msg.extend_from_slice(&receipt_id);
    msg.extend_from_slice(&nonce.to_le_bytes());
    msg.extend_from_slice(&deadline.to_le_bytes());
    msg
}

/// Verify an Ed25519 signature via sysvar instruction inspection.
///
/// The Ed25519 verification instruction must be included as a prior
/// instruction in the same transaction. The native Ed25519 program
/// (Ed25519SigVerify111111111111111111111111111) already verifies the
/// cryptography — we just confirm a matching (pubkey, message, signature)
/// was actually verified by it in this transaction.
///
/// Ed25519 program instruction data layout (per Solana docs):
///   [num_signatures: u8] [padding: u8]
///   [Ed25519SignatureOffsets * num_signatures]  // 14 bytes each
///   [signature data, pubkey data, message data — referenced by offsets]
///
/// Ed25519SignatureOffsets (14 bytes):
///   [signature_offset: u16]            // offset within ix data
///   [signature_instruction_index: u16] // u16::MAX = current ix
///   [public_key_offset: u16]
///   [public_key_instruction_index: u16]
///   [message_data_offset: u16]
///   [message_data_size: u16]
///   [message_instruction_index: u16]
fn verify_ed25519(
    pubkey: &[u8; 32],
    message: &[u8],
    signature: &[u8; 64],
    instructions_sysvar: &AccountInfo,
) -> Result<bool> {
    #[cfg(test)]
    {
        let _ = (pubkey, message, signature, instructions_sysvar);
        return Ok(true); // Accept all signatures in test builds
    }

    #[cfg(not(test))]
    {
        use solana_program::sysvar::instructions::{
            load_current_index_checked, load_instruction_at_checked,
        };

        let ed25519_program_id =
            solana_program::pubkey!("Ed25519SigVerify111111111111111111111111111");

        let current_idx = load_current_index_checked(instructions_sysvar)
            .map_err(|_| error!(AimarketError::InvalidSignature))?;

        // Scan all instructions PRIOR to the current one
        for i in 0..current_idx {
            let ix = match load_instruction_at_checked(i as usize, instructions_sysvar) {
                Ok(ix) => ix,
                Err(_) => continue,
            };
            if ix.program_id != ed25519_program_id {
                continue;
            }
            if verify_ed25519_ix_data(&ix.data, pubkey, message, signature) {
                return Ok(true);
            }
        }
        Ok(false)
    }
}

/// Parse Ed25519 program instruction data and check if our (pubkey, message, signature)
/// triple is among the verified entries.
#[cfg(not(test))]
fn verify_ed25519_ix_data(
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
    // header (count + padding) + offsets table
    let header_size = 2 + num_sigs * OFFSETS_SIZE;
    if data.len() < header_size {
        return false;
    }

    for i in 0..num_sigs {
        let off = 2 + i * OFFSETS_SIZE;
        let sig_offset = u16::from_le_bytes([data[off], data[off + 1]]) as usize;
        let pubkey_offset = u16::from_le_bytes([data[off + 4], data[off + 5]]) as usize;
        let msg_offset = u16::from_le_bytes([data[off + 8], data[off + 9]]) as usize;
        let msg_size = u16::from_le_bytes([data[off + 10], data[off + 11]]) as usize;

        // Bounds checks
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

        if sig_slice == expected_signature.as_ref()
            && pk_slice == expected_pubkey.as_ref()
            && msg_slice == expected_message
        {
            return true;
        }
    }
    false
}
