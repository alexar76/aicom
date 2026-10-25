//! Golden wire vectors first checked against Anchor 0.30.1 before migration.
//! Keep these independent from the serializer: deployed accounts and existing signers
//! must produce exactly the same messages under Anchor 1.x / Borsh 1.x.
use aimarket_lottery::{instruction, LotteryConfig, Round, Ticket, ID};
use anchor_lang::prelude::Pubkey;
use anchor_lang::{AccountDeserialize, AccountSerialize, InstructionData};

#[test]
fn instruction_discriminators_and_argument_bytes_are_legacy_compatible() {
    let mut cases: Vec<(&str, Vec<u8>, Vec<u8>)> = Vec::new();
    cases.push((
        "initialize",
        instruction::Initialize {
            ticket_price_lamports: 0x0807060504030201,
            prize_bps: 7000,
            opex_bps: 2000,
            operator_bps: 1000,
        }
        .data(),
        vec![
            175, 175, 109, 31, 13, 152, 155, 237, 1, 2, 3, 4, 5, 6, 7, 8, 88, 27, 208, 7, 232, 3,
        ],
    ));
    cases.push((
        "open_round",
        instruction::OpenRound {
            round_id: 0x0807060504030201,
        }
        .data(),
        vec![66, 235, 123, 240, 8, 35, 185, 159, 1, 2, 3, 4, 5, 6, 7, 8],
    ));
    cases.push((
        "buy_tickets",
        instruction::BuyTickets { count: 0x04030201 }.data(),
        vec![48, 16, 122, 137, 24, 214, 198, 58, 1, 2, 3, 4],
    ));
    cases.push((
        "fund",
        instruction::Fund {
            amount: 0x0807060504030201,
        }
        .data(),
        vec![218, 188, 111, 221, 152, 113, 174, 7, 1, 2, 3, 4, 5, 6, 7, 8],
    ));
    cases.push((
        "close_round",
        instruction::CloseRound {
            seed_commitment: [7; 32],
        }
        .data(),
        vec![
            149, 14, 81, 88, 230, 226, 234, 37, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
            7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
        ],
    ));
    cases.push((
        "fulfill_draw",
        instruction::FulfillDraw { seed: [9; 32] }.data(),
        vec![
            136, 46, 22, 51, 33, 153, 232, 234, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9,
            9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9,
        ],
    ));
    cases.push((
        "claim_prize",
        instruction::ClaimPrize {}.data(),
        vec![157, 233, 139, 121, 246, 62, 234, 235],
    ));
    cases.push((
        "withdraw_residual",
        instruction::WithdrawResidual {}.data(),
        vec![232, 75, 230, 96, 215, 6, 165, 144],
    ));
    cases.push((
        "cancel_round",
        instruction::CancelRound {}.data(),
        vec![82, 70, 134, 54, 46, 96, 148, 8],
    ));
    cases.push((
        "cancel_expired_round",
        instruction::CancelExpiredRound {}.data(),
        vec![116, 3, 118, 60, 62, 120, 198, 17],
    ));
    cases.push((
        "refund_ticket",
        instruction::RefundTicket {}.data(),
        vec![178, 97, 75, 218, 227, 28, 21, 73],
    ));
    cases.push((
        "reclaim_funding",
        instruction::ReclaimFunding {}.data(),
        vec![247, 12, 126, 149, 91, 114, 244, 109],
    ));
    cases.push((
        "close_vault",
        instruction::CloseVault {}.data(),
        vec![141, 103, 17, 126, 72, 75, 29, 29],
    ));
    for (name, actual, legacy) in cases {
        assert_eq!(actual, legacy, "{name}");
    }
}

fn account_bytes<T: AccountSerialize>(value: &T) -> Vec<u8> {
    let mut data = Vec::new();
    value.try_serialize(&mut data).unwrap();
    data
}

#[test]
fn account_layouts_and_discriminators_remain_byte_for_byte_compatible() {
    let config = LotteryConfig {
        authority: Pubkey::new_from_array([1; 32]),
        oracle_signer: Pubkey::new_from_array([2; 32]),
        treasury: Pubkey::new_from_array([3; 32]),
        ticket_price_lamports: 4,
        prize_bps: 7000,
        opex_bps: 2000,
        operator_bps: 1000,
        current_round_id: 5,
        total_prizes_paid: 6,
        total_funding: 7,
        bump: 254,
    };
    let mut expected = vec![174, 54, 184, 175, 81, 20, 237, 24];
    for key in [1, 2, 3] {
        expected.extend([key; 32]);
    }
    expected.extend(4u64.to_le_bytes());
    for bps in [7000u16, 2000, 1000] {
        expected.extend(bps.to_le_bytes());
    }
    for n in [5u64, 6, 7] {
        expected.extend(n.to_le_bytes());
    }
    expected.push(254);
    assert_eq!(account_bytes(&config), expected);
    assert_eq!(account_bytes(&config).len(), 143);
    let decoded = LotteryConfig::try_deserialize(&mut expected.as_slice()).unwrap();
    assert_eq!(decoded.authority, config.authority);
    assert_eq!(decoded.total_funding, 7);

    let ticket = Ticket {
        round_id: 11,
        agent: Pubkey::new_from_array([12; 32]),
        weight: 13,
        paid: 14,
        bump: 253,
        weight_start: 15,
        weight_end: 28,
    };
    let mut expected = vec![41, 228, 24, 165, 78, 90, 235, 200];
    expected.extend(11u64.to_le_bytes());
    expected.extend([12; 32]);
    for n in [13u64, 14] {
        expected.extend(n.to_le_bytes());
    }
    expected.push(253);
    for n in [15u64, 28] {
        expected.extend(n.to_le_bytes());
    }
    assert_eq!(account_bytes(&ticket), expected);
    assert_eq!(expected.len(), 81);
    let decoded = Ticket::try_deserialize(&mut expected.as_slice()).unwrap();
    assert_eq!(decoded.weight_end, 28);
    assert_eq!(decoded.paid, 14);

    let round = Round {
        round_id: 21,
        status: 3,
        opened_at: -22,
        entries_close: 23,
        s_prize_bps: 7000,
        s_opex_bps: 2000,
        s_operator_bps: 1000,
        ticket_revenue: 24,
        funding: 25,
        total_weight: 26,
        prize_pool: 27,
        winner: Pubkey::new_from_array([28; 32]),
        random_word: 29,
        prize_claimed: true,
        bump: 252,
        seed_commitment: [30; 32],
        close_slot: 31,
        draw_slot: 63,
        rent_reserve: 33,
        opex: 34,
        operator_fee: 35,
        residual_withdrawn: true,
        funding_reclaimed: false,
    };
    let mut expected = vec![87, 127, 165, 51, 73, 78, 116, 174];
    expected.extend(21u64.to_le_bytes());
    expected.push(3);
    expected.extend((-22i64).to_le_bytes());
    expected.extend(23i64.to_le_bytes());
    for bps in [7000u16, 2000, 1000] {
        expected.extend(bps.to_le_bytes());
    }
    for n in [24u64, 25, 26, 27] {
        expected.extend(n.to_le_bytes());
    }
    expected.extend([28; 32]);
    expected.extend(29u64.to_le_bytes());
    expected.extend([1, 252]);
    expected.extend([30; 32]);
    for n in [31u64, 63, 33, 34, 35] {
        expected.extend(n.to_le_bytes());
    }
    expected.extend([1, 0]);
    assert_eq!(account_bytes(&round), expected);
    assert_eq!(expected.len(), 187);
    let decoded = Round::try_deserialize(&mut expected.as_slice()).unwrap();
    assert_eq!(decoded.draw_slot, 63);
    assert_eq!(decoded.prize_pool, 27);
    assert_eq!(std::mem::size_of::<LotteryConfig>() + 8, 144);
    assert_eq!(std::mem::size_of::<Round>() + 8, 192);
    assert_eq!(std::mem::size_of::<Ticket>() + 8, 88);
}

#[test]
fn program_id_and_pda_seeds_are_legacy_compatible() {
    assert_eq!(
        ID.to_string(),
        "DT6QVF7HhCQTFRCcP7V6AJpQF6ZQzEc9LQSrq85MHpFD"
    );
    let rid = 42u64.to_le_bytes();
    let buyer = Pubkey::new_from_array([7; 32]);
    for (legacy_key, legacy_bump, seeds) in [
        (
            "9j4nCCS2xoDjAK2yJENBib9qqQQXNvvct8PppP9NcF6Q",
            253,
            vec![b"lottery_config".as_slice()],
        ),
        (
            "8EnJBffaaWBMs4n4nB8qXqA8QLAEqANHLvcQYbrQhm91",
            255,
            vec![b"round".as_slice(), rid.as_slice()],
        ),
        (
            "BPP5ipDhG8DcvKeyNxuux3JGYvm19Eat31zeHz4Ey3ij",
            254,
            vec![b"vault".as_slice(), rid.as_slice()],
        ),
        (
            "22qAqiKq3yZgKPJcmF79N9GywzNbLuMsCqvtSgjMChfm",
            254,
            vec![b"ticket".as_slice(), rid.as_slice(), buyer.as_ref()],
        ),
    ] {
        let (key, bump) = Pubkey::find_program_address(&seeds, &ID);
        assert_eq!(key.to_string(), legacy_key);
        assert_eq!(bump, legacy_bump);
    }
}
