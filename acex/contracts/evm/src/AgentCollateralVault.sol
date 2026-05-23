// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

import {AgentNoteToken} from "./AgentNoteToken.sol";

/// @title AgentCollateralVault — collateral for AgentNotes + lending health
contract AgentCollateralVault is ReentrancyGuard, Ownable, Pausable {
    using SafeERC20 for IERC20;

    error Unauthorized();
    error InsufficientCollateral();
    error NoteNotFound();
    error AlreadyRedeemed();

    event CollateralDeposited(bytes32 indexed listingId, uint256 amount);
    event CollateralWithdrawn(bytes32 indexed listingId, uint256 amount, address to);
    event NoteRegistered(bytes32 indexed listingId, address noteToken);
    event NoteRedeemed(bytes32 indexed listingId, address holder, uint256 payout);

    struct CollateralPosition {
        uint256 usdcBalance;
        uint256 lockedForNotes;
    }

    IERC20 public immutable usdc;
    address public registry;
    address public lendingPool;

    mapping(bytes32 => CollateralPosition) public positions;
    mapping(address => bytes32) public noteToListing;
    mapping(bytes32 => address) public listingNote;

    modifier onlyRegistry() {
        if (msg.sender != registry) revert Unauthorized();
        _;
    }

    modifier onlyLendingPool() {
        if (msg.sender != lendingPool) revert Unauthorized();
        _;
    }

    bool private _registrySet;

    constructor(address usdc_) Ownable(msg.sender) {
        usdc = IERC20(usdc_);
    }

    function setRegistry(address registry_) external onlyOwner {
        if (_registrySet || registry_ == address(0)) revert();
        registry = registry_;
        _registrySet = true;
    }

    function setLendingPool(address pool) external onlyOwner {
        lendingPool = pool;
    }

    function depositCollateral(bytes32 listingId, uint256 amount) external nonReentrant whenNotPaused {
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        _credit(listingId, amount);
        emit CollateralDeposited(listingId, amount);
    }

    /// @notice Registry credits collateral after pulling from agent wallet.
    function creditCollateral(bytes32 listingId, uint256 amount) external onlyRegistry nonReentrant whenNotPaused {
        _credit(listingId, amount);
        emit CollateralDeposited(listingId, amount);
    }

    function _credit(bytes32 listingId, uint256 amount) internal {
        positions[listingId].usdcBalance += amount;
    }

    function registerNote(bytes32 listingId, address noteToken) external onlyRegistry {
        listingNote[listingId] = noteToken;
        noteToListing[noteToken] = listingId;
        emit NoteRegistered(listingId, noteToken);
    }

    function lockForNote(bytes32 listingId, uint256 amount) external onlyRegistry {
        CollateralPosition storage p = positions[listingId];
        if (p.usdcBalance < amount) revert InsufficientCollateral();
        p.usdcBalance -= amount;
        p.lockedForNotes += amount;
    }

    /// @notice Redeem matured notes — pays USDC pro-rata to face value.
    function redeemNote(address noteToken, uint256 noteAmount) external nonReentrant whenNotPaused {
        bytes32 listingId = noteToListing[noteToken];
        if (listingId == bytes32(0)) revert NoteNotFound();

        AgentNoteToken note = AgentNoteToken(noteToken);
        if (!note.isMatured()) revert();

        uint256 payout = (noteAmount * note.faceValue()) / 1e18;
        CollateralPosition storage p = positions[listingId];
        if (p.lockedForNotes < payout) revert InsufficientCollateral();

        p.lockedForNotes -= payout;
        note.burnOnRedeem(msg.sender, noteAmount);
        usdc.safeTransfer(msg.sender, payout);
        emit NoteRedeemed(listingId, msg.sender, payout);
    }

    /// @notice Lending pool seizes collateral on liquidation.
    function seizeTo(
        bytes32 listingId,
        uint256 amount,
        address recipient
    ) external onlyLendingPool nonReentrant {
        CollateralPosition storage p = positions[listingId];
        if (p.usdcBalance < amount) revert InsufficientCollateral();
        p.usdcBalance -= amount;
        usdc.safeTransfer(recipient, amount);
    }

    function availableCollateral(bytes32 listingId) external view returns (uint256) {
        return positions[listingId].usdcBalance;
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }
}
