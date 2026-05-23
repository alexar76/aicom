// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title AgentShareToken — CapShares (ERC-20 per agent listing)
/// @notice Minting restricted to listing registry until public float enabled.
contract AgentShareToken is ERC20, Ownable {
    error MintCapExceeded();
    error TradingLocked();
    error NotRegistry();

    address public immutable registry;
    bytes32 public immutable listingId;
    uint256 public immutable maxSupply;
    bool public tradingEnabled;

    constructor(
        address registry_,
        bytes32 listingId_,
        string memory name_,
        string memory symbol_,
        uint256 maxSupply_
    ) ERC20(name_, symbol_) Ownable(registry_) {
        if (registry_ == address(0) || maxSupply_ == 0) revert();
        registry = registry_;
        listingId = listingId_;
        maxSupply = maxSupply_;
    }

    modifier onlyRegistry() {
        if (msg.sender != registry) revert NotRegistry();
        _;
    }

    /// @notice IPO mint to agent treasury wallet (one-shot or tranched via registry).
    function mintTo(address to, uint256 amount) external onlyRegistry {
        if (totalSupply() + amount > maxSupply) revert MintCapExceeded();
        _mint(to, amount);
    }

    function enableTrading() external onlyRegistry {
        tradingEnabled = true;
    }

    function _update(address from, address to, uint256 value) internal override {
        if (!tradingEnabled && from != address(0) && to != address(0)) {
            revert TradingLocked();
        }
        super._update(from, to, value);
    }
}
