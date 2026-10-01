// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {AIMarketEscrow} from "../src/AIMarketEscrow.sol";

/// A fee-on-transfer ERC-20. Ethereum USDT has exactly this: an owner-settable
/// `basisPointsRate`, currently 0. The escrow is documented as deploying "identically on
/// Base / Ethereum / Arbitrum" for "USDT/USDC", so a token whose fee is switched on later
/// is a token-behaviour dependency, not a hypothetical.
contract FeeToken {
    string public name = "FeeUSDT";
    uint8 public decimals = 6;
    uint256 public feeBps;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(uint256 bps) {
        feeBps = bps;
    }

    function mint(address to, uint256 a) external {
        balanceOf[to] += a;
    }

    function approve(address s, uint256 a) external returns (bool) {
        allowance[msg.sender][s] = a;
        return true;
    }

    function transfer(address to, uint256 a) external returns (bool) {
        balanceOf[msg.sender] -= a;
        balanceOf[to] += a;
        return true;
    }

    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        if (allowance[f][msg.sender] != type(uint256).max) {
            allowance[f][msg.sender] -= a;
        }
        uint256 fee = (a * feeBps) / 10_000;
        balanceOf[f] -= a;
        balanceOf[t] += a - fee;      // the fee never arrives
        balanceOf[address(0xFEE)] += fee;
        return true;
    }
}

/// `openChannel` booked `depositAmount` as both `depositAmount` and `balance` straight after
/// `safeTransferFrom`, without measuring what actually landed. Under a fee-taking token the
/// per-channel books therefore exceed the contract's real holdings, and the shortfall is
/// paid out of OTHER channels' escrowed principal until settlements start reverting.
///
/// The sibling accounting in this ecosystem already does it the other way: the lottery's
/// `_pullPayment` credits the measured delta.
contract EscrowMeasuresWhatArrivedTest is Test {
    AIMarketEscrow escrow;
    FeeToken token;
    address user = address(0xA11CE);

    function setUp() public {
        escrow = new AIMarketEscrow(new address[](0), new address[](0));
        token = new FeeToken(100); // 1%
        escrow.setTokenWhitelist(address(token), true);
        token.mint(user, 1_000_000e6);
        vm.prank(user);
        token.approve(address(escrow), type(uint256).max);
    }

    function test_the_channel_is_credited_with_what_actually_arrived() public {
        uint256 asked = 10_000e6;
        vm.prank(user);
        escrow.openChannel(bytes32("c1"), address(token), asked);

        uint256 held = token.balanceOf(address(escrow));
        (, , , uint256 depositAmount, uint256 balance, , , , ) = escrow.channels(bytes32("c1"));

        assertEq(held, asked - (asked / 100), "fixture: the fee did not apply");
        assertEq(depositAmount, held, "booked more than the escrow received");
        assertEq(balance, held, "spendable balance exceeds the escrow's holdings");
    }

    function test_the_books_never_exceed_the_holdings_across_channels() public {
        uint256 asked = 10_000e6;
        for (uint256 i = 0; i < 3; i++) {
            vm.prank(user);
            escrow.openChannel(bytes32(i + 1), address(token), asked);
        }
        uint256 booked;
        for (uint256 i = 0; i < 3; i++) {
            (, , , , uint256 balance, , , , ) = escrow.channels(bytes32(i + 1));
            booked += balance;
        }
        assertLe(booked, token.balanceOf(address(escrow)), "escrow is insolvent on its own books");
    }

    function test_a_zero_fee_token_is_unaffected() public {
        FeeToken plain = new FeeToken(0);
        escrow.setTokenWhitelist(address(plain), true);
        plain.mint(user, 1_000_000e6);
        vm.startPrank(user);
        plain.approve(address(escrow), type(uint256).max);
        escrow.openChannel(bytes32("plain"), address(plain), 10_000e6);
        vm.stopPrank();
        (, , , uint256 depositAmount, , , , , ) = escrow.channels(bytes32("plain"));
        assertEq(depositAmount, 10_000e6);
    }
}
