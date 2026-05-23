// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

import {AgentCollateralVault} from "./AgentCollateralVault.sol";
import {IAgentListingRegistry} from "./interfaces/IAgentListingRegistry.sol";

/// @title AgentLendingPool — LiquidityMesh (USDC lending between agents)
contract AgentLendingPool is ReentrancyGuard, Ownable, Pausable {
    using SafeERC20 for IERC20;

    error Unauthorized();
    error InsufficientLiquidity();
    error InsufficientCollateral();
    error InvalidListing();
    error DebtOutstanding();

    uint256 public constant MAX_LTV_BPS = 6500; // 65% of vault free collateral
    uint256 public constant BPS = 10_000;

    event Deposited(address indexed lender, uint256 amount, uint256 sharesMinted);
    event Withdrawn(address indexed lender, uint256 amount, uint256 sharesBurned);
    event Borrowed(bytes32 indexed listingId, address indexed agent, uint256 amount);
    event Repaid(bytes32 indexed listingId, address indexed agent, uint256 amount);

    IERC20 public immutable usdc;
    AgentCollateralVault public immutable vault;
    IAgentListingRegistry public immutable registry;

    uint256 public totalDeposits;
    uint256 public totalBorrowed;
    uint256 public totalShares;

    mapping(address => uint256) public lenderShares;
    mapping(bytes32 => uint256) public listingDebt;
    mapping(bytes32 => address) public listingBorrower;

    constructor(address usdc_, address vault_, address registry_) Ownable(msg.sender) {
        usdc = IERC20(usdc_);
        vault = AgentCollateralVault(vault_);
        registry = IAgentListingRegistry(registry_);
    }

    function deposit(uint256 amount) external nonReentrant whenNotPaused {
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        uint256 shares = totalShares == 0 ? amount : (amount * totalShares) / totalDeposits;
        lenderShares[msg.sender] += shares;
        totalShares += shares;
        totalDeposits += amount;
        emit Deposited(msg.sender, amount, shares);
    }

    function withdraw(uint256 shares) external nonReentrant whenNotPaused {
        if (shares > lenderShares[msg.sender]) revert();
        uint256 amount = (shares * totalDeposits) / totalShares;
        if (totalDeposits - totalBorrowed < amount) revert InsufficientLiquidity();
        lenderShares[msg.sender] -= shares;
        totalShares -= shares;
        totalDeposits -= amount;
        usdc.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount, shares);
    }

    function borrow(bytes32 listingId, uint256 amount) external nonReentrant whenNotPaused {
        IAgentListingRegistry.Listing memory L = registry.getListing(listingId);
        if (L.agentWallet != msg.sender) revert Unauthorized();
        if (
            L.status != IAgentListingRegistry.ListingStatus.Approved
        ) revert InvalidListing();

        uint256 collateral = vault.availableCollateral(listingId);
        uint256 maxBorrow = (collateral * MAX_LTV_BPS) / BPS;
        if (listingDebt[listingId] + amount > maxBorrow) revert InsufficientCollateral();
        if (totalDeposits - totalBorrowed < amount) revert InsufficientLiquidity();

        listingDebt[listingId] += amount;
        listingBorrower[listingId] = msg.sender;
        totalBorrowed += amount;
        usdc.safeTransfer(msg.sender, amount);
        emit Borrowed(listingId, msg.sender, amount);
    }

    function repay(bytes32 listingId, uint256 amount) external nonReentrant whenNotPaused {
        if (listingBorrower[listingId] != msg.sender) revert Unauthorized();
        if (amount > listingDebt[listingId]) amount = listingDebt[listingId];
        listingDebt[listingId] -= amount;
        totalBorrowed -= amount;
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        emit Repaid(listingId, msg.sender, amount);
    }

    function liquidate(bytes32 listingId) external nonReentrant whenNotPaused {
        uint256 debt = listingDebt[listingId];
        if (debt == 0) revert();
        uint256 collateral = vault.availableCollateral(listingId);
        if (collateral * MAX_LTV_BPS >= debt * BPS) revert InsufficientCollateral();
        listingDebt[listingId] = 0;
        totalBorrowed -= debt;
        vault.seizeTo(listingId, debt, msg.sender);
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }
}
