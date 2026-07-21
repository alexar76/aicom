// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice Test USDT for local Anvil / UNI mode (Alien Monitor bootstrap).
contract FakeUSDT is ERC20 {
    constructor() ERC20("FakeUSDT", "USDT") {
        _mint(msg.sender, 1_000_000 ether);
    }
}
