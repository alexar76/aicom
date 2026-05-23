// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

/**
 * @title AIMarketCapabilityNFT
 * @notice ERC-721 transferable entitlements for AI Market capability invocations.
 *
 * Each token represents N pre-paid calls to a specific capability. Owners can:
 *   - Transfer the NFT to another address (gift, secondary market, sub-agent delegation)
 *   - Have authorized hubs decrement remainingCalls on their behalf
 *   - Burn the NFT once exhausted (gas refund)
 *
 * Trust model:
 *   - Only the contract owner (operator) can mint (after USD payment received off-chain).
 *   - Only authorized hubs can call consumeCall (decrement).
 *   - Standard ERC-721 transfer rules (signed approve/transferFrom).
 *
 * This replaces the in-memory NFTRegistry which was development-only and
 * lost all state on restart (audit finding EXP-72).
 */

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {ERC721Burnable} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721Burnable.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

contract AIMarketCapabilityNFT is ERC721, ERC721Burnable, Ownable {
    struct Entitlement {
        bytes32 capabilityId;
        bytes32 productId;
        uint64 totalCalls;
        uint64 remainingCalls;
        uint64 pricePerCallUsd6;  // micro-USD (6 decimals)
        uint32 mintedAt;          // block.timestamp truncated
        uint32 transferCount;
    }

    // ── State ────────────────────────────────────────────────────

    mapping(uint256 => Entitlement) private _entitlements;
    mapping(address => bool) public authorizedHubs;
    uint256 private _nextTokenId = 1;

    // ── Errors ───────────────────────────────────────────────────

    error NoCallsRemaining(uint256 tokenId);
    error NotAuthorizedHub(address caller);
    error InvalidTotalCalls();
    error TokenDoesNotExist(uint256 tokenId);

    // ── Events ───────────────────────────────────────────────────

    event EntitlementMinted(
        uint256 indexed tokenId,
        address indexed to,
        bytes32 capabilityId,
        bytes32 productId,
        uint64 totalCalls,
        uint64 pricePerCallUsd6
    );

    event CallConsumed(
        uint256 indexed tokenId,
        address indexed consumer,
        uint64 remainingCalls
    );

    event HubAuthorized(address indexed hub, bool authorized);

    // ── Constructor ──────────────────────────────────────────────

    constructor() ERC721("AIMarket Capability Entitlement", "AIMCAP") Ownable(msg.sender) {}

    // ── Admin ────────────────────────────────────────────────────

    function setAuthorizedHub(address hub, bool authorized) external onlyOwner {
        authorizedHubs[hub] = authorized;
        emit HubAuthorized(hub, authorized);
    }

    function mint(
        address to,
        bytes32 capabilityId,
        bytes32 productId,
        uint64 totalCalls,
        uint64 pricePerCallUsd6
    ) external onlyOwner returns (uint256 tokenId) {
        if (totalCalls == 0) revert InvalidTotalCalls();
        tokenId = _nextTokenId++;
        _entitlements[tokenId] = Entitlement({
            capabilityId: capabilityId,
            productId: productId,
            totalCalls: totalCalls,
            remainingCalls: totalCalls,
            pricePerCallUsd6: pricePerCallUsd6,
            mintedAt: uint32(block.timestamp),
            transferCount: 0
        });
        _safeMint(to, tokenId);
        emit EntitlementMinted(tokenId, to, capabilityId, productId, totalCalls, pricePerCallUsd6);
    }

    // ── Consume (hub-only) ───────────────────────────────────────

    function consumeCall(uint256 tokenId) external returns (uint64 remaining) {
        if (!authorizedHubs[msg.sender]) revert NotAuthorizedHub(msg.sender);
        if (_ownerOf(tokenId) == address(0)) revert TokenDoesNotExist(tokenId);
        Entitlement storage e = _entitlements[tokenId];
        if (e.remainingCalls == 0) revert NoCallsRemaining(tokenId);
        unchecked { e.remainingCalls -= 1; }
        remaining = e.remainingCalls;
        emit CallConsumed(tokenId, msg.sender, remaining);
    }

    // ── Views ────────────────────────────────────────────────────

    function getEntitlement(uint256 tokenId) external view returns (Entitlement memory) {
        if (_ownerOf(tokenId) == address(0)) revert TokenDoesNotExist(tokenId);
        return _entitlements[tokenId];
    }

    function remainingCalls(uint256 tokenId) external view returns (uint64) {
        return _entitlements[tokenId].remainingCalls;
    }

    function isExhausted(uint256 tokenId) external view returns (bool) {
        return _entitlements[tokenId].remainingCalls == 0;
    }

    function nextTokenId() external view returns (uint256) {
        return _nextTokenId;
    }

    // ── ERC721 hooks ─────────────────────────────────────────────

    /// @dev Track transfer count for analytics / royalty schemes.
    function _update(address to, uint256 tokenId, address auth)
        internal
        override
        returns (address)
    {
        address from = super._update(to, tokenId, auth);
        // Only count actual transfers (not mint/burn)
        if (from != address(0) && to != address(0)) {
            _entitlements[tokenId].transferCount += 1;
        }
        return from;
    }
}
