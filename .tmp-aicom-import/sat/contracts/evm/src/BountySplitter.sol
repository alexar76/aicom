// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.28;

/**
 * @title BountySplitter
 * @notice On-chain settlement backend for MOMUS red-team bounties — the money side of the
 *         Treasury's off-chain decision (momus.economics.PayoutGate).
 *
 * The Treasury is the separate PAYER role: MOMUS finds and signs, verifiers independently confirm,
 * and only then does the Treasury authorize a payout. That authorization is decided OFF-CHAIN
 * (Ed25519 signature checks, independence quorum, dedup, deposit, fail-closed) — the same
 * Pay-on-Verified pattern the ecosystem already uses, because on-chain Ed25519 verification is
 * costly and non-standard on EVM. This contract is the thin, auditable on-chain half: it holds the
 * bounty pool for a finding and lets the Treasury OPERATOR release each contributor's share, while
 * enforcing the invariants that must hold regardless of what the operator intends:
 *
 *   - only the Treasury operator can fund or release (Ownable2Step owner == Treasury key);
 *   - a finding's pool can never be over-drawn (sum of releases ≤ funded pool);
 *   - each (finding, role) pays at most ONCE — no double-pay of a role, on-chain replay guard;
 *   - unclaimed pools auto-expire and refund to the Treasury after a deadline;
 *   - no custody beyond the funded pool; funds move only on explicit operator action or expiry.
 *
 * Roles are the economic SUBJECTS of the remediation pipeline (finder / fixer / conductor); the
 * SKOPOS node agents that perform the redeploy are not subjects and are not payees here. This
 * contract deploys identically on Base / Ethereum / Arbitrum via CREATE2 (Base is the live tier).
 *
 * NOTE: this file is provided as the settlement backend. Deploying it and moving real funds is an
 * operator decision — nothing here is deployed by default, and the Treasury emits HELD intents
 * until an operator wires and funds it.
 */

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";

contract BountySplitter is ReentrancyGuard, Ownable2Step {
    using SafeERC20 for IERC20;

    // A funded bounty pool for one finding.
    struct Pool {
        address token;       // USDC/USDT (whitelisted)
        uint256 funded;      // total escrowed for this finding
        uint256 released;    // total paid out so far (released ≤ funded, always)
        uint64 fundedAt;     // for expiry
        bool exists;
    }

    // findingId (a bytes32 hash of MOMUS's finding_id) → pool
    mapping(bytes32 => Pool) public pools;
    // (findingId, roleId) → paid? — the on-chain replay guard: a role pays once per finding.
    mapping(bytes32 => mapping(bytes32 => bool)) public rolePaid;
    // Whitelisted settlement tokens (USDC/USDT per chain).
    mapping(address => bool) public tokenWhitelisted;

    // MAX_POOL is denominated in whole units of a 6-decimal stablecoin and cannot adapt to a
    // token's own scale, so the whitelist is what keeps the assumption true: only tokens that
    // report exactly TOKEN_DECIMALS may ever be listed (see _whitelistToken). Without that gate
    // an 18-decimal token made MAX_POOL worth 0.0000000001 units — i.e. the cap stopped capping.
    // Mirrors AIMarketEscrow._whitelistToken, which learned this first.
    uint8 public constant TOKEN_DECIMALS = 6;

    uint256 public constant MAX_POOL = 100_000e6;     // $100k in 6-decimal USDC/USDT, sanity cap
    uint64 public constant EXPIRY = 30 days;          // unclaimed pool refunds to the Treasury

    error UnsupportedTokenDecimals();

    event PoolFunded(bytes32 indexed findingId, address indexed token, uint256 amount);
    event ShareReleased(bytes32 indexed findingId, bytes32 indexed roleId, address indexed recipient, uint256 amount);
    event PoolRefunded(bytes32 indexed findingId, uint256 amount);
    event TokenWhitelist(address indexed token, bool whitelisted);

    constructor(address[] memory initialTokens) Ownable(msg.sender) {
        for (uint256 i = 0; i < initialTokens.length; i++) {
            _whitelistToken(initialTokens[i], true);
        }
    }

    // ── Admin (owner == the Treasury operator key) ───────────────────────────
    /**
     * @notice Whitelist (or de-list) a settlement token.
     * @dev Listing requires the token to report exactly TOKEN_DECIMALS, because MAX_POOL is
     *      hardcoded in 6-decimal units. De-listing is always allowed (it can only tighten
     *      what may be funded).
     */
    function setTokenWhitelist(address token, bool whitelisted) external onlyOwner {
        _whitelistToken(token, whitelisted);
    }

    function _whitelistToken(address token, bool whitelisted) private {
        if (whitelisted) {
            // Fail closed: a token that does not answer decimals() (EOA, proxy without the
            // view, non-standard ERC-20) cannot be proven compatible with the hardcoded cap,
            // so it is refused rather than accepted on faith.
            (bool ok, bytes memory data) = token.staticcall(abi.encodeWithSignature("decimals()"));
            if (!ok || data.length < 32) revert UnsupportedTokenDecimals();
            if (abi.decode(data, (uint256)) != TOKEN_DECIMALS) revert UnsupportedTokenDecimals();
        }
        tokenWhitelisted[token] = whitelisted;
        emit TokenWhitelist(token, whitelisted);
    }

    // ── Fund a pool for a confirmed finding ──────────────────────────────────
    function fundPool(bytes32 findingId, address token, uint256 amount) external onlyOwner nonReentrant {
        require(tokenWhitelisted[token], "token not whitelisted");
        require(amount > 0 && amount <= MAX_POOL, "bad amount");
        Pool storage p = pools[findingId];
        require(!p.exists || p.token == token, "token mismatch");
        if (!p.exists) {
            p.token = token;
            p.exists = true;
        }

        // Book WHAT ARRIVED, not what was requested.
        //
        // Crediting the requested `amount` made the per-pool books exceed the contract's real
        // holdings for any token that takes a transfer fee (Ethereum USDT has an owner-settable
        // `basisPointsRate`, currently 0) or rebases down. Since `releaseShare` pays out the
        // CREDITED figure, the shortfall would come out of OTHER findings' escrowed pools until
        // those started reverting. AIMarketEscrow.openChannel measures the delta for exactly
        // this reason; so does the lottery's `_pullPayment`.
        uint256 balanceBefore = IERC20(token).balanceOf(address(this));
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
        uint256 received = IERC20(token).balanceOf(address(this)) - balanceBefore;
        require(received > 0, "nothing received");
        require(p.funded + received <= MAX_POOL, "pool cap");
        p.funded += received;

        // Restart the expiry clock on every top-up: a pool refunded once and then re-funded
        // kept its original `fundedAt` and was therefore already expired on arrival.
        p.fundedAt = uint64(block.timestamp);

        emit PoolFunded(findingId, token, received);
    }

    /**
     * @notice Release one contributor's share. The Treasury has ALREADY verified the off-chain
     *         decision (finder gate / fixer's MOMUS-signed 'fixed' verdict / conductor's completed
     *         job); this call enforces the on-chain money invariants only.
     * @param findingId  the bounty pool key
     * @param roleId     keccak256("finder"|"fixer"|"conductor") — pays at most once per finding
     * @param recipient  the subject's payout address
     * @param amount     share amount (released + amount ≤ funded)
     */
    function releaseShare(bytes32 findingId, bytes32 roleId, address recipient, uint256 amount)
        external onlyOwner nonReentrant
    {
        Pool storage p = pools[findingId];
        require(p.exists, "no pool");
        require(recipient != address(0), "bad recipient");
        require(amount > 0, "zero");
        require(!rolePaid[findingId][roleId], "role already paid");   // on-chain replay guard
        require(p.released + amount <= p.funded, "over-draw");        // pool can never be over-drawn
        rolePaid[findingId][roleId] = true;
        p.released += amount;
        IERC20(p.token).safeTransfer(recipient, amount);
        emit ShareReleased(findingId, roleId, recipient, amount);
    }

    // ── Refund the unspent remainder of an expired pool to the Treasury ──────
    function refundExpired(bytes32 findingId) external onlyOwner nonReentrant {
        Pool storage p = pools[findingId];
        require(p.exists, "no pool");
        require(block.timestamp >= p.fundedAt + EXPIRY, "not expired");
        uint256 remainder = p.funded - p.released;
        require(remainder > 0, "nothing to refund");
        p.released = p.funded;  // close it out
        IERC20(p.token).safeTransfer(owner(), remainder);
        emit PoolRefunded(findingId, remainder);
    }

    function poolRemaining(bytes32 findingId) external view returns (uint256) {
        Pool storage p = pools[findingId];
        return p.exists ? p.funded - p.released : 0;
    }
}
