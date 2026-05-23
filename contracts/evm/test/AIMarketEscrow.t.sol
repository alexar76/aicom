// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test, console} from "forge-std/Test.sol";
import {AIMarketEscrow} from "../AIMarketEscrow.sol";
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

    // ── Events ──────────────────────────────────────────────────────
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
    event ChannelExpired(bytes32 indexed channelId, uint256 refundAmount);
    event HubAuthorized(address indexed hub, bool authorized);
    event TokenWhitelisted(address indexed token, bool whitelisted);

    // ── Setup ───────────────────────────────────────────────────────

    function setUp() public {
        // Derive deterministic keys and addresses
        depositorKey = 0xA1CE;
        hubKey = 0xB0B1;
        depositor = vm.addr(depositorKey);
        hub = vm.addr(hubKey);
        other = address(0xBEEF);

        // Deploy tokens
        token = new MockERC20("USD Coin", "USDC", 6);
        unwhitelistedToken = new MockERC20("Unsupported Token", "UNSUP", 6);

        // Fund depositor
        token.mint(depositor, 10_000e6); // $10,000 for testing

        // Deploy escrow with initial authorized hub
        address[] memory initialHubs = new address[](1);
        initialHubs[0] = hub;
        address[] memory initialTokens = new address[](1);
        initialTokens[0] = address(token);

        escrow = new AIMarketEscrow(initialHubs, initialTokens);
    }

    // ── Helpers ─────────────────────────────────────────────────────

    /// @notice Approve escrow and open a channel as depositor.
    function _openChannel(bytes32 channelId, uint256 amount) internal {
        vm.startPrank(depositor);
        token.approve(address(escrow), amount);
        escrow.openChannel(channelId, address(token), amount);
        vm.stopPrank();
    }

    /// @notice Sign a debit authorization with the depositor's key.
    function _signDebit(
        bytes32 channelId,
        uint256 amount,
        bytes32 receiptId,
        uint256 nonce,
        uint256 deadline
    ) internal view returns (bytes memory) {
        bytes32 digest = escrow.computeDebitDigest(
            channelId, address(token), amount, receiptId, nonce, deadline
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(depositorKey, digest);
        return abi.encodePacked(r, s, v);
    }

    /// @notice Sign a debit authorization with a specific key (not depositor).
    function _signDebitWithKey(
        uint256 key,
        bytes32 channelId,
        uint256 amount,
        bytes32 receiptId,
        uint256 nonce,
        uint256 deadline
    ) internal view returns (bytes memory) {
        bytes32 digest = escrow.computeDebitDigest(
            channelId, address(token), amount, receiptId, nonce, deadline
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    // ══════════════════════════════════════════════════════════════════
    //  openChannel Tests
    // ══════════════════════════════════════════════════════════════════

    /// @notice Happy path: open a channel with valid token and deposit.
    function test_openChannel_happyPath() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(ch.depositor, depositor, "depositor should match");
        assertEq(ch.token, address(token), "token should match");
        assertEq(ch.depositAmount, DEPOSIT_AMOUNT, "deposit amount should match");
        assertEq(ch.balance, DEPOSIT_AMOUNT, "balance should equal deposit");
        assertEq(ch.usedAmount, 0, "used amount should be zero");
        assertEq(ch.nonce, 0, "nonce should start at zero");
        assertEq(uint256(ch.status), uint256(AIMarketEscrow.ChannelStatus.Open), "status should be Open");
    }

    /// @notice Revert when deposit is below MIN_DEPOSIT.
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

    /// @notice Revert when deposit exceeds MAX_DEPOSIT.
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

    /// @notice Revert when opening a channel with an already-used channelId.
    function test_openChannel_revertsDuplicateChannelId() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.startPrank(depositor);
        token.approve(address(escrow), DEPOSIT_AMOUNT);
        vm.expectRevert(); // Channel ID already used (bare revert)
        escrow.openChannel(CHANNEL_ID, address(token), DEPOSIT_AMOUNT);
        vm.stopPrank();
    }

    /// @notice Revert when token is not whitelisted.
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

    /// @notice Expiry is set to block.timestamp + 24 hours.
    function test_openChannel_expirySetCorrectly() public {
        uint256 startTime = block.timestamp;
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(ch.expiresAt, startTime + EXPIRY_DURATION, "expiry should be block.timestamp + 24h");
    }

    /// @notice ChannelOpened event is emitted with correct parameters.
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

    /// @notice Happy path: authorized hub debits with valid signature.
    function test_debitChannel_happyPath() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        bytes memory sig = _signDebit(
            CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours
        );

        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(ch.balance, DEPOSIT_AMOUNT - DEBIT_AMOUNT, "balance should decrease by debited amount");
        assertEq(ch.usedAmount, DEBIT_AMOUNT, "used amount should reflect debit");
        assertEq(ch.nonce, 1, "nonce should increment");
    }

    /// @notice Revert when caller is not an authorized hub.
    function test_debitChannel_revertsUnauthorizedHub() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        bytes memory sig = _signDebit(
            CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours
        );

        vm.prank(other);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.Unauthorized.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);
    }

    /// @notice Revert when signature is invalid (signed by wrong key).
    function test_debitChannel_revertsWrongSignature() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        // Sign with hub's key instead of depositor's key
        bytes memory sig = _signDebitWithKey(
            hubKey, CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours
        );

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InvalidSignature.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);
    }

    /// @notice Revert when replaying the same signature (nonce has changed).
    function test_debitChannel_revertsReplaySameNonce() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        bytes memory sig = _signDebit(
            CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours
        );

        // First debit succeeds
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);

        // Second attempt with same signature fails because nonce is now 1, not 0
        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InvalidSignature.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);
    }

    /// @notice Revert when debit amount exceeds channel balance.
    function test_debitChannel_revertsInsufficientBalance() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 overdraw = DEPOSIT_AMOUNT + 1;
        bytes memory sig = _signDebit(
            CHANNEL_ID, overdraw, RECEIPT_ID, 0, block.timestamp + 1 hours
        );

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InsufficientBalance.selector, overdraw, DEPOSIT_AMOUNT)
        );
        escrow.debitChannel(CHANNEL_ID, overdraw, RECEIPT_ID, block.timestamp + 1 hours, sig);
    }

    /// @notice Revert when channel has expired (24h passed).
    function test_debitChannel_revertsExpiredChannel() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        bytes memory sig = _signDebit(
            CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours
        );

        // Warp past expiry
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelExpired.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);
    }

    /// @notice Revert when the signature deadline has passed.
    function test_debitChannel_revertsDeadlineExpired() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 pastDeadline = block.timestamp - 1;
        bytes memory sig = _signDebit(
            CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, pastDeadline
        );

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelExpired.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, pastDeadline, sig);
    }

    /// @notice Revert when signer is not the channel depositor (wrong signer).
    function test_debitChannel_revertsWrongSigner() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        address wrongSigner = address(0xDEAD);
        uint256 wrongSignerKey = 0xDEAD;

        bytes memory sig = _signDebitWithKey(
            wrongSignerKey, CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours
        );

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InvalidSignature.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);
    }

    // ══════════════════════════════════════════════════════════════════
    //  settleChannel Tests
    // ══════════════════════════════════════════════════════════════════

    /// @notice Happy path: used funds go to hub recipient, refund to depositor.
    function test_settleChannel_happyPath() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        bytes memory sig = _signDebit(
            CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours
        );

        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);

        uint256 hubBalanceBefore = token.balanceOf(hub);
        uint256 depositorBalanceBefore = token.balanceOf(depositor);

        vm.prank(hub);
        escrow.settleChannel(CHANNEL_ID, hub);

        // Hub should receive the used amount
        assertEq(
            token.balanceOf(hub),
            hubBalanceBefore + DEBIT_AMOUNT,
            "hub should receive used amount"
        );
        // Depositor should receive the remaining balance
        assertEq(
            token.balanceOf(depositor),
            depositorBalanceBefore + (DEPOSIT_AMOUNT - DEBIT_AMOUNT),
            "depositor should receive refund"
        );

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(
            uint256(ch.status),
            uint256(AIMarketEscrow.ChannelStatus.Settled),
            "channel status should be Settled"
        );
    }

    /// @notice Revert when caller is neither depositor nor authorized hub.
    function test_settleChannel_revertsUnauthorizedCaller() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.prank(other);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.Unauthorized.selector)
        );
        escrow.settleChannel(CHANNEL_ID, other);
    }

    /// @notice Revert when settling an already-settled channel.
    function test_settleChannel_revertsAlreadySettled() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID, hub);

        vm.prank(depositor);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotOpen.selector)
        );
        escrow.settleChannel(CHANNEL_ID, hub);
    }

    /// @notice Depositor (not just hub) can trigger settlement.
    function test_settleChannel_depositorCanSettle() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID, hub);

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(
            uint256(ch.status),
            uint256(AIMarketEscrow.ChannelStatus.Settled),
            "depositor should be able to settle"
        );
    }

    // ══════════════════════════════════════════════════════════════════
    //  refundChannel Tests
    // ══════════════════════════════════════════════════════════════════

    /// @notice Depositor can refund their full deposit.
    function test_refundChannel_depositorRefund() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 balanceBefore = token.balanceOf(depositor);

        vm.prank(depositor);
        escrow.refundChannel(CHANNEL_ID, "user_cancelled");

        // Depositor gets full deposit back
        assertEq(
            token.balanceOf(depositor),
            balanceBefore + DEPOSIT_AMOUNT,
            "depositor should receive full refund"
        );

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(
            uint256(ch.status),
            uint256(AIMarketEscrow.ChannelStatus.Refunded),
            "channel status should be Refunded"
        );
    }

    /// @notice Revert when non-depositor tries to refund.
    function test_refundChannel_revertsUnauthorized() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.prank(other);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.Unauthorized.selector)
        );
        escrow.refundChannel(CHANNEL_ID, "unauthorized");
    }

    /// @notice Revert when refunding an already-refunded channel.
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

    /// @notice Anyone can expire a channel after 24h.
    function test_expireChannel_after24h() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        uint256 balanceBefore = token.balanceOf(depositor);
        vm.prank(other); // Permissionless
        escrow.expireChannel(CHANNEL_ID);

        assertEq(
            token.balanceOf(depositor),
            balanceBefore + DEPOSIT_AMOUNT,
            "depositor should receive full refund on expiry"
        );

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(
            uint256(ch.status),
            uint256(AIMarketEscrow.ChannelStatus.Expired),
            "channel status should be Expired"
        );
    }

    /// @notice Revert when attempting to expire before 24h.
    function test_expireChannel_revertsBefore24h() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        // Warp partway but not past expiry
        vm.warp(block.timestamp + EXPIRY_DURATION - 1 hours);

        vm.prank(other);
        vm.expectRevert(); // Not yet expired (bare revert)
        escrow.expireChannel(CHANNEL_ID);
    }

    /// @notice Permissionless: any address can trigger expiry.
    function test_expireChannel_permissionless() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        // Called by an unrelated address
        vm.prank(other);
        escrow.expireChannel(CHANNEL_ID);

        AIMarketEscrow.Channel memory ch = escrow.getChannel(CHANNEL_ID);
        assertEq(
            uint256(ch.status),
            uint256(AIMarketEscrow.ChannelStatus.Expired),
            "permissionless expire should succeed"
        );
    }

    /// @notice Full deposit is returned to depositor on expiry (even after debit).
    function test_expireChannel_refundsDepositorAfterDebit() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        bytes memory sig = _signDebit(
            CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours
        );
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);

        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        uint256 balanceBefore = token.balanceOf(depositor);
        escrow.expireChannel(CHANNEL_ID);

        assertEq(
            token.balanceOf(depositor),
            balanceBefore + DEPOSIT_AMOUNT,
            "depositor should receive full deposit even after debit"
        );
    }

    // ══════════════════════════════════════════════════════════════════
    //  setHubAuthorization Tests
    // ══════════════════════════════════════════════════════════════════

    /// @notice A new hub can be authorized.
    function test_setHubAuthorization_addHub() public {
        address newHub = address(0xCAFE);

        assertEq(escrow.authorizedHubs(newHub), false, "new hub should not be authorized initially");
        vm.expectEmit(true, true, false, true);
        emit HubAuthorized(newHub, true);

        escrow.setHubAuthorization(newHub, true);

        assertEq(escrow.authorizedHubs(newHub), true, "new hub should be authorized after setHubAuthorization");
    }

    /// @notice An existing hub can be deauthorized.
    function test_setHubAuthorization_removeHub() public {
        assertEq(escrow.authorizedHubs(hub), true, "hub should be authorized initially");
        vm.expectEmit(true, true, false, true);
        emit HubAuthorized(hub, false);

        escrow.setHubAuthorization(hub, false);

        assertEq(escrow.authorizedHubs(hub), false, "hub should be deauthorized");
    }

    /// @notice Only owner can call setHubAuthorization (Ownable gated).
    function test_setHubAuthorization_onlyOwnerCanCall() public {
        address random = address(0x1234);

        vm.prank(random);
        vm.expectRevert();
        escrow.setHubAuthorization(random, true);
    }

    // ══════════════════════════════════════════════════════════════════
    //  setTokenWhitelist Tests
    // ══════════════════════════════════════════════════════════════════

    /// @notice A new token can be whitelisted.
    function test_setTokenWhitelist_addToken() public {
        address newToken = address(0x70A1);

        assertEq(escrow.whitelistedTokens(newToken), false, "new token should not be whitelisted initially");
        vm.expectEmit(true, true, false, true);
        emit TokenWhitelisted(newToken, true);

        escrow.setTokenWhitelist(newToken, true);

        assertEq(escrow.whitelistedTokens(newToken), true, "new token should be whitelisted");
    }

    /// @notice A whitelisted token can be removed.
    function test_setTokenWhitelist_removeToken() public {
        assertEq(escrow.whitelistedTokens(address(token)), true, "token should be whitelisted initially");

        escrow.setTokenWhitelist(address(token), false);

        assertEq(escrow.whitelistedTokens(address(token)), false, "token should be removed from whitelist");
    }

    // ══════════════════════════════════════════════════════════════════
    //  EIP-712 Tests
    // ══════════════════════════════════════════════════════════════════

    /// @notice Domain separator matches EIP-712 specification.
    function test_eip712_domainSeparator() public {
        bytes32 expectedDomainSeparator = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes("AIMarketEscrow")),
                keccak256(bytes("1")),
                block.chainid,
                address(escrow)
            )
        );
        assertEq(
            escrow.domainSeparator(),
            expectedDomainSeparator,
            "domain separator should match EIP-712 spec"
        );
    }

    /// @notice The typehash is correct by verifying the digest matches manual computation.
    function test_eip712_typehashCorrect() public {
        bytes32 expectedTypehash = keccak256(
            "DebitAuthorization(bytes32 channelId,address token,uint256 amount,bytes32 receiptId,uint256 nonce,uint256 deadline)"
        );
        uint256 nonce = 0;
        uint256 deadline = block.timestamp + 1 hours;

        bytes32 expectedStructHash = keccak256(
            abi.encode(
                expectedTypehash,
                CHANNEL_ID,
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
            CHANNEL_ID, address(token), DEBIT_AMOUNT, RECEIPT_ID, nonce, deadline
        );

        assertEq(actualDigest, expectedDigest, "digest should match with correct typehash");
    }

    /// @notice Signature verification succeds with valid params and fails with tampered params.
    function test_eip712_signatureTampering() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 deadline = block.timestamp + 1 hours;

        // Sign for the real channel ID
        bytes memory sig = _signDebit(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);

        // Verify it works with the correct params
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);

        // Now try with a different channelId — must open another channel first
        bytes32 otherId = keccak256("other-channel");
        _openChannel(otherId, DEPOSIT_AMOUNT);

        // The same signature won't work because the structHash includes channelId
        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.InvalidSignature.selector)
        );
        escrow.debitChannel(otherId, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig);
    }

    // ══════════════════════════════════════════════════════════════════
    //  Channel Status & View Tests
    // ══════════════════════════════════════════════════════════════════

    /// @notice isChannelOpen returns true for an open, unexpired channel.
    function test_isChannelOpen_returnsTrue() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        assertTrue(escrow.isChannelOpen(CHANNEL_ID), "open channel should report as open");
    }

    /// @notice isChannelOpen returns false after expiry.
    function test_isChannelOpen_returnsFalseAfterExpiry() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);
        assertFalse(escrow.isChannelOpen(CHANNEL_ID), "expired channel should not be open");
    }

    /// @notice getChannelBalance returns the correct balance.
    function test_getChannelBalance() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        assertEq(escrow.getChannelBalance(CHANNEL_ID), DEPOSIT_AMOUNT, "balance should equal deposit");

        bytes memory sig = _signDebit(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);

        assertEq(
            escrow.getChannelBalance(CHANNEL_ID),
            DEPOSIT_AMOUNT - DEBIT_AMOUNT,
            "balance should reflect debit"
        );
    }

    // ══════════════════════════════════════════════════════════════════
    //  Edge Cases
    // ══════════════════════════════════════════════════════════════════

    /// @notice Revert when debiting a non-existent channel.
    function test_debitChannel_revertsChannelNotFound() public {
        bytes memory sig = _signDebit(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours);

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotFound.selector)
        );
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);
    }

    /// @notice Revert when settling a non-existent channel.
    function test_settleChannel_revertsChannelNotFound() public {
        vm.prank(depositor);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotFound.selector)
        );
        escrow.settleChannel(CHANNEL_ID, hub);
    }

    /// @notice Revert when refunding a non-existent channel.
    function test_refundChannel_revertsChannelNotFound() public {
        vm.prank(depositor);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotFound.selector)
        );
        escrow.refundChannel(CHANNEL_ID, "no_channel");
    }

    /// @notice Revert when expiring a non-existent channel.
    function test_expireChannel_revertsChannelNotFound() public {
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketEscrow.ChannelNotFound.selector)
        );
        escrow.expireChannel(CHANNEL_ID);
    }

    /// @notice Multiple debits on the same channel work correctly.
    function test_debitChannel_multipleDebits() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        uint256 deadline = block.timestamp + 1 hours;

        // First debit
        bytes memory sig1 = _signDebit(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, deadline, sig1);

        assertEq(escrow.getChannelBalance(CHANNEL_ID), DEPOSIT_AMOUNT - DEBIT_AMOUNT, "balance after first debit");

        // Second debit (nonce is now 1)
        bytes32 receiptId2 = keccak256("receipt-002");
        bytes memory sig2 = _signDebit(CHANNEL_ID, DEBIT_AMOUNT, receiptId2, 1, deadline);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, receiptId2, deadline, sig2);

        assertEq(
            escrow.getChannelBalance(CHANNEL_ID),
            DEPOSIT_AMOUNT - 2 * DEBIT_AMOUNT,
            "balance after second debit"
        );
        assertEq(
            escrow.getChannel(CHANNEL_ID).usedAmount,
            2 * DEBIT_AMOUNT,
            "used amount should reflect both debits"
        );
        assertEq(escrow.getChannel(CHANNEL_ID).nonce, 2, "nonce should be 2 after two debits");
    }

    /// @notice settleChannel with zero used amount — only refund, no hub transfer.
    function test_settleChannel_zeroUsed() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        uint256 depositorBalanceBefore = token.balanceOf(depositor);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID, hub);

        // Hub gets nothing (used = 0)
        assertEq(token.balanceOf(hub), 0, "hub should receive nothing when nothing was used");
        // Depositor gets full refund
        assertEq(
            token.balanceOf(depositor),
            depositorBalanceBefore + DEPOSIT_AMOUNT,
            "depositor should receive full refund when nothing was used"
        );
    }

    /// @notice settleChannel emits the expected event.
    function test_settleChannel_emitsEvent() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.expectEmit(true, true, false, true);
        emit ChannelSettled(CHANNEL_ID, 0, DEPOSIT_AMOUNT, depositor);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID, hub);
    }

    /// @notice refundChannel emits the expected event.
    function test_refundChannel_emitsEvent() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        vm.expectEmit(true, true, false, true);
        emit ChannelRefunded(CHANNEL_ID, DEPOSIT_AMOUNT, "safety_blocked");

        vm.prank(depositor);
        escrow.refundChannel(CHANNEL_ID, "safety_blocked");
    }

    /// @notice expireChannel emits the expected event.
    function test_expireChannel_emitsEvent() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        vm.expectEmit(true, true, false, true);
        emit ChannelExpired(CHANNEL_ID, DEPOSIT_AMOUNT);

        escrow.expireChannel(CHANNEL_ID);
    }

    // ══════════════════════════════════════════════════════════════════
    //  Integration Tests
    // ══════════════════════════════════════════════════════════════════

    /// @notice Full flow: open → debit → settle.
    function test_integration_openDebitSettle() public {
        // Open
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        // Debit
        bytes memory sig = _signDebit(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);

        // Settle
        uint256 hubBalanceBefore = token.balanceOf(hub);
        uint256 depositorBalanceBefore = token.balanceOf(depositor);

        vm.prank(hub);
        escrow.settleChannel(CHANNEL_ID, hub);

        uint256 refundAmount = DEPOSIT_AMOUNT - DEBIT_AMOUNT;

        assertEq(
            token.balanceOf(hub),
            hubBalanceBefore + DEBIT_AMOUNT,
            "integration: hub should receive debited amount"
        );
        assertEq(
            token.balanceOf(depositor),
            depositorBalanceBefore + refundAmount,
            "integration: depositor should receive remaining balance"
        );
        assertEq(
            uint256(escrow.getChannel(CHANNEL_ID).status),
            uint256(AIMarketEscrow.ChannelStatus.Settled),
            "integration: channel should be settled"
        );
    }

    /// @notice Full flow: open → debit → refund.
    function test_integration_openDebitRefund() public {
        // Open
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        // Debit
        bytes memory sig = _signDebit(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, 0, block.timestamp + 1 hours);
        vm.prank(hub);
        escrow.debitChannel(CHANNEL_ID, DEBIT_AMOUNT, RECEIPT_ID, block.timestamp + 1 hours, sig);

        // Refund (depositor gets full deposit back, even after debit)
        uint256 depositorBalanceBefore = token.balanceOf(depositor);

        vm.prank(depositor);
        escrow.refundChannel(CHANNEL_ID, "provider_error");

        assertEq(
            token.balanceOf(depositor),
            depositorBalanceBefore + DEPOSIT_AMOUNT,
            "integration: depositor should receive full deposit on refund"
        );
        assertEq(
            uint256(escrow.getChannel(CHANNEL_ID).status),
            uint256(AIMarketEscrow.ChannelStatus.Refunded),
            "integration: channel should be refunded"
        );
        // Hub should NOT receive anything (refund returns all to depositor)
        assertEq(
            token.balanceOf(hub),
            0,
            "integration: hub should receive nothing on refund"
        );
    }

    /// @notice Full flow: open → expire.
    function test_integration_openExpire() public {
        // Open
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        // Warp past expiry
        vm.warp(block.timestamp + EXPIRY_DURATION + 1);

        // Expire (permissionless)
        uint256 depositorBalanceBefore = token.balanceOf(depositor);

        escrow.expireChannel(CHANNEL_ID);

        assertEq(
            token.balanceOf(depositor),
            depositorBalanceBefore + DEPOSIT_AMOUNT,
            "integration: depositor should receive full deposit on expiry"
        );
        assertEq(
            uint256(escrow.getChannel(CHANNEL_ID).status),
            uint256(AIMarketEscrow.ChannelStatus.Expired),
            "integration: channel should be expired"
        );
    }

    /// @notice Full flow: open → settle works without any debit.
    function test_integration_openSettleWithoutDebit() public {
        _openChannel(CHANNEL_ID, DEPOSIT_AMOUNT);

        uint256 depositorBalanceBefore = token.balanceOf(depositor);

        vm.prank(depositor);
        escrow.settleChannel(CHANNEL_ID, hub);

        // No debit happened, so hub gets 0, depositor gets full refund
        assertEq(token.balanceOf(hub), 0, "hub should get nothing when no debit occurred");
        assertEq(
            token.balanceOf(depositor),
            depositorBalanceBefore + DEPOSIT_AMOUNT,
            "depositor should get full refund when no debit occurred"
        );
    }
}
