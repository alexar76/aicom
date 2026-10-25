//! Golden vectors captured with bincode 1.3.3 before replacing its engine.
//! Exercise public upstream APIs, so the deployed loader/sysvar and CPI formats
//! are checked without adding the removed codec as a test dependency.
use anchor_lang::compat::{solana_loader_v3_interface, solana_stake_interface, solana_sysvar};
use anchor_lang::error::{Error, ErrorCode};
use anchor_lang::prelude::{AccountInfo, Pubkey};
use anchor_lang::solana_program::{
    bpf_loader_upgradeable::UpgradeableLoaderState, instruction::Instruction,
    program_error::ProgramError, system_instruction::SystemInstruction,
};
use anchor_lang::{AccountDeserialize, ProgramData};
use solana_loader_v3_interface::instruction::UpgradeableLoaderInstruction;
use solana_stake_interface::{
    instruction::{
        AuthorizeCheckedWithSeedArgs, AuthorizeWithSeedArgs, LockupArgs, LockupCheckedArgs,
        StakeInstruction,
    },
    state::{Authorized, Lockup, StakeAuthorize},
};
use solana_sysvar::{
    clock::Clock, epoch_rewards::EpochRewards, epoch_schedule::EpochSchedule, fees::Fees,
    last_restart_slot::LastRestartSlot, recent_blockhashes::RecentBlockhashes, rent::Rent,
    rewards::Rewards, slot_hashes::SlotHashes, slot_history::SlotHistory, SysvarSerialize,
};

const BASELINE: &str = include_str!("fixtures/legacy-wire-v1.tsv");
const WIDE: u64 = 0x0807060504030201;
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn fixture(name: &str) -> Vec<u8> {
    let row = BASELINE
        .lines()
        .find(|line| line.starts_with(&format!("WIRE\t{name}\t")))
        .expect("missing legacy fixture");
    let parts: Vec<_> = row.split('\t').collect();
    let bytes: Vec<_> = parts[3]
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect();
    assert_eq!(bytes.len(), parts[2].parse::<usize>().unwrap());
    bytes
}
macro_rules! wire {
    ($name:expr,$value:expr) => {{
        let value = &$value;
        let actual = Instruction::new_with_bincode(Pubkey::default(), &value, vec![]).data;
        assert_eq!(
            actual,
            fixture($name),
            "legacy serialization changed: {}",
            $name
        );
    }};
}
fn info(key: Pubkey, data: Vec<u8>) -> AccountInfo<'static> {
    AccountInfo::new(
        Box::leak(Box::new(key)),
        false,
        false,
        Box::leak(Box::new(1)),
        Box::leak(data.into_boxed_slice()),
        Box::leak(Box::new(Pubkey::default())),
        false,
    )
}
fn program_error(error: Error, expected: ProgramError) {
    match error {
        Error::ProgramError(error) => assert_eq!(error.program_error, expected),
        other => panic!("expected {expected:?}, received {other:?}"),
    }
}
fn anchor_error(error: Error, expected: ErrorCode) {
    match error {
        Error::AnchorError(error) => assert_eq!(error.error_code_number, u32::from(expected)),
        other => panic!("expected Anchor error, received {other:?}"),
    }
}

#[test]
fn all_system_loader_and_stake_cpi_payloads_keep_legacy_bytes() {
    let a = Pubkey::new_from_array([0x11; 32]);
    let b = Pubkey::new_from_array([0x22; 32]);
    let c = Pubkey::new_from_array([0x33; 32]);
    let wide = WIDE;
    let sys = vec![
        (
            "system_create",
            SystemInstruction::CreateAccount {
                lamports: wide,
                space: 88,
                owner: c,
            },
        ),
        ("system_assign", SystemInstruction::Assign { owner: c }),
        (
            "system_transfer",
            SystemInstruction::Transfer { lamports: wide },
        ),
        (
            "system_create_seed",
            SystemInstruction::CreateAccountWithSeed {
                base: a,
                seed: "seed-ё".into(),
                lamports: wide,
                space: 88,
                owner: c,
            },
        ),
        (
            "system_advance_nonce",
            SystemInstruction::AdvanceNonceAccount,
        ),
        (
            "system_withdraw_nonce",
            SystemInstruction::WithdrawNonceAccount(wide),
        ),
        (
            "system_initialize_nonce",
            SystemInstruction::InitializeNonceAccount(a),
        ),
        (
            "system_authorize_nonce",
            SystemInstruction::AuthorizeNonceAccount(b),
        ),
        ("system_allocate", SystemInstruction::Allocate { space: 88 }),
        (
            "system_allocate_seed",
            SystemInstruction::AllocateWithSeed {
                base: a,
                seed: "seed-ё".into(),
                space: 88,
                owner: c,
            },
        ),
        (
            "system_assign_seed",
            SystemInstruction::AssignWithSeed {
                base: a,
                seed: "seed-ё".into(),
                owner: c,
            },
        ),
        (
            "system_transfer_seed",
            SystemInstruction::TransferWithSeed {
                lamports: wide,
                from_seed: "seed-ё".into(),
                from_owner: c,
            },
        ),
        (
            "system_upgrade_nonce",
            SystemInstruction::UpgradeNonceAccount,
        ),
    ];
    for (name, v) in sys {
        wire!(name, v);
    }
    let loader = vec![
        (
            "loader_ix_initialize",
            UpgradeableLoaderInstruction::InitializeBuffer,
        ),
        (
            "loader_ix_write",
            UpgradeableLoaderInstruction::Write {
                offset: 0x04030201,
                bytes: vec![0, 1, 2, 253, 254, 255],
            },
        ),
        (
            "loader_ix_deploy",
            UpgradeableLoaderInstruction::DeployWithMaxDataLen {
                max_data_len: 0x0807060504030201usize,
            },
        ),
        ("loader_ix_upgrade", UpgradeableLoaderInstruction::Upgrade),
        (
            "loader_ix_set_authority",
            UpgradeableLoaderInstruction::SetAuthority,
        ),
        ("loader_ix_close", UpgradeableLoaderInstruction::Close),
        (
            "loader_ix_extend",
            UpgradeableLoaderInstruction::ExtendProgram {
                additional_bytes: 0x04030201,
            },
        ),
        (
            "loader_ix_set_authority_checked",
            UpgradeableLoaderInstruction::SetAuthorityChecked,
        ),
        ("loader_ix_migrate", UpgradeableLoaderInstruction::Migrate),
        (
            "loader_ix_extend_checked",
            UpgradeableLoaderInstruction::ExtendProgramChecked {
                additional_bytes: 0x04030201,
            },
        ),
    ];
    for (name, v) in loader {
        wire!(name, v);
    }
    let stake = vec![
        (
            "stake_initialize",
            StakeInstruction::Initialize(
                Authorized {
                    staker: a,
                    withdrawer: b,
                },
                Lockup {
                    unix_timestamp: -5,
                    epoch: wide,
                    custodian: c,
                },
            ),
        ),
        (
            "stake_authorize",
            StakeInstruction::Authorize(a, StakeAuthorize::Withdrawer),
        ),
        ("stake_delegate", StakeInstruction::DelegateStake),
        ("stake_split", StakeInstruction::Split(wide)),
        ("stake_withdraw", StakeInstruction::Withdraw(wide)),
        ("stake_deactivate", StakeInstruction::Deactivate),
        (
            "stake_lockup",
            StakeInstruction::SetLockup(LockupArgs {
                unix_timestamp: Some(-5),
                epoch: Some(wide),
                custodian: Some(c),
            }),
        ),
        (
            "stake_lockup_none",
            StakeInstruction::SetLockup(LockupArgs {
                unix_timestamp: None,
                epoch: None,
                custodian: None,
            }),
        ),
        ("stake_merge", StakeInstruction::Merge),
        (
            "stake_authorize_seed",
            StakeInstruction::AuthorizeWithSeed(AuthorizeWithSeedArgs {
                new_authorized_pubkey: b,
                stake_authorize: StakeAuthorize::Staker,
                authority_seed: "seed-ё".into(),
                authority_owner: c,
            }),
        ),
        (
            "stake_initialize_checked",
            StakeInstruction::InitializeChecked,
        ),
        (
            "stake_authorize_checked",
            StakeInstruction::AuthorizeChecked(StakeAuthorize::Withdrawer),
        ),
        (
            "stake_authorize_checked_seed",
            StakeInstruction::AuthorizeCheckedWithSeed(AuthorizeCheckedWithSeedArgs {
                stake_authorize: StakeAuthorize::Withdrawer,
                authority_seed: "seed-ё".into(),
                authority_owner: c,
            }),
        ),
        (
            "stake_lockup_checked",
            StakeInstruction::SetLockupChecked(LockupCheckedArgs {
                unix_timestamp: Some(-5),
                epoch: Some(wide),
            }),
        ),
        ("stake_get_minimum", StakeInstruction::GetMinimumDelegation),
        (
            "stake_deactivate_delinquent",
            StakeInstruction::DeactivateDelinquent,
        ),
        ("stake_redelegate", StakeInstruction::Redelegate),
        ("stake_move", StakeInstruction::MoveStake(wide)),
        ("stake_move_lamports", StakeInstruction::MoveLamports(wide)),
    ];
    for (name, v) in stake {
        wire!(name, v);
    }
}

#[test]
fn loader_states_preserve_options_pubkeys_and_allow_trailing_program_bytes() {
    let a = Pubkey::new_from_array([0x11; 32]);
    let b = Pubkey::new_from_array([0x22; 32]);
    let c = Pubkey::new_from_array([0x33; 32]);
    for (name, state) in [
        (
            "loader_uninitialized",
            UpgradeableLoaderState::Uninitialized,
        ),
        (
            "loader_buffer_none",
            UpgradeableLoaderState::Buffer {
                authority_address: None,
            },
        ),
        (
            "loader_buffer_some",
            UpgradeableLoaderState::Buffer {
                authority_address: Some(a),
            },
        ),
        (
            "loader_program",
            UpgradeableLoaderState::Program {
                programdata_address: b,
            },
        ),
        (
            "loader_programdata_none",
            UpgradeableLoaderState::ProgramData {
                slot: WIDE,
                upgrade_authority_address: None,
            },
        ),
        (
            "loader_programdata_some",
            UpgradeableLoaderState::ProgramData {
                slot: WIDE,
                upgrade_authority_address: Some(c),
            },
        ),
    ] {
        wire!(name, state);
        let mut bytes = fixture(name);
        bytes.extend_from_slice(&[0x7f, b'E', b'L', b'F', 0xff]);
        assert_eq!(
            UpgradeableLoaderState::try_deserialize(&mut bytes.as_slice()).unwrap(),
            state
        );
        if let UpgradeableLoaderState::ProgramData {
            slot,
            upgrade_authority_address,
        } = state
        {
            let decoded = ProgramData::try_deserialize(&mut bytes.as_slice()).unwrap();
            assert_eq!(decoded.slot, slot);
            assert_eq!(decoded.upgrade_authority_address, upgrade_authority_address);
        } else {
            anchor_error(
                ProgramData::try_deserialize(&mut bytes.as_slice())
                    .err()
                    .unwrap(),
                ErrorCode::AccountNotProgramData,
            );
        }
    }
    for bytes in [
        vec![],
        vec![3, 0, 0],
        vec![99, 0, 0, 0],
        {
            let mut malformed = fixture("loader_programdata_some");
            malformed[12] = 2;
            malformed
        },
        fixture("loader_programdata_some")[..44].to_vec(),
    ] {
        program_error(
            UpgradeableLoaderState::try_deserialize(&mut bytes.as_slice()).unwrap_err(),
            ProgramError::InvalidAccountData,
        );
    }
}

fn assert_sysvar<T: SysvarSerialize>(name: &str, value: T) {
    wire!(name, value);
    let expected = fixture(name);
    let account = info(T::id(), expected.clone());
    let decoded = T::from_account_info(&account).unwrap();
    wire!(name, decoded);
    let mut padded = expected.clone();
    padded.extend([0xff; 8]);
    let padded_info = info(T::id(), padded);
    let padded_decoded = T::from_account_info(&padded_info).unwrap();
    wire!(name, padded_decoded);
    let mut output = info(T::id(), vec![0xaa; expected.len() + 8]);
    assert_eq!(value.to_account_info(&mut output), Some(()));
    let output = output.try_borrow_data().unwrap();
    assert_eq!(&output[..expected.len()], expected.as_slice());
    assert_eq!(&output[expected.len()..], &[0xaa; 8]);
}

#[test]
fn sysvar_public_apis_preserve_unsigned_signed_float_bool_and_u128_fields() {
    assert_sysvar(
        "clock",
        Clock {
            slot: WIDE,
            epoch_start_timestamp: -2,
            epoch: 3,
            leader_schedule_epoch: 4,
            unix_timestamp: -5,
        },
    );
    assert_sysvar(
        "rent",
        Rent {
            lamports_per_byte_year: WIDE,
            exemption_threshold: 2.5,
            burn_percent: 50,
        },
    );
    assert_sysvar(
        "epoch_schedule",
        EpochSchedule {
            slots_per_epoch: WIDE,
            leader_schedule_slot_offset: 2,
            warmup: true,
            first_normal_epoch: 3,
            first_normal_slot: 4,
        },
    );
    assert_sysvar(
        "epoch_rewards",
        EpochRewards {
            distribution_starting_block_height: WIDE,
            num_partitions: 2,
            parent_blockhash: [0x44; 32].into(),
            total_points: 0x100f0e0d0c0b0a090807060504030201u128,
            total_rewards: 3,
            distributed_rewards: 4,
            active: true,
        },
    );
    assert_sysvar(
        "last_restart_slot",
        LastRestartSlot {
            last_restart_slot: WIDE,
        },
    );
    let mut fees = Fees::default();
    fees.fee_calculator.lamports_per_signature = WIDE;
    assert_sysvar("fees", fees);
    assert_sysvar("rewards", Rewards::new(2.5));
    assert_sysvar("recent_blockhashes_empty", RecentBlockhashes::default());
    let hashes = SlotHashes::new(&[(502, [0x55; 32].into()), (500, [0x66; 32].into())]);
    let recent: RecentBlockhashes = hashes
        .iter()
        .map(|(slot, hash)| solana_sysvar::recent_blockhashes::IterItem(*slot, hash, WIDE))
        .collect();
    assert_sysvar("recent_blockhashes", recent);
    assert_eq!(Clock::size_of(), 40);
    assert_eq!(Rent::size_of(), 17);
    assert_eq!(EpochSchedule::size_of(), 33);
    assert_eq!(EpochRewards::size_of(), 81);
    assert_eq!(RecentBlockhashes::size_of(), 6008);
}

#[test]
fn sysvar_rejections_error_mapping_and_short_writer_behavior_remain_compatible() {
    let clock = Clock {
        slot: WIDE,
        epoch_start_timestamp: -2,
        epoch: 3,
        leader_schedule_epoch: 4,
        unix_timestamp: -5,
    };
    for account in [
        info(Pubkey::new_from_array([9; 32]), fixture("clock")),
        info(solana_sysvar::clock::ID, vec![0; 39]),
    ] {
        assert_eq!(
            Clock::from_account_info(&account).unwrap_err(),
            ProgramError::InvalidArgument
        );
        let account = Box::leak(Box::new(account));
        anchor_error(
            anchor_lang::accounts::sysvar::Sysvar::<Clock>::from_account_info(account).unwrap_err(),
            ErrorCode::AccountSysvarMismatch,
        );
    }
    let mut bad_bool = fixture("epoch_rewards");
    bad_bool[80] = 2;
    assert_eq!(
        EpochRewards::from_account_info(&info(solana_sysvar::epoch_rewards::ID, bad_bool))
            .unwrap_err(),
        ProgramError::InvalidArgument
    );
    let mut output = info(solana_sysvar::clock::ID, vec![0xaa; 5]);
    assert_eq!(clock.to_account_info(&mut output), None);
    assert_eq!(
        &output.try_borrow_data().unwrap()[..],
        fixture("clock_short_output").as_slice()
    );
}

#[test]
fn truncated_sysvar_sequences_are_rejected_instead_of_returning_short_vectors() {
    let full = fixture("recent_blockhashes");
    // The legacy header declares two entries. Keep one complete entry, then
    // truncate the second at each fixed field boundary and inside its hash.
    for length in [8usize, 9, 39, 40, 47, 48, 49, 79, 80, 87] {
        let account = info(
            solana_sysvar::recent_blockhashes::ID,
            full[..length].to_vec(),
        );
        assert_eq!(
            RecentBlockhashes::from_account_info(&account).unwrap_err(),
            ProgramError::InvalidArgument,
            "truncated sequence at byte {length} must not decode successfully"
        );
    }
    let account = info(
        solana_sysvar::recent_blockhashes::ID,
        2u64.to_le_bytes().to_vec(),
    );
    assert_eq!(
        RecentBlockhashes::from_account_info(&account).unwrap_err(),
        ProgramError::InvalidArgument
    );
}

#[test]
fn large_sysvar_sequences_keep_legacy_lengths_order_and_unsupported_read_behavior() {
    wire!(
        "slot_hashes",
        SlotHashes::new(&[(502, [0x11; 32].into()), (500, [0x22; 32].into())])
    );
    let mut history = SlotHistory::default();
    history.add(42);
    let bytes = Instruction::new_with_bincode(Pubkey::default(), &history, vec![]).data;
    let row = BASELINE
        .lines()
        .find(|line| line.starts_with("DIGEST\tslot_history\t"))
        .unwrap();
    let fields: Vec<_> = row.split('\t').collect();
    assert_eq!(bytes.len(), fields[2].parse::<usize>().unwrap());
    assert_eq!(hex(solana_sha256_hasher::hash(&bytes).as_ref()), fields[3]);
    assert_eq!(SlotHistory::size_of(), 131_097);
    assert_eq!(SlotHashes::size_of(), 20_488);
    let account = info(solana_sysvar::clock::ID, fixture("clock"));
    assert_eq!(
        SlotHistory::from_account_info(&account).unwrap_err(),
        ProgramError::UnsupportedSysvar
    );
    assert_eq!(
        SlotHashes::from_account_info(&account).unwrap_err(),
        ProgramError::UnsupportedSysvar
    );
}

#[test]
fn generic_instruction_serializer_preserves_integer_widths_unicode_and_float_bits() {
    wire!("usize", 0x0807060504030201usize);
    wire!("i128", -0x100f0e0d0c0b0a090807060504030201i128);
    wire!("char_utf8", 'ё');
    wire!("str_utf8", "seed-ё");
    wire!("bytes", vec![0u8, 1, 2, 255]);
    wire!("f64_nan", f64::from_bits(0x7ff8000000000042));
    wire!("f64_negative_zero", -0.0f64);
}
