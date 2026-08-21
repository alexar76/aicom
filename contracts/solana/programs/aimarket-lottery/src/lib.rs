//! AI Agent Oracle Lottery on Solana — analogue of `AIAgentLottery.sol` for UNI mode.
//!
//! Native-SOL tickets, Hub benefactor funding, oracle-attested draw, prize / opex /
//! operator split with a ≥70% prize floor. Simplified vs the EVM contract: one
//! ticket account per (round, agent) and operator-only round lifecycle for local UNI.
//!
//! MAINNET HARDENING (H18): `open_round` creates the vault PDA with a rent-exempt
//! reserve that is never part of prize/opex math. After prize + residual are swept,
//! `close_vault` returns the reserve to the authority and closes the account so it
//! never sits sub-rent-exempt. An unclaimed prize stays claimable indefinitely.
//!
//! DRAW HARDENING (H17): at `close_round` the program pins `draw_slot = close + DELAY`.
//! `fulfill_draw` must use THAT slot's hash (not "newest") and must land within
//! `DRAW_FULFILL_WINDOW` slots — an oracle cannot delay indefinitely to grind a
//! favourable recent slot hash. Miss the window → cancel + refunds.

use anchor_lang::prelude::*;
use anchor_lang::system_program;

declare_id!("DT6QVF7HhCQTFRCcP7V6AJpQF6ZQzEc9LQSrq85MHpFD");

const BPS: u16 = 10_000;
const MIN_PRIZE_BPS: u16 = 7_000;
const MAX_OPEX_BPS: u16 = 3_000;
const MAX_OPERATOR_BPS: u16 = 1_000;
/// Slots after close before the pinned draw hash exists (~13s on mainnet @ 400ms).
const DRAW_SLOT_DELAY: u64 = 32;
/// How long the oracle has after `draw_slot` to fulfill before the round must cancel.
const DRAW_FULFILL_WINDOW: u64 = 150;

#[program]
pub mod aimarket_lottery {
    use super::*;

    /// One-time config: roles + default splits + ticket price.
    pub fn initialize(
        ctx: Context<Initialize>,
        ticket_price_lamports: u64,
        prize_bps: u16,
        opex_bps: u16,
        operator_bps: u16,
    ) -> Result<()> {
        require!(ticket_price_lamports > 0, LotteryError::BadPayment);
        validate_splits(prize_bps, opex_bps, operator_bps)?;
        let cfg = &mut ctx.accounts.config;
        cfg.authority = ctx.accounts.authority.key();
        cfg.oracle_signer = ctx.accounts.oracle_signer.key();
        cfg.treasury = ctx.accounts.treasury.key();
        cfg.ticket_price_lamports = ticket_price_lamports;
        cfg.prize_bps = prize_bps;
        cfg.opex_bps = opex_bps;
        cfg.operator_bps = operator_bps;
        cfg.current_round_id = 0;
        cfg.total_prizes_paid = 0;
        cfg.total_funding = 0;
        cfg.bump = ctx.bumps.config;
        Ok(())
    }

    pub fn open_round(ctx: Context<OpenRound>, round_id: u64) -> Result<()> {
        let cfg = &mut ctx.accounts.config;
        require_keys_eq!(ctx.accounts.authority.key(), cfg.authority, LotteryError::Unauthorized);
        let expected = cfg.current_round_id.checked_add(1).ok_or(LotteryError::Overflow)?;
        require!(round_id == expected, LotteryError::WrongStatus);
        cfg.current_round_id = round_id;

        let clock = Clock::get()?;
        let round = &mut ctx.accounts.round;
        round.round_id = round_id;
        round.status = RoundStatus::Open as u8;
        round.opened_at = clock.unix_timestamp;
        round.entries_close = clock.unix_timestamp + 86_400; // 24h entry window
        round.s_prize_bps = cfg.prize_bps;
        round.s_opex_bps = cfg.opex_bps;
        round.s_operator_bps = cfg.operator_bps;
        round.ticket_revenue = 0;
        round.funding = 0;
        round.total_weight = 0;
        round.prize_pool = 0;
        round.winner = Pubkey::default();
        round.random_word = 0;
        round.prize_claimed = false;
        round.bump = ctx.bumps.round;
        round.seed_commitment = [0u8; 32];
        round.close_slot = 0;
        round.draw_slot = 0;
        round.opex = 0;
        round.operator_fee = 0;
        round.residual_withdrawn = false;
        round.funding_reclaimed = false;

        // H18: create the vault PDA with a rent-exempt reserve that is never distributed.
        let rent_reserve = Rent::get()?.minimum_balance(0);
        let vault = ctx.accounts.vault.to_account_info();
        if vault.lamports() == 0 {
            let rid = round_id.to_le_bytes();
            let bump = ctx.bumps.vault;
            let seeds: &[&[u8]] = &[b"vault", rid.as_ref(), &[bump]];
            let signer_seeds = &[seeds];
            let cpi = CpiContext::new(
                ctx.accounts.system_program.to_account_info(),
                system_program::CreateAccount {
                    from: ctx.accounts.authority.to_account_info(),
                    to: vault,
                },
            )
            .with_signer(signer_seeds);
            system_program::create_account(cpi, rent_reserve, 0, &system_program::ID)?;
        }
        round.rent_reserve = rent_reserve;

        emit!(RoundOpened { round_id, entries_close: round.entries_close });
        Ok(())
    }

    /// Agents buy tickets with native SOL transferred to the round vault PDA.
    pub fn buy_tickets(ctx: Context<BuyTickets>, count: u32) -> Result<()> {
        require!(count > 0, LotteryError::ZeroCount);
        let round = &mut ctx.accounts.round;
        require!(round.status() == RoundStatus::Open, LotteryError::WrongStatus);
        let clock = Clock::get()?;
        require!(clock.unix_timestamp <= round.entries_close, LotteryError::EntriesNotOpen);

        let cfg = &ctx.accounts.config;
        let cost = cfg
            .ticket_price_lamports
            .checked_mul(count as u64)
            .ok_or(LotteryError::Overflow)?;

        let cpi = CpiContext::new(
            ctx.accounts.system_program.to_account_info(),
            system_program::Transfer {
                from: ctx.accounts.buyer.to_account_info(),
                to: ctx.accounts.vault.to_account_info(),
            },
        );
        system_program::transfer(cpi, cost)?;

        // The ticket occupies the contiguous cumulative-weight range
        // [total_weight, total_weight + count); the winner check in fulfill_draw maps
        // `random_word % total_weight` into exactly one such range. (One buy per agent
        // per round keeps the range contiguous — re-buying the same round is rejected
        // by `init`.)
        let weight = count as u64;
        let start = round.total_weight;
        let end = start.checked_add(weight).ok_or(LotteryError::Overflow)?;

        let ticket = &mut ctx.accounts.ticket;
        ticket.agent = ctx.accounts.buyer.key();
        ticket.round_id = round.round_id;
        ticket.bump = ctx.bumps.ticket;
        ticket.weight = weight;
        ticket.paid = cost;
        ticket.weight_start = start;
        ticket.weight_end = end;

        round.ticket_revenue = round.ticket_revenue.checked_add(cost).ok_or(LotteryError::Overflow)?;
        round.total_weight = end;

        emit!(TicketsBought {
            round_id: round.round_id,
            agent: ctx.accounts.buyer.key(),
            count,
            weight,
            paid: cost,
        });
        Ok(())
    }

    /// Hub / benefactor tithe — 100% added to prize-side funding.
    pub fn fund(ctx: Context<Fund>, amount: u64) -> Result<()> {
        require!(amount > 0, LotteryError::BadPayment);
        let round = &mut ctx.accounts.round;
        require!(round.status() == RoundStatus::Open, LotteryError::WrongStatus);

        let cpi = CpiContext::new(
            ctx.accounts.system_program.to_account_info(),
            system_program::Transfer {
                from: ctx.accounts.benefactor.to_account_info(),
                to: ctx.accounts.vault.to_account_info(),
            },
        );
        system_program::transfer(cpi, amount)?;

        round.funding = round.funding.checked_add(amount).ok_or(LotteryError::Overflow)?;
        let cfg = &mut ctx.accounts.config;
        cfg.total_funding = cfg.total_funding.checked_add(amount).ok_or(LotteryError::Overflow)?;

        emit!(Funded {
            round_id: round.round_id,
            benefactor: ctx.accounts.benefactor.key(),
            amount,
        });
        Ok(())
    }

    /// Close entries and COMMIT the draw seed. The operator commits `sha256(seed)`
    /// now — before the draw-slot hash exists — so the revealed seed can't be ground
    /// against the (already-fixed) participant set to steer the winner.
    pub fn close_round(ctx: Context<CloseRound>, seed_commitment: [u8; 32]) -> Result<()> {
        let cfg = &ctx.accounts.config;
        require_keys_eq!(ctx.accounts.authority.key(), cfg.authority, LotteryError::Unauthorized);
        let round = &mut ctx.accounts.round;
        require!(round.status() == RoundStatus::Open, LotteryError::WrongStatus);
        require!(round.total_weight > 0, LotteryError::NoParticipants);
        round.status = RoundStatus::Drawing as u8;
        round.seed_commitment = seed_commitment;
        let close_slot = Clock::get()?.slot;
        round.close_slot = close_slot;
        // Pin the future slot whose hash mixes into randomness (H17).
        round.draw_slot = close_slot
            .checked_add(DRAW_SLOT_DELAY)
            .ok_or(LotteryError::Overflow)?;
        emit!(RoundClosed { round_id: round.round_id, close_slot: round.close_slot });
        Ok(())
    }

    /// Oracle-attested draw — selects the weighted winner ON-CHAIN.
    ///
    /// Security (SOL-001 fix): the winner is NOT taken from a caller-supplied address.
    /// `random_word` is derived from the revealed seed (must match the commitment) mixed
    /// with the *pinned* `draw_slot` hash (unknown at commit time), then
    /// `target = random_word % total_weight` must fall inside the supplied ticket's
    /// cumulative weight range. A malicious oracle can neither grind the seed, name an
    /// arbitrary winner, nor delay forever to shop a favourable "newest" slot hash (H17).
    pub fn fulfill_draw(ctx: Context<FulfillDraw>, seed: [u8; 32]) -> Result<()> {
        let cfg = &ctx.accounts.config;
        require_keys_eq!(ctx.accounts.oracle_signer.key(), cfg.oracle_signer, LotteryError::Unauthorized);
        let round = &mut ctx.accounts.round;
        require!(round.status() == RoundStatus::Drawing, LotteryError::WrongStatus);
        require!(round.total_weight > 0, LotteryError::NoParticipants);

        // commit-reveal: the revealed seed must hash to what was committed at close.
        let reveal = anchor_lang::solana_program::hash::hash(&seed).to_bytes();
        require!(reveal == round.seed_commitment, LotteryError::BadReveal);

        let now_slot = Clock::get()?.slot;
        require!(now_slot >= round.draw_slot, LotteryError::TooEarly);
        require!(
            now_slot <= round.draw_slot.saturating_add(DRAW_FULFILL_WINDOW),
            LotteryError::TooLate
        );
        let slot_hash = slot_hash_at(&ctx.accounts.slot_hashes, round.draw_slot)?;
        let random_word = derive_random_word(round.round_id, &seed, &slot_hash);

        // On-chain weighted selection: target must land in the supplied ticket's range.
        let target = random_word % round.total_weight;
        let wt = &ctx.accounts.winner_ticket;
        require!(wt.round_id == round.round_id, LotteryError::NotWinner);
        require!(range_contains(target, wt.weight_start, wt.weight_end), LotteryError::NotWinner);

        let income = round
            .ticket_revenue
            .checked_add(round.funding)
            .ok_or(LotteryError::Overflow)?;
        let opex = (income as u128)
            .checked_mul(round.s_opex_bps as u128)
            .ok_or(LotteryError::Overflow)?
            / BPS as u128;
        let operator_fee = (income as u128)
            .checked_mul(round.s_operator_bps as u128)
            .ok_or(LotteryError::Overflow)?
            / BPS as u128;
        let opex = opex as u64;
        let operator_fee = operator_fee as u64;
        let prize = income.checked_sub(opex).and_then(|v| v.checked_sub(operator_fee)).ok_or(LotteryError::Overflow)?;
        // Prize floor (≥ MIN_PRIZE_BPS) in u128 to avoid the multiply overflowing (SOL-004).
        require!(
            (prize as u128) * (BPS as u128) >= (income as u128) * (MIN_PRIZE_BPS as u128),
            LotteryError::InvalidSplits
        );

        round.prize_pool = prize;
        round.opex = opex;
        round.operator_fee = operator_fee;
        round.residual_withdrawn = false;
        round.random_word = random_word;
        round.status = RoundStatus::Settled as u8;
        round.winner = wt.agent;

        let cfg_mut = &mut ctx.accounts.config;
        cfg_mut.total_prizes_paid = cfg_mut.total_prizes_paid.checked_add(prize).ok_or(LotteryError::Overflow)?;

        emit!(Drawn {
            round_id: round.round_id,
            winner: round.winner,
            prize,
            opex,
            operator_fee,
            random_word,
        });
        Ok(())
    }

    /// Winner claims prize from the round vault.
    pub fn claim_prize(ctx: Context<ClaimPrize>) -> Result<()> {
        let round = &mut ctx.accounts.round;
        require!(round.status() == RoundStatus::Settled, LotteryError::WrongStatus);
        require!(!round.prize_claimed, LotteryError::AlreadyClaimed);
        require_keys_eq!(ctx.accounts.winner.key(), round.winner, LotteryError::NotWinner);
        require!(round.prize_pool > 0, LotteryError::BadPayment);

        let amount = round.prize_pool;
        round.prize_claimed = true;

        let round_id_bytes = round.round_id.to_le_bytes();
        let seeds = &[b"vault", round_id_bytes.as_ref(), &[ctx.bumps.vault]];
        let signer = &[&seeds[..]];

        let cpi = CpiContext::new_with_signer(
            ctx.accounts.system_program.to_account_info(),
            system_program::Transfer {
                from: ctx.accounts.vault.to_account_info(),
                to: ctx.accounts.winner.to_account_info(),
            },
            signer,
        );
        system_program::transfer(cpi, amount)?;

        emit!(PrizeClaimed {
            round_id: round.round_id,
            winner: round.winner,
            amount,
        });
        Ok(())
    }

    /// Sweep the round's opex + operator fee from the vault to the configured treasury
    /// (SOL-003: those lamports were previously stranded in the vault forever). Authority
    /// only, after settlement, once.
    pub fn withdraw_residual(ctx: Context<WithdrawResidual>) -> Result<()> {
        let cfg = &ctx.accounts.config;
        require_keys_eq!(ctx.accounts.authority.key(), cfg.authority, LotteryError::Unauthorized);
        require_keys_eq!(ctx.accounts.treasury.key(), cfg.treasury, LotteryError::Unauthorized);
        let round = &mut ctx.accounts.round;
        require!(round.status() == RoundStatus::Settled, LotteryError::WrongStatus);
        require!(!round.residual_withdrawn, LotteryError::AlreadyClaimed);
        let amount = round.opex.checked_add(round.operator_fee).ok_or(LotteryError::Overflow)?;
        round.residual_withdrawn = true;
        if amount == 0 {
            return Ok(());
        }

        let round_id_bytes = round.round_id.to_le_bytes();
        let seeds = &[b"vault", round_id_bytes.as_ref(), &[ctx.bumps.vault]];
        let signer = &[&seeds[..]];
        let cpi = CpiContext::new_with_signer(
            ctx.accounts.system_program.to_account_info(),
            system_program::Transfer {
                from: ctx.accounts.vault.to_account_info(),
                to: ctx.accounts.treasury.to_account_info(),
            },
            signer,
        );
        system_program::transfer(cpi, amount)?;

        emit!(ResidualWithdrawn { round_id: round.round_id, amount });
        Ok(())
    }

    /// Cancel an undrawn round (operator). Open or Drawing → Cancelled, after which every
    /// participant reclaims their OWN funds — no money is stuck if a draw never happens
    /// and there is NO admin drain (anti-rug). Mirrors AIAgentLottery.cancelRound.
    pub fn cancel_round(ctx: Context<CancelRound>) -> Result<()> {
        let cfg = &ctx.accounts.config;
        require_keys_eq!(ctx.accounts.authority.key(), cfg.authority, LotteryError::Unauthorized);
        let round = &mut ctx.accounts.round;
        let s = round.status();
        require!(s == RoundStatus::Open || s == RoundStatus::Drawing, LotteryError::WrongStatus);
        round.status = RoundStatus::Cancelled as u8;
        emit!(RoundCancelled { round_id: round.round_id });
        Ok(())
    }

    /// Refund one agent's ticket spend after a cancel — permissionless (anyone can trigger
    /// the refund, but it always pays the ticket's own `agent`), and the ticket account is
    /// closed so it can't be refunded twice (rent also returns to the agent).
    pub fn refund_ticket(ctx: Context<RefundTicket>) -> Result<()> {
        let round = &ctx.accounts.round;
        require!(round.status() == RoundStatus::Cancelled, LotteryError::WrongStatus);
        let amount = ctx.accounts.ticket.paid;
        if amount > 0 {
            let round_id_bytes = round.round_id.to_le_bytes();
            let seeds = &[b"vault", round_id_bytes.as_ref(), &[ctx.bumps.vault]];
            let signer = &[&seeds[..]];
            let cpi = CpiContext::new_with_signer(
                ctx.accounts.system_program.to_account_info(),
                system_program::Transfer {
                    from: ctx.accounts.vault.to_account_info(),
                    to: ctx.accounts.agent.to_account_info(),
                },
                signer,
            );
            system_program::transfer(cpi, amount)?;
        }
        emit!(TicketRefunded { round_id: round.round_id, agent: ctx.accounts.agent.key(), amount });
        Ok(())
    }

    /// Return the operator/Hub funding (tithe) to the configured treasury after a cancel.
    /// Authority-only, once; covers the non-ticket portion of the vault so nothing is left
    /// stranded. (Funding here is the operator/Hub tithe; a multi-donor model would track
    /// per-benefactor like the EVM `fundedBy` map.)
    pub fn reclaim_funding(ctx: Context<ReclaimFunding>) -> Result<()> {
        let cfg = &ctx.accounts.config;
        require_keys_eq!(ctx.accounts.authority.key(), cfg.authority, LotteryError::Unauthorized);
        require_keys_eq!(ctx.accounts.treasury.key(), cfg.treasury, LotteryError::Unauthorized);
        let round = &mut ctx.accounts.round;
        require!(round.status() == RoundStatus::Cancelled, LotteryError::WrongStatus);
        require!(!round.funding_reclaimed, LotteryError::AlreadyClaimed);
        let amount = round.funding;
        round.funding_reclaimed = true;
        if amount > 0 {
            let round_id_bytes = round.round_id.to_le_bytes();
            let seeds = &[b"vault", round_id_bytes.as_ref(), &[ctx.bumps.vault]];
            let signer = &[&seeds[..]];
            let cpi = CpiContext::new_with_signer(
                ctx.accounts.system_program.to_account_info(),
                system_program::Transfer {
                    from: ctx.accounts.vault.to_account_info(),
                    to: ctx.accounts.treasury.to_account_info(),
                },
                signer,
            );
            system_program::transfer(cpi, amount)?;
        }
        emit!(FundingReclaimed { round_id: round.round_id, amount });
        Ok(())
    }

    /// Return the rent-exempt reserve to the authority and close the vault (H18).
    /// Allowed only after the round is fully drained (Settled + prize claimed + residual
    /// withdrawn, or Cancelled + funding reclaimed — ticket refunds leave the reserve).
    pub fn close_vault(ctx: Context<CloseVault>) -> Result<()> {
        let cfg = &ctx.accounts.config;
        require_keys_eq!(ctx.accounts.authority.key(), cfg.authority, LotteryError::Unauthorized);
        let round = &ctx.accounts.round;
        let s = round.status();
        match s {
            RoundStatus::Settled => {
                require!(round.prize_claimed, LotteryError::WrongStatus);
                require!(round.residual_withdrawn, LotteryError::WrongStatus);
            }
            RoundStatus::Cancelled => {
                require!(round.funding_reclaimed, LotteryError::WrongStatus);
            }
            _ => return err!(LotteryError::WrongStatus),
        }

        let vault = ctx.accounts.vault.to_account_info();
        let authority = ctx.accounts.authority.to_account_info();
        let bal = vault.lamports();
        // Refuse to close while ticket/prize funds remain — only the rent reserve (or dust).
        require!(bal <= round.rent_reserve, LotteryError::FundsRemain);
        **vault.try_borrow_mut_lamports()? = 0;
        **authority.try_borrow_mut_lamports()? = authority
            .lamports()
            .checked_add(bal)
            .ok_or(LotteryError::Overflow)?;

        emit!(VaultClosed {
            round_id: round.round_id,
            returned: bal,
        });
        Ok(())
    }
}

/// Unbiasable draw word: sha256(round_id ‖ revealed_seed ‖ recent_slot_hash). The seed
/// is fixed at commit time and the slot hash is unknown then, so neither input alone
/// lets a party steer the result.
fn derive_random_word(round_id: u64, seed: &[u8; 32], slot_hash: &[u8; 32]) -> u64 {
    let mut buf = [0u8; 8 + 32 + 32];
    buf[..8].copy_from_slice(&round_id.to_le_bytes());
    buf[8..40].copy_from_slice(seed);
    buf[40..].copy_from_slice(slot_hash);
    let digest = anchor_lang::solana_program::hash::hash(&buf).to_bytes();
    u64::from_le_bytes(digest[..8].try_into().unwrap())
}

/// The winning ticket is the one whose cumulative range contains the target.
fn range_contains(target: u64, start: u64, end: u64) -> bool {
    target >= start && target < end
}

/// Hash of a *specific* slot from the SlotHashes sysvar (newest-first layout:
/// `[u64 num][(u64 slot, [u8;32] hash) …]`). Used so the oracle cannot shop the
/// moving "newest" entry by delaying fulfill (H17).
fn slot_hash_at(slot_hashes: &AccountInfo, target_slot: u64) -> Result<[u8; 32]> {
    require_keys_eq!(
        *slot_hashes.key,
        anchor_lang::solana_program::sysvar::slot_hashes::id(),
        LotteryError::BadReveal
    );
    let data = slot_hashes.try_borrow_data()?;
    require!(data.len() >= 8 + 8 + 32, LotteryError::BlockhashUnavailable);
    let num = u64::from_le_bytes(data[..8].try_into().unwrap());
    require!(num > 0, LotteryError::BlockhashUnavailable);
    let mut offset = 8usize;
    for _ in 0..num {
        require!(data.len() >= offset + 40, LotteryError::BlockhashUnavailable);
        let slot = u64::from_le_bytes(data[offset..offset + 8].try_into().unwrap());
        if slot == target_slot {
            let mut out = [0u8; 32];
            out.copy_from_slice(&data[offset + 8..offset + 40]);
            return Ok(out);
        }
        // Newest first — once slots drop below the target, it is gone from the ring.
        if slot < target_slot {
            break;
        }
        offset += 40;
    }
    err!(LotteryError::BlockhashUnavailable)
}

fn validate_splits(prize_bps: u16, opex_bps: u16, operator_bps: u16) -> Result<()> {
    require!(prize_bps + opex_bps + operator_bps == BPS, LotteryError::InvalidSplits);
    require!(prize_bps >= MIN_PRIZE_BPS, LotteryError::InvalidSplits);
    require!(opex_bps <= MAX_OPEX_BPS, LotteryError::InvalidSplits);
    require!(operator_bps <= MAX_OPERATOR_BPS, LotteryError::InvalidSplits);
    Ok(())
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum RoundStatus {
    None,
    Open,
    Drawing,
    Settled,
    Cancelled,
}

impl Round {
    fn status(&self) -> RoundStatus {
        match self.status {
            1 => RoundStatus::Open,
            2 => RoundStatus::Drawing,
            3 => RoundStatus::Settled,
            4 => RoundStatus::Cancelled,
            _ => RoundStatus::None,
        }
    }
}

#[account]
pub struct LotteryConfig {
    pub authority: Pubkey,
    pub oracle_signer: Pubkey,
    pub treasury: Pubkey,
    pub ticket_price_lamports: u64,
    pub prize_bps: u16,
    pub opex_bps: u16,
    pub operator_bps: u16,
    pub current_round_id: u64,
    pub total_prizes_paid: u64,
    pub total_funding: u64,
    pub bump: u8,
}

#[account]
pub struct Round {
    pub round_id: u64,
    pub status: u8,
    pub opened_at: i64,
    pub entries_close: i64,
    pub s_prize_bps: u16,
    pub s_opex_bps: u16,
    pub s_operator_bps: u16,
    pub ticket_revenue: u64,
    pub funding: u64,
    pub total_weight: u64,
    pub prize_pool: u64,
    pub winner: Pubkey,
    pub random_word: u64,
    pub prize_claimed: bool,
    pub bump: u8,
    // ── unbiasable draw (commit-reveal + slot hash, mirrors AIAgentLottery.sol) ──
    /// sha256(reveal seed) committed at close, BEFORE the draw-slot hash exists, so
    /// neither operator nor oracle can grind the revealed seed to steer the winner.
    pub seed_commitment: [u8; 32],
    /// slot at close — the draw must land on a later slot so a hash unknown at commit
    /// time mixes into the randomness.
    pub close_slot: u64,
    /// Slot whose hash is mixed into `random_word` (close_slot + DRAW_SLOT_DELAY).
    pub draw_slot: u64,
    /// Rent-exempt lamports locked in the vault PDA at open — never distributed (H18).
    pub rent_reserve: u64,
    // ── residual (opex + operator fee) accounting for withdraw_residual ──
    pub opex: u64,
    pub operator_fee: u64,
    pub residual_withdrawn: bool,
    /// set once the operator's funding has been reclaimed after a cancel.
    pub funding_reclaimed: bool,
}

#[account]
pub struct Ticket {
    pub round_id: u64,
    pub agent: Pubkey,
    pub weight: u64,
    pub paid: u64,
    pub bump: u8,
    /// Cumulative weight range [weight_start, weight_end) this ticket occupies in the
    /// round. The winner is the ticket whose range contains `random_word % total_weight`
    /// — verified ON-CHAIN, so the oracle cannot name an arbitrary winner (SOL-001).
    pub weight_start: u64,
    pub weight_end: u64,
}

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    /// CHECK: stored as config oracle signer pubkey
    pub oracle_signer: UncheckedAccount<'info>,
    /// CHECK: treasury recipient for opex withdrawals (off-chain in UNI)
    pub treasury: UncheckedAccount<'info>,
    #[account(
        init,
        payer = authority,
        space = 8 + std::mem::size_of::<LotteryConfig>(),
        seeds = [b"lottery_config"],
        bump,
    )]
    pub config: Account<'info, LotteryConfig>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(round_id: u64)]
pub struct OpenRound<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(mut, seeds = [b"lottery_config"], bump = config.bump)]
    pub config: Account<'info, LotteryConfig>,
    #[account(
        init,
        payer = authority,
        space = 8 + std::mem::size_of::<Round>(),
        seeds = [b"round", round_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub round: Account<'info, Round>,
    /// CHECK: system-owned vault PDA, created with rent-exempt reserve (H18)
    #[account(
        mut,
        seeds = [b"vault", round_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub vault: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(count: u32)]
pub struct BuyTickets<'info> {
    #[account(mut)]
    pub buyer: Signer<'info>,
    #[account(seeds = [b"lottery_config"], bump = config.bump)]
    pub config: Account<'info, LotteryConfig>,
    #[account(mut, seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
    // `init` (not init_if_needed): one ticket per (round, agent) so its cumulative
    // weight range stays contiguous. A second buy in the same round is rejected.
    #[account(
        init,
        payer = buyer,
        space = 8 + std::mem::size_of::<Ticket>(),
        seeds = [b"ticket", round.round_id.to_le_bytes().as_ref(), buyer.key().as_ref()],
        bump,
    )]
    pub ticket: Account<'info, Ticket>,
    /// CHECK: round vault PDA holds SOL
    #[account(
        mut,
        seeds = [b"vault", round.round_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub vault: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct Fund<'info> {
    #[account(mut)]
    pub benefactor: Signer<'info>,
    #[account(mut, seeds = [b"lottery_config"], bump = config.bump)]
    pub config: Account<'info, LotteryConfig>,
    #[account(mut, seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
    /// CHECK: vault
    #[account(
        mut,
        seeds = [b"vault", round.round_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub vault: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct CloseRound<'info> {
    pub authority: Signer<'info>,
    #[account(seeds = [b"lottery_config"], bump = config.bump)]
    pub config: Account<'info, LotteryConfig>,
    #[account(mut, seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
}

#[derive(Accounts)]
pub struct FulfillDraw<'info> {
    pub oracle_signer: Signer<'info>,
    #[account(mut, seeds = [b"lottery_config"], bump = config.bump)]
    pub config: Account<'info, LotteryConfig>,
    #[account(mut, seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
    /// The proposed winner's ticket — its PDA is re-derived from its own `agent`, so it
    /// must be a real ticket of THIS round; fulfill_draw then checks the random target
    /// falls in its cumulative weight range. The oracle cannot substitute an arbitrary
    /// account (SOL-001).
    #[account(
        seeds = [b"ticket", round.round_id.to_le_bytes().as_ref(), winner_ticket.agent.as_ref()],
        bump = winner_ticket.bump,
    )]
    pub winner_ticket: Account<'info, Ticket>,
    /// CHECK: the SlotHashes sysvar — address-checked in `slot_hash_at`; supplies the
    /// pinned draw_slot hash (unknown at commit) to make the draw unbiasable.
    pub slot_hashes: AccountInfo<'info>,
}

#[derive(Accounts)]
pub struct ClaimPrize<'info> {
    #[account(mut)]
    pub winner: Signer<'info>,
    #[account(mut, seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
    /// CHECK: vault
    #[account(
        mut,
        seeds = [b"vault", round.round_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub vault: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct CancelRound<'info> {
    pub authority: Signer<'info>,
    #[account(seeds = [b"lottery_config"], bump = config.bump)]
    pub config: Account<'info, LotteryConfig>,
    #[account(mut, seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
}

#[derive(Accounts)]
pub struct RefundTicket<'info> {
    #[account(mut, seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
    /// CHECK: the ticket's own agent — receives the refund + reclaimed rent (has_one below).
    #[account(mut)]
    pub agent: UncheckedAccount<'info>,
    #[account(
        mut,
        close = agent,
        has_one = agent,
        seeds = [b"ticket", round.round_id.to_le_bytes().as_ref(), agent.key().as_ref()],
        bump = ticket.bump,
    )]
    pub ticket: Account<'info, Ticket>,
    /// CHECK: round vault PDA
    #[account(mut, seeds = [b"vault", round.round_id.to_le_bytes().as_ref()], bump)]
    pub vault: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct ReclaimFunding<'info> {
    pub authority: Signer<'info>,
    #[account(seeds = [b"lottery_config"], bump = config.bump)]
    pub config: Account<'info, LotteryConfig>,
    #[account(mut, seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
    /// CHECK: must equal config.treasury (checked in the handler); receives the funding.
    #[account(mut)]
    pub treasury: UncheckedAccount<'info>,
    /// CHECK: round vault PDA
    #[account(mut, seeds = [b"vault", round.round_id.to_le_bytes().as_ref()], bump)]
    pub vault: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct WithdrawResidual<'info> {
    pub authority: Signer<'info>,
    #[account(seeds = [b"lottery_config"], bump = config.bump)]
    pub config: Account<'info, LotteryConfig>,
    #[account(mut, seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
    /// CHECK: must equal config.treasury (checked in the handler); receives the residual.
    #[account(mut)]
    pub treasury: UncheckedAccount<'info>,
    /// CHECK: round vault PDA
    #[account(
        mut,
        seeds = [b"vault", round.round_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub vault: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct CloseVault<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(seeds = [b"lottery_config"], bump = config.bump)]
    pub config: Account<'info, LotteryConfig>,
    #[account(seeds = [b"round", round.round_id.to_le_bytes().as_ref()], bump = round.bump)]
    pub round: Account<'info, Round>,
    /// CHECK: round vault PDA — drained and left at 0 lamports
    #[account(
        mut,
        seeds = [b"vault", round.round_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub vault: UncheckedAccount<'info>,
}

#[event]
pub struct RoundOpened {
    pub round_id: u64,
    pub entries_close: i64,
}

#[event]
pub struct TicketsBought {
    pub round_id: u64,
    pub agent: Pubkey,
    pub count: u32,
    pub weight: u64,
    pub paid: u64,
}

#[event]
pub struct Funded {
    pub round_id: u64,
    pub benefactor: Pubkey,
    pub amount: u64,
}

#[event]
pub struct RoundClosed {
    pub round_id: u64,
    pub close_slot: u64,
}

#[event]
pub struct RoundCancelled {
    pub round_id: u64,
}

#[event]
pub struct TicketRefunded {
    pub round_id: u64,
    pub agent: Pubkey,
    pub amount: u64,
}

#[event]
pub struct FundingReclaimed {
    pub round_id: u64,
    pub amount: u64,
}

#[event]
pub struct ResidualWithdrawn {
    pub round_id: u64,
    pub amount: u64,
}

#[event]
pub struct Drawn {
    pub round_id: u64,
    pub winner: Pubkey,
    pub prize: u64,
    pub opex: u64,
    pub operator_fee: u64,
    pub random_word: u64,
}

#[event]
pub struct PrizeClaimed {
    pub round_id: u64,
    pub winner: Pubkey,
    pub amount: u64,
}

#[event]
pub struct VaultClosed {
    pub round_id: u64,
    pub returned: u64,
}

#[error_code]
pub enum LotteryError {
    #[msg("invalid prize/opex/operator split")]
    InvalidSplits,
    #[msg("wrong round status")]
    WrongStatus,
    #[msg("count must be > 0")]
    ZeroCount,
    #[msg("bad payment amount")]
    BadPayment,
    #[msg("entries not open")]
    EntriesNotOpen,
    #[msg("no participants")]
    NoParticipants,
    #[msg("not the round winner")]
    NotWinner,
    #[msg("prize already claimed")]
    AlreadyClaimed,
    #[msg("unauthorized")]
    Unauthorized,
    #[msg("overflow")]
    Overflow,
    #[msg("revealed seed does not match the commitment")]
    BadReveal,
    #[msg("draw too early — wait for the pinned draw_slot")]
    TooEarly,
    #[msg("draw window missed — cancel the round and refund")]
    TooLate,
    #[msg("recent slot hash unavailable")]
    BlockhashUnavailable,
    #[msg("vault still holds distributable funds")]
    FundsRemain,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn random_word_is_deterministic_and_slot_hash_sensitive() {
        let seed = [7u8; 32];
        let h1 = [1u8; 32];
        let h2 = [2u8; 32];
        // same inputs → same word (reproducible on-chain)
        assert_eq!(derive_random_word(5, &seed, &h1), derive_random_word(5, &seed, &h1));
        // the slot hash (unknown at commit) actually changes the outcome → unbiasable
        assert_ne!(derive_random_word(5, &seed, &h1), derive_random_word(5, &seed, &h2));
        // the round id also separates words across rounds
        assert_ne!(derive_random_word(5, &seed, &h1), derive_random_word(6, &seed, &h1));
    }

    #[test]
    fn contiguous_ranges_partition_every_target_exactly_once() {
        // tickets: A[0,3) B[3,5) C[5,10) — total_weight = 10
        let ranges = [(0u64, 3u64), (3, 5), (5, 10)];
        let total = 10u64;
        for target in 0..total {
            let hits = ranges.iter().filter(|(s, e)| range_contains(target, *s, *e)).count();
            assert_eq!(hits, 1, "target {target} must fall in exactly one ticket range");
        }
    }

    #[test]
    fn winner_must_be_inside_its_range() {
        // a target outside a ticket's range is rejected — the oracle can't point the
        // winner at a non-matching ticket.
        assert!(range_contains(4, 3, 5));
        assert!(!range_contains(5, 3, 5)); // end is exclusive
        assert!(!range_contains(2, 3, 5));
    }
}
