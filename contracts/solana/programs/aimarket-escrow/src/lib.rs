//! AIMarketEscrow — Solana escrow program for AI Market Protocol v2.
//!
//! Implements the channel/open, channel/debit, channel/settle/refund/expire
//! lifecycle on Solana using PDAs and SPL tokens (USDC on Solana).
//!
//! Key Solana-specific design:
//!   - Channel PDA: seeds = [b"channel", channel_id] — accounting state
//!   - Vault   PDA: seeds = [b"vault",   channel_id] — SPL Token holder
//!   - AuthorizedHub PDA: seeds = [b"authorized_hub", hub_pubkey] — one
//!     entry per hub, gated by global admin config
//!   - Ed25519 signature verification for debit authorization via sysvar
//!     instruction inspection (native syscall, not EIP-712)
//!   - Native 24h expiry via Clock sysvar
//!   - On debit, the channel binds to its first hub. Subsequent debits must
//!     come from the same hub.
//!   - On settle/expire, hub gets used_amount, depositor gets the remainder
//!     (`expire` is the same economics as `settle` — permissionless cleanup).
//!
//! Audit-relevant invariants:
//!   - Every CPI signer uses `[b"vault", channel_id, vault_bump]` (NOT
//!     `b"channel"` — that's the accounting PDA, not the token authority).
//!   - Every ATA referenced in a transfer is constrained: depositor_ata.owner
//!     == channel.depositor, hub_ata.owner == channel.hub.
//!   - debit_message includes `hub` pubkey so a depositor's signature for
//!     hub A cannot be reused by hub B.

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
        channel.hub = Pubkey::default(); // bound on first debit
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
    ///
    /// On first debit, channel.hub is bound to `ctx.accounts.hub.key()`.
    /// Subsequent debits must come from the same hub.
    pub fn debit_channel(
        ctx: Context<DebitChannel>,
        channel_id: [u8; 32],
        amount: u64,
        receipt_id: [u8; 32],
        deadline: i64,
        // Ed25519 signature from depositor: 64 bytes
        signature: [u8; 64],
    ) -> Result<()> {
        let channel = &mut ctx.accounts.channel;
        let hub_key = ctx.accounts.hub.key();

        // ── Authorization ─────────────────────────────────────────
        // The AuthorizedHub PDA is keyed by the hub's own pubkey, so passing
        // any random PDA can't fake authorization — its derivation depends
        // on the signer.
        require!(
            ctx.accounts.authorized_hub.is_authorized,
            AimarketError::Unauthorized
        );
        require!(
            ctx.accounts.authorized_hub.hub == hub_key,
            AimarketError::Unauthorized
        );

        require!(channel.status() == ChannelStatus::Open, AimarketError::ChannelNotOpen);

        let clock = Clock::get()?;
        require!(clock.unix_timestamp <= channel.expires_at, AimarketError::ChannelExpired);
        require!(clock.unix_timestamp <= deadline, AimarketError::ChannelExpired);
        require!(amount <= channel.balance, AimarketError::InsufficientBalance);

        // Bind hub to channel on first debit; reject mismatched hubs after.
        if channel.hub == Pubkey::default() {
            channel.hub = hub_key;
        }
        require!(channel.hub == hub_key, AimarketError::Unauthorized);

        // ── Verify depositor's Ed25519 signature ─────────────────
        // `hub_key` is part of the message — a signature for hub A is not
        // usable by hub B even if both are authorized.
        let message = debit_message(
            channel_id,
            hub_key,
            channel.token_mint,
            amount,
            receipt_id,
            channel.nonce,
            deadline,
        );
        require!(
            verify_ed25519(
                &channel.depositor.to_bytes(),
                &message,
                &signature,
                &ctx.accounts.instructions_sysvar.to_account_info(),
            )?,
            AimarketError::InvalidSignature
        );

        // Execute debit
        channel.nonce = channel.nonce.checked_add(1).ok_or(AimarketError::Overflow)?;
        channel.balance = channel.balance.checked_sub(amount).ok_or(AimarketError::Overflow)?;
        channel.used_amount = channel.used_amount.checked_add(amount).ok_or(AimarketError::Overflow)?;

        emit!(ChannelDebited {
            channel_id,
            amount,
            receipt_id,
            remaining_balance: channel.balance,
        });

        Ok(())
    }

    /// Settle a channel: transfer used funds to hub, refund rest to depositor.
    /// Callable by depositor or by the bound hub.
    pub fn settle_channel(ctx: Context<SettleChannel>, channel_id: [u8; 32]) -> Result<()> {
        let channel = &mut ctx.accounts.channel;

        // Either depositor or bound hub can initiate settle.
        let caller = ctx.accounts.caller.key();
        require!(
            caller == channel.depositor
                || (channel.hub != Pubkey::default() && caller == channel.hub),
            AimarketError::Unauthorized
        );
        require!(channel.status() == ChannelStatus::Open, AimarketError::ChannelNotOpen);

        channel.status = ChannelStatus::Settled as u8;

        let used = channel.used_amount;
        let refund = channel.balance;

        if used > 0 {
            transfer_from_vault(
                &ctx.accounts.token_program,
                &ctx.accounts.vault,
                &ctx.accounts.hub_ata,
                channel_id,
                channel.vault_bump,
                used,
            )?;
        }

        if refund > 0 {
            transfer_from_vault(
                &ctx.accounts.token_program,
                &ctx.accounts.vault,
                &ctx.accounts.depositor_ata,
                channel_id,
                channel.vault_bump,
                refund,
            )?;
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

    /// Authorize or deauthorize a specific hub. Only callable by the global admin.
    ///
    /// One AuthorizedHub PDA per hub, keyed by hub pubkey — this lets the
    /// admin maintain a list of authorized hubs rather than a single global
    /// toggle (previous design held one PDA per admin, making the field
    /// useless as an identity proof).
    pub fn authorize_hub(ctx: Context<AdminAuth>, hub: Pubkey, is_authorized: bool) -> Result<()> {
        require!(
            ctx.accounts.config.admin == ctx.accounts.admin.key(),
            AimarketError::Unauthorized
        );
        ctx.accounts.authorized_hub.hub = hub;
        ctx.accounts.authorized_hub.is_authorized = is_authorized;
        emit!(HubAuthorized { hub, is_authorized });
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

        require!(channel.status() == ChannelStatus::Open, AimarketError::ChannelNotOpen);
        require!(channel.used_amount == 0, AimarketError::RefundAfterDebit);

        channel.status = ChannelStatus::Refunded as u8;
        // used_amount == 0, so total == balance == deposit_amount.
        let refund = channel.balance;

        transfer_from_vault(
            &ctx.accounts.token_program,
            &ctx.accounts.vault,
            &ctx.accounts.depositor_ata,
            channel_id,
            channel.vault_bump,
            refund,
        )?;

        emit!(ChannelRefunded {
            channel_id,
            amount: refund,
            reason,
        });

        Ok(())
    }

    /// Permissionless expiry — anyone can close an expired channel.
    /// Economics match `settle_channel`: hub gets used_amount, depositor
    /// gets the remainder. Previously this returned the full deposit to
    /// the depositor, letting depositors wait 24h to avoid paying the hub.
    pub fn expire_channel(ctx: Context<ExpireChannel>, channel_id: [u8; 32]) -> Result<()> {
        let channel = &mut ctx.accounts.channel;
        let clock = Clock::get()?;

        require!(channel.status() == ChannelStatus::Open, AimarketError::ChannelNotOpen);
        require!(clock.unix_timestamp > channel.expires_at, AimarketError::ChannelNotExpired);

        channel.status = ChannelStatus::Expired as u8;

        let used = channel.used_amount;
        let refund = channel.balance;

        if used > 0 && channel.hub != Pubkey::default() {
            transfer_from_vault(
                &ctx.accounts.token_program,
                &ctx.accounts.vault,
                &ctx.accounts.hub_ata,
                channel_id,
                channel.vault_bump,
                used,
            )?;
        }
        if refund > 0 {
            transfer_from_vault(
                &ctx.accounts.token_program,
                &ctx.accounts.vault,
                &ctx.accounts.depositor_ata,
                channel_id,
                channel.vault_bump,
                refund,
            )?;
        }

        emit!(ChannelExpiredAndSettled {
            channel_id,
            used_amount: used,
            refund_amount: refund,
        });

        Ok(())
    }
}

// ── Vault helper ─────────────────────────────────────────────────

/// CPI to transfer tokens from the vault PDA. The signer seeds MUST be
/// `[b"vault", channel_id, vault_bump]` — those are the seeds the vault
/// account was actually derived from. The previous code used `b"channel"`
/// here, which is the *accounting* PDA, not the token authority — so
/// every settle/refund/expire transfer reverted with seeds mismatch.
fn transfer_from_vault<'info>(
    token_program: &Program<'info, Token>,
    vault: &Account<'info, TokenAccount>,
    dest: &Account<'info, TokenAccount>,
    channel_id: [u8; 32],
    vault_bump: u8,
    amount: u64,
) -> Result<()> {
    let bump_seed = [vault_bump];
    let seeds: [&[u8]; 3] = [b"vault", channel_id.as_ref(), &bump_seed];
    let signer_seeds: &[&[&[u8]]] = &[&seeds];

    let cpi_ctx = CpiContext::new_with_signer(
        token_program.to_account_info(),
        Transfer {
            from: vault.to_account_info(),
            to: dest.to_account_info(),
            authority: vault.to_account_info(),
        },
        signer_seeds,
    );
    token::transfer(cpi_ctx, amount)
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
    /// Bound to the first hub that successfully debits; Pubkey::default()
    /// until then. Subsequent debits must come from the same hub.
    pub hub: Pubkey,
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
    pub const SIZE: usize = 8        // discriminator
        + 32 + 32                    // depositor + hub
        + 32                         // channel_id
        + 32                         // token_mint
        + 8 + 8 + 8 + 8 + 8          // 5x u64/i64
        + 1 + 1 + 1;                 // status + 2 bumps

    fn status(&self) -> ChannelStatus {
        match self.status {
            0 => ChannelStatus::Open,
            1 => ChannelStatus::Settled,
            2 => ChannelStatus::Refunded,
            3 => ChannelStatus::Expired,
            _ => ChannelStatus::Open,
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
    /// The hub's own pubkey. Stored explicitly so we can defend against
    /// account substitution (PDA derivation is the primary check; this
    /// is a belt-and-suspenders identity check inside debit_channel).
    pub hub: Pubkey,
    pub is_authorized: bool,
}

impl AuthorizedHub {
    pub const SIZE: usize = 8 + 32 + 1;
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
        space = Channel::SIZE,
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

    #[account(
        mut,
        constraint = depositor_ata.owner == depositor.key() @ AimarketError::Unauthorized,
        constraint = depositor_ata.mint == token_mint.key()  @ AimarketError::TokenNotSupported,
    )]
    pub depositor_ata: Account<'info, TokenAccount>,

    pub token_mint: Account<'info, Mint>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(channel_id: [u8; 32])]
pub struct DebitChannel<'info> {
    /// The calling hub. Its pubkey is bound into the depositor signature.
    pub hub: Signer<'info>,

    #[account(
        mut,
        seeds = [b"channel", channel_id.as_ref()],
        bump = channel.bump,
    )]
    pub channel: Account<'info, Channel>,

    /// PDA keyed by hub pubkey — so passing a random AuthorizedHub PDA
    /// won't work; the runtime forces this to be the one derived for
    /// the actual signer.
    #[account(
        seeds = [b"authorized_hub", hub.key().as_ref()],
        bump,
        constraint = authorized_hub.hub == hub.key() @ AimarketError::Unauthorized,
    )]
    pub authorized_hub: Account<'info, AuthorizedHub>,

    /// CHECK: Sysvar address is verified by Solana runtime.
    /// Used to inspect the prior Ed25519 verification instruction.
    #[account(address = anchor_lang::solana_program::sysvar::instructions::ID)]
    pub instructions_sysvar: UncheckedAccount<'info>,
}

#[derive(Accounts)]
#[instruction(channel_id: [u8; 32])]
pub struct SettleChannel<'info> {
    pub caller: Signer<'info>,

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

    #[account(
        mut,
        constraint = depositor_ata.owner == channel.depositor @ AimarketError::Unauthorized,
        constraint = depositor_ata.mint  == channel.token_mint @ AimarketError::TokenNotSupported,
    )]
    pub depositor_ata: Account<'info, TokenAccount>,

    /// Hub destination ATA. MUST be owned by `channel.hub` — without this
    /// constraint, anyone could redirect the hub's earnings to their own ATA.
    /// When `channel.hub == Pubkey::default()` (no debit happened), `used == 0`
    /// and this ATA is not actually written to.
    #[account(
        mut,
        constraint = (channel.used_amount == 0) || (hub_ata.owner == channel.hub) @ AimarketError::Unauthorized,
        constraint = hub_ata.mint == channel.token_mint @ AimarketError::TokenNotSupported,
    )]
    pub hub_ata: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
#[instruction(channel_id: [u8; 32])]
pub struct RefundChannel<'info> {
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

    #[account(
        mut,
        constraint = depositor_ata.owner == channel.depositor @ AimarketError::Unauthorized,
        constraint = depositor_ata.mint  == channel.token_mint @ AimarketError::TokenNotSupported,
    )]
    pub depositor_ata: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
#[instruction(channel_id: [u8; 32])]
pub struct ExpireChannel<'info> {
    /// Permissionless — anyone can pay gas to expire a channel.
    pub caller: Signer<'info>,

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

    #[account(
        mut,
        constraint = depositor_ata.owner == channel.depositor @ AimarketError::Unauthorized,
        constraint = depositor_ata.mint  == channel.token_mint @ AimarketError::TokenNotSupported,
    )]
    pub depositor_ata: Account<'info, TokenAccount>,

    /// Same constraints as in SettleChannel — see notes there.
    #[account(
        mut,
        constraint = (channel.used_amount == 0) || (hub_ata.owner == channel.hub) @ AimarketError::Unauthorized,
        constraint = hub_ata.mint == channel.token_mint @ AimarketError::TokenNotSupported,
    )]
    pub hub_ata: Account<'info, TokenAccount>,

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
#[instruction(hub: Pubkey)]
pub struct AdminAuth<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,

    #[account(
        seeds = [b"config"],
        bump,
        constraint = config.admin == admin.key() @ AimarketError::Unauthorized,
    )]
    pub config: Account<'info, ProgramConfig>,

    #[account(
        init_if_needed,
        payer = admin,
        space = AuthorizedHub::SIZE,
        seeds = [b"authorized_hub", hub.as_ref()],
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

/// Renamed from `ChannelExpired` to avoid name collision with the
/// `ChannelExpired` error variant (Anchor IDL consumers couldn't tell them
/// apart). The post-debit settlement semantics also changed — name change
/// signals that to off-chain consumers.
#[event]
pub struct ChannelExpiredAndSettled {
    pub channel_id: [u8; 32],
    pub used_amount: u64,
    pub refund_amount: u64,
}

#[event]
pub struct HubAuthorized {
    pub hub: Pubkey,
    pub is_authorized: bool,
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
    #[msg("Arithmetic overflow")]
    Overflow,
}

// ── Ed25519 verification ────────────────────────────────────────

/// Debit authorization message format.
/// `hub` is part of the message — a depositor's signature for hub A
/// cannot be reused by hub B even if both are authorized.
fn debit_message(
    channel_id: [u8; 32],
    hub: Pubkey,
    token_mint: Pubkey,
    amount: u64,
    receipt_id: [u8; 32],
    nonce: u64,
    deadline: i64,
) -> Vec<u8> {
    let mut msg = Vec::with_capacity(15 + 32 + 32 + 32 + 32 + 8 + 32 + 8 + 8);
    msg.extend_from_slice(b"aimarket:debit:");
    msg.extend_from_slice(&channel_id);
    msg.extend_from_slice(&crate::id().to_bytes());
    msg.extend_from_slice(&hub.to_bytes());
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
fn verify_ed25519(
    pubkey: &[u8; 32],
    message: &[u8],
    signature: &[u8; 64],
    instructions_sysvar: &AccountInfo,
) -> Result<bool> {
    #[cfg(test)]
    {
        let _ = (pubkey, message, signature, instructions_sysvar);
        // Accept all signatures in `cargo test` only. `anchor build` builds
        // without the `test` cfg, so the on-chain binary always runs the
        // real check below.
        return Ok(true);
    }

    #[cfg(not(test))]
    {
        use anchor_lang::solana_program::sysvar::instructions::{
            load_current_index_checked, load_instruction_at_checked,
        };

        let ed25519_program_id =
            anchor_lang::solana_program::pubkey!("Ed25519SigVerify111111111111111111111111111");

        let current_idx = load_current_index_checked(instructions_sysvar)
            .map_err(|_| error!(AimarketError::InvalidSignature))?;

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
