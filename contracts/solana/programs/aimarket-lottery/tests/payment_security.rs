//! Native entrypoint regression tests with a strict System Program CPI stub.
//! These validate real Anchor account constraints and instruction dispatch. The
//! stub executes only native SOL transfers, checks signatures/PDA signer seeds,
//! and checks the exact amounts and destinations; it never contacts an RPC.
use aimarket_lottery::{instruction, LotteryConfig, Round, RoundStatus, Ticket, ID};
use anchor_lang::prelude::*;
use anchor_lang::solana_program::{instruction::Instruction, program_error::ProgramError};
use anchor_lang::{AccountDeserialize, AccountSerialize, InstructionData};
use solana_sysvar::program_stubs::{set_syscall_stubs, SyscallStubs};
use std::sync::{Arc, Mutex};

static STUB_LOCK: Mutex<()> = Mutex::new(());

#[derive(Clone, Debug, PartialEq)]
struct Transfer {
    from: Pubkey,
    to: Pubkey,
    amount: u64,
    pda_signed: bool,
}

struct TestSyscalls {
    clock: Clock,
    transfers: Arc<Mutex<Vec<Transfer>>>,
}
impl SyscallStubs for TestSyscalls {
    fn sol_get_clock_sysvar(&self, output: *mut u8) -> u64 {
        // The syscall API gives us a valid aligned Clock output buffer.
        unsafe { std::ptr::write(output.cast::<Clock>(), self.clock.clone()) };
        0
    }
    fn sol_invoke_signed(
        &self,
        ix: &Instruction,
        infos: &[AccountInfo],
        seeds: &[&[&[u8]]],
    ) -> std::result::Result<(), ProgramError> {
        if ix.program_id != solana_sdk_ids::system_program::ID
            || ix.data.len() != 12
            || ix.data[..4] != 2u32.to_le_bytes()
            || infos.len() != 2
        {
            return Err(ProgramError::InvalidInstructionData);
        }
        let source = &infos[0];
        let destination = &infos[1];
        if ix.accounts.len() != 2
            || ix.accounts[0].pubkey != *source.key
            || ix.accounts[1].pubkey != *destination.key
            || !ix.accounts[0].is_signer
            || !ix.accounts[0].is_writable
            || !ix.accounts[1].is_writable
        {
            return Err(ProgramError::InvalidAccountData);
        }
        let pda_signed = seeds.iter().any(|seed| {
            Pubkey::create_program_address(seed, &ID).ok().as_ref() == Some(source.key)
        });
        if !source.is_signer && !pda_signed {
            return Err(ProgramError::MissingRequiredSignature);
        }
        if source.owner != &solana_sdk_ids::system_program::ID || !source.data_is_empty() {
            return Err(ProgramError::InvalidAccountData);
        }
        let amount = u64::from_le_bytes(ix.data[4..].try_into().unwrap());
        let remaining = source
            .lamports()
            .checked_sub(amount)
            .ok_or(ProgramError::InsufficientFunds)?;
        let received = destination
            .lamports()
            .checked_add(amount)
            .ok_or(ProgramError::ArithmeticOverflow)?;
        **source.try_borrow_mut_lamports()? = remaining;
        **destination.try_borrow_mut_lamports()? = received;
        self.transfers.lock().unwrap().push(Transfer {
            from: *source.key,
            to: *destination.key,
            amount,
            pda_signed,
        });
        Ok(())
    }
}
struct RestoreStubs(Option<Box<dyn SyscallStubs>>);
impl Drop for RestoreStubs {
    fn drop(&mut self) {
        set_syscall_stubs(self.0.take().unwrap());
    }
}
fn install_stubs(slot: u64) -> (RestoreStubs, Arc<Mutex<Vec<Transfer>>>) {
    let transfers = Arc::new(Mutex::new(Vec::new()));
    let old = set_syscall_stubs(Box::new(TestSyscalls {
        clock: Clock {
            slot,
            unix_timestamp: 1_700_000_000,
            ..Clock::default()
        },
        transfers: transfers.clone(),
    }));
    (RestoreStubs(Some(old)), transfers)
}
fn account(
    key: Pubkey,
    owner: Pubkey,
    signer: bool,
    writable: bool,
    executable: bool,
    lamports: u64,
    data: Vec<u8>,
) -> AccountInfo<'static> {
    AccountInfo::new(
        Box::leak(Box::new(key)),
        signer,
        writable,
        Box::leak(Box::new(lamports)),
        Box::leak(data.into_boxed_slice()),
        Box::leak(Box::new(owner)),
        executable,
    )
}
fn serialized<T: AccountSerialize>(value: &T) -> Vec<u8> {
    let mut v = Vec::new();
    value.try_serialize(&mut v).unwrap();
    v
}
fn read<T: AccountDeserialize>(info: &AccountInfo) -> T {
    T::try_deserialize(&mut &info.try_borrow_data().unwrap()[..]).unwrap()
}
fn config(authority: Pubkey, oracle: Pubkey, treasury: Pubkey) -> AccountInfo<'static> {
    let (key, bump) = Pubkey::find_program_address(&[b"lottery_config"], &ID);
    account(
        key,
        ID,
        false,
        true,
        false,
        1_000_000,
        serialized(&LotteryConfig {
            authority,
            oracle_signer: oracle,
            treasury,
            ticket_price_lamports: 1000,
            prize_bps: 7000,
            opex_bps: 2000,
            operator_bps: 1000,
            current_round_id: 42,
            total_prizes_paid: 0,
            total_funding: 0,
            bump,
        }),
    )
}
fn round(status: RoundStatus, winner: Pubkey) -> AccountInfo<'static> {
    let (key, bump) = Pubkey::find_program_address(&[b"round", &42u64.to_le_bytes()], &ID);
    account(
        key,
        ID,
        false,
        true,
        false,
        1_000_000,
        serialized(&Round {
            round_id: 42,
            status: status as u8,
            opened_at: 1_699_999_000,
            entries_close: 1_700_086_400,
            s_prize_bps: 7000,
            s_opex_bps: 2000,
            s_operator_bps: 1000,
            ticket_revenue: 10_000,
            funding: 5_000,
            total_weight: 10,
            prize_pool: 10_500,
            winner,
            random_word: 1,
            prize_claimed: false,
            bump,
            seed_commitment: solana_sha256_hasher::hash(&[7; 32]).to_bytes(),
            close_slot: 468,
            draw_slot: 500,
            rent_reserve: 890_880,
            opex: 3000,
            operator_fee: 1500,
            residual_withdrawn: false,
            funding_reclaimed: false,
        }),
    )
}
fn wallet(byte: u8, signer: bool) -> AccountInfo<'static> {
    account(
        Pubkey::new_from_array([byte; 32]),
        solana_sdk_ids::system_program::ID,
        signer,
        true,
        false,
        1_000_000,
        vec![],
    )
}
fn vault() -> AccountInfo<'static> {
    let (key, _) = Pubkey::find_program_address(&[b"vault", &42u64.to_le_bytes()], &ID);
    account(
        key,
        solana_sdk_ids::system_program::ID,
        false,
        true,
        false,
        905_880,
        vec![],
    )
}
fn system() -> AccountInfo<'static> {
    account(
        solana_sdk_ids::system_program::ID,
        solana_sdk_ids::native_loader::ID,
        false,
        false,
        true,
        1,
        vec![],
    )
}
fn run(
    accounts: Vec<AccountInfo<'static>>,
    data: Vec<u8>,
) -> std::result::Result<(), ProgramError> {
    let accounts = Box::leak(accounts.into_boxed_slice());
    aimarket_lottery::entry(&ID, accounts, Box::leak(data.into_boxed_slice()))
}

#[test]
fn sol_funding_and_payouts_preserve_amount_destinations_signers_and_replay_guards() {
    let _lock = STUB_LOCK.lock().unwrap();
    let (_restore, transfers) = install_stubs(500);
    let authority = wallet(1, true);
    let oracle = wallet(2, true);
    let treasury = wallet(3, false);
    let winner = wallet(4, true);
    let benefactor = wallet(5, true);
    let cfg = config(*authority.key, *oracle.key, *treasury.key);
    let r = round(RoundStatus::Open, *winner.key);
    let v = vault();
    let sys = system();
    let fund_accounts = vec![
        benefactor.clone(),
        cfg.clone(),
        r.clone(),
        v.clone(),
        sys.clone(),
    ];
    run(
        fund_accounts.clone(),
        instruction::Fund { amount: 2500 }.data(),
    )
    .unwrap();
    assert_eq!(benefactor.lamports(), 997_500);
    assert_eq!(v.lamports(), 908_380);
    assert_eq!(read::<Round>(&r).funding, 7500);
    assert_eq!(read::<LotteryConfig>(&cfg).total_funding, 2500);
    let mut unsigned = fund_accounts.clone();
    unsigned[0].is_signer = false;
    assert!(run(unsigned, instruction::Fund { amount: 2500 }.data()).is_err());
    assert!(run(fund_accounts, instruction::Fund { amount: 0 }.data()).is_err());
    assert_eq!(transfers.lock().unwrap().len(), 1);

    let settled = round(RoundStatus::Settled, *winner.key);
    let v = vault();
    let claim = vec![winner.clone(), settled.clone(), v.clone(), sys.clone()];
    let mut unsigned = claim.clone();
    unsigned[0].is_signer = false;
    assert!(run(unsigned, instruction::ClaimPrize {}.data()).is_err());
    let mut wrong_winner = claim.clone();
    wrong_winner[0] = authority.clone();
    assert!(run(wrong_winner, instruction::ClaimPrize {}.data()).is_err());
    let mut foreign_owner = claim.clone();
    foreign_owner[1].owner = benefactor.key;
    assert!(run(foreign_owner, instruction::ClaimPrize {}.data()).is_err());
    let mut forged_vault = claim.clone();
    forged_vault[2] = benefactor.clone();
    assert!(run(forged_vault, instruction::ClaimPrize {}.data()).is_err());
    run(claim.clone(), instruction::ClaimPrize {}.data()).unwrap();
    assert_eq!(winner.lamports(), 1_010_500);
    assert_eq!(v.lamports(), 895_380);
    assert!(read::<Round>(&settled).prize_claimed);
    assert!(run(claim, instruction::ClaimPrize {}.data()).is_err());
    let withdraw = vec![
        authority.clone(),
        cfg.clone(),
        settled.clone(),
        treasury.clone(),
        v.clone(),
        sys.clone(),
    ];
    let mut wrong_treasury = withdraw.clone();
    wrong_treasury[3] = benefactor.clone();
    assert!(run(wrong_treasury, instruction::WithdrawResidual {}.data()).is_err());
    let mut wrong_authority = withdraw.clone();
    wrong_authority[0] = winner.clone();
    assert!(run(wrong_authority, instruction::WithdrawResidual {}.data()).is_err());
    run(withdraw.clone(), instruction::WithdrawResidual {}.data()).unwrap();
    assert_eq!(treasury.lamports(), 1_004_500);
    assert_eq!(v.lamports(), 890_880);
    assert!(read::<Round>(&settled).residual_withdrawn);
    assert!(run(withdraw, instruction::WithdrawResidual {}.data()).is_err());
    assert_eq!(
        transfers.lock().unwrap().as_slice(),
        [
            Transfer {
                from: *benefactor.key,
                to: *v.key,
                amount: 2500,
                pda_signed: false
            },
            Transfer {
                from: *v.key,
                to: *winner.key,
                amount: 10_500,
                pda_signed: true
            },
            Transfer {
                from: *v.key,
                to: *treasury.key,
                amount: 4500,
                pda_signed: true
            },
        ]
    );
}

#[test]
fn draw_requires_the_pinned_hash_reveal_oracle_signature_and_real_winning_ticket() {
    let _lock = STUB_LOCK.lock().unwrap();
    let (_restore, transfers) = install_stubs(500);
    let authority = wallet(1, true);
    let oracle = wallet(2, true);
    let treasury = wallet(3, false);
    let winner = wallet(4, true);
    let cfg = config(*authority.key, *oracle.key, *treasury.key);
    let r = round(RoundStatus::Drawing, *winner.key);
    let (ticket_key, bump) =
        Pubkey::find_program_address(&[b"ticket", &42u64.to_le_bytes(), winner.key.as_ref()], &ID);
    let ticket = account(
        ticket_key,
        ID,
        false,
        false,
        false,
        1_000_000,
        serialized(&Ticket {
            round_id: 42,
            agent: *winner.key,
            weight: 10,
            paid: 10_000,
            bump,
            weight_start: 0,
            weight_end: 10,
        }),
    );
    let mut hashes = Vec::new();
    hashes.extend(2u64.to_le_bytes());
    for (slot, hash) in [(501u64, [9u8; 32]), (500, [8; 32])] {
        hashes.extend(slot.to_le_bytes());
        hashes.extend(hash);
    }
    let slot_hashes = account(
        solana_sdk_ids::sysvar::slot_hashes::ID,
        solana_sdk_ids::sysvar::ID,
        false,
        false,
        false,
        1,
        hashes,
    );
    let accounts = vec![
        oracle.clone(),
        cfg.clone(),
        r.clone(),
        ticket.clone(),
        slot_hashes.clone(),
    ];
    let mut unsigned = accounts.clone();
    unsigned[0].is_signer = false;
    assert!(run(unsigned, instruction::FulfillDraw { seed: [7; 32] }.data()).is_err());
    let mut wrong_oracle = accounts.clone();
    wrong_oracle[0] = authority.clone();
    assert!(run(
        wrong_oracle,
        instruction::FulfillDraw { seed: [7; 32] }.data()
    )
    .is_err());
    assert!(run(
        accounts.clone(),
        instruction::FulfillDraw { seed: [6; 32] }.data()
    )
    .is_err());
    let mut forged_hashes = accounts.clone();
    forged_hashes[4].key = winner.key;
    assert!(run(
        forged_hashes,
        instruction::FulfillDraw { seed: [7; 32] }.data()
    )
    .is_err());
    let mut wrong_ticket = accounts.clone();
    wrong_ticket[3].key = authority.key;
    assert!(run(
        wrong_ticket,
        instruction::FulfillDraw { seed: [7; 32] }.data()
    )
    .is_err());
    let rejected_ticket = Ticket {
        round_id: 42,
        agent: *winner.key,
        weight: 10,
        paid: 10_000,
        bump,
        weight_start: 10,
        weight_end: 20,
    };
    ticket
        .try_borrow_mut_data()
        .unwrap()
        .copy_from_slice(&serialized(&rejected_ticket));
    assert!(run(
        accounts.clone(),
        instruction::FulfillDraw { seed: [7; 32] }.data()
    )
    .is_err());
    ticket
        .try_borrow_mut_data()
        .unwrap()
        .copy_from_slice(&serialized(&Ticket {
            weight_start: 0,
            weight_end: 10,
            ..rejected_ticket
        }));
    run(
        accounts.clone(),
        instruction::FulfillDraw { seed: [7; 32] }.data(),
    )
    .unwrap();
    let drawn = read::<Round>(&r);
    assert_eq!(drawn.status, RoundStatus::Settled as u8);
    assert_eq!(drawn.winner, *winner.key);
    assert_eq!(drawn.prize_pool, 10_500);
    assert_eq!(drawn.opex, 3000);
    assert_eq!(drawn.operator_fee, 1500);
    assert_eq!(drawn.prize_pool + drawn.opex + drawn.operator_fee, 15_000);
    assert_eq!(drawn.random_word, 5966281344519424921); // legacy SHA256 vector
    assert_eq!(read::<LotteryConfig>(&cfg).total_prizes_paid, 10_500);
    assert!(run(accounts, instruction::FulfillDraw { seed: [7; 32] }.data()).is_err());
    assert!(transfers.lock().unwrap().is_empty());
}

#[test]
fn cancelled_funding_returns_only_to_configured_treasury_once() {
    let _lock = STUB_LOCK.lock().unwrap();
    let (_restore, transfers) = install_stubs(500);
    let authority = wallet(1, true);
    let oracle = wallet(2, true);
    let treasury = wallet(3, false);
    let cfg = config(*authority.key, *oracle.key, *treasury.key);
    let r = round(RoundStatus::Cancelled, *authority.key);
    let v = vault();
    let accounts = vec![
        authority.clone(),
        cfg,
        r.clone(),
        treasury.clone(),
        v.clone(),
        system(),
    ];
    let mut unsigned = accounts.clone();
    unsigned[0].is_signer = false;
    assert!(run(unsigned, instruction::ReclaimFunding {}.data()).is_err());
    let mut wrong_authority = accounts.clone();
    wrong_authority[0] = oracle.clone();
    assert!(run(wrong_authority, instruction::ReclaimFunding {}.data()).is_err());
    let mut wrong_recipient = accounts.clone();
    wrong_recipient[3] = oracle.clone();
    assert!(run(wrong_recipient, instruction::ReclaimFunding {}.data()).is_err());
    run(accounts.clone(), instruction::ReclaimFunding {}.data()).unwrap();
    assert!(read::<Round>(&r).funding_reclaimed);
    assert_eq!(treasury.lamports(), 1_005_000);
    assert_eq!(v.lamports(), 900_880);
    assert!(run(accounts, instruction::ReclaimFunding {}.data()).is_err());
    assert_eq!(
        transfers.lock().unwrap().as_slice(),
        [Transfer {
            from: *v.key,
            to: *treasury.key,
            amount: 5000,
            pda_signed: true
        }]
    );
}

#[test]
fn close_vault_uses_system_cpi_and_validated_remaining_program_account() {
    let _lock = STUB_LOCK.lock().unwrap();
    let (_restore, transfers) = install_stubs(500);
    let authority = wallet(1, true);
    let oracle = wallet(2, true);
    let treasury = wallet(3, false);
    let cfg = config(*authority.key, *oracle.key, *treasury.key);
    let r = round(RoundStatus::Settled, *authority.key);
    let mut settled = read::<Round>(&r);
    settled.prize_claimed = true;
    settled.residual_withdrawn = true;
    r.try_borrow_mut_data()
        .unwrap()
        .copy_from_slice(&serialized(&settled));
    let v = vault();
    **v.try_borrow_mut_lamports().unwrap() = 890_880;
    let fixed = vec![authority.clone(), cfg, r, v.clone()];
    assert!(run(fixed.clone(), instruction::CloseVault {}.data()).is_err());
    let mut forged = fixed.clone();
    forged.push(oracle);
    assert!(run(forged, instruction::CloseVault {}.data()).is_err());
    let mut valid = fixed;
    valid.push(system());
    run(valid, instruction::CloseVault {}.data()).unwrap();
    assert_eq!(v.lamports(), 0);
    assert_eq!(authority.lamports(), 1_890_880);
    assert_eq!(
        transfers.lock().unwrap().as_slice(),
        [Transfer {
            from: *v.key,
            to: *authority.key,
            amount: 890_880,
            pda_signed: true
        }]
    );
}
