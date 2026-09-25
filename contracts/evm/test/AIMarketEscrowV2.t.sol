// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AIMarketEscrow} from "../src/AIMarketEscrow.sol";
import {AIMarketEscrowV2} from "../src/AIMarketEscrowV2.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * Five ways the deployed escrow loses money, each proved against V1 and then shown fixed
 * in V2. Every test here opens with the V1 behaviour in the same file, so the patch can
 * never be argued about in the abstract: the assertion that V1 fails is the finding.
 *
 * The audit that produced them is not hypothetical. On the production bridge
 * `escrow_bridge.db` holds 113 captured debit authorizations: 27 confirmed, 86 abandoned —
 * 79 of those because a later invoke replaced the earlier one at the same on-chain nonce,
 * and every one of the 86 with `attempts = 0`. Authorizations are captured when a call is
 * served and submitted later; the collector is opt-in and defaults to never. So the window
 * between "served" and "debited on chain" is not a corner case, it is the normal state.
 */

contract MockUSDC is ERC20 {
    mapping(address => bool) public blocked;

    constructor() ERC20("USD Coin", "USDC") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    /// @notice Circle's FiatToken carries exactly this: an issuer blacklist that makes
    ///         `transfer` revert for one address, for reasons unrelated to any channel.
    function setBlocked(address who, bool value) external {
        blocked[who] = value;
    }

    function _update(address from, address to, uint256 value) internal override {
        require(!blocked[from] && !blocked[to], "Blacklistable: account is blocked");
        super._update(from, to, value);
    }
}

contract AIMarketEscrowV2Test is Test {
    address internal depositor;
    address internal hub;
    uint256 internal depositorKey = 0xA1CE;

    MockUSDC internal token;
    AIMarketEscrow internal v1;
    AIMarketEscrowV2 internal v2;

    bytes32 internal constant CH = keccak256("channel-1");
    bytes32 internal constant CH2 = keccak256("channel-2");
    bytes32 internal constant RECEIPT = keccak256("receipt-1");
    uint256 internal constant DEPOSIT = 100e6;
    uint256 internal constant DEBIT = 30e6;

    function setUp() public {
        depositor = vm.addr(depositorKey);
        hub = address(0xB0B);
        token = new MockUSDC();
        token.mint(depositor, 10_000e6);

        address[] memory hubs = new address[](1);
        hubs[0] = hub;
        address[] memory tokens = new address[](1);
        tokens[0] = address(token);

        v1 = new AIMarketEscrow(hubs, tokens);
        v2 = new AIMarketEscrowV2(hubs, tokens);
        vm.warp(1_000_000);
    }

    // ── helpers ──────────────────────────────────────────────────────

    function _open(address escrow, bytes32 id, uint256 amount) internal {
        vm.startPrank(depositor);
        token.approve(escrow, amount);
        AIMarketEscrow(escrow).openChannel(id, address(token), amount);
        vm.stopPrank();
    }

    function _sign(address escrow, bytes32 id, uint256 amount, bytes32 receipt,
                   uint256 nonce, uint256 deadline) internal view returns (bytes memory) {
        bytes32 digest = AIMarketEscrow(escrow).computeDebitDigest(
            id, hub, address(token), amount, receipt, nonce, deadline
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(depositorKey, digest);
        return abi.encodePacked(r, s, v);
    }

    // ══════════════════════════════════════════════════════════════════
    //  1 + 2. The depositor could exit before the hub landed what it earned
    // ══════════════════════════════════════════════════════════════════

    function test_V1_depositorRefundsTheWholeDepositAfterBeingServed() public {
        _open(address(v1), CH, DEPOSIT);
        // The hub served a call and holds a signed authorization. Nothing is on chain yet:
        // `usedAmount` is still 0, which is the only thing refundChannel checks.
        uint256 before = token.balanceOf(depositor);

        vm.prank(depositor);
        v1.refundChannel(CH, "provider_error");

        assertEq(token.balanceOf(depositor) - before, DEPOSIT, "V1 gave it all back");
        // And the authorization is now worthless: the channel is no longer Open.
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _sign(address(v1), CH, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        vm.expectRevert(AIMarketEscrow.ChannelNotOpen.selector);
        v1.debitChannel(CH, DEBIT, RECEIPT, deadline, sig);
    }

    function test_V2_theHubCanStillDebitInsideTheAnnouncedWindow() public {
        _open(address(v2), CH, DEPOSIT);

        // An exit must be announced; a silent one is refused outright.
        vm.prank(depositor);
        vm.expectRevert(AIMarketEscrowV2.CloseNotRequested.selector);
        v2.refundChannel(CH, "provider_error");

        vm.prank(depositor);
        v2.requestClose(CH);

        // Inside the window the hub lands the call it already served.
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory _sig1 = _sign(address(v2), CH, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        v2.debitChannel(CH, DEBIT, RECEIPT, deadline, _sig1);

        // Now the refund path is closed for a different and correct reason.
        vm.warp(block.timestamp + v2.SETTLE_WINDOW() + 1);
        vm.prank(depositor);
        vm.expectRevert(AIMarketEscrow.RefundAfterDebit.selector);
        v2.refundChannel(CH, "provider_error");

        vm.prank(depositor);
        v2.settleChannel(CH);
        assertEq(token.balanceOf(hub), DEBIT, "the hub was paid for the call it served");
    }

    function test_V2_anImmediateSettleIsRefusedUntilTheWindowElapses() public {
        _open(address(v2), CH, DEPOSIT);
        vm.prank(depositor);
        v2.requestClose(CH);

        bytes memory tooEarly = abi.encodeWithSelector(
            AIMarketEscrowV2.SettlementWindowOpen.selector,
            block.timestamp + v2.SETTLE_WINDOW()
        );
        vm.prank(depositor);
        vm.expectRevert(tooEarly);
        v2.settleChannel(CH);
    }

    function test_V2_theHubsOwnSettleStaysImmediate() public {
        _open(address(v2), CH, DEPOSIT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory _sig2 = _sign(address(v2), CH, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        v2.debitChannel(CH, DEBIT, RECEIPT, deadline, _sig2);
        // A hub closing gives up nothing, so it waits for nobody.
        vm.prank(hub);
        v2.settleChannel(CH);
        assertEq(token.balanceOf(hub), DEBIT);
    }

    // ══════════════════════════════════════════════════════════════════
    //  3. usedReceipts was one namespace for the whole contract
    // ══════════════════════════════════════════════════════════════════

    function test_V1_aReceiptBurnedOnOneChannelBlocksAnother() public {
        _open(address(v1), CH, DEPOSIT);
        _open(address(v1), CH2, DEPOSIT);
        uint256 deadline = block.timestamp + 1 hours;

        bytes memory _sig3 = _sign(address(v1), CH, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        v1.debitChannel(CH, DEBIT, RECEIPT, deadline, _sig3);

        // The very same id, on a DIFFERENT channel, for a call that was really served.
        bytes memory sig2 = _sign(address(v1), CH2, DEBIT, RECEIPT, 0, deadline);
        bytes memory expected = abi.encodeWithSelector(
            AIMarketEscrow.ReceiptAlreadyUsed.selector, RECEIPT
        );
        vm.prank(hub);
        vm.expectRevert(expected);
        v1.debitChannel(CH2, DEBIT, RECEIPT, deadline, sig2);
    }

    function test_V2_aReceiptIsSpentOnItsOwnChannelOnly() public {
        _open(address(v2), CH, DEPOSIT);
        _open(address(v2), CH2, DEPOSIT);
        uint256 deadline = block.timestamp + 1 hours;

        bytes memory _sig4 = _sign(address(v2), CH, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        v2.debitChannel(CH, DEBIT, RECEIPT, deadline, _sig4);
        bytes memory _sig5 = _sign(address(v2), CH2, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        v2.debitChannel(CH2, DEBIT, RECEIPT, deadline, _sig5);

        assertTrue(v2.isReceiptUsed(CH, RECEIPT));
        assertTrue(v2.isReceiptUsed(CH2, RECEIPT));
        // Both debits landed, so both served calls are now owed to the hub on chain.
        assertEq(v2.getChannel(CH).usedAmount, DEBIT);
        assertEq(v2.getChannel(CH2).usedAmount, DEBIT);
        vm.prank(hub);
        v2.settleChannel(CH);
        vm.prank(hub);
        v2.settleChannel(CH2);
        assertEq(token.balanceOf(hub), DEBIT * 2, "both served calls were collectable");
    }

    function test_V2_replayOnTheSameChannelIsStillRefused() public {
        _open(address(v2), CH, DEPOSIT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory _sig6 = _sign(address(v2), CH, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        v2.debitChannel(CH, DEBIT, RECEIPT, deadline, _sig6);
        bytes memory replay = _sign(address(v2), CH, DEBIT, RECEIPT, 1, deadline);
        bytes memory expectedReplay = abi.encodeWithSelector(
            AIMarketEscrow.ReceiptAlreadyUsed.selector, RECEIPT
        );
        vm.prank(hub);
        vm.expectRevert(expectedReplay);
        v2.debitChannel(CH, DEBIT, RECEIPT, deadline, replay);
    }

    // ══════════════════════════════════════════════════════════════════
    //  4. The debit window and the expiry window abutted exactly
    // ══════════════════════════════════════════════════════════════════

    function test_V1_anAuthorizationSignedNearExpiryCanNeverLand() public {
        _open(address(v1), CH, DEPOSIT);
        uint256 expiresAt = block.timestamp + 24 hours;
        uint256 deadline = expiresAt + 30 minutes;      // the buyer allowed longer
        bytes memory sig = _sign(address(v1), CH, DEBIT, RECEIPT, 0, deadline);

        vm.warp(expiresAt + 1);                          // one second late
        vm.prank(hub);
        vm.expectRevert(AIMarketEscrow.ChannelExpired.selector);
        v1.debitChannel(CH, DEBIT, RECEIPT, deadline, sig);

        // And expiry is callable at that same instant, by anyone.
        v1.expireChannel(CH);
    }

    function test_V2_theHubKeepsASettlementGraceAfterExpiry() public {
        _open(address(v2), CH, DEPOSIT);
        uint256 expiresAt = block.timestamp + 24 hours;
        uint256 deadline = expiresAt + 30 minutes;
        bytes memory sig = _sign(address(v2), CH, DEBIT, RECEIPT, 0, deadline);

        vm.warp(expiresAt + 1);
        vm.prank(hub);
        v2.debitChannel(CH, DEBIT, RECEIPT, deadline, sig);
        assertEq(v2.getChannel(CH).usedAmount, DEBIT);

        // Expiry cannot be raced during the grace.
        vm.expectRevert(AIMarketEscrow.ChannelNotExpired.selector);
        v2.expireChannel(CH);

        vm.warp(expiresAt + v2.SETTLE_WINDOW() + 1);
        v2.expireChannel(CH);
        assertEq(token.balanceOf(hub), DEBIT);
    }

    function test_V2_theBuyersOwnDeadlineIsStillTheCap() public {
        _open(address(v2), CH, DEPOSIT);
        uint256 deadline = block.timestamp + 10 minutes;
        bytes memory sig = _sign(address(v2), CH, DEBIT, RECEIPT, 0, deadline);
        vm.warp(deadline + 1);
        vm.prank(hub);
        vm.expectRevert(AIMarketEscrow.ChannelExpired.selector);
        v2.debitChannel(CH, DEBIT, RECEIPT, deadline, sig);
    }

    // ══════════════════════════════════════════════════════════════════
    //  5. One blocked address froze both parties' money forever
    // ══════════════════════════════════════════════════════════════════

    function test_V1_aBlockedDepositorLocksTheHubsEarningsToo() public {
        _open(address(v1), CH, DEPOSIT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _sign(address(v1), CH, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        v1.debitChannel(CH, DEBIT, RECEIPT, deadline, sig);

        token.setBlocked(depositor, true);              // nothing to do with this channel

        vm.prank(hub);
        vm.expectRevert();
        v1.settleChannel(CH);

        // The channel is Open forever: status is written before the transfers, so every
        // later attempt takes the same path and reverts the same way.
        assertTrue(v1.isChannelOpen(CH), "V1 left the whole channel stuck");
        assertEq(token.balanceOf(hub), 0, "the hub's earned money is trapped with it");
    }

    function test_V2_theUnblockedLegStillLandsAndTheOtherIsClaimable() public {
        _open(address(v2), CH, DEPOSIT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory _sig8 = _sign(address(v2), CH, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        v2.debitChannel(CH, DEBIT, RECEIPT, deadline, _sig8);

        token.setBlocked(depositor, true);

        vm.prank(hub);
        v2.settleChannel(CH);

        assertEq(token.balanceOf(hub), DEBIT, "the hub was paid despite the other party");
        assertEq(v2.withdrawable(address(token), depositor), DEPOSIT - DEBIT,
                 "the depositor's refund is recorded, not lost");
        assertFalse(v2.isChannelOpen(CH), "and the channel actually closed");

        // When the depositor can receive again, they claim it themselves.
        token.setBlocked(depositor, false);
        uint256 before = token.balanceOf(depositor);
        vm.prank(depositor);
        v2.withdraw(address(token));
        assertEq(token.balanceOf(depositor) - before, DEPOSIT - DEBIT);
        assertEq(v2.withdrawable(address(token), depositor), 0);
    }

    function test_V2_withdrawWithNothingOwedIsRefused() public {
        vm.prank(depositor);
        vm.expectRevert(AIMarketEscrowV2.NothingToWithdraw.selector);
        v2.withdraw(address(token));
    }

    // ══════════════════════════════════════════════════════════════════
    //  The ordinary path is unchanged
    // ══════════════════════════════════════════════════════════════════

    function test_V2_theHappyPathStillPushesBothLegs() public {
        _open(address(v2), CH, DEPOSIT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory _sig9 = _sign(address(v2), CH, DEBIT, RECEIPT, 0, deadline);
        vm.prank(hub);
        v2.debitChannel(CH, DEBIT, RECEIPT, deadline, _sig9);

        uint256 beforeDepositor = token.balanceOf(depositor);
        vm.prank(hub);
        v2.settleChannel(CH);

        assertEq(token.balanceOf(hub), DEBIT);
        assertEq(token.balanceOf(depositor) - beforeDepositor, DEPOSIT - DEBIT);
        assertEq(v2.withdrawable(address(token), depositor), 0, "nothing was deferred");
    }
}
