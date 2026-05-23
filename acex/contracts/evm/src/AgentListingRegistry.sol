// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

import {IAgentListingRegistry} from "./interfaces/IAgentListingRegistry.sol";
import {AgentShareToken} from "./AgentShareToken.sol";
import {AgentNoteToken} from "./AgentNoteToken.sol";
import {AgentCollateralVault} from "./AgentCollateralVault.sol";

/// @title AgentListingRegistry — ALP (Agent Listing Protocol)
/// @notice IPO-style listing: apply → audit → mint CapShares → optional AgentNotes.
contract AgentListingRegistry is IAgentListingRegistry, Ownable, Pausable {
    using SafeERC20 for IERC20;

    error ListingExists();
    error InvalidStatus();
    error AuditScoreTooLow();
    error ZeroAddress();

    uint256 public constant MIN_AUDIT_SCORE_BPS = 7000; // 70%

    AgentCollateralVault public immutable vault;

    mapping(bytes32 => Listing) public listings;
    mapping(address => bool) public auditors;
    mapping(address => bool) public pulseMarketMakers;

    IERC20 public immutable usdc;

    constructor(address vault_, address usdc_) Ownable(msg.sender) {
        if (vault_ == address(0) || usdc_ == address(0)) revert ZeroAddress();
        vault = AgentCollateralVault(vault_);
        usdc = IERC20(usdc_);
    }

    function setAuditor(address auditor, bool allowed) external onlyOwner {
        auditors[auditor] = allowed;
    }

    function setMarketMaker(address mm, bool allowed) external onlyOwner {
        pulseMarketMakers[mm] = allowed;
    }

    function applyForListing(bytes32 listingId, bytes32 metadataHash)
        external
        override
        whenNotPaused
    {
        if (listings[listingId].agentWallet != address(0)) revert ListingExists();
        listings[listingId] = Listing({
            listingId: listingId,
            agentWallet: msg.sender,
            metadataHash: metadataHash,
            auditScoreBps: 0,
            shareToken: address(0),
            maxSupply: 0,
            status: ListingStatus.Pending,
            listedAt: 0
        });
        emit ListingApplied(listingId, msg.sender, metadataHash);
    }

    function recordAudit(bytes32 listingId, uint256 auditScoreBps) external whenNotPaused {
        if (!auditors[msg.sender]) revert();
        Listing storage L = listings[listingId];
        if (L.status != ListingStatus.Pending && L.status != ListingStatus.UnderAudit) {
            revert InvalidStatus();
        }
        L.auditScoreBps = auditScoreBps;
        L.status = ListingStatus.UnderAudit;
        emit ListingAudited(listingId, auditScoreBps, msg.sender);
    }

    function approveListing(
        bytes32 listingId,
        string calldata name,
        string calldata symbol,
        uint256 maxSupply
    ) external override onlyOwner whenNotPaused returns (address shareToken) {
        Listing storage L = listings[listingId];
        if (L.status != ListingStatus.UnderAudit && L.status != ListingStatus.Pending) {
            revert InvalidStatus();
        }
        if (L.auditScoreBps < MIN_AUDIT_SCORE_BPS) revert AuditScoreTooLow();

        AgentShareToken token = new AgentShareToken(
            address(this),
            listingId,
            name,
            symbol,
            maxSupply
        );
        token.mintTo(L.agentWallet, maxSupply);
        token.enableTrading();

        L.shareToken = address(token);
        L.maxSupply = maxSupply;
        L.status = ListingStatus.Approved;
        L.listedAt = uint64(block.timestamp);

        emit ListingApproved(listingId, address(token), maxSupply);
        return address(token);
    }

    function rejectListing(bytes32 listingId, string calldata reason)
        external
        override
        onlyOwner
        whenNotPaused
    {
        Listing storage L = listings[listingId];
        if (L.status == ListingStatus.Approved || L.status == ListingStatus.Delisted) {
            revert InvalidStatus();
        }
        L.status = ListingStatus.Rejected;
        emit ListingRejected(listingId, reason);
    }

    function issueAgentNotes(
        bytes32 listingId,
        string calldata name,
        string calldata symbol,
        uint256 supply,
        uint64 maturity,
        uint256 faceValue,
        uint256 collateralUsdc
    ) external whenNotPaused returns (address noteToken) {
        Listing storage L = listings[listingId];
        if (L.status != ListingStatus.Approved) revert InvalidStatus();

        usdc.safeTransferFrom(L.agentWallet, address(vault), collateralUsdc);
        vault.creditCollateral(listingId, collateralUsdc);
        noteToken = address(
            new AgentNoteToken(
                address(vault),
                L.agentWallet,
                listingId,
                name,
                symbol,
                supply,
                maturity,
                faceValue
            )
        );
        vault.registerNote(listingId, noteToken);
        vault.lockForNote(listingId, (supply * faceValue) / 1e18);
        return noteToken;
    }

    function getListing(bytes32 listingId) external view override returns (Listing memory) {
        return listings[listingId];
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }
}
