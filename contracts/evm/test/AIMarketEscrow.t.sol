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
        address usedRecipient,
        address refundRecipient
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
        address newToken = address(new MockERC20("Tether", "USDT", 6));
        vm.expectEmit(true, true, false, true);
        emit TokenWhitelisted(newToken, true);
        escrow.setTokenWhitelist(newToken, true);
        assertEq(escrow.whitelistedTokens(newToken), true);
    }

    function test_setTokenWhitelist_removeToken() public {
        escrow.setTokenWhitelist(address(token), false);
        assertEq(escrow.whitelistedTokens(address(token)), false);
    }

    /// @notice MIN_DEPOSIT/MAX_DEPOSIT are hardcoded 6-decimal amounts, so an
    /// 18-decimal token would make the whole range meaningless ($1 minimum becomes
    /// 10^-12 of a token). The whitelist is what keeps the assumption true.
    function test_setTokenWhitelist_rejectsWrongDecimals() public {
        MockERC20 wei18 = new MockERC20("Wrapped Ether", "WETH", 18);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.UnsupportedTokenDecimals.selector)
        );
        escrow.setTokenWhitelist(address(wei18), true);
        assertEq(escrow.whitelistedTokens(address(wei18)), false);

        MockERC20 dec2 = new MockERC20("Two", "TWO", 2);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.UnsupportedTokenDecimals.selector)
        );
        escrow.setTokenWhitelist(address(dec2), true);
    }

    /// @notice Fail closed: a token whose decimals() cannot be read (EOA, non-standard
    /// ERC-20) is not provably compatible with the deposit range.
    function test_setTokenWhitelist_rejectsTokenWithoutDecimals() public {
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.UnsupportedTokenDecimals.selector)
        );
        escrow.setTokenWhitelist(address(0x70A1), true); // no code at all
    }

    /// @notice De-listing must always work, even for a token that could not be listed.
    function test_setTokenWhitelist_removalNeverBlocked() public {
        escrow.setTokenWhitelist(address(0x70A1), false);
        assertEq(escrow.whitelistedTokens(address(0x70A1)), false);
    }

    /// @notice The same gate applies to the constructor's initial token list.
    function test_constructor_rejectsWrongDecimalsToken() public {
        address[] memory hubs = new address[](0);
        address[] memory tokens = new address[](1);
        tokens[0] = address(new MockERC20("Wrapped Ether", "WETH", 18));
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.UnsupportedTokenDecimals.selector)
        );
        new AIMarketEscrow(hubs, tokens);
    }

    function test_depositRange_isDeclaredInTokenDecimals() public {
        assertEq(escrow.TOKEN_DECIMALS(), token.decimals(), "whitelist enforces the assumed scale");
        assertEq(escrow.MIN_DEPOSIT(), 10 ** escrow.TOKEN_DECIMALS(), "$1");
        assertEq(escrow.MAX_DEPOSIT(), 10_000 * 10 ** escrow.TOKEN_DECIMALS(), "$10,000");
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

        // Nothing was used, so no hub was paid — usedRecipient is the zero address.
        vm.expectEmit(true, false, false, true);
        emit ChannelSettled(CHANNEL_ID, 0, DEPOSIT_AMOUNT, address(0), depositor);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID);
    }

    /// @notice REGRESSION: the settle event used to name `ch.depositor` as the single
    /// `recipient` while `usedAmount` was transferred to `ch.hub` — every indexer built
    /// on the log credited the hub's revenue to the depositor. Both legs are now named.
    function test_settleChannel_eventNamesTheHubForTheUsedPortion() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(CHANNEL_ID, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        vm.expectEmit(true, false, false, true);
        emit ChannelSettled(CHANNEL_ID, DEBIT_AMOUNT, DEPOSIT_AMOUNT - DEBIT_AMOUNT, hub, depositor);

        vm.prank(hub);
        escrow.settleChannel(CHANNEL_ID);

        // and the log matches where the money actually went
        assertEq(token.balanceOf(hub), DEBIT_AMOUNT);
        assertEq(token.balanceOf(address(escrow)), 0);
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

    // ── batchRefund (dust-friendly multi-channel refund) ─────────────

    function test_batchRefund_refundsAllOwnedOpenChannels() public {
        bytes32 c1 = keccak256("batch-1");
        bytes32 c2 = keccak256("batch-2");
        bytes32 c3 = keccak256("batch-3");
        _openChannel(c1, DEPOSIT_AMOUNT);
        _openChannel(c2, DEPOSIT_AMOUNT);
        _openChannel(c3, DEPOSIT_AMOUNT);
        uint256 balanceBefore = token.balanceOf(depositor);

        bytes32[] memory ids = new bytes32[](3);
        ids[0] = c1;
        ids[1] = c2;
        ids[2] = c3;

        vm.prank(depositor);
        uint256 refunded = escrow.batchRefund(ids, "batch_cleanup");

        assertEq(refunded, 3);
        assertEq(token.balanceOf(depositor), balanceBefore + 3 * DEPOSIT_AMOUNT);
        assertEq(uint256(escrow.getChannel(c1).status), uint256(AIMarketEscrow.ChannelStatus.Refunded));
        assertEq(uint256(escrow.getChannel(c2).status), uint256(AIMarketEscrow.ChannelStatus.Refunded));
        assertEq(uint256(escrow.getChannel(c3).status), uint256(AIMarketEscrow.ChannelStatus.Refunded));
    }

    function test_batchRefund_skipsDebitedChannel() public {
        bytes32 c1 = keccak256("batch-ok");
        bytes32 c2 = keccak256("batch-debited");
        _openChannel(c1, DEPOSIT_AMOUNT);
        _openChannel(c2, DEPOSIT_AMOUNT);

        // Debit c2 so it is no longer refundable.
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _signDebit(c2, hub, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);
        vm.prank(hub);
        escrow.debitChannel(c2, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        bytes32[] memory ids = new bytes32[](2);
        ids[0] = c1;
        ids[1] = c2;

        vm.prank(depositor);
        uint256 refunded = escrow.batchRefund(ids, "batch_cleanup");

        // One bad entry must not block the rest of the batch.
        assertEq(refunded, 1);
        assertEq(uint256(escrow.getChannel(c1).status), uint256(AIMarketEscrow.ChannelStatus.Refunded));
        assertEq(uint256(escrow.getChannel(c2).status), uint256(AIMarketEscrow.ChannelStatus.Open));
    }

    function test_batchRefund_skipsForeignAndUnknownIds() public {
        bytes32 owned = keccak256("batch-owned");
        _openChannel(owned, DEPOSIT_AMOUNT);

        bytes32[] memory ids = new bytes32[](2);
        ids[0] = owned;                       // belongs to depositor, not `other`
        ids[1] = keccak256("does-not-exist"); // unknown id

        // `other` cannot refund the depositor's channel, and unknown ids are no-ops.
        vm.prank(other);
        uint256 refunded = escrow.batchRefund(ids, "x");

        assertEq(refunded, 0);
        assertEq(uint256(escrow.getChannel(owned).status), uint256(AIMarketEscrow.ChannelStatus.Open));
    }
}
