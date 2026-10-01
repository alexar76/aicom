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

/// @notice 6-decimal token that skims 1% on every transfer — the shape of Ethereum USDT with a
///         non-zero `basisPointsRate`. Whitelistable (decimals are right), yet a funder who
///         sends N delivers less than N.
contract MockFeeUSDC is ERC20 {
    uint256 public constant FEE_BPS = 100;              // 1%
    address public constant SINK = address(0xFEE);

    constructor() ERC20("Fee USD Coin", "fUSDC") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amt) external { _mint(to, amt); }

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && to != address(0)) {
            uint256 fee = value * FEE_BPS / 10_000;
            super._update(from, SINK, fee);
            super._update(from, to, value - fee);
        } else {
            super._update(from, to, value);         // mint / burn pay no fee
        }
    }
}

/// @notice 6-decimal token whose transfers deliver nothing (absorbing blocklist behaviour).
///         Listing it is allowed — the decimals are right — so `fundPool` is the only place
///         that can notice the pool would be credited for money that never showed up.
contract MockBlackHole is ERC20 {
    address public constant SINK = address(0xDEAD);

    constructor() ERC20("Black Hole", "BH") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amt) external { _mint(to, amt); }

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && to != address(0)) {
            super._update(from, SINK, value);           // the whole transfer is swallowed
        } else {
            super._update(from, to, value);
        }
    }
}

/// @notice Default OpenZeppelin ERC20 — 18 decimals, so MAX_POOL (6-decimal units) would stop
///         bounding anything if this were ever listed.
contract MockToken18 is ERC20 {
    constructor() ERC20("Eighteen", "E18") {}
    function mint(address to, uint256 amt) external { _mint(to, amt); }
}

/// @notice Answers no `decimals()` at all (proxy without the view, or an EOA).
contract NoDecimals {}

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

    // ── solvency: book what arrived, not what was asked for ─────────────────

    function _feeToken() internal returns (MockFeeUSDC t) {
        t = new MockFeeUSDC();
        t.mint(treasury, 1_000_000e6);
        t.approve(address(splitter), type(uint256).max);
        splitter.setTokenWhitelist(address(t), true);   // 6 decimals — listing is allowed
    }

    function test_FundPoolCreditsOnlyWhatArrived() public {
        MockFeeUSDC fee = _feeToken();
        splitter.fundPool(FINDING, address(fee), 100e6);
        // 1% skimmed in flight: 99 arrived, so 99 is what the pool may ever pay out.
        assertEq(fee.balanceOf(address(splitter)), 99e6);
        assertEq(splitter.poolRemaining(FINDING), 99e6);
    }

    /// The invariant the old code broke: crediting the REQUESTED amount let pool A's books
    /// spend tokens that only ever arrived for pool B.
    function test_CreditedTotalNeverExceedsHoldings() public {
        MockFeeUSDC fee = _feeToken();
        bytes32 second = keccak256("mom-2");
        splitter.fundPool(FINDING, address(fee), 100e6);
        splitter.fundPool(second, address(fee), 100e6);

        uint256 credited = splitter.poolRemaining(FINDING) + splitter.poolRemaining(second);
        assertLe(credited, fee.balanceOf(address(splitter)));
        assertEq(credited, 198e6);                      // not the 200e6 that was requested
    }

    function test_RejectsTokenThatDeliversNothing() public {
        MockBlackHole bh = new MockBlackHole();
        bh.mint(treasury, 1_000e6);
        bh.approve(address(splitter), type(uint256).max);
        splitter.setTokenWhitelist(address(bh), true);  // decimals are fine; delivery is not
        vm.expectRevert(bytes("nothing received"));
        splitter.fundPool(FINDING, address(bh), 100e6);
    }

    // ── whitelist may only admit the scale MAX_POOL assumes ─────────────────

    function test_RejectsTokenWithWrongDecimals() public {
        MockToken18 t = new MockToken18();
        vm.expectRevert(BountySplitter.UnsupportedTokenDecimals.selector);
        splitter.setTokenWhitelist(address(t), true);
    }

    function test_RejectsTokenWithoutDecimals() public {
        NoDecimals t = new NoDecimals();
        vm.expectRevert(BountySplitter.UnsupportedTokenDecimals.selector);
        splitter.setTokenWhitelist(address(t), true);
    }

    function test_DelistingIsNeverBlocked() public {
        MockToken18 t = new MockToken18();
        splitter.setTokenWhitelist(address(t), false);  // can only tighten — must not revert
        assertFalse(splitter.tokenWhitelisted(address(t)));
    }

    // ── expiry clock restarts on top-up ─────────────────────────────────────

    /// A pool refunded once and then re-funded kept its original `fundedAt`, so it was already
    /// expired the moment it was topped up — the new money could be swept straight back out.
    function test_TopUpRestartsExpiryClock() public {
        _fund(50e6);
        vm.warp(block.timestamp + 31 days);
        splitter.refundExpired(FINDING);

        _fund(20e6);                                    // same finding, fresh money
        assertEq(splitter.poolRemaining(FINDING), 20e6);
        vm.expectRevert(bytes("not expired"));
        splitter.refundExpired(FINDING);
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
