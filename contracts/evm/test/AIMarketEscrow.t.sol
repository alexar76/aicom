// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test, console} from "forge-std/Test.sol";
import {AIMarketEscrow} from "../src/AIMarketEscrow.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

// ── Mock ERC20 with configurable decimals ────────────────────────────────────

contract MockERC20 is ERC20 {
    uint8 private _dec;

    constructor(string memory name_, string memory symbol_, uint8 decimals_)
        ERC20(name_, symbol_)
    {
        _dec = decimals_;
    }

    function decimals() public view override returns (uint8) {
        return _dec;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

// ── Test Contract ────────────────────────────────────────────────────────────

contract AIMarketEscrowTest is Test {
    // ── Test actors ──────────────────────────────────────────────────
    address public depositor;
    address public hub;
    address public other;
    uint256 public depositorKey;
    uint256 public hubKey;

    // ── Tokens ───────────────────────────────────────────────────────
    MockERC20 public token;
    MockERC20 public unwhitelistedToken;

    // ── Escrow ───────────────────────────────────────────────────────
    AIMarketEscrow public escrow;

    // ── Constants ────────────────────────────────────────────────────
    bytes32 public constant CHANNEL_ID = keccak256("test-channel-001");
    bytes32 public constant RECEIPT_ID = keccak256("receipt-001");
    uint256 public constant MIN_DEPOSIT = 1e6;          // $1
    uint256 public constant MAX_DEPOSIT = 10_000e6;     // $10,000
    uint256 public constant DEPOSIT_AMOUNT = 100e6;      // $100
    uint256 public constant DEBIT_AMOUNT = 30e6;         // $30
    uint256 public constant EXPIRY_DURATION = 24 hours;

    // ── Events (must match contract definitions exactly) ─────────────
    event ChannelOpened(
        bytes32 indexed channelId,
        address indexed depositor,
        address token,
        uint256 depositAmount,
        uint256 expiresAt
    );
    event ChannelDebited(
        bytes32 indexed channelId,
        uint256 amount,
        bytes32 receiptId,
        uint256 remainingBalance
    );
    event ChannelSettled(
        bytes32 indexed channelId,
        uint256 usedAmount,
        uint256 refundAmount,
        address recipient
    );
    event ChannelRefunded(
        bytes32 indexed channelId,
        uint256 amount,
        string reason
    );
    event ChannelExpiredAndSettled(
        bytes32 indexed channelId,
        uint256 usedAmount,
        uint256 refundAmount
    );
    event HubAuthorized(address indexed hub, bool authorized);
    event TokenWhitelisted(address indexed token, bool whitelisted);

    // ── Setup ───────────────────────────────────────────────────────

    function setUp() public {
        depositorKey = 0xA1CE;
        hubKey = 0xB0B1;
        depositor = vm.addr(depositorKey);
        hub = vm.addr(hubKey);
        other = address(0xBEEF);

        token = new MockERC20("USD Coin", "USDC", 6);
        unwhitelistedToken = new MockERC20("Unsupported Token", "UNSUP", 6);

        token.mint(depositor, 10_000e6);

        address[] memory initialHubs = new address[](1);
        initialHubs[0] = hub;
        address[] memory initialTokens = new address[](1);
        initialTokens[0] = address(token);

        escrow = new AIMarketEscrow(initialHubs, initialTokens);
    }

    // ── Helpers ─────────────────────────────────────────────────────

    function _openChannel(bytes32 channelId, uint256 amount) internal {
        vm.startPrank(depositor);
        token.approve(address(escrow), amount);
        escrow.openChannel(channelId, address(token), amount);
        vm.stopPrank();
    }

    /// @notice Sign a debit authorization with the depositor's key for a given hub.
    function _signDebit(
        bytes32 channelId,
        address debitHub,
        uint256 amount,
        bytes32 receiptId,
        uint256 nonce,
        uint256 deadline
    ) internal view returns (bytes memory) {
        bytes32 digest = escrow.computeDebitDigest(
            channelId, debitHub, address(token), amount, receiptId, nonce, deadline
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(depositorKey, digest);
        return abi.encodePacked(r, s, v);
    }

    function _signDebitWithKey(
        uint256 key,
        bytes32 channelId,
        address debitHub,
        uint256 amount,
        bytes32 receiptId,
        uint256 nonce,
        uint256 deadline
    ) internal view returns (bytes memory) {
        bytes32 digest = escrow.computeDebitDigest(
            channelId, debitHub, address(token), amount, receiptId, nonce, deadline
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    // ══════════════════════════════════════════════════════════════════
    //  openChannel Tests
    // ══════════════════════════════════════════════════════════════════

    function test_openChannel_happyPath() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(ch.depositor, depositor);
        assertEq(ch.token, address(token));
        assertEq(ch.depositAmount, DEPOSIT_AMOUNT);
        assertEq(ch.balance, DEPOSIT_AMOUNT);
        assertEq(ch.usedAmount, 0);
        assertEq(ch.nonce, 0);
        assertEq(uint256(ch.status), uint256(AIMarketEscrow.ChannelStatus.Open));
    }

    function test_openChannel_revertsInsufficientDeposit() public {
        uint256 tinyDeposit = MIN_DEPOSIT - 1;
        vm.startPrank(depositor);
        token.approve(address(escrow), tinyDeposit);

        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.DepositOutOfRange.selector)
        );
        escrow.openChannel(CHANNEL_ID, address(token), tinyDeposit);
        vm.stopPrank();
    }

    function test_openChannel_revertsTooLargeDeposit() public {
        uint256 hugeDeposit = MAX_DEPOSIT + 1;
        vm.startPrank(depositor);
        token.approve(address(escrow), hugeDeposit);

        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.DepositOutOfRange.selector)
        );
        escrow.openChannel(CHANNEL_ID, address(token), hugeDeposit);
        vm.stopPrank();
    }

    function test_openChannel_revertsDuplicateChannelId() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.startPrank(depositor);
        token.approve(address(escrow), DEPOSIT_AMOUNT);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelExists.selector)
        );
        escrow.openChannel(CHANNEL_ID, address(token), DEPOSIT_AMOUNT);
        vm.stopPrank();
    }

    function test_openChannel_revertsUnapprovedToken() public {
        vm.startPrank(depositor);
        unwhitelistedToken.mint(depositor, DEPOSIT_AMOUNT);
        unwhitelistedToken.approve(address(escrow), DEPOSIT_AMOUNT);

        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.TokenNotSupported.selector)
        );
        escrow.openChannel(CHANNEL_ID, address(unwhitelistedToken), DEPOSIT_AMOUNT);
        vm.stopPrank();
    }

    function test_openChannel_expirySetCorrectly() public {
        uint256 startTime = block.timestamp;
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(ch.expiresAt, startTime + EXPIRY_DURATION);
    }

    function test_openChannel_emitsEvent() public {
        vm.startPrank(depositor);
        token.approve(address(escrow), DEPOSIT_AMOUNT);

        uint256 expectedExpiry = block.timestamp + EXPIRY_DURATION;
        vm.expectEmit(true, true, false, true);
        emit ChannelOpened(CHANNEL_ID, depositor, address(token), DEPOSIT_AMOUNT, expectedExpiry);
        escrow.openChannel(CHANNEL_ID, address(token), DEPOSIT_AMOUNT);
        vm.stopPrank();
    }

    // ══════════════════════════════════════════════════════════════════
    //  debitChannel Tests
    // ══════════════════════════════════════════════════════════════════

    function test_debitChannel_happyPath() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);

        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(ch.balance, DEPOSIT_AMOUNT - DEBIT_AMOUNT);
        assertEq(ch.usedAmount, DEBIT_AMOUNT);
        assertEq(ch.nonce, 1);
        assertEq(ch.hub, hub);
    }

    function test_debitChannel_revertsUnauthorizedHub() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, other, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);

        vm.prank(other);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.Unauthorized.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);
    }

    function test_debitChannel_revertsWrongSignature() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        // Sign with hub's key instead of depositor's
        bytes memory sig = _signDebitWithKey(
            hubKey, CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline
        );

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InvalidSignature.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);
    }

    function test_debitChannel_revertsReplaySameNonce() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);

        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        // Same signature now mismatches: contract uses ch.nonce=1, sig committed nonce=0
        vm.prank(hub);
        vm.expectRevert();
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);
    }

    function test_debitChannel_revertsInsufficientBalance() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        uint256 overdraw = DEPOSIT_AMOUNT + 1;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, overdraw, RECEIPT_ID, 0, deadline);

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InsufficientBalance.selector, overdraw, DEPOSIT_AMOUNT)
        );
        escrow.debitChannel(CHANNEL_ID, overdraw, RECEIPT_ID, deadline, sig);
    }

    function test_debitChannel_revertsExpiredChannel() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);

        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelExpired.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);
    }

    function test_debitChannel_revertsDeadlineExpired() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 pastDeadline = block.timestamp - 1;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, pastDeadline);

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelExpired.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, pastDeadline, sig);
    }

    function test_debitChannel_revertsWrongSigner() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 wrongSignerKey = 0xDEAD;
        uint256 deadline = block.timestamp + 1 hours;

        bytes memory sig = _signDebitWithKey(
            wrongSignerKey, CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline
        );

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InvalidSignature.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);
    }

    /// @notice REGRESSION: depositor's signature for hub A must not be usable by hub B.
    function test_debitChannel_revertsSignatureBoundToHub() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;

        // Authorize a second hub
        address otherHub = address(0xC0FFEE);
        escrow.setHubAuthorization(otherHub, true);

        // Depositor signed for `hub`, not for `otherHub`
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);

        // otherHub tries to use the signature meant for hub
        vm.prank(otherHub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InvalidSignature.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);
    }

    // ══════════════════════════════════════════════════════════════════
    //  settleChannel Tests
    // ══════════════════════════════════════════════════════════════════

    function test_settleChannel_happyPath() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);

        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        uint256 hubBalanceBefore = token.balanceOf(hub);
        uint256 depositorBalanceBefore = token.balanceOf(depositor);

        vm.prank(hub);
        escrow.settleChannel(CHANNEL_ID);

        assertEq(token.balanceOf(hub), hubBalanceBefore + DEBIT_AMOUNT);
        assertEq(
            token.balanceOf(depositor),
            depositorBalanceBefore + (DEPOSIT_AMOUNT - DEBIT_AMOUNT)
        );
        assertEq(
            uint256(escrow.getChannel(CHANNEL_ID).status),
            uint256(AIMarketEscrow.ChannelStatus.Settled)
        );
    }

    function test_settleChannel_revertsUnauthorizedCaller() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.prank(other);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.Unauthorized.selector)
        );
        escrow.settleChannel(CHANNEL_ID);
    }

    function test_settleChannel_revertsAlreadySettled() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID);

        vm.prank(depositor);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotOpen.selector)
        );
        escrow.settleChannel(CHANNEL_ID);
    }

    function test_settleChannel_depositorCanSettle() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID);

        assertEq(
            uint256(escrow.getChannel(CHANNEL_ID).status),
            uint256(AIMarketEscrow.ChannelStatus.Settled)
        );
    }

    // ══════════════════════════════════════════════════════════════════
    //  refundChannel Tests
    // ══════════════════════════════════════════════════════════════════

    function test_refundChannel_depositorRefund() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 balanceBefore = token.balanceOf(depositor);

        vm.prank(depositor);
        escrow.refundChannel(CHANNEL_ID, "user_cancelled");

        assertEq(token.balanceOf(depositor), balanceBefore + DEPOSIT_AMOUNT);
        assertEq(
            uint256(escrow.getChannel(CHANNEL_ID).status),
            uint256(AIMarketEscrow.ChannelStatus.Refunded)
        );
    }

    function test_refundChannel_revertsUnauthorized() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.prank(other);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.Unauthorized.selector)
        );
        escrow.refundChannel(CHANNEL_ID, "unauthorized");
    }

    function test_refundChannel_revertsAfterDebit() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        vm.prank(depositor);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.RefundAfterDebit.selector)
        );
        escrow.refundChannel(CHANNEL_ID, "too_late");
    }

    function test_refundChannel_revertsAlreadyRefunded() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.prank(depositor);
        escrow.refundChannel(CHANNEL_ID, "user_cancelled");

        vm.prank(depositor);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotOpen.selector)
        );
        escrow.refundChannel(CHANNEL_ID, "user_cancelled");
    }

    // ══════════════════════════════════════════════════════════════════
    //  expireChannel Tests
    // ══════════════════════════════════════════════════════════════════

    function test_expireChannel_after24h_noDebit() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        uint256 depBefore = token.balanceOf(depositor);
        vm.prank(other);
        escrow.expireChannel(CHANNEL_ID);

        assertEq(token.balanceOf(depositor), depBefore + DEPOSIT_AMOUNT);
        assertEq(token.balanceOf(hub), 0, "no debit happened - hub gets nothing");
        assertEq(
            uint256(escrow.getChannel(CHANNEL_ID).status),
            uint256(AIMarketEscrow.ChannelStatus.Expired)
        );
    }

    function test_expireChannel_revertsBefore24h() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        vm.warp(block.timestamp + EXPIRY_DURATION - 1 hours);

        vm.prank(other);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotExpired.selector)
        );
        escrow.expireChannel(CHANNEL_ID);
    }

    function test_expireChannel_permissionless() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        vm.prank(other);
        escrow.expireChannel(CHANNEL_ID);

        assertEq(
            uint256(escrow.getChannel(CHANNEL_ID).status),
            uint256(AIMarketEscrow.ChannelStatus.Expired)
        );
    }

    /// @notice REGRESSION: post-debit expiry must pay hub its usedAmount.
    /// Previously a depositor could wait 24h and have anyone expire the
    /// channel — the depositor got the full deposit back and the hub lost
    /// all earned funds. Now expire behaves like settle on the economic side.
    function test_expireChannel_paysHubUsedAmountAfterDebit() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        uint256 hubBefore = token.balanceOf(hub);
        uint256 depBefore = token.balanceOf(depositor);

        escrow.expireChannel(CHANNEL_ID);

        assertEq(token.balanceOf(hub), hubBefore + DEBIT_AMOUNT, "hub paid its debited amount on expiry");
        assertEq(
            token.balanceOf(depositor),
            depBefore + (DEPOSIT_AMOUNT - DEBIT_AMOUNT),
            "depositor refunded only the unused balance"
        );
    }

    // ══════════════════════════════════════════════════════════════════
    //  Admin tests
    // ══════════════════════════════════════════════════════════════════

    function test_setHubAuthorization_addHub() public {
        address newHub = address(0xCAFE);
        assertEq(escrow.authorizedHubs(newHub), false);

        vm.expectEmit(true, true, false, true);
        emit HubAuthorized(newHub, true);
        escrow.setHubAuthorization(newHub, true);

        assertEq(escrow.authorizedHubs(newHub), true);
    }

    function test_setHubAuthorization_removeHub() public {
        assertEq(escrow.authorizedHubs(hub), true);

        vm.expectEmit(true, true, false, true);
        emit HubAuthorized(hub, false);
        escrow.setHubAuthorization(hub, false);

        assertEq(escrow.authorizedHubs(hub), false);
    }

    function test_setHubAuthorization_onlyOwnerCanCall() public {
        vm.prank(address(0x1234));
        vm.expectRevert();
        escrow.setHubAuthorization(address(0x1234), true);
    }

    function test_setTokenWhitelist_addToken() public {
        address newToken = address(0x70A1);
        vm.expectEmit(true, true, false, true);
        emit TokenWhitelisted(newToken, true);
        escrow.setTokenWhitelist(newToken, true);
        assertEq(escrow.whitelistedTokens(newToken), true);
    }

    function test_setTokenWhitelist_removeToken() public {
        escrow.setTokenWhitelist(address(token), false);
        assertEq(escrow.whitelistedTokens(address(token)), false);
    }

    // ══════════════════════════════════════════════════════════════════
    //  EIP-712 Tests
    // ══════════════════════════════════════════════════════════════════

    function test_eip712_domainSeparator() public {
        bytes32 expected = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes("AIMarketEscrow")),
                keccak256(bytes("1")),
                block.chainid,
                address(escrow)
            )
        );
        assertEq(escrow.domainSeparator(), expected);
    }

    function test_eip712_typehashIncludesHub() public {
        bytes32 expectedTypehash = keccak256(
            "DebitAuthorization(bytes32 channelId,address hub,address token,uint256 amount,bytes32 receiptId,uint256 nonce,uint256 deadline)"
        );
        uint256 nonce = 0;
        uint256 deadline = block.timestamp + 1 hours;

        bytes32 expectedStructHash = keccak256(
            abi.encode(
                expectedTypehash,
                CHANNEL_ID,
                hub,
                address(token),
                DEBIT_AMOUNT,
                RECEIPT_ID,
                nonce,
                deadline
            )
        );
        bytes32 expectedDigest = keccak256(
            abi.encodePacked("\x19\x01", escrow.domainSeparator(), expectedStructHash)
        );

        bytes32 actualDigest = escrow.computeDebitDigest(
            CHANNEL_ID, hub, address(token), DEBIT_AMOUNT, RECEIPT_ID, nonce, deadline
        );

        assertEq(actualDigest, expectedDigest);
    }

    function test_eip712_signatureTampering_channelId() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        bytes32 otherId = keccak256("other-channel");
        _openChannel(otherId, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;

        // Sign for CHANNEL_ID but submit the digest on `otherId`. Use a fresh
        // receiptId so the contract's receipt double-spend guard doesn't fire
        // first (defense in depth) — we want this revert path to land on the
        // signature check.
        bytes32 freshReceipt = keccak256("receipt-fresh");
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, freshReceipt, 0, deadline);

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InvalidSignature.selector)
        );
        escrow.debitChannel(otherId, DEBIT_AMOUNT, freshReceipt, deadline, sig);
    }

    /// @notice After hardfork (chainid change), digest must use the new chainId.
    function test_eip712_recomputesSeparatorOnFork() public {
        bytes32 before = escrow.domainSeparator();
        vm.chainId(block.chainid + 1);
        bytes32 afterFork = escrow.domainSeparator();
        assertTrue(before != afterFork, "domain separator must change with chainId");
    }

    // ══════════════════════════════════════════════════════════════════
    //  Views & Events
    // ══════════════════════════════════════════════════════════════════

    function test_isChannelOpen_true() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        assertTrue(escrow.isChannelOpen(CHANNEL_ID));
    }

    function test_isChannelOpen_falseAfterExpiry() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);
        assertFalse(escrow.isChannelOpen(CHANNEL_ID));
    }

    function test_getChannelBalance() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        assertEq(escrow.getChannelBalance(CHANNEL_ID), DEPOSIT_AMOUNT);

        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        assertEq(escrow.getChannelBalance(CHANNEL_ID), DEPOSIT_AMOUNT - DEBIT_AMOUNT);
    }

    function test_settleChannel_emitsEvent() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.expectEmit(true, false, false, true);
        emit ChannelSettled(CHANNEL_ID, 0, DEPOSIT_AMOUNT, depositor);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID);
    }

    function test_refundChannel_emitsEvent() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.expectEmit(true, false, false, true);
        emit ChannelRefunded(CHANNEL_ID, DEPOSIT_AMOUNT, "safety_blocked");

        vm.prank(depositor);
        escrow.refundChannel(CHANNEL_ID, "safety_blocked");
    }

    function test_expireChannel_emitsEvent() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        vm.expectEmit(true, false, false, true);
        emit ChannelExpiredAndSettled(CHANNEL_ID, 0, DEPOSIT_AMOUNT);

        escrow.expireChannel(CHANNEL_ID);
    }

    // ══════════════════════════════════════════════════════════════════
    //  Edge cases
    // ══════════════════════════════════════════════════════════════════

    function test_debitChannel_revertsChannelNotFound() public {
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotFound.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);
    }

    function test_settleChannel_revertsChannelNotFound() public {
        vm.prank(depositor);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotFound.selector)
        );
        escrow.settleChannel(CHANNEL_ID);
    }

    function test_refundChannel_revertsChannelNotFound() public {
        vm.prank(depositor);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotFound.selector)
        );
        escrow.refundChannel(CHANNEL_ID, "no_channel");
    }

    function test_expireChannel_revertsChannelNotFound() public {
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotFound.selector)
        );
        escrow.expireChannel(CHANNEL_ID);
    }

    function test_debitChannel_multipleDebits() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;

        bytes memory sig1 = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig1);

        bytes32 receiptId2 = keccak256("receipt-002");
        bytes memory sig2 = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, receiptId2, 1, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, receiptId2, deadline, sig2);

        assertEq(escrow.getChannelBalance(CHANNEL_ID), DEPOSIT_AMOUNT - 2 * DEBIT_AMOUNT);
        assertEq(escrow.getChannel(CHANNEL_ID).usedAmount, 2 * DEBIT_AMOUNT);
        assertEq(escrow.getChannel(CHANNEL_ID).nonce, 2);
    }

    function test_settleChannel_zeroUsed() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 depBefore = token.balanceOf(depositor);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID);

        assertEq(token.balanceOf(hub), 0);
        assertEq(token.balanceOf(depositor), depBefore + DEPOSIT_AMOUNT);
    }

    // ══════════════════════════════════════════════════════════════════
    //  Integration Tests
    // ══════════════════════════════════════════════════════════════════

    function test_integration_openDebitSettle() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        uint256 hubBefore = token.balanceOf(hub);
        uint256 depBefore = token.balanceOf(depositor);

        vm.prank(hub);
        escrow.settleChannel(CHANNEL_ID);

        assertEq(token.balanceOf(hub), hubBefore + DEBIT_AMOUNT);
        assertEq(token.balanceOf(depositor), depBefore + (DEPOSIT_AMOUNT - DEBIT_AMOUNT));
    }

    function test_integration_openExpire_withDebit() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        uint256 hubBefore = token.balanceOf(hub);
        uint256 depBefore = token.balanceOf(depositor);

        escrow.expireChannel(CHANNEL_ID);

        assertEq(token.balanceOf(hub), hubBefore + DEBIT_AMOUNT);
        assertEq(token.balanceOf(depositor), depBefore + (DEPOSIT_AMOUNT - DEBIT_AMOUNT));
    }
}
