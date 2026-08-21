// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice Test USDT for local Anvil / UNI mode (Alien Monitor bootstrap).
///
/// @dev SCALE: 6 decimals, like the real USDT/USDC this stands in for — NOT the
///      ERC20 default of 18. This is not cosmetic. `AIMarketEscrow` fails closed on
///      any token whose `decimals()` is not `TOKEN_DECIMALS` (6), because its
///      MIN_DEPOSIT/MAX_DEPOSIT bounds are 6-decimal literals; an 18-decimal
///      stand-in made the escrow constructor revert `UnsupportedTokenDecimals`,
///      which took out the whole UNI-mode bootstrap (`universe.py` hands this token
///      to `script/Deploy.s.sol` as INITIAL_TOKENS). Keeping the fake token on the
///      real token's scale also means every amount flowing through the local sim is
///      the same integer it would be on Base.
contract FakeUSDT is ERC20 {
    uint8 private constant _DECIMALS = 6;

    constructor() ERC20("FakeUSDT", "USDT") {
        // 1,000,000 "USDT" at 6 decimals — deliberately expressed in the token's own
        // scale rather than `ether`, which would mint 10**24 base units (= 10**18
        // nominal USDT) and make every supply/balance figure meaningless.
        _mint(msg.sender, 1_000_000 * 10 ** uint256(_DECIMALS));
    }

    function decimals() public pure override returns (uint8) {
        return _DECIMALS;
    }
}
