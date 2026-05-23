//! ACEX Capital — Solana programs for Agent Listing Protocol (ALP) + collateral.
//!
//! Mirrors EVM: apply → audit → approve → deposit USDC collateral → lock for notes.
//! CapShares SPL mint is recorded on approval (mint created in same tx via CPI or pre-created).

use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

declare_id!("AcexCap1italMark3tL1st1ngReg1stryPDA");

pub const MIN_AUDIT_SCORE_BPS: u16 = 7000;

#[program]
pub mod acex_capital {
    use super::*;

    pub fn initialize(ctx: Context<Initialize>) -> Result<()> {
        let cfg = &mut ctx.accounts.config;
        require!(!cfg.initialized, AcexError::AlreadyInitialized);
        cfg.admin = ctx.accounts.admin.key();
        cfg.usdc_mint = ctx.accounts.usdc_mint.key();
        cfg.initialized = true;
        cfg.paused = false;
        Ok(())
    }

    pub fn set_paused(ctx: Context<AdminOnly>, paused: bool) -> Result<()> {
        ctx.accounts.config.paused = paused;
        Ok(())
    }

    pub fn set_auditor(ctx: Context<SetAuditor>, is_auditor: bool) -> Result<()> {
        ctx.accounts.auditor_record.is_auditor = is_auditor;
        Ok(())
    }

    pub fn apply_listing(
        ctx: Context<ApplyListing>,
        listing_id: [u8; 32],
        metadata_hash: [u8; 32],
    ) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        let listing = &mut ctx.accounts.listing;
        listing.agent = ctx.accounts.agent.key();
        listing.listing_id = listing_id;
        listing.metadata_hash = metadata_hash;
        listing.status = ListingStatus::Pending as u8;
        listing.audit_score_bps = 0;
        listing.share_mint = Pubkey::default();
        listing.bump = ctx.bumps.listing;
        emit!(ListingApplied {
            listing_id,
            agent: listing.agent,
            metadata_hash,
        });
        Ok(())
    }

    pub fn record_audit(ctx: Context<RecordAudit>, listing_id: [u8; 32], score_bps: u16) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        require!(ctx.accounts.auditor_record.is_auditor, AcexError::Unauthorized);
        let listing = &mut ctx.accounts.listing;
        require!(listing.agent != Pubkey::default(), AcexError::ListingNotFound);
        listing.audit_score_bps = score_bps;
        listing.status = ListingStatus::UnderAudit as u8;
        emit!(ListingAudited {
            listing_id,
            score_bps,
            auditor: ctx.accounts.auditor.key(),
        });
        Ok(())
    }

    pub fn approve_listing(
        ctx: Context<ApproveListing>,
        listing_id: [u8; 32],
        share_mint: Pubkey,
        max_supply: u64,
    ) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        let listing = &mut ctx.accounts.listing;
        require!(
            listing.status == ListingStatus::Pending as u8
                || listing.status == ListingStatus::UnderAudit as u8,
            AcexError::InvalidStatus
        );
        require!(listing.audit_score_bps >= MIN_AUDIT_SCORE_BPS, AcexError::AuditScoreTooLow);

        listing.share_mint = share_mint;
        listing.max_supply = max_supply;
        listing.status = ListingStatus::Approved as u8;
        listing.listed_at = Clock::get()?.unix_timestamp;

        emit!(ListingApproved {
            listing_id,
            share_mint,
            max_supply,
        });
        Ok(())
    }

    pub fn reject_listing(ctx: Context<RejectListing>, listing_id: [u8; 32]) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        let listing = &mut ctx.accounts.listing;
        listing.status = ListingStatus::Rejected as u8;
        emit!(ListingRejected { listing_id });
        Ok(())
    }

    /// Deposit USDC collateral into listing vault PDA.
    pub fn deposit_collateral(
        ctx: Context<DepositCollateral>,
        listing_id: [u8; 32],
        amount: u64,
    ) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        require!(amount > 0, AcexError::ZeroAmount);

        let listing = &ctx.accounts.listing;
        require!(listing.status == ListingStatus::Approved as u8, AcexError::InvalidStatus);

        token::transfer(
            CpiContext::new(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.depositor_ata.to_account_info(),
                    to: ctx.accounts.vault_ata.to_account_info(),
                    authority: ctx.accounts.depositor.to_account_info(),
                },
            ),
            amount,
        )?;

        let collateral = &mut ctx.accounts.collateral;
        if collateral.listing_id == [0u8; 32] {
            collateral.listing_id = listing_id;
            collateral.bump = ctx.bumps.collateral;
        }
        collateral.usdc_balance = collateral
            .usdc_balance
            .checked_add(amount)
            .ok_or(AcexError::MathOverflow)?;

        emit!(CollateralDeposited {
            listing_id,
            amount,
            depositor: ctx.accounts.depositor.key(),
        });
        Ok(())
    }

    /// Lock collateral backing AgentNotes (admin/registry only).
    pub fn lock_collateral(
        ctx: Context<LockCollateral>,
        listing_id: [u8; 32],
        amount: u64,
    ) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        let collateral = &mut ctx.accounts.collateral;
        require!(collateral.usdc_balance >= amount, AcexError::InsufficientCollateral);
        collateral.usdc_balance -= amount;
        collateral.locked_for_notes = collateral
            .locked_for_notes
            .checked_add(amount)
            .ok_or(AcexError::MathOverflow)?;
        emit!(CollateralLocked { listing_id, amount });
        Ok(())
    }

    /// Release locked collateral to agent (maturity / admin).
    pub fn release_collateral(
        ctx: Context<ReleaseCollateral>,
        listing_id: [u8; 32],
        amount: u64,
    ) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        let collateral = &mut ctx.accounts.collateral;
        require!(collateral.locked_for_notes >= amount, AcexError::InsufficientCollateral);
        collateral.locked_for_notes -= amount;

        let seeds: &[&[u8]] = &[b"vault", listing_id.as_ref(), &[ctx.bumps.vault_authority]];
        token::transfer(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.vault_ata.to_account_info(),
                    to: ctx.accounts.recipient_ata.to_account_info(),
                    authority: ctx.accounts.vault_authority.to_account_info(),
                },
                &[seeds],
            ),
            amount,
        )?;
        emit!(CollateralReleased {
            listing_id,
            amount,
            recipient: ctx.accounts.recipient.key(),
        });
        Ok(())
    }

    // ── CapSense Options (Phase 2) ─────────────────────────────

    /// Create a CapSense call option series on a listing revenue index.
    pub fn create_capsense_series(
        ctx: Context<CreateCapsenseSeries>,
        listing_id: [u8; 32],
        strike_index_bps: u64,
        expiry_ts: i64,
    ) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        let listing = &ctx.accounts.listing;
        require!(listing.status == ListingStatus::Approved as u8, AcexError::InvalidStatus);
        require!(expiry_ts > Clock::get()?.unix_timestamp, AcexError::OptionExpired);

        let series = &mut ctx.accounts.series;
        series.listing_id = listing_id;
        series.strike_index_bps = strike_index_bps;
        series.expiry_ts = expiry_ts;
        series.open_interest = 0;
        series.premium_pool = 0;
        series.settled = false;
        series.bump = ctx.bumps.series;

        emit!(CapsenseSeriesCreated {
            listing_id,
            strike_index_bps,
            expiry_ts,
            series: series.key(),
        });
        Ok(())
    }

    /// Buy CapSense contracts; premium USDC flows to series vault.
    pub fn buy_capsense_option(
        ctx: Context<BuyCapsenseOption>,
        listing_id: [u8; 32],
        strike_index_bps: u64,
        expiry_ts: i64,
        contracts: u64,
        premium_per_contract: u64,
    ) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        require!(contracts > 0, AcexError::ZeroAmount);
        require!(premium_per_contract > 0, AcexError::ZeroAmount);

        let series = &mut ctx.accounts.series;
        require!(!series.settled, AcexError::OptionSettled);
        require!(Clock::get()?.unix_timestamp < series.expiry_ts, AcexError::OptionExpired);

        let total_premium = premium_per_contract
            .checked_mul(contracts)
            .ok_or(AcexError::MathOverflow)?;

        token::transfer(
            CpiContext::new(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.buyer_ata.to_account_info(),
                    to: ctx.accounts.series_vault_ata.to_account_info(),
                    authority: ctx.accounts.buyer.to_account_info(),
                },
            ),
            total_premium,
        )?;

        let position = &mut ctx.accounts.position;
        if position.contracts == 0 {
            position.buyer = ctx.accounts.buyer.key();
            position.series = series.key();
            position.exercised = false;
            position.bump = ctx.bumps.position;
        }
        position.contracts = position
            .contracts
            .checked_add(contracts)
            .ok_or(AcexError::MathOverflow)?;
        position.premium_paid = position
            .premium_paid
            .checked_add(total_premium)
            .ok_or(AcexError::MathOverflow)?;

        series.open_interest = series
            .open_interest
            .checked_add(contracts)
            .ok_or(AcexError::MathOverflow)?;
        series.premium_pool = series
            .premium_pool
            .checked_add(total_premium)
            .ok_or(AcexError::MathOverflow)?;

        emit!(CapsenseOptionPurchased {
            listing_id,
            buyer: ctx.accounts.buyer.key(),
            contracts,
            premium: total_premium,
        });
        Ok(())
    }

    /// Exercise in-the-money CapSense calls against index level (bps × 1e-4 USD).
    pub fn exercise_capsense_option(
        ctx: Context<ExerciseCapsenseOption>,
        listing_id: [u8; 32],
        strike_index_bps: u64,
        expiry_ts: i64,
        index_level_bps: u64,
    ) -> Result<()> {
        require!(!ctx.accounts.config.paused, AcexError::Paused);
        let series = &ctx.accounts.series;
        require!(!series.settled, AcexError::OptionSettled);
        let now = Clock::get()?.unix_timestamp;
        require!(now <= series.expiry_ts, AcexError::OptionExpired);
        require!(index_level_bps > series.strike_index_bps, AcexError::OptionOutOfMoney);

        let position = &mut ctx.accounts.position;
        require!(!position.exercised, AcexError::OptionAlreadyExercised);
        require!(position.contracts > 0, AcexError::ZeroAmount);

        let intrinsic_bps = index_level_bps
            .checked_sub(series.strike_index_bps)
            .ok_or(AcexError::MathOverflow)?;
        let payout = (intrinsic_bps as u128)
            .checked_mul(position.contracts as u128)
            .ok_or(AcexError::MathOverflow)?
            .checked_div(10_000)
            .ok_or(AcexError::MathOverflow)? as u64;
        require!(payout > 0, AcexError::ZeroAmount);
        require!(ctx.accounts.series_vault_ata.amount >= payout, AcexError::InsufficientCollateral);

        let seeds: &[&[u8]] = &[
            b"capsense_vault",
            listing_id.as_ref(),
            &strike_index_bps.to_le_bytes(),
            &expiry_ts.to_le_bytes(),
            &[ctx.bumps.series_vault_authority],
        ];
        token::transfer(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.series_vault_ata.to_account_info(),
                    to: ctx.accounts.buyer_ata.to_account_info(),
                    authority: ctx.accounts.series_vault_authority.to_account_info(),
                },
                &[seeds],
            ),
            payout,
        )?;

        position.exercised = true;
        emit!(CapsenseOptionExercised {
            listing_id,
            buyer: position.buyer,
            payout,
            index_level_bps,
        });
        Ok(())
    }
}

// ── Accounts ─────────────────────────────────────────────────────

#[account]
pub struct ProgramConfig {
    pub admin: Pubkey,
    pub usdc_mint: Pubkey,
    pub initialized: bool,
    pub paused: bool,
}

#[account]
pub struct AuditorRecord {
    pub is_auditor: bool,
}

#[account]
pub struct Listing {
    pub agent: Pubkey,
    pub listing_id: [u8; 32],
    pub metadata_hash: [u8; 32],
    pub audit_score_bps: u16,
    pub status: u8,
    pub share_mint: Pubkey,
    pub max_supply: u64,
    pub listed_at: i64,
    pub bump: u8,
}

#[account]
pub struct CollateralAccount {
    pub listing_id: [u8; 32],
    pub usdc_balance: u64,
    pub locked_for_notes: u64,
    pub bump: u8,
}

#[account]
pub struct CapsenseSeries {
    pub listing_id: [u8; 32],
    pub strike_index_bps: u64,
    pub expiry_ts: i64,
    pub open_interest: u64,
    pub premium_pool: u64,
    pub settled: bool,
    pub bump: u8,
}

#[account]
pub struct CapsensePosition {
    pub buyer: Pubkey,
    pub series: Pubkey,
    pub contracts: u64,
    pub premium_paid: u64,
    pub exercised: bool,
    pub bump: u8,
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, PartialEq, Eq)]
pub enum ListingStatus {
    Pending = 0,
    UnderAudit = 1,
    Approved = 2,
    Rejected = 3,
    Delisted = 4,
}

// ── Contexts ─────────────────────────────────────────────────────

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(init, payer = admin, space = 8 + 32 + 32 + 1 + 1, seeds = [b"config"], bump)]
    pub config: Account<'info, ProgramConfig>,
    pub usdc_mint: Account<'info, Mint>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct AdminOnly<'info> {
    pub admin: Signer<'info>,
    #[account(seeds = [b"config"], bump, has_one = admin @ AcexError::Unauthorized)]
    pub config: Account<'info, ProgramConfig>,
}

#[derive(Accounts)]
pub struct SetAuditor<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(seeds = [b"config"], bump, has_one = admin @ AcexError::Unauthorized)]
    pub config: Account<'info, ProgramConfig>,
    /// CHECK: auditor pubkey in seeds
    pub auditor: UncheckedAccount<'info>,
    #[account(init_if_needed, payer = admin, space = 8 + 1, seeds = [b"auditor", auditor.key().as_ref()], bump)]
    pub auditor_record: Account<'info, AuditorRecord>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32])]
pub struct ApplyListing<'info> {
    #[account(mut)]
    pub agent: Signer<'info>,
    #[account(seeds = [b"config"], bump)]
    pub config: Account<'info, ProgramConfig>,
    #[account(
        init,
        payer = agent,
        space = 8 + 32 + 32 + 2 + 1 + 32 + 8 + 8 + 1,
        seeds = [b"listing", listing_id.as_ref()],
        bump
    )]
    pub listing: Account<'info, Listing>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32])]
pub struct RecordAudit<'info> {
    pub auditor: Signer<'info>,
    #[account(seeds = [b"config"], bump)]
    pub config: Account<'info, ProgramConfig>,
    #[account(seeds = [b"auditor", auditor.key().as_ref()], bump)]
    pub auditor_record: Account<'info, AuditorRecord>,
    #[account(mut, seeds = [b"listing", listing_id.as_ref()], bump = listing.bump)]
    pub listing: Account<'info, Listing>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32])]
pub struct ApproveListing<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(seeds = [b"config"], bump, has_one = admin @ AcexError::Unauthorized)]
    pub config: Account<'info, ProgramConfig>,
    #[account(mut, seeds = [b"listing", listing_id.as_ref()], bump = listing.bump)]
    pub listing: Account<'info, Listing>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32])]
pub struct RejectListing<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(seeds = [b"config"], bump, has_one = admin @ AcexError::Unauthorized)]
    pub config: Account<'info, ProgramConfig>,
    #[account(mut, seeds = [b"listing", listing_id.as_ref()], bump = listing.bump)]
    pub listing: Account<'info, Listing>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32])]
pub struct DepositCollateral<'info> {
    #[account(mut)]
    pub depositor: Signer<'info>,
    #[account(seeds = [b"config"], bump)]
    pub config: Account<'info, ProgramConfig>,
    #[account(seeds = [b"listing", listing_id.as_ref()], bump = listing.bump)]
    pub listing: Account<'info, Listing>,
    #[account(
        init_if_needed,
        payer = depositor,
        space = 8 + 32 + 8 + 8 + 1,
        seeds = [b"collateral", listing_id.as_ref()],
        bump
    )]
    pub collateral: Account<'info, CollateralAccount>,
    /// CHECK: PDA authority for vault ATA
    #[account(seeds = [b"vault", listing_id.as_ref()], bump)]
    pub vault_authority: UncheckedAccount<'info>,
    #[account(
        init_if_needed,
        payer = depositor,
        token::mint = usdc_mint,
        token::authority = vault_authority,
        seeds = [b"vault_ata", listing_id.as_ref()],
        bump,
    )]
    pub vault_ata: Account<'info, TokenAccount>,
    #[account(mut)]
    pub depositor_ata: Account<'info, TokenAccount>,
    pub usdc_mint: Account<'info, Mint>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32])]
pub struct LockCollateral<'info> {
    pub admin: Signer<'info>,
    #[account(seeds = [b"config"], bump, has_one = admin @ AcexError::Unauthorized)]
    pub config: Account<'info, ProgramConfig>,
    #[account(mut, seeds = [b"collateral", listing_id.as_ref()], bump)]
    pub collateral: Account<'info, CollateralAccount>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32], strike_index_bps: u64, expiry_ts: i64)]
pub struct CreateCapsenseSeries<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(seeds = [b"config"], bump, has_one = admin @ AcexError::Unauthorized)]
    pub config: Account<'info, ProgramConfig>,
    #[account(seeds = [b"listing", listing_id.as_ref()], bump = listing.bump)]
    pub listing: Account<'info, Listing>,
    #[account(
        init,
        payer = admin,
        space = 8 + 32 + 8 + 8 + 8 + 8 + 1 + 1,
        seeds = [
            b"capsense",
            listing_id.as_ref(),
            &strike_index_bps.to_le_bytes(),
            &expiry_ts.to_le_bytes(),
        ],
        bump
    )]
    pub series: Account<'info, CapsenseSeries>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32], strike_index_bps: u64, expiry_ts: i64)]
pub struct BuyCapsenseOption<'info> {
    #[account(mut)]
    pub buyer: Signer<'info>,
    #[account(seeds = [b"config"], bump)]
    pub config: Account<'info, ProgramConfig>,
    #[account(
        mut,
        seeds = [
            b"capsense",
            listing_id.as_ref(),
            &strike_index_bps.to_le_bytes(),
            &expiry_ts.to_le_bytes(),
        ],
        bump = series.bump
    )]
    pub series: Account<'info, CapsenseSeries>,
    #[account(
        init_if_needed,
        payer = buyer,
        space = 8 + 32 + 32 + 8 + 8 + 1 + 1,
        seeds = [b"capsense_pos", buyer.key().as_ref(), series.key().as_ref()],
        bump
    )]
    pub position: Account<'info, CapsensePosition>,
    /// CHECK: series vault authority
    #[account(
        seeds = [
            b"capsense_vault",
            listing_id.as_ref(),
            &strike_index_bps.to_le_bytes(),
            &expiry_ts.to_le_bytes(),
        ],
        bump
    )]
    pub series_vault_authority: UncheckedAccount<'info>,
    #[account(
        init_if_needed,
        payer = buyer,
        token::mint = usdc_mint,
        token::authority = series_vault_authority,
        seeds = [
            b"capsense_vault_ata",
            listing_id.as_ref(),
            &strike_index_bps.to_le_bytes(),
            &expiry_ts.to_le_bytes(),
        ],
        bump,
    )]
    pub series_vault_ata: Account<'info, TokenAccount>,
    #[account(mut)]
    pub buyer_ata: Account<'info, TokenAccount>,
    pub usdc_mint: Account<'info, Mint>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32], strike_index_bps: u64, expiry_ts: i64)]
pub struct ExerciseCapsenseOption<'info> {
    #[account(mut)]
    pub buyer: Signer<'info>,
    #[account(seeds = [b"config"], bump)]
    pub config: Account<'info, ProgramConfig>,
    #[account(
        seeds = [
            b"capsense",
            listing_id.as_ref(),
            &strike_index_bps.to_le_bytes(),
            &expiry_ts.to_le_bytes(),
        ],
        bump = series.bump
    )]
    pub series: Account<'info, CapsenseSeries>,
    #[account(
        mut,
        seeds = [b"capsense_pos", buyer.key().as_ref(), series.key().as_ref()],
        bump = position.bump,
        has_one = buyer @ AcexError::Unauthorized
    )]
    pub position: Account<'info, CapsensePosition>,
    /// CHECK: vault PDA
    #[account(
        seeds = [
            b"capsense_vault",
            listing_id.as_ref(),
            &strike_index_bps.to_le_bytes(),
            &expiry_ts.to_le_bytes(),
        ],
        bump
    )]
    pub series_vault_authority: UncheckedAccount<'info>,
    #[account(
        mut,
        seeds = [
            b"capsense_vault_ata",
            listing_id.as_ref(),
            &strike_index_bps.to_le_bytes(),
            &expiry_ts.to_le_bytes(),
        ],
        bump
    )]
    pub series_vault_ata: Account<'info, TokenAccount>,
    #[account(mut)]
    pub buyer_ata: Account<'info, TokenAccount>,
    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
#[instruction(listing_id: [u8; 32])]
pub struct ReleaseCollateral<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(seeds = [b"config"], bump, has_one = admin @ AcexError::Unauthorized)]
    pub config: Account<'info, ProgramConfig>,
    #[account(mut, seeds = [b"collateral", listing_id.as_ref()], bump)]
    pub collateral: Account<'info, CollateralAccount>,
    /// CHECK: vault PDA
    #[account(seeds = [b"vault", listing_id.as_ref()], bump)]
    pub vault_authority: UncheckedAccount<'info>,
    #[account(mut, seeds = [b"vault_ata", listing_id.as_ref()], bump)]
    pub vault_ata: Account<'info, TokenAccount>,
    #[account(mut)]
    pub recipient: Signer<'info>,
    #[account(mut)]
    pub recipient_ata: Account<'info, TokenAccount>,
    pub token_program: Program<'info, Token>,
}

// ── Events / Errors ──────────────────────────────────────────────

#[event]
pub struct ListingApplied {
    pub listing_id: [u8; 32],
    pub agent: Pubkey,
    pub metadata_hash: [u8; 32],
}

#[event]
pub struct ListingAudited {
    pub listing_id: [u8; 32],
    pub score_bps: u16,
    pub auditor: Pubkey,
}

#[event]
pub struct ListingApproved {
    pub listing_id: [u8; 32],
    pub share_mint: Pubkey,
    pub max_supply: u64,
}

#[event]
pub struct ListingRejected {
    pub listing_id: [u8; 32],
}

#[event]
pub struct CollateralDeposited {
    pub listing_id: [u8; 32],
    pub amount: u64,
    pub depositor: Pubkey,
}

#[event]
pub struct CollateralLocked {
    pub listing_id: [u8; 32],
    pub amount: u64,
}

#[event]
pub struct CollateralReleased {
    pub listing_id: [u8; 32],
    pub amount: u64,
    pub recipient: Pubkey,
}

#[event]
pub struct CapsenseSeriesCreated {
    pub listing_id: [u8; 32],
    pub strike_index_bps: u64,
    pub expiry_ts: i64,
    pub series: Pubkey,
}

#[event]
pub struct CapsenseOptionPurchased {
    pub listing_id: [u8; 32],
    pub buyer: Pubkey,
    pub contracts: u64,
    pub premium: u64,
}

#[event]
pub struct CapsenseOptionExercised {
    pub listing_id: [u8; 32],
    pub buyer: Pubkey,
    pub payout: u64,
    pub index_level_bps: u64,
}

#[error_code]
pub enum AcexError {
    #[msg("Unauthorized")]
    Unauthorized,
    #[msg("Already initialized")]
    AlreadyInitialized,
    #[msg("Paused")]
    Paused,
    #[msg("Listing not found")]
    ListingNotFound,
    #[msg("Invalid status")]
    InvalidStatus,
    #[msg("Audit score too low")]
    AuditScoreTooLow,
    #[msg("Insufficient collateral")]
    InsufficientCollateral,
    #[msg("Math overflow")]
    MathOverflow,
    #[msg("Zero amount")]
    ZeroAmount,
    #[msg("Option expired")]
    OptionExpired,
    #[msg("Option settled")]
    OptionSettled,
    #[msg("Option out of the money")]
    OptionOutOfMoney,
    #[msg("Option already exercised")]
    OptionAlreadyExercised,
}
