// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

/// @title IAgentListingRegistry — ALP listing surface
interface IAgentListingRegistry {
    enum ListingStatus {
        Pending,
        UnderAudit,
        Approved,
        Rejected,
        Delisted
    }

    struct Listing {
        bytes32 listingId;
        address agentWallet;
        bytes32 metadataHash;
        uint256 auditScoreBps; // 0–10000
        address shareToken;
        uint256 maxSupply;
        ListingStatus status;
        uint64 listedAt;
    }

    event ListingApplied(
        bytes32 indexed listingId,
        address indexed agentWallet,
        bytes32 metadataHash
    );
    event ListingAudited(bytes32 indexed listingId, uint256 auditScoreBps, address auditor);
    event ListingApproved(
        bytes32 indexed listingId,
        address shareToken,
        uint256 maxSupply
    );
    event ListingRejected(bytes32 indexed listingId, string reason);
    event ListingDelisted(bytes32 indexed listingId, string reason);

    function applyForListing(bytes32 listingId, bytes32 metadataHash) external;

    function recordAudit(bytes32 listingId, uint256 auditScoreBps) external;

    function approveListing(
        bytes32 listingId,
        string calldata name,
        string calldata symbol,
        uint256 maxSupply
    ) external returns (address shareToken);

    function rejectListing(bytes32 listingId, string calldata reason) external;

    function getListing(bytes32 listingId) external view returns (Listing memory);
}
