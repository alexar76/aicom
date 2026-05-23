// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title AgentNoteToken — AgentNotes (bond instrument ERC-20)
/// @notice Fixed supply at issuance; redeemable at maturity via CollateralVault.
contract AgentNoteToken is ERC20, Ownable {
    error Matured();
    error NotMatured();
    error NotVault();

    address public immutable vault;
    bytes32 public immutable listingId;
    uint64 public immutable maturity;
    uint256 public immutable faceValue; // USDC 6-decimal units per 1 note token

    bool public redeemed;

    constructor(
        address vault_,
        address beneficiary_,
        bytes32 listingId_,
        string memory name_,
        string memory symbol_,
        uint256 supply_,
        uint64 maturity_,
        uint256 faceValue_
    ) ERC20(name_, symbol_) Ownable(vault_) {
        if (beneficiary_ == address(0)) revert();
        vault = vault_;
        listingId = listingId_;
        maturity = maturity_;
        faceValue = faceValue_;
        _mint(beneficiary_, supply_);
    }

    modifier onlyVault() {
        if (msg.sender != vault) revert NotVault();
        _;
    }

    function burnOnRedeem(address holder, uint256 amount) external onlyVault {
        if (block.timestamp < maturity) revert NotMatured();
        redeemed = true;
        _burn(holder, amount);
    }

    function isMatured() external view returns (bool) {
        return block.timestamp >= maturity;
    }
}
