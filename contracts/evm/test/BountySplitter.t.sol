// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {BountySplitter} from "../src/BountySplitter.sol";

contract MockUSDC is ERC20 {
    constructor() ERC20("USD Coin", "USDC") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amt) external { _mint(to, amt); }
}

/// @notice The money invariants that must hold no matter what the Treasury operator intends:
/// a pool can never be over-drawn, a role pays at most once per finding, only the owner can move
/// anything, and an expired pool refunds. The off-chain gate (signatures, verifier quorum, dedup)
/// is tested in the Python suite; this file guards the on-chain half.
contract BountySplitterTest is Test {
    BountySplitter splitter;
    MockUSDC usdc;

    address treasury = address(this);        // the owner == the Treasury operator key
    address finder = address(0xF1);
    address fixer = address(0xF2);
    address conductor = address(0xF3);
    address stranger = address(0xBAD);

    bytes32 constant FINDING = keccak256("mom-1");
    bytes32 constant ROLE_FINDER = keccak256("finder");
    bytes32 constant ROLE_FIXER = keccak256("fixer");
    bytes32 constant ROLE_CONDUCTOR = keccak256("conductor");

    function setUp() public {
        usdc = new MockUSDC();
        address[] memory tokens = new address[](1);
        tokens[0] = address(usdc);
        splitter = new BountySplitter(tokens);
        usdc.mint(treasury, 1_000_000e6);
        usdc.approve(address(splitter), type(uint256).max);
    }

    function _fund(uint256 amount) internal {
        splitter.fundPool(FINDING, address(usdc), amount);
    }

    // ── funding ─────────────────────────────────────────────────────────────
    function test_FundPoolEscrowsTokens() public {
        _fund(50e6);
        assertEq(usdc.balanceOf(address(splitter)), 50e6);
        assertEq(splitter.poolRemaining(FINDING), 50e6);
    }

    function test_OnlyOwnerCanFund() public {
        vm.prank(stranger);
        vm.expectRevert();
        splitter.fundPool(FINDING, address(usdc), 10e6);
    }

    function test_RejectsNonWhitelistedToken() public {
        MockUSDC other = new MockUSDC();
        other.mint(treasury, 100e6);
        other.approve(address(splitter), type(uint256).max);
        vm.expectRevert(bytes("token not whitelisted"));
        splitter.fundPool(FINDING, address(other), 10e6);
    }

    function test_RejectsOverCap() public {
        vm.expectRevert(bytes("bad amount"));
        splitter.fundPool(FINDING, address(usdc), 200_000e6); // > MAX_POOL
    }

    // ── the split, and the invariants that bound it ──────────────────────────
    function test_ReleasesTheFullSplit() public {
        _fund(50e6);
        splitter.releaseShare(FINDING, ROLE_FINDER, finder, 25e6);        // 50%
        splitter.releaseShare(FINDING, ROLE_FIXER, fixer, 17_500_000);    // 35%
        splitter.releaseShare(FINDING, ROLE_CONDUCTOR, conductor, 7_500_000); // 15%
        assertEq(usdc.balanceOf(finder), 25e6);
        assertEq(usdc.balanceOf(fixer), 17_500_000);
        assertEq(usdc.balanceOf(conductor), 7_500_000);
        assertEq(splitter.poolRemaining(FINDING), 0);
    }

    function test_PoolCannotBeOverDrawn() public {
        _fund(50e6);
        splitter.releaseShare(FINDING, ROLE_FINDER, finder, 25e6);
        vm.expectRevert(bytes("over-draw"));
        splitter.releaseShare(FINDING, ROLE_FIXER, fixer, 30e6); // 25 + 30 > 50
    }

    function test_RolePaysOnlyOncePerFinding() public {
        _fund(50e6);
        splitter.releaseShare(FINDING, ROLE_FINDER, finder, 10e6);
        vm.expectRevert(bytes("role already paid"));
        splitter.releaseShare(FINDING, ROLE_FINDER, finder, 5e6);   // on-chain replay guard
    }

    function test_SameRoleCanPayOnADifferentFinding() public {
        _fund(50e6);
        splitter.releaseShare(FINDING, ROLE_FINDER, finder, 10e6);
        bytes32 other = keccak256("mom-2");
        splitter.fundPool(other, address(usdc), 20e6);
        splitter.releaseShare(other, ROLE_FINDER, finder, 10e6);     // different bug → allowed
        assertEq(usdc.balanceOf(finder), 20e6);
    }

    function test_OnlyOwnerCanRelease() public {
        _fund(50e6);
        vm.prank(stranger);
        vm.expectRevert();
        splitter.releaseShare(FINDING, ROLE_FINDER, stranger, 25e6);
    }

    function test_CannotReleaseWithoutPool() public {
        vm.expectRevert(bytes("no pool"));
        splitter.releaseShare(FINDING, ROLE_FINDER, finder, 1e6);
    }

    function test_RejectsZeroRecipientAndAmount() public {
        _fund(10e6);
        vm.expectRevert(bytes("bad recipient"));
        splitter.releaseShare(FINDING, ROLE_FINDER, address(0), 1e6);
        vm.expectRevert(bytes("zero"));
        splitter.releaseShare(FINDING, ROLE_FINDER, finder, 0);
    }

    // ── expiry ──────────────────────────────────────────────────────────────
    function test_RefundExpiredReturnsRemainderToTreasury() public {
        _fund(50e6);
        splitter.releaseShare(FINDING, ROLE_FINDER, finder, 25e6);
        uint256 before = usdc.balanceOf(treasury);
        vm.warp(block.timestamp + 31 days);
        splitter.refundExpired(FINDING);
        assertEq(usdc.balanceOf(treasury) - before, 25e6);      // the unclaimed half comes back
        assertEq(splitter.poolRemaining(FINDING), 0);
    }

    function test_CannotRefundBeforeExpiry() public {
        _fund(50e6);
        vm.expectRevert(bytes("not expired"));
        splitter.refundExpired(FINDING);
    }

    function test_CannotReleaseAfterRefund() public {
        _fund(50e6);
        vm.warp(block.timestamp + 31 days);
        splitter.refundExpired(FINDING);
        vm.expectRevert(bytes("over-draw"));                     // pool closed out
        splitter.releaseShare(FINDING, ROLE_FINDER, finder, 1e6);
    }

    // ── fuzz: the core invariant ────────────────────────────────────────────
    function testFuzz_NeverPaysMoreThanFunded(uint96 funded, uint96 a, uint96 b) public {
        funded = uint96(bound(funded, 1e6, 100_000e6));
        _fund(funded);
        uint256 paid;
        if (a > 0 && a <= funded) {
            splitter.releaseShare(FINDING, ROLE_FINDER, finder, a);
            paid += a;
        }
        if (b > 0 && paid + b <= funded) {
            splitter.releaseShare(FINDING, ROLE_FIXER, fixer, b);
            paid += b;
        }
        assertLe(paid, funded);
        assertEq(usdc.balanceOf(finder) + usdc.balanceOf(fixer), paid);
    }
}
