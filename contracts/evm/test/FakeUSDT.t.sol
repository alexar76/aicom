// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {FakeUSDT} from "../src/FakeUSDT.sol";
import {AIMarketEscrow} from "../src/AIMarketEscrow.sol";

/**
 * @title FakeUSDTTest
 * @notice FakeUSDT is the token the UNI-mode bootstrap deploys and then hands to
 *         `script/Deploy.s.sol` as INITIAL_TOKENS (see
 *         `alien-monitor/backend/universe.py::_deploy_usdt_forge` →
 *         `_forge_run`, which sets INITIAL_TOKENS to the deployed address).
 *
 *         `AIMarketEscrow` fails closed on any token whose `decimals()` is not
 *         `TOKEN_DECIMALS`, so a FakeUSDT reporting the ERC20 default of 18 made
 *         the escrow CONSTRUCTOR revert `UnsupportedTokenDecimals` — the whole
 *         local universe bricked at bootstrap, one hop away from the contract that
 *         enforces the rule and with no test on either side of the seam.
 *
 *         These cases hold the seam: the fake token's scale, its supply expressed
 *         in that scale, and the actual escrow deployment + a real MIN_DEPOSIT
 *         deposit through it.
 */
contract FakeUSDTTest is Test {
    FakeUSDT internal token;
    address internal constant HUB = address(0xBEEF);

    function setUp() public {
        token = new FakeUSDT();
    }

    /// @notice The stand-in must be on the scale of the thing it stands in for.
    function test_decimals_matchRealUSDT() public {
        assertEq(token.decimals(), 6, "USDT/USDC are 6-decimal tokens");
        AIMarketEscrow escrow = new AIMarketEscrow(new address[](0), new address[](0));
        assertEq(token.decimals(), escrow.TOKEN_DECIMALS(), "escrow's assumed scale");
    }

    /// @notice Supply is 1,000,000 nominal USDT — in the token's own scale, not `ether`.
    function test_supply_isOneMillionNominalUnits() public view {
        assertEq(token.totalSupply(), 1_000_000 * 10 ** 6);
        assertEq(token.balanceOf(address(this)), token.totalSupply());
    }

    /// @notice The exact call the UNI bootstrap makes: deploy the escrow with FakeUSDT
    /// in the initial token list. This is what reverted `UnsupportedTokenDecimals`.
    function test_escrowConstructor_acceptsFakeUSDT() public {
        address[] memory hubs = new address[](1);
        hubs[0] = HUB;
        address[] memory tokens = new address[](1);
        tokens[0] = address(token);

        AIMarketEscrow escrow = new AIMarketEscrow(hubs, tokens);

        assertTrue(escrow.whitelistedTokens(address(token)), "bootstrap token must be usable");
        assertTrue(escrow.authorizedHubs(hubs[0]));
    }

    /// @notice And the deposit bounds are meaningful against it: MIN_DEPOSIT is $1 of
    /// FakeUSDT, not 10^-12 of it, so a sim deposit is the same integer as on Base.
    function test_deposit_atMinimum_worksAndIsWorthOneDollar() public {
        address[] memory hubs = new address[](1);
        hubs[0] = HUB;
        address[] memory tokens = new address[](1);
        tokens[0] = address(token);
        AIMarketEscrow escrow = new AIMarketEscrow(hubs, tokens);

        uint256 min = escrow.MIN_DEPOSIT();
        assertEq(min, 1_000_000, "$1.00 at 6 decimals");

        token.approve(address(escrow), min);
        escrow.openChannel(keccak256("uni-bootstrap-channel"), address(token), min);

        assertEq(token.balanceOf(address(escrow)), min);
        assertEq(token.balanceOf(address(this)), token.totalSupply() - min);
    }
}
