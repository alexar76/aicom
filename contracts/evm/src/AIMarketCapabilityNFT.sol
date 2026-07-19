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
 * Ownership transfer uses OpenZeppelin's Ownable2Step (the new owner must
 * accept) so a fat-fingered transferOwnership(0xWRONG) cannot brick mint /
 * pause / authorizeHub forever — recovery is still possible until the new
 * owner explicitly calls acceptOwnership().
 *
 * This replaces the in-memory NFTRegistry which was development-only and
 * lost all state on restart (audit finding EXP-72).
 */

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {ERC721Burnable} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721Burnable.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
// Ownable is imported for the constructor identifier (`Ownable(msg.sender)`)
// since Ownable2Step inherits from but does not re-export it.
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @dev Ownership uses `Ownable2Step` — `transferOwnership` requires the new
 *      owner to call `acceptOwnership()` before the role moves. Prevents
 *      accidental transfer to an unreachable address (mistype, dead contract).
 *      Production: transfer to a Gnosis Safe multi-sig after deploy.
 */
contract AIMarketCapabilityNFT is ERC721, ERC721Burnable, Ownable2Step, Pausable {
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
    // Per-token consume freeze — owner can stop a specific entitlement's
    // calls without involving the hub (e.g., suspected key theft on hub side).
    mapping(uint256 => bool) public consumePaused;
    uint256 private _nextTokenId = 1;

    // ── Errors ───────────────────────────────────────────────────

    error NoCallsRemaining(uint256 tokenId);
    error NotAuthorizedHub(address caller);
    error InvalidTotalCalls();
    error TokenDoesNotExist(uint256 tokenId);
    error TokenConsumePaused(uint256 tokenId);
    error NotTokenOwnerOrContractOwner(address caller);

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
    event ConsumePauseToggled(uint256 indexed tokenId, address indexed by, bool paused);
    event EntitlementBurned(uint256 indexed tokenId);

    // ── Constructor ──────────────────────────────────────────────

    constructor() ERC721("AIMarket Capability Entitlement", "AIMCAP") Ownable(msg.sender) {}

    // ── Admin ────────────────────────────────────────────────────

    function setAuthorizedHub(address hub, bool authorized) external onlyOwner {
        authorizedHubs[hub] = authorized;
        emit HubAuthorized(hub, authorized);
    }

    /// @notice Bulk-deauthorize many hubs in one tx (emergency response).
    function setAuthorizedHubBulk(address[] calldata hubs, bool authorized) external onlyOwner {
        for (uint256 i = 0; i < hubs.length; i++) {
            authorizedHubs[hubs[i]] = authorized;
            emit HubAuthorized(hubs[i], authorized);
        }
    }

    /// @notice Pause ALL consumeCall traffic globally (emergency stop).
    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function mint(
        address to,
        bytes32 capabilityId,
        bytes32 productId,
        uint64 totalCalls,
        uint64 pricePerCallUsd6
    ) external onlyOwner whenNotPaused returns (uint256 tokenId) {
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

    // ── Per-token pause (owner-side gate vs hub-key compromise) ──

    /// @notice Token owner or contract owner can freeze consumption on a single token.
    function setConsumePaused(uint256 tokenId, bool paused) external {
        address tokenOwner = _ownerOf(tokenId);
        if (tokenOwner == address(0)) revert TokenDoesNotExist(tokenId);
        if (msg.sender != tokenOwner && msg.sender != owner()) {
            revert NotTokenOwnerOrContractOwner(msg.sender);
        }
        consumePaused[tokenId] = paused;
        emit ConsumePauseToggled(tokenId, msg.sender, paused);
    }

    // ── Consume (hub-only) ───────────────────────────────────────

    function consumeCall(uint256 tokenId)
        external
        whenNotPaused
        returns (uint64 remaining)
    {
        if (!authorizedHubs[msg.sender]) revert NotAuthorizedHub(msg.sender);
        if (_ownerOf(tokenId) == address(0)) revert TokenDoesNotExist(tokenId);
        if (consumePaused[tokenId]) revert TokenConsumePaused(tokenId);
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
        // Return 0 for burned/never-minted tokens to avoid stale storage reads.
        if (_ownerOf(tokenId) == address(0)) return 0;
        return _entitlements[tokenId].remainingCalls;
    }

    function isExhausted(uint256 tokenId) external view returns (bool) {
        if (_ownerOf(tokenId) == address(0)) return true;
        return _entitlements[tokenId].remainingCalls == 0;
    }

    function nextTokenId() external view returns (uint256) {
        return _nextTokenId;
    }

    // ── ERC721 hooks ─────────────────────────────────────────────

    /// @dev Track transfers and clean up entitlement storage on burn.
    function _update(address to, uint256 tokenId, address auth)
        internal
        override
        returns (address)
    {
        address from = super._update(to, tokenId, auth);
        if (from == address(0) || to == address(0)) {
            // Mint (from==0) or burn (to==0). On burn, delete entitlement + flag.
            if (to == address(0) && from != address(0)) {
                delete _entitlements[tokenId];
                delete consumePaused[tokenId];
                emit EntitlementBurned(tokenId);
            }
        } else {
            // Real transfer between two non-zero addresses.
            _entitlements[tokenId].transferCount += 1;
        }
        return from;
    }
}
