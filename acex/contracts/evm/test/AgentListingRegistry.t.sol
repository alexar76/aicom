// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import {AgentCollateralVault} from "../src/AgentCollateralVault.sol";
import {AgentListingRegistry} from "../src/AgentListingRegistry.sol";
import {AgentShareToken} from "../src/AgentShareToken.sol";
import {IAgentListingRegistry} from "../src/interfaces/IAgentListingRegistry.sol";

contract MockUSDC6 is ERC20 {
    constructor() ERC20("USDC", "USDC") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }
}

contract AgentListingRegistryTest is Test {
    AgentCollateralVault vault;
    AgentListingRegistry registry;
    address agent = address(0xA1);
    address auditor = address(0xA2);
    bytes32 listingId = keccak256("x");

    function setUp() public {
        MockUSDC6 usdc = new MockUSDC6();
        vault = new AgentCollateralVault(address(usdc));
        registry = new AgentListingRegistry(address(vault), address(usdc));
        vault.setRegistry(address(registry));
        registry.setAuditor(auditor, true);
    }

    function test_reject_listing() public {
        vm.prank(agent);
        registry.applyForListing(listingId, bytes32(uint256(1)));
        registry.rejectListing(listingId, "low quality");
        assertEq(
            uint8(registry.getListing(listingId).status),
            uint8(IAgentListingRegistry.ListingStatus.Rejected)
        );
    }

    function test_cannot_approve_below_min_audit_score() public {
        vm.prank(agent);
        registry.applyForListing(listingId, bytes32(uint256(1)));
        vm.prank(auditor);
        registry.recordAudit(listingId, 5000);
        vm.expectRevert();
        registry.approveListing(listingId, "A", "A", 1e18);
    }

    function test_pause_blocks_apply() public {
        registry.pause();
        vm.prank(agent);
        vm.expectRevert();
        registry.applyForListing(listingId, bytes32(uint256(1)));
    }

    function test_share_trading_locked_until_enabled() public {
        AgentShareToken token = new AgentShareToken(
            address(this), listingId, "A", "A", 1e24
        );
        token.mintTo(agent, 1e18);
        vm.prank(agent);
        vm.expectRevert();
        token.transfer(address(0xBEEF), 1e18);
        token.enableTrading();
        vm.prank(agent);
        token.transfer(address(0xBEEF), 1e18);
        assertEq(token.balanceOf(address(0xBEEF)), 1e18);
    }
}
