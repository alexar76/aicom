// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

/**
 * @title AIMarketEscrow
 * @notice On-chain escrow for AI Market Protocol v2 payment channels.
 *
 * Implements the channel/open, channel/debit, channel/close lifecycle from
 * the protocol spec §6. The contract holds USDT/USDC in escrow during
 * capability invocations and settles on close or expiry.
 *
 * Design principles:
 *   - No custody: funds only move on explicit user action or expiry
 *   - Receipt-gated debit: hub must present Ed25519-signed receipt to debit
 *   - Safety auto-refund: if safety gate blocks, user can refund without hub
 *   - 24h expiry: channels auto-expire, refund to depositor
 *   - Multi-chain: deployed identically on Base / Ethereum / Arbitrum
 *
 * Chain deployment addresses are managed via CREATE2 (same address everywhere).
 *
 * Security: ReentrancyGuard on all state-changing functions.
 *           Ownable — admin functions restricted to contract owner.
 *           EIP-712 typed signatures for off-chain receipt verification.
 */

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

contract AIMarketEscrow is ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;

    // ── Errors ───────────────────────────────────────────────────

    error ChannelNotFound();
    error ChannelNotOpen();
    error ChannelExists();
    error ChannelNotExpired();
    error InsufficientBalance(uint256 needed, uint256 available);
    error InvalidSignature();
    error ChannelExpired();
    error Unauthorized();
    error DepositOutOfRange();
    error TokenNotSupported();
    error ReceiptAlreadyUsed(bytes32 receiptId);
    error RefundAfterDebit();
    error InvalidHubRecipient();

    // ── Events ───────────────────────────────────────────────────

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
        string reason // "safety_blocked", "provider_error", "user_cancelled"
    );

    event ChannelExpired(bytes32 indexed channelId, uint256 refundAmount);

    event HubAuthorized(address indexed hub, bool authorized);
    event TokenWhitelisted(address indexed token, bool whitelisted);

    // ── State ────────────────────────────────────────────────────

    struct Channel {
        address depositor;
        address hub;       // hub authorized to debit this channel (bound on first debit)
        address token;
        uint256 depositAmount;
        uint256 balance;
        uint256 usedAmount;
        uint256 expiresAt;
        uint256 nonce; // prevents replay on debit signatures
        ChannelStatus status;
    }

    enum ChannelStatus { Open, Settled, Refunded, Expired }

    // channelId => Channel
    mapping(bytes32 => Channel) public channels;

    // Hub addresses authorized to debit channels
    mapping(address => bool) public authorizedHubs;

    // Whitelisted ERC-20 tokens (USDT, USDC on each chain)
    mapping(address => bool) public whitelistedTokens;

    // Receipt IDs that have been used (prevents double-spend)
    mapping(bytes32 => bool) public usedReceipts;

    // Hub nonces for replay protection on debit signatures
    mapping(address => uint256) public hubNonces;

    // Channel expiry window (24h default)
    uint256 public constant CHANNEL_EXPIRY = 24 hours;

    // Maximum deposit per channel
    uint256 public constant MAX_DEPOSIT = 10_000e6; // $10,000 in 6-decimal USDT/USDC

    // Minimum deposit per channel
    uint256 public constant MIN_DEPOSIT = 1e6; // $1.00

    // EIP-712 type hash for debit authorization
    bytes32 private constant DEBIT_TYPEHASH = keccak256(
        "DebitAuthorization(bytes32 channelId,address token,uint256 amount,bytes32 receiptId,uint256 nonce,uint256 deadline)"
    );

    bytes32 private immutable DOMAIN_SEPARATOR;

    // ── Constructor ──────────────────────────────────────────────

    constructor(address[] memory _initialHubs, address[] memory _initialTokens) Ownable(msg.sender) {
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes("AIMarketEscrow")),
                keccak256(bytes("1")),
                block.chainid,
                address(this)
            )
        );

        for (uint256 i = 0; i < _initialHubs.length; i++) {
            authorizedHubs[_initialHubs[i]] = true;
            emit HubAuthorized(_initialHubs[i], true);
        }
        for (uint256 i = 0; i < _initialTokens.length; i++) {
            whitelistedTokens[_initialTokens[i]] = true;
            emit TokenWhitelisted(_initialTokens[i], true);
        }
    }

    // ── Admin (gated by Ownable) ─────────────────────────────────

    function setHubAuthorization(address hub, bool authorized) external onlyOwner {
        authorizedHubs[hub] = authorized;
        emit HubAuthorized(hub, authorized);
    }

    function setTokenWhitelist(address token, bool whitelisted) external onlyOwner {
        whitelistedTokens[token] = whitelisted;
        emit TokenWhitelisted(token, whitelisted);
    }

    // ── Channel: Open ────────────────────────────────────────────

    /**
     * @notice Open a pre-funded payment channel.
     * @param channelId Unique channel identifier (generated off-chain)
     * @param token ERC-20 token address (USDT or USDC)
     * @param depositAmount Amount in token decimals (6 for USDT/USDC)
     *
     * User MUST approve token transfer before calling this.
     * Funds are transferred to this contract and held in escrow.
     */
    function openChannel(
        bytes32 channelId,
        address token,
        uint256 depositAmount
    ) external nonReentrant returns (uint256 expiresAt) {
        if (!whitelistedTokens[token]) revert TokenNotSupported();
        if (depositAmount < MIN_DEPOSIT || depositAmount > MAX_DEPOSIT) {
            revert DepositOutOfRange();
        }
        if (channels[channelId].depositor != address(0)) {
            revert ChannelExists();
        }

        // Transfer tokens from user to escrow
        IERC20(token).safeTransferFrom(msg.sender, address(this), depositAmount);

        uint256 expiry = block.timestamp + CHANNEL_EXPIRY;

        channels[channelId] = Channel({
            depositor: msg.sender,
            hub: address(0),  // bound on first debit
            token: token,
            depositAmount: depositAmount,
            balance: depositAmount,
            usedAmount: 0,
            expiresAt: expiry,
            nonce: 0,
            status: ChannelStatus.Open
        });

        emit ChannelOpened(channelId, msg.sender, token, depositAmount, expiry);
        return expiry;
    }

    // ── Channel: Debit (hub-only) ────────────────────────────────

    /**
     * @notice Debit a channel for a capability invocation.
     * @dev Only authorized hubs can call this. Must present a valid EIP-712
     *      signed debit authorization from the channel depositor.
     *
     * @param channelId Channel to debit
     * @param amount Amount to debit (in token decimals)
     * @param receiptId Receipt identifier for the invocation
     * @param deadline Signature expiry timestamp
     * @param signature EIP-712 signature from channel depositor
     */
    function debitChannel(
        bytes32 channelId,
        uint256 amount,
        bytes32 receiptId,
        uint256 deadline,
        bytes calldata signature
    ) external nonReentrant {
        if (!authorizedHubs[msg.sender]) revert Unauthorized();

        Channel storage ch = channels[channelId];
        if (ch.depositor == address(0)) revert ChannelNotFound();
        if (ch.status != ChannelStatus.Open) revert ChannelNotOpen();
        if (block.timestamp > ch.expiresAt) revert ChannelExpired();
        if (amount > ch.balance) {
            revert InsufficientBalance(amount, ch.balance);
        }
        if (block.timestamp > deadline) revert ChannelExpired();
        if (usedReceipts[receiptId]) revert ReceiptAlreadyUsed(receiptId);

        // Bind hub to channel on first debit
        if (ch.hub == address(0)) {
            ch.hub = msg.sender;
        }
        if (msg.sender != ch.hub) revert Unauthorized();

        // Verify depositor's EIP-712 signature authorizing this debit
        bytes32 structHash = keccak256(
            abi.encode(
                DEBIT_TYPEHASH,
                channelId,
                ch.token,
                amount,
                receiptId,
                ch.nonce,
                deadline
            )
        );
        bytes32 digest = MessageHashUtils.toTypedDataHash(DOMAIN_SEPARATOR, structHash);
        address signer = ECDSA.recover(digest, signature);
        if (signer != ch.depositor) revert InvalidSignature();

        // Execute debit
        ch.nonce += 1;
        ch.balance -= amount;
        ch.usedAmount += amount;
        usedReceipts[receiptId] = true;

        emit ChannelDebited(channelId, amount, receiptId, ch.balance);
    }

    // ── Channel: Settle ──────────────────────────────────────────

    /**
     * @notice Settle a channel — transfer used funds to hub, refund rest to depositor.
     * @dev Can be called by depositor OR authorized hub after channel use.
     * @param channelId Channel to settle
     * @param hubRecipient Address to receive the spent portion (hub's wallet)
     */
    function settleChannel(
        bytes32 channelId,
        address hubRecipient
    ) external nonReentrant {
        Channel storage ch = channels[channelId];
        if (ch.depositor == address(0)) revert ChannelNotFound();
        if (ch.status != ChannelStatus.Open) revert ChannelNotOpen();

        // Either depositor or bound hub can initiate settlement
        if (msg.sender != ch.depositor && msg.sender != ch.hub) {
            revert Unauthorized();
        }
        // If channel was debited, hubRecipient must match the bound hub.
        // If no debit happened (ch.hub == 0), hubRecipient is ignored (no payment).
        if (ch.usedAmount > 0 && hubRecipient != ch.hub) {
            revert InvalidHubRecipient();
        }

        ch.status = ChannelStatus.Settled;

        uint256 used = ch.usedAmount;
        uint256 refund = ch.balance;

        // Pay hub for used invocations
        if (used > 0) {
            IERC20(ch.token).safeTransfer(ch.hub, used);
        }

        // Refund remaining to depositor
        if (refund > 0) {
            IERC20(ch.token).safeTransfer(ch.depositor, refund);
        }

        emit ChannelSettled(channelId, used, refund, ch.depositor);
    }

    // ── Channel: Refund (safety / error) ─────────────────────────

    /**
     * @notice Full refund — called when safety gate blocks or provider errors.
     * @dev Can be called by depositor (without hub) for safety auto-refund.
     * @param channelId Channel to refund
     * @param reason Human-readable reason ("safety_blocked", "provider_error")
     */
    function refundChannel(
        bytes32 channelId,
        string calldata reason
    ) external nonReentrant {
        Channel storage ch = channels[channelId];
        if (ch.depositor == address(0)) revert ChannelNotFound();
        if (ch.status != ChannelStatus.Open) revert ChannelNotOpen();

        // Only depositor can trigger safety refund, and only before first debit
        if (msg.sender != ch.depositor) revert Unauthorized();
        if (ch.usedAmount > 0) revert RefundAfterDebit();

        ch.status = ChannelStatus.Refunded;
        uint256 total = ch.balance + ch.usedAmount;

        IERC20(ch.token).safeTransfer(ch.depositor, total);

        emit ChannelRefunded(channelId, total, reason);
    }

    // ── Channel: Expire ──────────────────────────────────────────

    /**
     * @notice Close an expired channel and refund depositor.
     * @dev Anyone can call this after expiry (permissionless cleanup).
     */
    function expireChannel(bytes32 channelId) external nonReentrant {
        Channel storage ch = channels[channelId];
        if (ch.depositor == address(0)) revert ChannelNotFound();
        if (ch.status != ChannelStatus.Open) revert ChannelNotOpen();
        if (block.timestamp <= ch.expiresAt) revert ChannelNotExpired();

        ch.status = ChannelStatus.Expired;
        uint256 total = ch.balance + ch.usedAmount;

        // Full refund on expiry (no hub payment for unused channel)
        IERC20(ch.token).safeTransfer(ch.depositor, total);

        emit ChannelExpired(channelId, total);
    }

    // ── Views ────────────────────────────────────────────────────

    function getChannel(bytes32 channelId) external view returns (Channel memory) {
        return channels[channelId];
    }

    function isChannelOpen(bytes32 channelId) external view returns (bool) {
        Channel storage ch = channels[channelId];
        return ch.status == ChannelStatus.Open && block.timestamp <= ch.expiresAt;
    }

    function getChannelBalance(bytes32 channelId) external view returns (uint256) {
        return channels[channelId].balance;
    }

    /**
     * @notice Compute EIP-712 digest for a debit authorization.
     * @dev Used off-chain by depositor to sign debit authorizations.
     */
    function computeDebitDigest(
        bytes32 channelId,
        address token,
        uint256 amount,
        bytes32 receiptId,
        uint256 nonce,
        uint256 deadline
    ) external view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(DEBIT_TYPEHASH, channelId, token, amount, receiptId, nonce, deadline)
        );
        return MessageHashUtils.toTypedDataHash(DOMAIN_SEPARATOR, structHash);
    }

    function domainSeparator() external view returns (bytes32) {
        return DOMAIN_SEPARATOR;
    }
}
