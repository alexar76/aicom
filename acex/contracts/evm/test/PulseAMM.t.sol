// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import {AgentShareToken} from "../src/AgentShareToken.sol";
import {PulseAMM} from "../src/PulseAMM.sol";

contract MockUSDC6 is ERC20 {
    constructor() ERC20("USDC", "USDC") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amt) external {
        _mint(to, amt);
    }
}

contract PulseAMMTest is Test {
    MockUSDC6 usdc;
    PulseAMM amm;
    AgentShareToken share;
    bytes32 listingId = keccak256("pool-agent");

    function setUp() public {
        usdc = new MockUSDC6();
        amm = new PulseAMM();
        share = new AgentShareToken(address(this), listingId, "Cap", "CAP", 10_000_000e18);
        share.mintTo(address(this), 1_000_000e18);
        share.enableTrading();
        usdc.mint(address(this), 1_000_000e6);
    }

    function test_create_pool_and_swap_both_ways() public {
        assertGe(share.balanceOf(address(this)), 500_000e18);
        share.approve(address(amm), type(uint256).max);
        usdc.approve(address(amm), type(uint256).max);
        amm.createPool(address(share), address(usdc), 500_000e18, 100_000e6);

        uint256 usdcBefore = usdc.balanceOf(address(this));
        amm.swapShareForUsdc(address(share), 10_000e18, 1);
        assertGt(usdc.balanceOf(address(this)), usdcBefore);

        share.approve(address(amm), 1_000e18);
        usdc.approve(address(amm), 10_000e6);
        uint256 shareBefore = share.balanceOf(address(this));
        amm.swapUsdcForShare(address(share), 5_000e6, 1);
        assertGt(share.balanceOf(address(this)), shareBefore);
    }

    function test_revert_swap_unknown_pool() public {
        vm.expectRevert();
        amm.swapShareForUsdc(address(share), 1e18, 1);
    }
}
