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
 *           Ownable2Step — two-step ownership transfer (prevents accidental
 *           transfer to unreachable address). For production, set the owner
 *           to a Gnosis Safe multi-sig (or equivalent) with N-of-M signers.
 *           EIP-712 typed signatures for off-chain receipt verification.
 */

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

contract AIMarketEscrow is ReentrancyGuard, Ownable2Step {
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

    // Distinct name from the `ChannelExpired()` error to avoid collision in
    // log decoders/indexers that don't namespace events vs errors.
    event ChannelExpiredAndSettled(
        bytes32 indexed channelId,
        uint256 usedAmount,
        uint256 refundAmount
    );

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

    // Channel expiry window (24h default)
    uint256 public constant CHANNEL_EXPIRY = 24 hours;

    // Maximum deposit per channel
    uint256 public constant MAX_DEPOSIT = 10_000e6; // $10,000 in 6-decimal USDT/USDC

    // Minimum deposit per channel
    uint256 public constant MIN_DEPOSIT = 1e6; // $1.00

    // EIP-712 type hash for debit authorization.
    // `hub` is part of the signed payload so a depositor's signature is bound to
    // exactly one hub — preventing any other authorized hub from front-running
    // the first debit and capturing the channel.
    bytes32 private constant DEBIT_TYPEHASH = keccak256(
        "DebitAuthorization(bytes32 channelId,address hub,address token,uint256 amount,bytes32 receiptId,uint256 nonce,uint256 deadline)"
    );

    // EIP-712 domain separator: chainId baked in at deploy time. We also expose
    // a recompute path (`_buildDomainSeparator`) so verification re-derives the
    // separator if the chain forks (chainid changes), avoiding cross-fork replay.
    bytes32 private immutable INITIAL_DOMAIN_SEPARATOR;
    uint256 private immutable INITIAL_CHAIN_ID;

    // ── Constructor ──────────────────────────────────────────────

    constructor(address[] memory _initialHubs, address[] memory _initialTokens) Ownable(msg.sender) {
        INITIAL_CHAIN_ID = block.chainid;
        INITIAL_DOMAIN_SEPARATOR = _buildDomainSeparator(block.chainid);

        for (uint256 i = 0; i < _initialHubs.length; i++) {
            authorizedHubs[_initialHubs[i]] = true;
            emit HubAuthorized(_initialHubs[i], true);
        }
        for (uint256 i = 0; i < _initialTokens.length; i++) {
            whitelistedTokens[_initialTokens[i]] = true;
            emit TokenWhitelisted(_initialTokens[i], true);
        }
    }

    // ── EIP-712 domain helpers ───────────────────────────────────

    function _buildDomainSeparator(uint256 chainId) private view returns (bytes32) {
        return keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes("AIMarketEscrow")),
                keccak256(bytes("1")),
                chainId,
                address(this)
            )
        );
    }

    /// @dev Return cached separator on the original chain, or recompute on fork.
    function _domainSeparator() internal view returns (bytes32) {
        if (block.chainid == INITIAL_CHAIN_ID) {
            return INITIAL_DOMAIN_SEPARATOR;
        }
        return _buildDomainSeparator(block.chainid);
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

        // Verify depositor's EIP-712 signature authorizing this debit.
        // `msg.sender` (the calling hub) is part of the signed payload, so a
        // depositor's signature for hub A cannot be used by hub B.
        bytes32 structHash = keccak256(
            abi.encode(
                DEBIT_TYPEHASH,
                channelId,
                msg.sender,
                ch.token,
                amount,
                receiptId,
                ch.nonce,
                deadline
            )
        );
        bytes32 digest = MessageHashUtils.toTypedDataHash(_domainSeparator(), structHash);
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
     *      Payment goes to `ch.hub` (bound at first debit). No caller-supplied
     *      recipient — that would let either side redirect funds.
     * @param channelId Channel to settle
     */
    function settleChannel(bytes32 channelId) external nonReentrant {
        Channel storage ch = channels[channelId];
        if (ch.depositor == address(0)) revert ChannelNotFound();
        if (ch.status != ChannelStatus.Open) revert ChannelNotOpen();

        // Either depositor or bound hub can initiate settlement
        if (msg.sender != ch.depositor && msg.sender != ch.hub) {
            revert Unauthorized();
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
        // usedAmount is guaranteed 0 here; refund == balance == deposit.
        uint256 refund = ch.balance;

        IERC20(ch.token).safeTransfer(ch.depositor, refund);

        emit ChannelRefunded(channelId, refund, reason);
    }

    // ── Channel: Expire ──────────────────────────────────────────

    /**
     * @notice Close an expired channel: pay hub its accumulated `usedAmount`
     *         and refund the remaining `balance` to the depositor.
     * @dev Anyone can call this after expiry (permissionless cleanup).
     *      Previously this returned the full deposit to the depositor — that
     *      let depositors avoid paying the hub by simply waiting 24h before
     *      calling settle. Now expiry has identical economic semantics to
     *      settleChannel, only without the auth requirement.
     */
    function expireChannel(bytes32 channelId) external nonReentrant {
        Channel storage ch = channels[channelId];
        if (ch.depositor == address(0)) revert ChannelNotFound();
        if (ch.status != ChannelStatus.Open) revert ChannelNotOpen();
        if (block.timestamp <= ch.expiresAt) revert ChannelNotExpired();

        ch.status = ChannelStatus.Expired;

        uint256 used = ch.usedAmount;
        uint256 refund = ch.balance;

        if (used > 0 && ch.hub != address(0)) {
            IERC20(ch.token).safeTransfer(ch.hub, used);
        }
        if (refund > 0) {
            IERC20(ch.token).safeTransfer(ch.depositor, refund);
        }

        emit ChannelExpiredAndSettled(channelId, used, refund);
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
     *      `hub` MUST match the calling hub's address — depositor signs for one
     *      specific hub only.
     */
    function computeDebitDigest(
        bytes32 channelId,
        address hub,
        address token,
        uint256 amount,
        bytes32 receiptId,
        uint256 nonce,
        uint256 deadline
    ) external view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(DEBIT_TYPEHASH, channelId, hub, token, amount, receiptId, nonce, deadline)
        );
        return MessageHashUtils.toTypedDataHash(_domainSeparator(), structHash);
    }

    function domainSeparator() external view returns (bytes32) {
        return _domainSeparator();
    }
}
